r"""
Chọn ngưỡng quyết định theo chi phí thay vì chỉ tối đa F1, đúng yêu cầu
Ch3 tr. 48. Ngưỡng được quét trên tập validation.

Chạy: python MaNguon\threshold_cost_table.py
Đọc: KetQuaChay/val_predictions.csv và baseline_metrics.json.
Ghi: KetQuaChay/threshold_cost_table.json và bảng trên màn hình.

Quét trên validation chứ không phải test vì ngưỡng là một tham số của mô hình;
quét trên test thì test không còn là dữ liệu chưa từng thấy và mọi con số báo
cáo sẽ lạc quan giả tạo.

F1 coi loại nhầm (dương tính giả) và bỏ lọt (âm tính giả) nặng như nhau.
Trong bài toán lọc review giả, bỏ lọt một review giả thường tốn hơn loại nhầm
một review thật, nên bảng chi phí biến giả định đó thành con số. Hai hằng số
COST_FALSE_POSITIVE và COST_FALSE_NEGATIVE trong MaNguon/config.py là giả định
của đồ án, không phải số liệu kinh doanh thật.
"""

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from config import (
    COST_FALSE_NEGATIVE,
    COST_FALSE_POSITIVE,
    METRICS_JSON_PATH,
    THRESHOLD_COST_JSON_PATH,
    THRESHOLD_DEFAULT,
    THRESHOLD_MAX,
    THRESHOLD_MIN,
    THRESHOLD_STEP,
    VAL_PREDICTIONS_CSV_PATH,
)

# Ngưỡng in ra màn hình để bảng không quá dài; JSON vẫn giữ đủ mọi ngưỡng.
PRINT_STEP = 0.05


def build_thresholds():
    """Danh sách ngưỡng từ THRESHOLD_MIN đến THRESHOLD_MAX theo THRESHOLD_STEP."""
    count = int(round((THRESHOLD_MAX - THRESHOLD_MIN) / THRESHOLD_STEP)) + 1
    return [round(THRESHOLD_MIN + index * THRESHOLD_STEP, 2) for index in range(count)]


def evaluate_threshold(true_labels, probabilities, threshold):
    """Tính ma trận nhầm lẫn, F1 và tổng chi phí tại một ngưỡng."""
    predicted = (probabilities >= threshold).astype(int)

    true_positive = int(np.sum((predicted == 1) & (true_labels == 1)))
    false_positive = int(np.sum((predicted == 1) & (true_labels == 0)))
    false_negative = int(np.sum((predicted == 0) & (true_labels == 1)))
    true_negative = int(np.sum((predicted == 0) & (true_labels == 0)))

    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive > 0
        else 0.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative > 0
        else 0.0
    )
    f1 = 2 * precision * recall / (precision + recall) if precision + recall > 0 else 0.0

    # Cộng chi phí thay vì tối ưu riêng precision/recall vì đây là hàm mất mát
    # thật của quyết định, có trọng số cho từng loại sai.
    total_cost = COST_FALSE_POSITIVE * false_positive + COST_FALSE_NEGATIVE * false_negative

    return {
        "threshold": round(float(threshold), 2),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "true_negative": true_negative,
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1": round(float(f1), 4),
        "cost": int(total_cost),
    }


def find_best(rows, key, prefer_high_threshold):
    """
    Tìm dòng tốt nhất theo một khóa.

    Cần quy tắc hoà vì nhiều ngưỡng liền nhau có thể cùng chi phí hoặc cùng
    F1. Khi hoà, chọn ngưỡng cao hơn nếu prefer_high_threshold=True, nghĩa là
    ít review bị gắn cờ hơn, giảm việc kiểm tra tay.
    """
    if key == "cost":
        best_value = min(row[key] for row in rows)
    else:
        best_value = max(row[key] for row in rows)

    candidates = [row for row in rows if row[key] == best_value]

    if prefer_high_threshold:
        return max(candidates, key=lambda row: row["threshold"])
    return min(candidates, key=lambda row: row["threshold"])


def row_at(rows, threshold):
    """Lấy dòng đúng ngưỡng; báo lỗi rõ nếu ngưỡng nằm ngoài lưới quét."""
    for row in rows:
        if abs(row["threshold"] - threshold) < 1e-9:
            return row
    raise SystemExit(
        f"LỖI: ngưỡng {threshold} không có trong lưới quét "
        f"({THRESHOLD_MIN}..{THRESHOLD_MAX} bước {THRESHOLD_STEP})."
    )


def main():
    predictions = pd.read_csv(VAL_PREDICTIONS_CSV_PATH, encoding="utf-8")
    true_labels = predictions["true_label"].to_numpy()
    probabilities = predictions["prob_fake"].to_numpy()

    with METRICS_JSON_PATH.open(encoding="utf-8") as file:
        main_metrics = json.load(file)

    selected_threshold = float(main_metrics["validation"]["best_threshold"])
    f1_threshold = selected_threshold

    rows = [
        evaluate_threshold(true_labels, probabilities, threshold)
        for threshold in build_thresholds()
    ]

    best_cost = find_best(rows, "cost", prefer_high_threshold=True)
    best_f1 = find_best(rows, "f1", prefer_high_threshold=True)

    selected_row = row_at(rows, selected_threshold)
    default_row = row_at(rows, THRESHOLD_DEFAULT)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "source": "KetQuaChay/val_predictions.csv",
            "rows": int(len(predictions)),
            "label_counts": {
                "real_0": int(np.sum(true_labels == 0)),
                "fake_1": int(np.sum(true_labels == 1)),
            },
        },
        "cost_assumption": {
            "cost_false_positive": COST_FALSE_POSITIVE,
            "cost_false_negative": COST_FALSE_NEGATIVE,
            "note": "Giả định của đồ án, không phải số liệu kinh doanh thật.",
        },
        "scan": {
            "threshold_min": THRESHOLD_MIN,
            "threshold_max": THRESHOLD_MAX,
            "threshold_step": THRESHOLD_STEP,
            "points": len(rows),
        },
        "best_by_cost": best_cost,
        "best_by_f1": best_f1,
        "f1_selected_threshold": selected_row,
        "default_threshold": default_row,
        "savings_versus_default": {
            "cost_at_default": default_row["cost"],
            "cost_at_best": best_cost["cost"],
            "saved": default_row["cost"] - best_cost["cost"],
            "saved_percent": round(
                100.0 * (default_row["cost"] - best_cost["cost"]) / default_row["cost"], 2
            )
            if default_row["cost"] > 0
            else 0.0,
        },
        "savings_at_selected_threshold": {
            "cost_at_default": default_row["cost"],
            "cost_at_selected": selected_row["cost"],
            "saved": default_row["cost"] - selected_row["cost"],
            "saved_percent": round(
                100.0 * (default_row["cost"] - selected_row["cost"]) / default_row["cost"], 2
            )
            if default_row["cost"] > 0
            else 0.0,
        },
        "thresholds": rows,
    }

    THRESHOLD_COST_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    THRESHOLD_COST_JSON_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=== BẢNG CHỌN NGƯỠNG THEO CHI PHÍ (tập validation) ===")
    print(
        f"Chi phí: FP = {COST_FALSE_POSITIVE}, FN = {COST_FALSE_NEGATIVE} "
        f"(giả định của đồ án)"
    )
    print(f"Số dòng: {len(predictions)}  |  thật = {report['dataset']['label_counts']['real_0']}"
          f"  |  giả = {report['dataset']['label_counts']['fake_1']}")
    print()
    print(f"{'Ngưỡng':>7}{'TP':>7}{'FP':>7}{'FN':>7}{'Prec':>8}{'Rec':>8}{'F1':>8}{'Chi phí':>10}")

    printed_thresholds = set()
    for row in rows:
        is_print_step = abs(row["threshold"] / PRINT_STEP - round(row["threshold"] / PRINT_STEP)) < 1e-9
        if (
            is_print_step
            or row["threshold"] == best_cost["threshold"]
            or row["threshold"] == best_f1["threshold"]
            or row["threshold"] == selected_threshold
            or row["threshold"] == THRESHOLD_DEFAULT
        ):
            printed_thresholds.add(row["threshold"])
            print(
                f"{row['threshold']:>7.2f}{row['true_positive']:>7}{row['false_positive']:>7}"
                f"{row['false_negative']:>7}{row['precision']:>8.4f}{row['recall']:>8.4f}"
                f"{row['f1']:>8.4f}{row['cost']:>10}"
            )

    print()
    print("Kết luận:")
    print(
        f"  - Tối thiểu chi phí : ngưỡng {best_cost['threshold']:.2f}, "
        f"chi phí {best_cost['cost']}, F1 {best_cost['f1']:.4f}"
    )
    print(
        f"  - Tối đa F1         : ngưỡng {best_f1['threshold']:.2f}, "
        f"chi phí {best_f1['cost']}, F1 {best_f1['f1']:.4f}"
    )
    print(
        f"  - Ngưỡng đang dùng  : {selected_threshold:.2f}, "
        f"chi phí {selected_row['cost']}, F1 {selected_row['f1']:.4f}"
    )
    print(
        f"  - Ngưỡng mặc định 0.5: chi phí {default_row['cost']}, "
        f"F1 {default_row['f1']:.4f}"
    )
    print(
        f"  - Tiết kiệm của ngưỡng tối thiểu chi phí so với 0.5: "
        f"{report['savings_versus_default']['saved']} "
        f"({report['savings_versus_default']['saved_percent']}%)"
    )
    print(
        f"  - Tiết kiệm của ngưỡng đang dùng {selected_threshold:.2f} so với 0.5: "
        f"{report['savings_at_selected_threshold']['saved']} "
        f"({report['savings_at_selected_threshold']['saved_percent']}%)"
    )
    print(f"\nĐã ghi: {THRESHOLD_COST_JSON_PATH}")

    # Ngưỡng đang dùng phải trùng ngưỡng đã chọn theo F1; nếu lệch thì file
    # metrics và file dự đoán không còn đồng bộ, cần dừng để tránh báo cáo sai.
    if abs(f1_threshold - selected_row["threshold"]) > 1e-9:
        raise SystemExit("LỖI: ngưỡng trong baseline_metrics.json không khớp lưới quét.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
