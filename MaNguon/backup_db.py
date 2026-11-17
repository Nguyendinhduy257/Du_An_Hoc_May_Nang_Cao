r"""
Sao lưu toàn bộ database của đồ án ra một file .dump duy nhất.

Chạy: python MaNguon\backup_db.py
Kết quả: SaoLuu/fakereview_YYYYmmdd_HHMMSS.dump

pg_dump chạy bên trong container để dùng đúng phiên bản với server, không phụ
thuộc máy Windows có cài pg_dump hay không. Định dạng custom (-Fc) nhỏ hơn
file SQL văn bản và restore_db.py đọc lại được.
"""

import subprocess
from datetime import datetime

import db
from config import BACKUP_DIR, DB_CONTAINER_NAME


def run_docker(arguments):
    """
    Chạy một lệnh docker và trả về stdout dạng bytes.

    Gom vào một hàm để mọi lỗi docker được báo cùng một kiểu, thay vì mỗi chỗ
    gọi tự xử lý một khác.
    """
    result = subprocess.run(
        ["docker"] + arguments,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if result.returncode != 0:
        error_text = result.stderr.decode("utf-8", errors="replace").strip()
        raise SystemExit(f"Lệnh docker thất bại: {error_text}")

    return result.stdout


def main():
    settings = db.get_settings()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # Tên file có thời gian nên hai lần sao lưu không ghi đè nhau.
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"fakereview_{timestamp}.dump"

    print(f"Đang sao lưu database {settings['database']} ...")

    dump_bytes = run_docker(
        [
            "exec",
            DB_CONTAINER_NAME,
            "pg_dump",
            "-U",
            settings["user"],
            "-d",
            settings["database"],
            "--format=custom",
        ]
    )

    backup_path.write_bytes(dump_bytes)

    size_megabytes = len(dump_bytes) / (1024 * 1024)
    print(f"Đã ghi       : {backup_path}")
    print(f"Kích thước   : {size_megabytes:.2f} MB")
    print("Phục hồi thử : python MaNguon\\restore_db.py --file " + str(backup_path))


if __name__ == "__main__":
    main()
