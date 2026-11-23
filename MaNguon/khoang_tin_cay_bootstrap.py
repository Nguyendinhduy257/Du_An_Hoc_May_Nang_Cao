r"""
Khoảng tin cậy 95% bằng bootstrap cho chỉ số chính trên tập test (B9.1).

Không huấn luyện lại model: đọc xác suất đã lưu trong test_predictions.csv và
ngưỡng đã chọn trong baseline_metrics.json, rồi lấy mẫu có hoàn trả 1.000 lần
với hạt giống SEED = 2026 + G. Tập test vẫn chỉ "được dùng" đúng một lần để
tính điểm điểm; bootstrap chỉ ước lượng độ bất định của con số đó.

Chạy: python MaNGuon\khoang_tin_cay_bootstrap.py
Ghi ra KetQuaChay/khoang_tin_cay_bootstrap.json; không tham gia run_all.py.
"""

import atexit
import json

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

from config import METRICS_JSON_PATH, RESULTS_DIR, TEST_PREDICTIONS_CSV_PATH
from cau_hinh_tinh_tay import BOOTSTRAP_ITERATIONS, HAND_CALC_SEED
from don_rac import auto_cleanup
from file_safety import save_text_with_warning

atexit.register(auto_cleanup)


BOOTSTRAP_CI_PATH = RESULTS_DIR / "khoang_tin_cay_bootstrap.json"


def compute_metrics(true_labels, predicted_labels):
    """Bộ chỉ số tại một lần lấy mẫu bootstrap."""
    return {
        "f1": float(f1_score(true_labels, predicted_labels, zero_division=0)),
        "accuracy": float(accuracy_score(true_labels, predicted_labels)),
        "precision": float(precision_score(true_labels, predicted_labels, zero_division=0)),
        "recall": float(recall_score(true_labels, predicted_labels, zero_division=0)),
    }


def bootstrap_metrics(true_labels, probabilities, threshold, iterations, seed):
    """
    Bootstrap có hoàn trả, trả mảng chỉ số của từng lần lặp.

    Bỏ qua lần lấy mẫu mà trong đó chỉ còn một lớp: F1/precision không có
    nghĩa khi không có lớp dương (hoặc chỉ có lớp dương).
    """
    rng = np.random.default_rng(seed)
    sample_count = len(true_labels)
    collected = {name: [] for name in ("f1", "accuracy", "precision", "recall")}

    for _ in range(iterations):
        indices = rng.integers(0, sample_count, sample_count)
        sampled_true = true_labels[indices]
        if np.unique(sampled_true).size < 2:
            continue
        sampled_predicted = (probabilities[indices] >= threshold).astype(int)
        for name, value in compute_metrics(sampled_true, sampled_predicted).items():
            collected[name].append(value)

    return {name: np.asarray(values) for name, values in collected.items()}


def main():
    predictions = pd.read_csv(TEST_PREDICTIONS_CSV_PATH, encoding="utf-8")
    true_labels = predictions["true_label"].to_numpy()
    probabilities = predictions["prob_fake"].to_numpy()

    metrics = json.loads(METRICS_JSON_PATH.read_text(encoding="utf-8"))
    threshold = float(metrics["test"]["threshold"])
    point_estimate = compute_metrics(
        true_labels, (probabilities >= threshold).astype(int)
    )

    bootstrapped = bootstrap_metrics(
        true_labels, probabilities, threshold, BOOTSTRAP_ITERATIONS, HAND_CALC_SEED
    )

    print("=" * 68)
    print(f"BOOTSTRAP 95% - {BOOTSTRAP_ITERATIONS} lan lap, SEED={HAND_CALC_SEED}")
    print("=" * 68)
    print(f"    nguon: {TEST_PREDICTIONS_CSV_PATH.name}, nguong={threshold:.4f}")

    summary = {}
    for name, values in bootstrapped.items():
        lower, upper = np.percentile(values, [2.5, 97.5])
        summary[name] = {
            "point": round(point_estimate[name], 4),
            "lower_95": round(float(lower), 4),
            "upper_95": round(float(upper), 4),
            "mean": round(float(values.mean()), 4),
            "std": round(float(values.std(ddof=1)), 4),
            "iterations_used": int(values.size),
        }
        print(f"    {name:<9}: {point_estimate[name]:.4f} "
              f"CI95=[{lower:.4f}; {upper:.4f}] mean={values.mean():.4f} std={values.std(ddof=1):.4f}")

    output = {
        "seed": HAND_CALC_SEED,
        "group_code": HAND_CALC_SEED - 2026,
        "threshold": threshold,
        "sample_count": int(len(true_labels)),
        "iterations": BOOTSTRAP_ITERATIONS,
        "metrics": summary,
    }
    save_text_with_warning(
        BOOTSTRAP_CI_PATH, json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    )
    print(f"\nGhi: {BOOTSTRAP_CI_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
