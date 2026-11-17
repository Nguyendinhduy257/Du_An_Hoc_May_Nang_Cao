r"""
Phục hồi một file sao lưu .dump vào database trong container.

Chạy:
    python MaNguon\restore_db.py --file SaoLuu\fakereview_seed.dump --database fakereview --allow-production
    python MaNguon\restore_db.py --file <file> --database fakereview_restore_check

Mặc định chỉ phục hồi vào database tạm vì thao tác này ghi đè toàn bộ dữ liệu
đích; muốn đụng database chính phải thêm cờ --allow-production. Database đích
được xoá rồi tạo lại trước khi restore để tránh lỗi trùng khoá.
"""

import argparse
import subprocess
from pathlib import Path

import db
from config import DB_CONTAINER_NAME, DB_RESTORE_SCRATCH_NAME


def run_docker(arguments, input_bytes=None):
    """
    Chạy một lệnh docker; trả stdout dạng bytes.

    input_bytes khác None nghĩa là nội dung được đẩy vào stdin của lệnh.
    Dùng stdin thay vì docker cp để không để lại file tạm trong container.
    """
    result = subprocess.run(
        ["docker"] + arguments,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if result.returncode != 0:
        error_text = result.stderr.decode("utf-8", errors="replace").strip()
        raise SystemExit(f"Lệnh docker thất bại: {error_text}")

    return result.stdout


def main():
    parser = argparse.ArgumentParser(
        description="Phục hồi file sao lưu PostgreSQL vào một database."
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Đường dẫn file .dump cần phục hồi.",
    )
    parser.add_argument(
        "--database",
        default=DB_RESTORE_SCRATCH_NAME,
        help="Tên database đích (mặc định: database tạm để kiểm tra).",
    )
    parser.add_argument(
        "--allow-production",
        action="store_true",
        help="Cho phép ghi đè database chính. Chỉ dùng khi thật sự cần.",
    )
    arguments = parser.parse_args()

    backup_path = Path(arguments.file)
    if not backup_path.is_absolute():
        backup_path = (Path.cwd() / backup_path).resolve()

    if not backup_path.exists():
        raise SystemExit(f"Không thấy file sao lưu: {backup_path}")

    settings = db.get_settings()
    production_name = settings["database"]
    target_name = arguments.database

    # Chốt an toàn: không để một lệnh gõ nhầm xóa dữ liệu thật.
    if target_name == production_name and not arguments.allow_production:
        raise SystemExit(
            "Từ chối phục hồi vào database chính "
            f"({production_name}). Thêm --allow-production nếu chắc chắn."
        )

    print(f"Đang tạo lại database đích: {target_name} ...")
    run_docker(
        [
            "exec",
            DB_CONTAINER_NAME,
            "dropdb",
            "-U",
            settings["user"],
            "--if-exists",
            target_name,
        ]
    )
    run_docker(
        ["exec", DB_CONTAINER_NAME, "createdb", "-U", settings["user"], target_name]
    )

    print("Đang phục hồi dữ liệu ...")
    run_docker(
        [
            "exec",
            "-i",
            DB_CONTAINER_NAME,
            "pg_restore",
            "-U",
            settings["user"],
            "-d",
            target_name,
        ],
        input_bytes=backup_path.read_bytes(),
    )

    # Đếm lại ngay trong database đích để chứng minh phục hồi thành công,
    # thay vì chỉ tin vào mã thoát của pg_restore.
    print("Kiểm tra số dòng bảng reviews ...")
    count_output = run_docker(
        [
            "exec",
            DB_CONTAINER_NAME,
            "psql",
            "-U",
            settings["user"],
            "-d",
            target_name,
            "-t",
            "-A",
            "-c",
            "SELECT count(*) FROM reviews;",
        ]
    )
    row_count = count_output.decode("utf-8", errors="replace").strip()

    print(f"Xong. Database {target_name} có {row_count} dòng review.")
    print("Database tạm được giữ lại để kiểm tra; xóa bằng:")
    print(f"    docker exec {DB_CONTAINER_NAME} dropdb -U {settings['user']} {target_name}")


if __name__ == "__main__":
    main()
