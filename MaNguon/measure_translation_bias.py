r"""
Đo model lệch bao nhiêu khi câu phải đi qua dịch máy hai lần.

Cách đo (dịch vòng):
    1. Lấy một review tiếng Anh gốc đã biết xác suất giả từ lần chạy train.
    2. Dịch sang tiếng Việt.
    3. Dịch bản tiếng Việt trở lại tiếng Anh, mô phỏng đúng việc người dùng
       nhập tiếng Việt và hệ thống dịch sang tiếng Anh trước khi dự đoán.
    4. Chấm lại bản dịch vòng rồi so với dự đoán gốc.

Dịch máy có thể đổi từ ngữ, mất sắc thái hoặc làm câu giống văn máy viết. Tỷ
lệ đổi nhãn cao nghĩa là kết quả với người dùng nước ngoài không đáng tin như
con số trên tập test tiếng Anh. Đây vẫn chỉ là mô phỏng: nó đo tác động của
công cụ dịch, không đo khả năng hiểu tiếng Việt của model.

Chạy: python MaNguon\measure_translation_bias.py
Kết quả: KetQuaChay/translation_bias.json
"""

import json
import math
import pickle
import random
from datetime import datetime, timezone

import db
from config import (
    CALIBRATION_EPSILON,
    MODEL_PATH,
    RANDOM_SEED,
    TRANSLATION_BIAS_JSON_PATH,
    TRANSLATION_BIAS_SAMPLE_SIZE,
)
from file_safety import save_text_with_warning
from translate import translate_text


def apply_calibration(probability, slope, intercept):
    """
    Áp dụng hàm Platt đã học lúc train.

    Chép công thức thay vì gọi api_server vì script đo phải chạy độc lập, không
    phụ thuộc vào tiến trình server. Công thức rất ngắn và có kiểm chứng bằng
    so sánh với xác suất đã lưu trong DB.
    """
    clipped = min(max(probability, CALIBRATION_EPSILON), 1.0 - CALIBRATION_EPSILON)
    logit = math.log(clipped / (1.0 - clipped))
    return 1.0 / (1.0 + math.exp(-(slope * logit + intercept)))


def predict_probability(bundle, text):
    """Trả xác suất giả ĐÃ hiệu chuẩn cho một câu."""
    vectorizer = bundle["vectorizer"]
    classifier = bundle["classifier"]
    slope = float(bundle.get("platt_slope", 1.0))
    intercept = float(bundle.get("platt_intercept", 0.0))

    feature_matrix = vectorizer.transform([text])
    probabilities = classifier.predict_proba(feature_matrix)[0]
    positive_index = list(classifier.classes_).index(1)

    return apply_calibration(float(probabilities[positive_index]), slope, intercept)


def main():
    if not db.is_available():
        raise SystemExit(
            "Không kết nối được PostgreSQL. Hãy chạy: docker compose up -d"
        )

    with MODEL_PATH.open("rb") as model_file:
        bundle = pickle.load(model_file)

    threshold = float(bundle["threshold"])

    connection = db.connect()
    try:
        model_run = db.get_latest_model_run(connection)
        if model_run is None:
            raise SystemExit("Chưa có dữ liệu. Hãy chạy: python MaNguon\\load_db.py")
        reviews = db.fetch_split_reviews(connection, "test", model_run["id"])
    finally:
        connection.close()

    # Chọn mẫu cố định theo seed để chạy lại cho cùng kết quả.
    # Không lấy N dòng đầu vì dữ liệu đã sắp theo nhãn, lấy đầu sẽ lệch.
    random_generator = random.Random(RANDOM_SEED)
    sample_size = min(TRANSLATION_BIAS_SAMPLE_SIZE, len(reviews))
    sample = random_generator.sample(reviews, sample_size)

    comparisons = []
    translation_failures = 0

    for position, review in enumerate(sample, start=1):
        original_text = review["text"]
        original_probability = float(review["prob_fake"])
        original_label = 1 if original_probability >= threshold else 0

        to_vietnamese = translate_text(original_text, target_language="vi")
        if not to_vietnamese["used_translation"]:
            translation_failures = translation_failures + 1
            continue

        back_to_english = translate_text(
            to_vietnamese["translated_text"], target_language="en"
        )
        if not back_to_english["used_translation"]:
            translation_failures = translation_failures + 1
            continue

        roundtrip_text = back_to_english["translated_text"]
        roundtrip_probability = predict_probability(bundle, roundtrip_text)
        roundtrip_label = 1 if roundtrip_probability >= threshold else 0

        comparisons.append(
            {
                "row_index": int(review["row_index"]),
                "original_probability": round(original_probability, 4),
                "roundtrip_probability": round(roundtrip_probability, 4),
                "probability_delta": round(
                    abs(roundtrip_probability - original_probability), 4
                ),
                "original_label": original_label,
                "roundtrip_label": roundtrip_label,
                "label_flipped": bool(original_label != roundtrip_label),
                "original_text": original_text,
                "vietnamese_text": to_vietnamese["translated_text"],
                "roundtrip_text": roundtrip_text,
            }
        )

        print(
            f"[{position}/{sample_size}] row={review['row_index']} "
            f"p={original_probability:.4f} -> {roundtrip_probability:.4f} "
            f"{'ĐỔI NHÃN' if original_label != roundtrip_label else ''}"
        )

    measured = len(comparisons)

    if measured == 0:
        raise SystemExit(
            "Không đo được mẫu nào: dịch vụ dịch không phản hồi. "
            "Hãy kiểm tra kết nối mạng rồi chạy lại."
        )

    flipped = sum(1 for item in comparisons if item["label_flipped"])
    mean_delta = sum(item["probability_delta"] for item in comparisons) / measured
    max_delta = max(item["probability_delta"] for item in comparisons)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_run_id": model_run["id"],
        "threshold": round(threshold, 2),
        "method": "round_trip_english_vietnamese_english",
        "sample_size_requested": sample_size,
        "sample_size_measured": measured,
        "translation_failures": translation_failures,
        "label_flip_count": flipped,
        "label_flip_rate": round(flipped / measured, 4),
        "mean_absolute_probability_delta": round(mean_delta, 4),
        "max_absolute_probability_delta": round(max_delta, 4),
        "comparisons": comparisons,
        "notes": [
            "Đây là mô phỏng dịch vòng, không phải review do người Việt viết.",
            "Kết quả đo tác động của công cụ dịch, không đo khả năng hiểu tiếng Việt.",
            "Dịch vụ dịch là endpoint công khai không chính thức, có thể đổi hành vi.",
        ],
    }

    json_text = json.dumps(result, ensure_ascii=False, indent=2)
    save_text_with_warning(TRANSLATION_BIAS_JSON_PATH, json_text)

    print("\n=== ĐỘ LỆCH DO DỊCH MÁY ===")
    print(f"Mẫu đo được          : {measured}/{sample_size}")
    print(f"Lỗi dịch             : {translation_failures}")
    print(f"Đổi nhãn             : {flipped} ({result['label_flip_rate']})")
    print(f"Lệch xác suất trung bình: {result['mean_absolute_probability_delta']}")
    print(f"Lệch xác suất lớn nhất  : {result['max_absolute_probability_delta']}")
    print(f"\nFile kết quả: {TRANSLATION_BIAS_JSON_PATH}")


if __name__ == "__main__":
    main()
