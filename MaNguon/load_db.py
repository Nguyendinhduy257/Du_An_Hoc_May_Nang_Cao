r"""
Nạp dữ liệu demo (test và val) từ CSV vào PostgreSQL.

Đây là bước duy nhất biến các file rời rạc thành dữ liệu có nguồn gốc trong
database; web và API về sau chỉ đọc database. Nếu web đọc CSV còn API đọc
database thì hai bên có thể hiện hai con số khác nhau mà không ai biết bên nào
đúng.

Đọc: test.csv, val.csv, test_predictions.csv, val_predictions.csv,
baseline_metrics.json và model .pkl (chỉ để lấy từ vựng TF-IDF).
Chạy: python MaNguon\load_db.py
"""

import hashlib
import json
import pickle

import pandas as pd

import db
from classify import classify_review, normalize_text
from config import (
    METRICS_JSON_PATH,
    MODEL_PATH,
    TEST_CSV_PATH,
    TEST_PREDICTIONS_CSV_PATH,
    VAL_CSV_PATH,
    VAL_PREDICTIONS_CSV_PATH,
)

# Số chữ số thập phân khi so khớp xác suất giữa file dự đoán và bảng review.
# Cần vì cột prob_fake là NUMERIC(7,6), ghi 6 chữ số; đọc lại phải khớp.
PROBABILITY_DECIMALS = 6


def sha256_of_file(path):
    """Băm nội dung file để nhận biết file có thay đổi hay không."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def content_hash(text):
    """Băm nội dung review sau chuẩn hóa, dùng để tra trùng lặp về sau."""
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def load_predictions(path):
    """
    Đọc file dự đoán và trả dict {row_index: prob_fake}.

    Dùng dict theo row_index vì file CSV dự đoán và file CSV dữ liệu có thể
    được đọc theo thứ tự khác nhau; khớp theo chỉ số an toàn hơn.
    """
    table = pd.read_csv(path, encoding="utf-8")
    result = {}

    for row in table.itertuples(index=False):
        result[int(row.row_index)] = float(row.prob_fake)

    return result


def compute_known_token_ratio(vectorizer, text):
    """
    Tỷ lệ token của câu nằm trong từ vựng TF-IDF đã học.

    Cách làm: dùng chính bộ phân tích của vectorizer (build_analyzer) để cắt
    câu thành token y như lúc train, rồi đếm bao nhiêu token có trong
    vocabulary_.

    Cần chỉ số này vì model chỉ hiểu tiếng Anh đúng như dữ liệu train. Một câu
    tiếng Việt có thể nhận xác suất "thật" một cách ngẫu nhiên; tỷ lệ token
    quen thuộc phát hiện trường hợp đó để không giữ câu ấy lại như review hữu
    ích.
    """
    analyzer = vectorizer.build_analyzer()
    tokens = analyzer(text)

    if not tokens:
        return 0.0

    vocabulary = vectorizer.vocabulary_
    known = 0
    for token in tokens:
        if token in vocabulary:
            known = known + 1

    return known / len(tokens)


def to_optional_float(value):
    """Đổi giá trị có thể là NaN thành float hoặc None."""
    if value is None:
        return None
    if pd.isna(value):
        return None
    return float(value)


def build_split_reviews(split_name, reviews_path, predictions_path, vectorizer, threshold):
    """
    Ghép dữ liệu review + dự đoán + luật phân nhóm thành danh sách dict.

    split_name: "test" hoặc "val" - chỉ dùng để ghi vào cột dataset_split.
    """
    reviews_table = pd.read_csv(reviews_path, encoding="utf-8")
    probabilities = load_predictions(predictions_path)

    if len(reviews_table) != len(probabilities):
        raise ValueError(
            f"{split_name}: số dòng dữ liệu ({len(reviews_table)}) khác "
            f"số dòng dự đoán ({len(probabilities)})."
        )

    rows = []

    # seen_texts: các nội dung đã gặp trong CÙNG tập, để phát hiện trùng lặp.
    # Chỉ so trong cùng tập vì một review ở test trùng với val không phải lỗi
    # của tập test; phạm vi so sánh phải rõ ràng.
    seen_texts = set()

    for row_index in range(len(reviews_table)):
        row = reviews_table.iloc[row_index]

        text = str(row["text_"])
        normalized = normalize_text(text)

        is_duplicate = normalized in seen_texts
        seen_texts.add(normalized)

        probability_fake = probabilities[row_index]
        predicted_label = 1 if probability_fake >= threshold else 0

        known_token_ratio = compute_known_token_ratio(vectorizer, text)

        classification = classify_review(
            text=text,
            probability_fake=probability_fake,
            threshold=threshold,
            rating=to_optional_float(row.get("rating")),
            is_duplicate=is_duplicate,
            known_token_ratio=known_token_ratio,
        )

        rows.append(
            {
                "row_index": row_index,
                "text": text,
                "translated_text": "",
                "used_translation": False,
                "rating": to_optional_float(row.get("rating")),
                "product_category": str(row.get("category", "")),
                "true_label": int(row["label_binary"]),
                "prob_fake": round(probability_fake, PROBABILITY_DECIMALS),
                "predicted_label": predicted_label,
                "category": classification["primary_category"],
                "flags": classification["flags"],
                "reasons": classification["reasons"],
                "is_useful": classification["is_useful"],
                "is_reliable": classification["is_reliable"],
                "word_count": classification["word_count"],
                "known_token_ratio": classification["known_token_ratio"],
                "content_hash": content_hash(text),
            }
        )

    return rows


def ensure_model_run(connection):
    """
    Bảo đảm có một dòng model_runs khớp với KetQuaChay/baseline_metrics.json.

    So bằng mã băm thay vì so từng con số vì JSONB lưu số thực có thể bị làm
    tròn khi đọc lại; so mã băm của cả file là cách chắc chắn nhất để biết
    "file kết quả này đã được nạp chưa".

    Trả về model_run_id.
    """
    metrics_text = METRICS_JSON_PATH.read_text(encoding="utf-8")
    metrics = json.loads(metrics_text)
    metrics_hash = sha256_of_file(METRICS_JSON_PATH)

    latest = db.get_latest_model_run(connection)
    if latest is not None:
        stored_hash = latest["config"].get("metrics_sha256")
        if stored_hash == metrics_hash:
            print(f"[DB] Dùng lại lần chạy model id={latest['id']} (số liệu không đổi).")
            return latest["id"]

    threshold = float(metrics["validation"]["best_threshold"])
    model_run_id = db.save_model_run(
        connection=connection,
        model_name="logistic_regression_tfidf_sgd",
        threshold=threshold,
        metrics=metrics,
        config_values={
            "metrics_sha256": metrics_hash,
            "source_file": str(METRICS_JSON_PATH),
            "calibration": metrics.get("calibration", {}).get("method", "none"),
        },
    )
    print(f"[DB] Tạo lần chạy model mới id={model_run_id}, ngưỡng={threshold}.")
    return model_run_id


def main():
    if not db.is_available():
        raise SystemExit(
            "Không kết nối được PostgreSQL. Hãy chạy: docker compose up -d"
        )

    connection = db.connect()
    try:
        db.init_schema(connection)

        # Đọc model một lần, chỉ dùng vectorizer để tính tỷ lệ token quen thuộc.
        with MODEL_PATH.open("rb") as model_file:
            model_bundle = pickle.load(model_file)

        vectorizer = model_bundle["vectorizer"]
        threshold = float(model_bundle["threshold"])

        model_run_id = ensure_model_run(connection)

        for split_name, reviews_path, predictions_path in (
            ("test", TEST_CSV_PATH, TEST_PREDICTIONS_CSV_PATH),
            ("val", VAL_CSV_PATH, VAL_PREDICTIONS_CSV_PATH),
        ):
            rows = build_split_reviews(
                split_name, reviews_path, predictions_path, vectorizer, threshold
            )
            db.replace_split_reviews(connection, model_run_id, split_name, rows)

            category_counts = db.count_by_category(connection, split_name, model_run_id)
            total_in_db = db.count_reviews(connection, split_name)

            print(f"\n=== Tập {split_name} ===")
            print(f"Số dòng đã nạp : {len(rows)}")
            print(f"Số dòng trong DB: {total_in_db}")
            for category_id, count in sorted(category_counts.items()):
                print(f"  {category_id:<20} {count}")

        print("\nNạp dữ liệu vào PostgreSQL hoàn tất.")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
