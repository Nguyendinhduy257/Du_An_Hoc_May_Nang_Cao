r"""
Vẽ các biểu đồ phân tích/trực quan hóa theo học phần 004759.

Không huấn luyện lại model chính. Script đọc xác suất đã lưu, model bundle và
hai tập đã chia rồi vẽ:
- histogram/boxplot xác suất theo nhãn: 004759 Chương 1 slide 16, Chương 2 slide 17;
- ma trận nhầm, ROC/AUC, Precision-Recall, độ quan trọng thuộc tính, đường cong
  học, biên quyết định 2 chiều: 004759 Chương 4 slide 52-54 (CLO4/CLO6, Rubric R2).

Đường cong học dùng tập val, không đụng tập test; tập test chỉ được dùng để vẽ
các biểu đồ đánh giá từ kết quả đã có từ trước.

Chạy: python MaNGuon\ve_bieu_do_chan_doan.py
Ghi: KetQuaChay/figures/*.png
"""

import atexit
import json
import pickle

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.metrics import (
    average_precision_score,
    auc,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    roc_curve,
)

from config import (
    LABEL_BINARY_COLUMN,
    METRICS_JSON_PATH,
    MODEL_PATH,
    RESULTS_DIR,
    SGD_CLASSIFIER_PARAMS,
    TEST_PREDICTIONS_CSV_PATH,
    TEXT_COLUMN,
    TRAIN_CSV_PATH,
    VAL_CSV_PATH,
)
from don_rac import auto_cleanup
from tinh_tay import build_numeric_features, fisher_scores

atexit.register(auto_cleanup)

FIGURES_DIR = RESULTS_DIR / "figures"
CLASS_NAMES = ["thật (0)", "giả (1)"]


def save_figure(figure, name):
    """Lưu một hình vào KetQuaChay/figures và đóng figure để nhớ bộ nhớ."""
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIGURES_DIR / name
    figure.tight_layout()
    figure.savefig(path, dpi=130)
    plt.close(figure)
    return path


def plot_probability_distribution(true_labels, probabilities):
    """Histogram và boxplot: Chương 1 slide 16, Chương 2 slide 17."""
    figure, axes = plt.subplots(1, 2, figsize=(12, 4))
    for label, color in ((0, "#2ca02c"), (1, "#d62728")):
        axes[0].hist(
            probabilities[true_labels == label],
            bins=40,
            alpha=0.6,
            color=color,
            label=CLASS_NAMES[label],
        )
    axes[0].set_title("Phân bố xác suất giả theo nhãn thật")
    axes[0].set_xlabel("xác suất giả")
    axes[0].set_ylabel("số review")
    axes[0].legend()

    axes[1].boxplot(
        [probabilities[true_labels == 0], probabilities[true_labels == 1]],
        tick_labels=CLASS_NAMES,
    )
    axes[1].set_title("Boxplot xác suất giả (phát hiện ngoại lai)")
    axes[1].set_ylabel("xác suất giả")
    return save_figure(figure, "phan_bo_xac_suat.png")


def plot_confusion_matrix(true_labels, predicted_labels):
    """Ma trận nhầm dạng nhiệt: Chương 4 slide 53, biểu đồ số 1."""
    matrix = confusion_matrix(true_labels, predicted_labels, labels=[0, 1])
    figure, axis = plt.subplots(figsize=(5, 4))
    image = axis.imshow(matrix, cmap="Blues")
    for row in range(2):
        for column in range(2):
            axis.text(column, row, str(matrix[row, column]), ha="center", va="center")
    axis.set_xticks([0, 1])
    axis.set_xticklabels(["dự đoán thật", "dự đoán giả"])
    axis.set_yticks([0, 1])
    axis.set_yticklabels(["thật", "giả"])
    axis.set_title("Ma trận nhầm lẫn (ngưỡng đã chọn)")
    figure.colorbar(image, ax=axis, fraction=0.046)
    return save_figure(figure, "ma_tran_nham.png")


def plot_roc(true_labels, probabilities):
    """Đường ROC kèm AUC: Chương 4 slide 52 và slide 53, biểu đồ số 2."""
    false_positive, true_positive, _ = roc_curve(true_labels, probabilities)
    score = auc(false_positive, true_positive)
    figure, axis = plt.subplots(figsize=(5, 5))
    axis.plot(false_positive, true_positive, label=f"model chính (AUC={score:.4f})")
    axis.plot([0, 1], [0, 1], "k--", label="đoán mò")
    axis.set_xlabel("FPR = FP / (FP + TN)")
    axis.set_ylabel("TPR = recall")
    axis.set_title("Đường ROC trên tập test")
    axis.legend(loc="lower right")
    return save_figure(figure, "duong_roc.png")


def plot_precision_recall(true_labels, probabilities):
    """Đường Precision-Recall kèm AP: Chương 4 slide 53, biểu đồ số 3."""
    precision, recall, _ = precision_recall_curve(true_labels, probabilities)
    average_precision = average_precision_score(true_labels, probabilities)
    figure, axis = plt.subplots(figsize=(5, 5))
    axis.plot(recall, precision, label=f"model chính (AP={average_precision:.4f})")
    axis.axhline(true_labels.mean(), color="k", linestyle="--", label="tỷ lệ lớp giả")
    axis.set_xlabel("recall")
    axis.set_ylabel("precision")
    axis.set_title("Đường Precision-Recall trên tập test")
    axis.legend(loc="lower left")
    return save_figure(figure, "duong_do_chinh_xac_thu_hoi.png")


def plot_feature_importance(bundle):
    """15 từ có trọng số lớn nhất: Chương 4 slide 53, biểu đồ số 4."""
    coefficients = bundle["classifier"].coef_[0]
    names = bundle["vectorizer"].get_feature_names_out()
    top_indices = np.argsort(np.abs(coefficients))[-15:][::-1]
    figure, axis = plt.subplots(figsize=(8, 6))
    axis.barh(
        names[top_indices][::-1],
        coefficients[top_indices][::-1],
        color=np.where(coefficients[top_indices][::-1] >= 0, "#d62728", "#2ca02c"),
    )
    axis.axvline(0, color="black", linewidth=0.8)
    axis.set_title("TF-IDF có trọng số lớn nhất (đỏ: đẩy sang giả)")
    axis.set_xlabel("trọng số của classifier")
    return save_figure(figure, "do_quan_trong_dac_trung.png")


def plot_learning_curve(bundle, train_reviews, val_reviews):
    """F1 trên val theo kích thước train: Chương 4 slide 53, biểu đồ số 5."""
    vectorizer = bundle["vectorizer"]
    x_train = vectorizer.transform(train_reviews[TEXT_COLUMN])
    x_val = vectorizer.transform(val_reviews[TEXT_COLUMN])
    y_train = train_reviews[LABEL_BINARY_COLUMN].to_numpy()
    y_val = val_reviews[LABEL_BINARY_COLUMN].to_numpy()

    fractions = (0.1, 0.25, 0.5, 0.75, 1.0)
    scores = []
    for fraction in fractions:
        sample_count = max(100, int(len(y_train) * fraction))
        classifier = SGDClassifier(**SGD_CLASSIFIER_PARAMS)
        classifier.fit(x_train[:sample_count], y_train[:sample_count])
        probabilities = classifier.predict_proba(x_val)[:, 1]
        scores.append(f1_score(y_val, (probabilities >= 0.5).astype(int)))

    figure, axis = plt.subplots(figsize=(6, 4))
    axis.plot(fractions, scores, marker="o")
    axis.set_xlabel("tỷ lệ tập huấn luyện dùng để fit")
    axis.set_ylabel("F1 trên tập val (ngưỡng 0,5, chưa hiệu chuẩn)")
    axis.set_title("Đường cong học tập")
    return save_figure(figure, "duong_hoc_tap.png")


def plot_decision_boundary(train_reviews):
    """Biên 2 chiều từ hai đặc trưng Fisher: Chương 4 slide 53, biểu đồ số 6."""
    target = np.where(train_reviews[LABEL_BINARY_COLUMN].to_numpy() == 1, 1, -1)
    features = build_numeric_features(train_reviews)
    scores = fisher_scores(features.to_numpy(), target)
    selected = np.argsort(-scores)[:2]
    values = features.iloc[:, selected].to_numpy()

    mean = values.mean(axis=0)
    std = np.where(values.std(axis=0) > 1e-12, values.std(axis=0), 1.0)
    standardized = (values - mean) / std

    classifier = LogisticRegression(max_iter=1000)
    classifier.fit(standardized, target)

    horizontal = np.linspace(standardized[:, 0].min() - 0.5, standardized[:, 0].max() + 0.5, 120)
    vertical = np.linspace(standardized[:, 1].min() - 0.5, standardized[:, 1].max() + 0.5, 120)
    grid_x, grid_y = np.meshgrid(horizontal, vertical)
    grid = np.column_stack([grid_x.ravel(), grid_y.ravel()])
    grid_probability = classifier.predict_proba(grid)[:, 1].reshape(grid_x.shape)

    figure, axis = plt.subplots(figsize=(7, 5))
    axis.contourf(grid_x, grid_y, grid_probability, alpha=0.25, cmap="RdBu_r")
    axis.contour(grid_x, grid_y, grid_probability, levels=[0.5], colors="black")

    sample_indices = np.random.default_rng(0).choice(
        len(standardized), min(3000, len(standardized)), replace=False
    )
    for label, color in ((1, "#d62728"), (-1, "#2ca02c")):
        chosen = sample_indices[target[sample_indices] == label]
        axis.scatter(
            standardized[chosen, 0], standardized[chosen, 1],
            s=8, alpha=0.5, color=color, label="giả" if label == 1 else "thật",
        )

    axis.set_xlabel(features.columns[selected[0]] + " (z-score)")
    axis.set_ylabel(features.columns[selected[1]] + " (z-score)")
    axis.set_title("Biên quyết định 2 chiều - chỉ để minh hoạ, không phải model chính")
    axis.legend(loc="best")
    return save_figure(figure, "bien_gioi_quyet_dinh_2d.png")


def main():
    predictions = pd.read_csv(TEST_PREDICTIONS_CSV_PATH, encoding="utf-8")
    true_labels = predictions["true_label"].to_numpy()
    probabilities = predictions["prob_fake"].to_numpy()
    metrics = json.loads(METRICS_JSON_PATH.read_text(encoding="utf-8"))
    threshold = float(metrics["test"]["threshold"])
    predicted_labels = (probabilities >= threshold).astype(int)

    bundle = pickle.loads(MODEL_PATH.read_bytes())
    train_reviews = pd.read_csv(TRAIN_CSV_PATH, encoding="utf-8")
    val_reviews = pd.read_csv(VAL_CSV_PATH, encoding="utf-8")

    print("VE BIEU DO 004759 - Ch1 slide 14-16, Ch2 slide 17, Ch4 slide 52-54")
    for path in (
        plot_probability_distribution(true_labels, probabilities),
        plot_confusion_matrix(true_labels, predicted_labels),
        plot_roc(true_labels, probabilities),
        plot_precision_recall(true_labels, probabilities),
        plot_feature_importance(bundle),
        plot_learning_curve(bundle, train_reviews, val_reviews),
        plot_decision_boundary(train_reviews),
    ):
        print(f"   Da ve: {path}")
    print(f"Tong: 7 hinh trong {FIGURES_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
