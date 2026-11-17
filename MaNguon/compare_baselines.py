r"""
So model chính với hai baseline mà Ch3 tr. 43/47 yêu cầu: đoán lớp đa số và
hồi quy logistic đơn giản ngưỡng 0,5.

Chạy: python MaNguon\compare_baselines.py
Đọc: train/val/test trong DuLieuDeHoc\DuLieuDaXuLy\, baseline_metrics.json và
test_predictions.csv.
Ghi: KetQuaChay/baseline_comparison.json và bảng so sánh trên màn hình.

Chỉ báo F1 mà không so gì thì chưa chứng minh được model có ích. Baseline đa
số cho biết "đoán bừa" được bao nhiêu; baseline hồi quy logistic ngưỡng 0,5
cho biết phần cải thiện đến từ mô hình và phần đến từ việc chọn ngưỡng. Không
huấn luyện lại model chính mà dùng lại xác suất đã lưu trong
test_predictions.csv, để bảng so sánh khớp với baseline_metrics.json.
"""

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

from config import (
    BASELINE_COMPARISON_JSON_PATH,
    LABEL_BINARY_COLUMN,
    METRICS_JSON_PATH,
    RANDOM_SEED,
    TEST_CSV_PATH,
    TEST_PREDICTIONS_CSV_PATH,
    THRESHOLD_DEFAULT,
    TRAIN_CSV_PATH,
    VAL_CSV_PATH,
)
from features import fit_transform_features

# Lấy đường dẫn từ config để mọi script khác cũng đọc/ghi đúng một chỗ, không
# tự ghép "parent.parent" (dễ sai cấp thư mục).
MAIN_METRICS_PATH = METRICS_JSON_PATH
MAIN_TEST_PREDICTIONS_PATH = TEST_PREDICTIONS_CSV_PATH


def load_split(csv_path):
    """Đọc một tập đã chia."""
    return pd.read_csv(csv_path, encoding="utf-8")


def compute_metrics(true_labels, probabilities, threshold):
    """
    Tính bộ chỉ số tại một ngưỡng.

    threshold = None nghĩa là mô hình không sinh xác suất (baseline đa số).
    """
    if threshold is None:
        predicted = probabilities
    else:
        predicted = (probabilities >= threshold).astype(int)

    matrix = confusion_matrix(true_labels, predicted, labels=[0, 1]).ravel()
    tn, fp, fn, tp = matrix

    return {
        "threshold": None if threshold is None else round(float(threshold), 2),
        "accuracy": round(float(np.mean(predicted == true_labels)), 4),
        "precision": round(float(precision_score(true_labels, predicted, zero_division=0)), 4),
        "recall": round(float(recall_score(true_labels, predicted, zero_division=0)), 4),
        "f1": round(float(f1_score(true_labels, predicted, zero_division=0)), 4),
        "confusion_matrix": {
            "tn": int(tn),
            "fp": int(fp),
            "fn": int(fn),
            "tp": int(tp),
        },
    }


def majority_baseline(train_reviews, test_reviews):
    """
    Baseline đoán lớp đa số của tập train cho mọi dòng test.

    Phải xử lý hoà vì dataset gốc có đúng 20.216 CG và 20.216 OR. Nếu sau khử
    trùng lặp hai lớp vẫn bằng nhau thì không có "lớp đa số" thật, khi đó chọn
    nhãn 0 và ghi rõ trong báo cáo.
    """
    counts = train_reviews[LABEL_BINARY_COLUMN].value_counts()
    label_zero = int(counts.get(0, 0))
    label_one = int(counts.get(1, 0))

    if label_zero > label_one:
        majority_label = 0
        note = "Lớp 0 (thật) nhiều hơn trong train."
    elif label_one > label_zero:
        majority_label = 1
        note = "Lớp 1 (giả) nhiều hơn trong train."
    else:
        majority_label = 0
        note = "Hai lớp bằng nhau trong train (hoà), chọn nhãn 0."

    predicted = np.full(len(test_reviews), majority_label)
    metrics = compute_metrics(
        test_reviews[LABEL_BINARY_COLUMN].to_numpy(), predicted, None
    )
    metrics["name"] = "Đoán lớp đa số"
    metrics["note"] = note
    metrics["train_label_counts"] = {"label_0": label_zero, "label_1": label_one}
    return metrics


def simple_logistic_baseline(train_reviews, val_reviews, test_reviews):
    """
    Logistic Regression mặc định của scikit-learn, ngưỡng 0.5.

    Dùng LogisticRegression thay vì SGDClassifier vì đây là cấu hình "mặc
    định, không tinh chỉnh" mà Ch3 tr. 47 coi là mốc so sánh. Model chính dùng
    SGD + hiệu chuẩn + ngưỡng riêng, nên khác biệt đo được chính là phần đóng
    góp của các bước đó.
    """
    x_train, x_val, x_test, _ = fit_transform_features(
        train_reviews, val_reviews, test_reviews
    )

    classifier = LogisticRegression(max_iter=1000, random_state=RANDOM_SEED)
    classifier.fit(x_train, train_reviews[LABEL_BINARY_COLUMN])

    positive_index = list(classifier.classes_).index(1)
    probabilities = classifier.predict_proba(x_test)[:, positive_index]

    metrics = compute_metrics(
        test_reviews[LABEL_BINARY_COLUMN].to_numpy(),
        probabilities,
        THRESHOLD_DEFAULT,
    )
    metrics["name"] = "Logistic Regression mặc định (ngưỡng 0.5)"
    metrics["note"] = "Cùng TF-IDF, không hiệu chuẩn, ngưỡng mặc định."
    return metrics


def main_model_row(main_metrics, test_reviews):
    """
    Lấy số liệu model chính từ KetQuaChay/baseline_metrics.json.

    Không tự tính lại vì báo cáo chính thức phải khớp đúng file metrics đã
    dùng trong README và web.
    """
    test_block = main_metrics["test"]
    return {
        "name": "Model chính (LR + SGD + hiệu chuẩn)",
        "threshold": test_block["threshold"],
        "accuracy": test_block["accuracy"],
        "precision": test_block["precision"],
        "recall": test_block["recall"],
        "f1": test_block["f1"],
        "confusion_matrix": test_block["confusion_matrix"],
        "note": "Số liệu đọc từ KetQuaChay/baseline_metrics.json.",
        "rows_test": int(len(test_reviews)),
    }


def main_model_at_threshold(predictions, test_reviews, threshold, main_metrics):
    """
    Tính lại model chính tại một ngưỡng khác, dùng xác suất đã lưu.

    Cần bước này để so công bằng với LR mặc định: cả hai phải cùng ngưỡng 0.5.
    Hàm cũng tự kiểm tra rằng xác suất trong CSV khớp với metrics chính thức ở
    ngưỡng đã chọn; nếu lệch nghĩa là file dự đoán không còn đồng bộ.
    """
    true_labels = test_reviews[LABEL_BINARY_COLUMN].to_numpy()
    probabilities = predictions["prob_fake"].to_numpy()

    official_threshold = main_metrics["test"]["threshold"]
    official_matrix = main_metrics["test"]["confusion_matrix"]
    check = compute_metrics(true_labels, probabilities, official_threshold)
    if check["confusion_matrix"] != official_matrix:
        raise SystemExit(
            "LỖI: test_predictions.csv không khớp baseline_metrics.json. "
            "Hãy chạy lại MaNguon\\train_baseline.py trước khi so sánh."
        )

    metrics = compute_metrics(true_labels, probabilities, threshold)
    metrics["name"] = "Model chính (cùng ngưỡng 0.5)"
    metrics["note"] = "Cùng model, chỉ đổi ngưỡng về 0.5 để so công bằng."
    return metrics


def main():
    train_reviews = load_split(TRAIN_CSV_PATH)
    val_reviews = load_split(VAL_CSV_PATH)
    test_reviews = load_split(TEST_CSV_PATH)

    with MAIN_METRICS_PATH.open(encoding="utf-8") as file:
        main_metrics = json.load(file)

    predictions = pd.read_csv(MAIN_TEST_PREDICTIONS_PATH, encoding="utf-8")

    rows = [
        majority_baseline(train_reviews, test_reviews),
        simple_logistic_baseline(train_reviews, val_reviews, test_reviews),
        main_model_at_threshold(
            predictions, test_reviews, THRESHOLD_DEFAULT, main_metrics
        ),
        main_model_row(main_metrics, test_reviews),
    ]

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "rows_train": int(len(train_reviews)),
            "rows_val": int(len(val_reviews)),
            "rows_test": int(len(test_reviews)),
        },
        "rows": rows,
    }

    BASELINE_COMPARISON_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_COMPARISON_JSON_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=== SO SÁNH BASELINE (tập test) ===")
    print(f"{'Mô hình':<46}{'Ngưỡng':>8}{'Acc':>8}{'Prec':>8}{'Rec':>8}{'F1':>8}")
    for row in rows:
        threshold_text = "—" if row["threshold"] is None else f"{row['threshold']:.2f}"
        print(
            f"{row['name']:<46}{threshold_text:>8}"
            f"{row['accuracy']:>8.4f}{row['precision']:>8.4f}"
            f"{row['recall']:>8.4f}{row['f1']:>8.4f}"
        )

    print("\nGhi chú:")
    for row in rows:
        print(f"  - {row['name']}: {row['note']}")

    print(f"\nĐã ghi: {BASELINE_COMPARISON_JSON_PATH}")


if __name__ == "__main__":
    main()
