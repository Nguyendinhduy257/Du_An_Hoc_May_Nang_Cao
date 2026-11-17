r"""
Đo chất lượng các luật phân nhóm bằng nhãn thật (máy sinh / người viết).

Đây là bước tự kiểm tra, không phải thuật toán thứ hai. Nó trả lời câu hỏi
trung thực hơn là "model bắt bot chính xác bao nhiêu": trong số review bị xếp
vào nhóm nghi bot/boost, bao nhiêu phần trăm thật sự do máy sinh? Dataset
không có nhãn bot nên không được báo cáo con số đó như một kết quả phân loại.

Chạy: python MaNguon\audit_heuristics.py
Kết quả: KetQuaChay/heuristic_audit.json
"""

import json
from datetime import datetime, timezone

import db
from config import CATEGORY_ORDER, HEURISTIC_AUDIT_JSON_PATH
from file_safety import save_text_with_warning


def rate(part, whole):
    """Tỷ lệ an toàn: trả 0.0 khi mẫu số bằng 0 thay vì chia cho 0."""
    if whole == 0:
        return 0.0
    return round(part / whole, 4)


def audit_category(reviews, category_id):
    """
    Thống kê một nhóm: bao nhiêu review, bao nhiêu thật/giả theo nhãn gốc.

    fake_rate = tỷ lệ review máy sinh (CG, nhãn 1) trong nhóm.
    Với nhóm "genuine", fake_rate càng thấp càng tốt.
    Với nhóm "suspected_fake", fake_rate càng cao càng tốt.
    """
    in_category = [row for row in reviews if row["category"] == category_id]
    true_fake = sum(1 for row in in_category if int(row["true_label"]) == 1)
    true_real = len(in_category) - true_fake

    return {
        "count": len(in_category),
        "true_fake": true_fake,
        "true_real": true_real,
        "fake_rate": rate(true_fake, len(in_category)),
    }


def build_audit(reviews, model_run):
    """Tính toàn bộ số liệu kiểm chứng luật."""
    total = len(reviews)
    total_fake = sum(1 for row in reviews if int(row["true_label"]) == 1)
    total_real = total - total_fake

    categories = {}
    for category_id in CATEGORY_ORDER:
        categories[category_id] = audit_category(reviews, category_id)

    useful_reviews = [row for row in reviews if bool(row["is_useful"])]
    useful_real = sum(1 for row in useful_reviews if int(row["true_label"]) == 0)
    useful_fake = len(useful_reviews) - useful_real

    # Độ "nâng" (lift) của luật nghi bot/boost: tỷ lệ máy sinh trong nhóm chia
    # cho tỷ lệ máy sinh của toàn tập. Lift > 1 nghĩa là luật tập trung được
    # nhiều review máy sinh hơn mức trung bình - đó là bằng chứng luật có ích.
    bot_rate = categories["suspected_bot_boost"]["fake_rate"]
    base_rate = rate(total_fake, total)
    if base_rate == 0:
        bot_lift = None
    else:
        bot_lift = round(bot_rate / base_rate, 4)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_run_id": model_run["id"],
        "threshold": round(float(model_run["threshold"]), 2),
        "dataset_split": "test",
        "rows": total,
        "label_balance": {
            "true_fake_cg": total_fake,
            "true_real_or": total_real,
            "fake_rate": rate(total_fake, total),
        },
        "categories": categories,
        "useful_set": {
            "count": len(useful_reviews),
            "true_real": useful_real,
            "true_fake": useful_fake,
            # precision_real: trong các review được giữ lại, bao nhiêu % là thật.
            "precision_real": rate(useful_real, len(useful_reviews)),
            # recall_real: giữ được bao nhiêu % tổng số review thật của tập test.
            "recall_real": rate(useful_real, total_real),
            "lost_real": total_real - useful_real,
        },
        "bot_boost_lift": bot_lift,
        "notes": [
            "Nhóm 'genuine', 'suspected_fake', 'suspected_bot_boost' là luật hiển thị, "
            "không phải nhãn ground truth.",
            "Dataset gốc chỉ có nhãn CG (máy sinh) và OR (người viết), "
            "không có nhãn bot/boost/spam.",
            "useful_set.precision_real là tỷ lệ review thật trong tập hữu ích; "
            "đây là con số nên dùng khi báo cáo, thay vì nói 'độ chính xác phát hiện bot'.",
        ],
    }


def main():
    if not db.is_available():
        raise SystemExit(
            "Không kết nối được PostgreSQL. Hãy chạy: docker compose up -d"
        )

    connection = db.connect()
    try:
        model_run = db.get_latest_model_run(connection)
        if model_run is None:
            raise SystemExit("Chưa có dữ liệu. Hãy chạy: python MaNguon\\load_db.py")

        reviews = db.fetch_split_reviews(connection, "test", model_run["id"])
    finally:
        connection.close()

    audit = build_audit(reviews, model_run)

    json_text = json.dumps(audit, ensure_ascii=False, indent=2)
    save_text_with_warning(HEURISTIC_AUDIT_JSON_PATH, json_text)

    print("\n=== KIỂM CHỨNG LUẬT PHÂN NHÓM (tập test) ===")
    print(f"Tổng review       : {audit['rows']}")
    print(f"Nhãn giả (CG)     : {audit['label_balance']['true_fake_cg']}")
    print(f"Nhãn thật (OR)    : {audit['label_balance']['true_real_or']}")
    print("\nTheo nhóm hiển thị:")
    for category_id, stats in audit["categories"].items():
        print(
            f"  {category_id:<20} n={stats['count']:<5} "
            f"thật={stats['true_real']:<5} giả={stats['true_fake']:<5} "
            f"tỷ lệ giả={stats['fake_rate']}"
        )

    useful = audit["useful_set"]
    print("\nTập hữu ích (genuine + đáng tin):")
    print(f"  Số review giữ lại : {useful['count']}")
    print(f"  Thật / Giả        : {useful['true_real']} / {useful['true_fake']}")
    print(f"  Độ chính xác thật : {useful['precision_real']}")
    print(f"  Giữ được review thật: {useful['recall_real']}")
    print(f"  Lift nghi bot/boost: {audit['bot_boost_lift']}")
    print(f"\nFile kết quả: {HEURISTIC_AUDIT_JSON_PATH}")


if __name__ == "__main__":
    main()
