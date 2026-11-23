r"""
Dọn rác bộ nhớ do chính Python/agent sinh ra, với phạm vi khoá chặt.

Chỉ xử lý hai thư mục bytecode cache do Python tạo ra:
- MaNGuon/__pycache__
- KetQuaChay/__pycache__


Chạy tay: python MaNGuon\don_rac.py
Xem trước không xoá: python MaNGuon\don_rac.py --dry-run

Ba script tự cài mới đã đăng ký hàm này bằng atexit nên tự dọn sau mỗi lần
chạy. Có thể gọi clean_generated_cache() từ script khác nếu cần.
"""

import sys
from pathlib import Path

# Không tạo thêm .pyc ngay trong lúc dọn. Đặt trước khi import config để cả
# config.py cũng không bị ghi bytecode mới.
sys.dont_write_bytecode = True

from config import RESULTS_DIR  # noqa: E402

MODULE_DIR = Path(__file__).resolve().parent
ALLOWED_CACHE_DIRS = (MODULE_DIR / "__pycache__", RESULTS_DIR / "__pycache__")
ALLOWED_SUFFIXES = {".pyc", ".pyo"}


def clean_generated_cache(apply=True, verbose=False):
    """
    Xoá bytecode cache trong phạm vi cho phép.

    Trả về (số tệp đã xoá hoặc sẽ xoá, số thư mục đã dọn, danh sách tệp giữ lại).
    Khi apply=False chỉ liệt kê, không ghi/xoá gì.
    """
    removed_files = 0
    removed_dirs = 0
    kept_items = []

    for directory in ALLOWED_CACHE_DIRS:
        if not directory.is_dir():
            continue

        kept_here = []
        for item in sorted(directory.iterdir()):
            if item.is_file() and item.suffix in ALLOWED_SUFFIXES:
                if apply:
                    try:
                        item.unlink()
                    except OSError:
                        kept_here.append(str(item))
                        continue
                removed_files += 1
            else:
                kept_here.append(str(item))

        kept_items.extend(kept_here)
        if kept_here:
            continue
        if apply:
            try:
                directory.rmdir()
            except OSError:
                # Windows/OneDrive có thể giữ thư mục rỗng vài giây. Bên trong
                # đã sạch bytecode rồi, nên cứ tính là dọn xong, không báo là
                # dữ liệu bị giữ lại.
                continue
        removed_dirs += 1

    if verbose:
        print(f"[DON RAC] tệp .pyc/.pyo: {removed_files}, thư mục cache: {removed_dirs}")
        for item in kept_items:
            print(f"[GIỮ LẠI] {item}")

    return removed_files, removed_dirs, kept_items


def auto_cleanup():
    """Dùng cho atexit: im lặng và không làm script chính lỗi vì lỗi dọn rác."""
    try:
        clean_generated_cache(apply=True, verbose=False)
    except OSError:
        pass


def main():
    apply = "--dry-run" not in sys.argv
    removed_files, removed_dirs, kept_items = clean_generated_cache(
        apply=apply, verbose=True
    )
    print("Che do: " + ("XOA THAT" if apply else "XEM TRUOC, KHONG XOA"))
    print(f"Tong: {removed_files} tep bytecode, {removed_dirs} thu muc cache")
    for item in kept_items:
        print(f"Giữ lại (khong nam trong pham vi xoa): {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
