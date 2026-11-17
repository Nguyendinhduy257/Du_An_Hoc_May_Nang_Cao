r"""
Huấn luyện hồi quy logistic bằng SGD, hiệu chuẩn xác suất bằng Platt scaling
trên tập val, chọn ngưỡng theo F1 cao nhất trên val, rồi báo cáo kết quả trên
test đúng một lần.

Ghi ra: baseline_metrics.json, baseline_metrics_v1.json (bản trước hiệu chuẩn,
giữ để so sánh), val_predictions.csv, test_predictions.csv và model .pkl.

SGDClassifier với loss="log_loss" cho điểm số đúng thứ tự nhưng con số đó
không phải xác suất đúng nghĩa: model nói 0,90 mà thực tế chỉ khoảng 70%
trong số đó là giả. Platt scaling học một hàm logistic một biến trên val để
kéo con số về đúng tần suất thực nghiệm; sau đó "xác suất 0,45" mới thật sự
có nghĩa là khoảng 45%.
"""

import json
import pickle

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from config import (
    CALIBRATION_EPSILON,
    METRICS_JSON_PATH,
    METRICS_JSON_V1_PATH,
    MODEL_PATH,
    RANDOM_SEED,
    RELIABILITY_BIN_COUNT,
    SGD_CLASSIFIER_PARAMS,
    TEST_CSV_PATH,
    TEST_PREDICTIONS_CSV_PATH,
    TEST_RATIO,
    TFIDF_PARAMS,
    THRESHOLD_MAX,
    THRESHOLD_MIN,
    THRESHOLD_STEP,
    TRAIN_CSV_PATH,
    TRAIN_RATIO,
    VAL_CSV_PATH,
    VAL_PREDICTIONS_CSV_PATH,
    VAL_RATIO,
)
from features import fit_transform_features
from file_safety import save_bytes_with_warning, save_text_with_warning


def load_split(csv_path):
    """Đọc một tập đã chia sẵn."""
    return pd.read_csv(csv_path, encoding="utf-8")


def to_logit(probabilities):
    """
    Đổi xác suất sang thang logit: log(p / (1 - p)).

    Platt scaling fit một hàm logistic trên thang logit chứ không fit trực
    tiếp trên xác suất. Kẹp p vào [epsilon, 1 - epsilon] để tránh chia cho 0
    hoặc log(0).
    """
    clipped = np.clip(probabilities, CALIBRATION_EPSILON, 1.0 - CALIBRATION_EPSILON)
    return np.log(clipped / (1.0 - clipped))


def fit_platt(probabilities, true_labels):
    """
    Học hai hệ số a, b sao cho sigmoid(a * logit(p) + b) khớp tần suất thật.

    Dùng LogisticRegression một đặc trưng, đây chính là Platt scaling. C rất
    lớn nghĩa là gần như không phạt hệ số, để mô hình bám sát dữ liệu val.
    """
    logits = to_logit(probabilities).reshape(-1, 1)

    calibrator = LogisticRegression(C=1e6, solver="lbfgs", max_iter=1000)
    calibrator.fit(logits, true_labels)

    slope = float(calibrator.coef_[0][0])
    intercept = float(calibrator.intercept_[0])

    # Nếu slope <= 0 thì hàm hiệu chuẩn đảo ngược thứ tự xác suất, chắc chắn
    # là lỗi dữ liệu. Khi đó giữ nguyên xác suất gốc thay vì làm sai thêm.
    if slope <= 0:
        print("[CẢNH BÁO] Platt scaling cho slope <= 0, giữ nguyên xác suất gốc.")
        return 1.0, 0.0

    return slope, intercept


def apply_platt(probabilities, slope, intercept):
    """Áp dụng hàm hiệu chuẩn đã học lên một mảng xác suất."""
    logits = to_logit(probabilities)
    return 1.0 / (1.0 + np.exp(-(slope * logits + intercept)))


def find_best_threshold(probabilities, true_labels):
    """Quét ngưỡng, trả về ngưỡng cho F1 cao nhất trên val."""
    # Quét trên val chứ không phải test: test phải giữ kín để báo cáo khách
    # quan. Chọn ngưỡng trên test là tự "nhìn đáp án".
    thresholds = np.round(
        np.arange(THRESHOLD_MIN, THRESHOLD_MAX + THRESHOLD_STEP / 2, THRESHOLD_STEP),
        2,
    )

    best_threshold = THRESHOLD_MIN
    best_f1 = -1.0
    for threshold in thresholds:
        predicted = (probabilities >= threshold).astype(int)
        f1 = f1_score(true_labels, predicted, zero_division=0)
        if f1 > best_f1:
            best_f1 = f1
            best_threshold = float(threshold)

    return best_threshold, best_f1


def build_reliability_bins(probabilities, true_labels, bin_count):
    """
    Chia xác suất thành các khoảng và so "xác suất trung bình" với
    "tỷ lệ thật sự là giả" trong từng khoảng.

    Đây là bằng chứng trực quan cho việc hiệu chuẩn. Nếu hai con số gần nhau
    ở mọi khoảng thì xác suất đáng tin.
    """
    edges = np.linspace(0.0, 1.0, bin_count + 1)
    bins = []

    for index in range(bin_count):
        low = edges[index]
        high = edges[index + 1]

        # Khoảng cuối bao gồm cả biên phải để không bỏ sót xác suất = 1.0.
        if index == bin_count - 1:
            mask = (probabilities >= low) & (probabilities <= high)
        else:
            mask = (probabilities >= low) & (probabilities < high)

        count = int(mask.sum())
        if count == 0:
            bins.append(
                {
                    "low": round(float(low), 2),
                    "high": round(float(high), 2),
                    "count": 0,
                    "mean_predicted": None,
                    "observed_fake_rate": None,
                }
            )
            continue

        bins.append(
            {
                "low": round(float(low), 2),
                "high": round(float(high), 2),
                "count": count,
                "mean_predicted": round(float(probabilities[mask].mean()), 4),
                "observed_fake_rate": round(float(true_labels[mask].mean()), 4),
            }
        )

    return bins


def expected_calibration_error(bins, total):
    """
    ECE = trung bình có trọng số của |tần suất thật - xác suất dự đoán|.

    Càng nhỏ càng tốt; 0 nghĩa là xác suất khớp hoàn hảo với thực tế.
    """
    if total == 0:
        return 0.0

    error = 0.0
    for item in bins:
        if item["count"] == 0:
            continue
        gap = abs(item["observed_fake_rate"] - item["mean_predicted"])
        error = error + (item["count"] / total) * gap
    return float(error)


def compute_metrics(true_labels, probabilities, threshold):
    """Tính toàn bộ chỉ số tại một ngưỡng cho trước."""
    predicted = (probabilities >= threshold).astype(int)

    # labels=[0, 1] cố định thứ tự 4 ô, tránh lệch nếu một lớp vắng mặt.
    tn, fp, fn, tp = confusion_matrix(true_labels, predicted, labels=[0, 1]).ravel()

    return {
        "threshold": round(float(threshold), 2),
        "accuracy": round(float(accuracy_score(true_labels, predicted)), 4),
        "precision": round(float(precision_score(true_labels, predicted, zero_division=0)), 4),
        "recall": round(float(recall_score(true_labels, predicted, zero_division=0)), 4),
        "f1": round(float(f1_score(true_labels, predicted, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(true_labels, probabilities)), 4),
        "pr_auc": round(float(average_precision_score(true_labels, probabilities)), 4),
        "brier": round(float(brier_score_loss(true_labels, probabilities)), 4),
        "confusion_matrix": {
            "tn": int(tn),
            "fp": int(fp),
            "fn": int(fn),
            "tp": int(tp),
        },
    }


def build_prediction_table(true_labels, probabilities):
    """
    Tạo bảng dự đoán từng review để lớp web dùng lại.

    Cột:
      row_index  : vị trí dòng trong file CSV của tập tương ứng (bắt đầu từ 0).
      true_label : nhãn thật (0 = thật, 1 = giả).
      prob_fake  : xác suất ĐÃ HIỆU CHUẨN model gán nhãn giả.
    """
    # reset_index vì Series nhãn lấy từ DataFrame đã chia nên chỉ số bị nhảy
    # (ví dụ 17, 42, 103...). Đưa về 0..n-1 để khớp đúng thứ tự với file CSV.
    table = pd.DataFrame(
        {
            "row_index": np.arange(len(probabilities)),
            "true_label": true_labels.reset_index(drop=True).to_numpy(),
            "prob_fake": probabilities,
        }
    )
    return table


def print_metrics(title, metrics):
    print(f"\n=== {title} ===")
    print(f"Ngưỡng (threshold) : {metrics['threshold']:.2f}")
    print(f"Accuracy           : {metrics['accuracy']:.4f}")
    print(f"Precision          : {metrics['precision']:.4f}")
    print(f"Recall             : {metrics['recall']:.4f}")
    print(f"F1                 : {metrics['f1']:.4f}")
    print(f"ROC-AUC            : {metrics['roc_auc']:.4f}")
    print(f"PR-AUC             : {metrics['pr_auc']:.4f}")
    print(f"Brier              : {metrics['brier']:.4f} (càng nhỏ càng tốt)")

    matrix = metrics["confusion_matrix"]
    print("Confusion matrix   :")
    print(f"  TN={matrix['tn']:>6}  FP={matrix['fp']:>6}")
    print(f"  FN={matrix['fn']:>6}  TP={matrix['tp']:>6}")


def main():
    train_reviews = load_split(TRAIN_CSV_PATH)
    val_reviews = load_split(VAL_CSV_PATH)
    test_reviews = load_split(TEST_CSV_PATH)

    X_train, X_val, X_test, vectorizer = fit_transform_features(
        train_reviews, val_reviews, test_reviews
    )

    classifier = SGDClassifier(**SGD_CLASSIFIER_PARAMS)
    classifier.fit(X_train, train_reviews["label_binary"])

    # predict_proba trả xác suất theo thứ tự classifier.classes_. Cần cột của
    # lớp 1 (giả), không nên giả định nó luôn ở vị trí 1.
    positive_index = list(classifier.classes_).index(1)

    prob_val_raw = classifier.predict_proba(X_val)[:, positive_index]
    prob_test_raw = classifier.predict_proba(X_test)[:, positive_index]

    # Học hàm hiệu chuẩn CHỈ trên val. Test tuyệt đối không được dùng ở bước này.
    slope, intercept = fit_platt(prob_val_raw, val_reviews["label_binary"])

    prob_val = apply_platt(prob_val_raw, slope, intercept)
    prob_test = apply_platt(prob_test_raw, slope, intercept)

    best_threshold, best_f1_on_val = find_best_threshold(
        prob_val, val_reviews["label_binary"]
    )

    # Test chỉ được dùng ở đây, đúng một lần, sau khi ngưỡng đã chốt trên val.
    test_metrics = compute_metrics(
        test_reviews["label_binary"], prob_test, best_threshold
    )

    reliability_bins = build_reliability_bins(
        prob_test, test_reviews["label_binary"].to_numpy(), RELIABILITY_BIN_COUNT
    )
    bins_before = build_reliability_bins(
        prob_test_raw, test_reviews["label_binary"].to_numpy(), RELIABILITY_BIN_COUNT
    )

    total_test = len(test_reviews)
    ece_after = expected_calibration_error(reliability_bins, total_test)
    ece_before = expected_calibration_error(bins_before, total_test)
    brier_before = float(
        brier_score_loss(test_reviews["label_binary"], prob_test_raw)
    )

    print(f"\nSố đặc trưng TF-IDF: {X_train.shape[1]:,}")
    print(f"Platt scaling      : slope={slope:.4f}, intercept={intercept:.4f}")
    print(
        f"Brier trước/sau    : {brier_before:.4f} -> {test_metrics['brier']:.4f}"
    )
    print(f"ECE trước/sau      : {ece_before:.4f} -> {ece_after:.4f}")
    print(
        f"Ngưỡng tốt nhất trên val: {best_threshold:.2f} "
        f"(F1 val = {best_f1_on_val:.4f})"
    )
    print_metrics("KẾT QUẢ TRÊN TẬP TEST", test_metrics)

    # Xuất dự đoán từng review ngay tại đây, vì đây là nơi DUY NHẤT đang giữ
    # prob_val / prob_test trong bộ nhớ. Nếu để script web train lại thì có hai
    # nguồn số liệu và chúng có thể lệch nhau mà không ai phát hiện.
    # float_format="%.6f": cắt bớt chữ số thập phân để file nhỏ và ổn định,
    # giúp lần chạy sau so sánh được với lần trước (không báo đổi vô ích).
    val_predictions = build_prediction_table(val_reviews["label_binary"], prob_val)
    test_predictions = build_prediction_table(test_reviews["label_binary"], prob_test)
    save_text_with_warning(
        VAL_PREDICTIONS_CSV_PATH,
        val_predictions.to_csv(index=False, float_format="%.6f"),
    )
    save_text_with_warning(
        TEST_PREDICTIONS_CSV_PATH,
        test_predictions.to_csv(index=False, float_format="%.6f"),
    )

    # Lưu model để API dùng lại mà không phải train lại.
    # Dùng pickle của thư viện chuẩn thay vì joblib để không phát sinh thư viện
    # mới. Model chỉ gồm numpy array và cấu hình Python thuần nên pickle là đủ.
    # platt_slope / platt_intercept: API phải áp dụng đúng hàm hiệu chuẩn này,
    # nếu không xác suất hiển thị sẽ khác xác suất lúc train.
    model_bundle = {
        "vectorizer": vectorizer,
        "classifier": classifier,
        "threshold": round(float(best_threshold), 2),
        "platt_slope": slope,
        "platt_intercept": intercept,
    }
    save_bytes_with_warning(MODEL_PATH, pickle.dumps(model_bundle))

    result = {
        "dataset": {
            "rows_train": int(len(train_reviews)),
            "rows_val": int(len(val_reviews)),
            "rows_test": int(len(test_reviews)),
            "n_features": int(X_train.shape[1]),
        },
        "config": {
            "random_seed": RANDOM_SEED,
            "train_ratio": TRAIN_RATIO,
            "val_ratio": VAL_RATIO,
            "test_ratio": TEST_RATIO,
            "tfidf": TFIDF_PARAMS,
            "sgd_classifier": SGD_CLASSIFIER_PARAMS,
        },
        "validation": {
            "best_threshold": round(float(best_threshold), 2),
            "best_f1": round(float(best_f1_on_val), 4),
        },
        "calibration": {
            "method": "platt",
            "platt_slope": round(slope, 6),
            "platt_intercept": round(intercept, 6),
            "brier_before": round(brier_before, 4),
            "brier_after": test_metrics["brier"],
            "ece_before": round(ece_before, 4),
            "ece_after": round(ece_after, 4),
            "reliability_bins": reliability_bins,
        },
        "test": test_metrics,
    }

    # Giữ lại số liệu TRƯỚC hiệu chuẩn ở lần chạy đầu tiên. Nếu file v1 đã có
    # thì không ghi đè: đó là mốc gốc để so sánh, không phải bản nháp.
    if METRICS_JSON_PATH.exists() and not METRICS_JSON_V1_PATH.exists():
        old_text = METRICS_JSON_PATH.read_text(encoding="utf-8")
        save_text_with_warning(METRICS_JSON_V1_PATH, old_text)

    # Serialize trước vì file_safety cần nội dung trong bộ nhớ để so sánh với
    # bản cũ trước khi quyết định ghi đè.
    json_text = json.dumps(result, ensure_ascii=False, indent=2)
    save_text_with_warning(METRICS_JSON_PATH, json_text)

    print(f"\nFile kết quả: {METRICS_JSON_PATH}")
    print(f"File dự đoán val : {VAL_PREDICTIONS_CSV_PATH}")
    print(f"File dự đoán test: {TEST_PREDICTIONS_CSV_PATH}")
    print(f"File model       : {MODEL_PATH}")


if __name__ == "__main__":
    main()
