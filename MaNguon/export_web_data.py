r"""
Đọc dữ liệu đã nạp trong PostgreSQL rồi xuất hai gói cho trang web:
data_meta.js (thông tin và số liệu) và data_reviews.js (toàn bộ review).
Không huấn luyện lại, không đọc CSV gốc.

Chạy:
    python MaNguon\export_web_data.py            ghi cả hai file
    python MaNguon\export_web_data.py --check    chỉ báo hai file có lệch không

Xuất ra .js thay vì .json vì mở trang bằng double-click dùng giao thức file://,
fetch() bị chặn (CORS) còn thẻ <script src> vẫn nạp được. Tách làm hai file để
phần đầu trang nhẹ, hiện nhanh; file review hơn 4 MB chỉ cần khi kéo xuống
bảng. Chế độ --check để biết dữ liệu web đã cũ chưa mà không phải ghi đè.
"""

import hashlib
import json
import sys

import numpy as np
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score

import db
from classify import (
    REASON_TEMPLATES,
    build_reason_codes,
    build_summary,
    category_basis_for_category,
    flag_source_for_category,
)
from config import (
    BOT_MAX_WORDS,
    CATEGORY_ORDER,
    HISTOGRAM_BIN_COUNT,
    MAX_UPLOAD_ROWS,
    MAX_UPLOAD_TRANSLATE_SECONDS,
    MIN_KNOWN_TOKEN_RATIO,
    MIN_USEFUL_WORDS,
    SAMPLE_PAGE_SIZE,
    THRESHOLD_MAX,
    THRESHOLD_MIN,
    THRESHOLD_STEP,
    WEB_META_PATH,
    WEB_REVIEWS_PATH,
)
from file_safety import save_text_with_warning

# Số chữ số thập phân của xác suất khi đưa lên web.
# Bốn chữ số đủ để phân biệt hai review gần nhau, mà file nhỏ hơn đáng kể so
# với sáu chữ số khi có hơn 6.000 dòng.
WEB_PROBABILITY_DECIMALS = 4

# Nhãn hiển thị cho category_basis. Để trong meta để web và báo cáo dùng chung
# một cách gọi, không mỗi nơi viết một kiểu.
BASIS_LABELS = {
    "model": "MODEL",
    "rule": "LUẬT",
    "model+rule": "MODEL + LUẬT",
}


def clean_text(value):
    """Gộp mọi khoảng trắng để bảng HTML không bị vỡ bố cục."""
    if value is None:
        return ""
    return " ".join(str(value).split())


def build_histogram(probabilities, true_labels, bin_count):
    """
    Đếm số review rơi vào từng khoảng xác suất, tách theo nhãn thật.

    Tách theo nhãn thật để thấy model đẩy review thật về gần 0 và review giả
    về gần 1. Hai "ngọn núi" càng xa nhau thì model càng tốt.
    """
    # bin_edges: 21 mốc chia đều 0.0 -> 1.0 (20 khoảng).
    bin_edges = np.linspace(0.0, 1.0, bin_count + 1)

    real_counts, _ = np.histogram(probabilities[true_labels == 0], bins=bin_edges)
    fake_counts, _ = np.histogram(probabilities[true_labels == 1], bins=bin_edges)

    return {
        "bin_edges": [round(float(edge), 4) for edge in bin_edges],
        "real_counts": [int(count) for count in real_counts],
        "fake_counts": [int(count) for count in fake_counts],
    }


def build_threshold_curve(probabilities, true_labels):
    """
    Tính Precision / Recall / F1 tại từng ngưỡng trên tập val.

    Phần này là bằng chứng trực quan cho việc chọn ngưỡng: người xem thấy F1
    đạt đỉnh ở đâu, và thấy rõ đánh đổi Precision - Recall.
    """
    thresholds = np.round(
        np.arange(THRESHOLD_MIN, THRESHOLD_MAX + THRESHOLD_STEP / 2, THRESHOLD_STEP),
        2,
    )

    curve = []
    for threshold in thresholds:
        predicted = (probabilities >= threshold).astype(int)
        curve.append(
            {
                "threshold": round(float(threshold), 2),
                "precision": round(
                    float(precision_score(true_labels, predicted, zero_division=0)), 4
                ),
                "recall": round(
                    float(recall_score(true_labels, predicted, zero_division=0)), 4
                ),
                "f1": round(float(f1_score(true_labels, predicted, zero_division=0)), 4),
            }
        )
    return curve


def build_reviews(review_rows, threshold):
    """
    Chuyển các dòng trong DB thành cấu trúc gọn cho web.

    Lấy toàn bộ tập test thay vì một mẫu nhỏ vì bảng có phân trang nên không
    cần cắt bớt; dữ liệu đầy đủ giúp người xem tự lọc và tự kiểm chứng, không
    bị thiên lệch do chọn mẫu.

    Không xuất câu reasons đầy đủ vì mỗi câu lặp lại hàng nghìn lần. Chỉ xuất
    reason_codes; web ghép câu từ REASON_TEMPLATES trong meta.
    """
    rows = []

    for row in review_rows:
        true_label = int(row["true_label"])
        predicted_label = int(row["predicted_label"])
        category = row["category"]
        flags = row["flags"] or []

        reason_codes = build_reason_codes(
            category=category,
            probability_fake=float(row["prob_fake"]),
            threshold=threshold,
            word_count=int(row["word_count"]),
            known_token_ratio=float(row.get("known_token_ratio", 1.0)),
            is_reliable=bool(row["is_reliable"]),
            has_link_flag="has_link" in flags,
            used_translation=bool(row.get("used_translation", False)),
        )

        rows.append(
            {
                "row_index": int(row["row_index"]),
                "text": clean_text(row["text"]),
                "rating": row["rating"],
                "product_category": clean_text(row["product_category"]),
                "true_label": true_label,
                "prob_fake": round(float(row["prob_fake"]), WEB_PROBABILITY_DECIMALS),
                "predicted_label": predicted_label,
                "is_correct": bool(predicted_label == true_label),
                "category": category,
                "category_basis": category_basis_for_category(category),
                "flag_source": flag_source_for_category(category),
                "flags": flags,
                "reason_codes": reason_codes,
                "is_reliable": bool(row["is_reliable"]),
                "is_useful": bool(row["is_useful"]),
                "word_count": int(row["word_count"]),
            }
        )

    return rows


def check_confusion(test_reviews, threshold, expected_matrix):
    """
    Tính lại confusion matrix từ dữ liệu DB và đối chiếu với JSON đã lưu.

    Nếu ai đó sửa tay số liệu trong DB hoặc trong file JSON, web sẽ hiển thị
    số không khớp báo cáo. Cảnh báo này phát hiện sớm chuyện đó.
    """
    probabilities = np.array([row["prob_fake"] for row in test_reviews], dtype=float)
    true_labels = np.array([row["true_label"] for row in test_reviews], dtype=int)
    predicted = (probabilities >= threshold).astype(int)

    tn, fp, fn, tp = confusion_matrix(true_labels, predicted, labels=[0, 1]).ravel()
    actual_matrix = {
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "tp": int(tp),
    }

    if actual_matrix != expected_matrix:
        print("[CẢNH BÁO] Confusion matrix tính lại KHÁC baseline_metrics.json")
        print(f"    trong JSON : {expected_matrix}")
        print(f"    tính lại   : {actual_matrix}")
    else:
        print("[ĐỐI CHIẾU OK] Confusion matrix khớp baseline_metrics.json")


def build_web_data():
    """
    Đọc DB và trả về (meta_data dict, reviews list, summary dict).

    Tách khỏi main() để chế độ --check dùng lại đúng cùng một logic, tránh
    hai nhánh sinh ra hai kết quả khác nhau.
    """
    connection = db.connect()
    try:
        model_run = db.get_latest_model_run(connection)
        if model_run is None:
            raise SystemExit(
                "Bảng model_runs đang trống. Hãy chạy: python MaNguon\\load_db.py"
            )

        model_run_id = model_run["id"]
        threshold = float(model_run["threshold"])
        metrics = model_run["metrics"]

        test_reviews = db.fetch_split_reviews(connection, "test", model_run_id)
        val_reviews = db.fetch_split_reviews(connection, "val", model_run_id)

        if not test_reviews:
            raise SystemExit(
                f"Không có review test cho lần chạy model id={model_run_id}. "
                "Hãy chạy: python MaNguon\\load_db.py"
            )

        check_confusion(
            test_reviews, threshold, metrics["test"]["confusion_matrix"]
        )

        review_rows = build_reviews(test_reviews, threshold)
        summary = build_summary(review_rows)

        test_probabilities = np.array(
            [row["prob_fake"] for row in test_reviews], dtype=float
        )
        test_true_labels = np.array(
            [row["true_label"] for row in test_reviews], dtype=int
        )
        val_probabilities = np.array(
            [row["prob_fake"] for row in val_reviews], dtype=float
        )
        val_true_labels = np.array(
            [row["true_label"] for row in val_reviews], dtype=int
        )

        # data_version: băm nội dung review đã xuất. Nếu dữ liệu đổi, mã đổi.
        # Nhờ vậy người xem biết trang đang hiển thị bản dữ liệu nào, và chế độ
        # --check có thể so sánh hai bản một cách chắc chắn.
        reviews_json = json.dumps(
            review_rows, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )
        data_version = hashlib.sha256(reviews_json.encode("utf-8")).hexdigest()[:12]

        meta_data = {
            "meta": {
                "model": "Logistic Regression (SGD, log_loss) + TF-IDF",
                "model_run_id": model_run_id,
                "threshold": round(threshold, 2),
                "rows_test": int(len(test_reviews)),
                "rows_val": int(len(val_reviews)),
                "sample_page_size": SAMPLE_PAGE_SIZE,
                "max_upload_rows": MAX_UPLOAD_ROWS,
                "max_upload_translate_seconds": MAX_UPLOAD_TRANSLATE_SECONDS,
                "category_order": CATEGORY_ORDER,
                "min_useful_words": MIN_USEFUL_WORDS,
                "bot_max_words": BOT_MAX_WORDS,
                "min_known_token_ratio": MIN_KNOWN_TOKEN_RATIO,
                "source": "fake-reviews-dataset - Salminen et al. (2022) - CC BY 4.0",
                # generated_at lấy từ lúc NẠP DỮ LIỆU, không phải lúc xuất file.
                # Xuất lại cùng dữ liệu không nên làm thời gian nhảy, nếu không
                # chế độ --check sẽ luôn báo lệch.
                "generated_at": model_run["created_at"].isoformat(),
                "data_version": data_version,
                # Bảng mẫu câu và nhãn cơ sở: web dùng để ghép lý do và hiện
                # "MODEL" / "LUẬT" mà không phải chép lại câu chữ.
                "reason_templates": REASON_TEMPLATES,
                "basis_labels": BASIS_LABELS,
                "web_files": {
                    "meta": WEB_META_PATH.name,
                    "reviews": WEB_REVIEWS_PATH.name,
                },
            },
            "summary": summary,
            # Số liệu kỹ thuật để trong một khối riêng: giao diện chính chỉ hiện
            # thứ người xem cần, phần này mở ra khi bảo vệ / đối chiếu báo cáo.
            "technical": {
                "metrics": metrics,
                "histogram": build_histogram(
                    test_probabilities, test_true_labels, HISTOGRAM_BIN_COUNT
                ),
                "threshold_curve": build_threshold_curve(
                    val_probabilities, val_true_labels
                ),
            },
        }

        return meta_data, review_rows, summary
    finally:
        connection.close()


def serialize_meta_data(meta_data):
    """
    Đổi dict thông tin thành nội dung file data_meta.js.

    ensure_ascii=False: giữ nguyên ký tự có dấu trong phần chữ tiếng Việt.
    separators=(",", ":"): bỏ khoảng trắng thừa của JSON.
    """
    return (
        "window.WEB_DATA_META = "
        + json.dumps(meta_data, ensure_ascii=False, separators=(",", ":"))
        + ";\n"
    )


def serialize_reviews(reviews):
    """Đổi danh sách review thành nội dung file data_reviews.js."""
    return (
        "window.WEB_DATA_REVIEWS = "
        + json.dumps(reviews, ensure_ascii=False, separators=(",", ":"))
        + ";\n"
    )


def check_file_matches(path, expected_text):
    """
    So file trên đĩa với nội dung vừa sinh.

    Trả (khớp, thông báo). Tách hàm để --check báo cùng một kiểu cho hai file.
    """
    if not path.exists():
        return False, f"[LỆCH] Chưa có file {path}. Hãy xuất dữ liệu."

    current_text = path.read_text(encoding="utf-8")
    if current_text == expected_text:
        return True, f"[ĐỐI CHIẾU OK] {path.name} khớp dữ liệu trong PostgreSQL."

    return False, f"[LỆCH] {path.name} KHÁC dữ liệu trong PostgreSQL."


def main():
    check_only = "--check" in sys.argv

    meta_data, reviews, summary = build_web_data()
    meta_text = serialize_meta_data(meta_data)
    reviews_text = serialize_reviews(reviews)

    if check_only:
        meta_ok, meta_message = check_file_matches(WEB_META_PATH, meta_text)
        reviews_ok, reviews_message = check_file_matches(
            WEB_REVIEWS_PATH, reviews_text
        )

        print(meta_message)
        print(reviews_message)

        if meta_ok and reviews_ok:
            raise SystemExit(0)

        print("    Hãy chạy: python MaNguon\\export_web_data.py")
        raise SystemExit(1)

    save_text_with_warning(WEB_META_PATH, meta_text)
    save_text_with_warning(WEB_REVIEWS_PATH, reviews_text)

    print(f"\nSố review đưa lên web: {len(reviews)}")
    print(f"Số dòng mỗi trang    : {SAMPLE_PAGE_SIZE}")
    print(f"Review hữu ích       : {summary['useful_count']}")
    print(f"Review bị loại       : {summary['removed_count']}")
    print(f"Review không đáng tin: {summary['unreliable_count']}")
    print("Số lượng theo nhóm:")
    for category_id in summary["categories"]:
        print(f"    {category_id:<22} {summary['categories'][category_id]}")
    print(f"Phiên bản dữ liệu    : {meta_data['meta']['data_version']}")
    print(f"File thông tin  : {WEB_META_PATH}")
    print(f"File review     : {WEB_REVIEWS_PATH}")
    print("Mở Web/index.html bằng double-click để xem báo cáo.")


if __name__ == "__main__":
    main()
