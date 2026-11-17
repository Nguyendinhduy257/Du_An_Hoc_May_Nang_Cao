r"""
Xóa các lô review tải lên đã cũ để CSDL không phình dần.

Chạy tay:
    python MaNguon\cleanup_uploads.py
    python MaNguon\cleanup_uploads.py --days 14
    python MaNguon\cleanup_uploads.py --days 0 --dry-run

Script chỉ đụng dữ liệu upload; review demo test/val luôn được giữ nguyên.
Dùng --dry-run trước khi đặt lịch để xem sẽ xóa bao nhiêu dòng.
"""

import argparse

import db
from config import UPLOAD_RETENTION_DAYS


def main():
    parser = argparse.ArgumentParser(
        description="Xóa review tải lên cũ hơn số ngày quy định."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=UPLOAD_RETENTION_DAYS,
        help=f"Giữ dữ liệu bao nhiêu ngày (mặc định {UPLOAD_RETENTION_DAYS}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chỉ đếm, không xóa.",
    )
    args = parser.parse_args()

    if args.days < 0:
        parser.error("--days phải lớn hơn hoặc bằng 0.")

    connection = db.connect()
    try:
        result = db.delete_old_uploads(
            connection, args.days, dry_run=args.dry_run
        )
    finally:
        connection.close()

    print(f"Mốc cắt   : {result['cutoff']:%Y-%m-%d %H:%M:%S %Z}")
    print(f"Giữ       : {result['retention_days']} ngày")
    print(f"Lô upload : {result['batches']}")
    print(f"Review    : {result['reviews']}")
    print(f"Review mồ côi: {result['orphan_reviews']}")

    if args.dry_run:
        print("Chế độ thử: KHÔNG xóa dòng nào.")
    else:
        print("Đã xóa xong.")


if __name__ == "__main__":
    main()
