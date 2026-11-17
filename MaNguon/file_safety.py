r"""
Ghi file an toàn: cảnh báo khi ghi đè một file đã có nhưng nội dung khác.

Nhận đường dẫn đích và nội dung dạng chuỗi, ghi bằng UTF-8 rồi in trạng thái
ra màn hình.
"""

import hashlib
from pathlib import Path


def sha256_of_bytes(data):
    """Trả về chuỗi hex SHA-256 của dữ liệu nhị phân."""
    return hashlib.sha256(data).hexdigest()


def normalize_line_endings(text):
    """Chuẩn hóa xuống dòng để so sánh nội dung logic giữa Windows và Linux."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def save_text_with_warning(path, text):
    """
    Ghi text (UTF-8) xuống path, in cảnh báo nếu ghi đè nội dung khác.

    Trả về một trong ba trạng thái:
      "created"     - file chưa tồn tại, đã tạo mới.
      "unchanged"   - file tồn tại và nội dung giống hệt, không ghi lại.
      "overwritten" - file tồn tại nhưng nội dung khác, đã ghi đè (có cảnh báo).
    """
    path = Path(path)
    new_bytes = text.encode("utf-8")

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(new_bytes)
        print(f"[TẠO MỚI] {path}")
        return "created"

    old_bytes = path.read_bytes()

    # So sánh nội dung đã chuẩn hóa vì cùng một dữ liệu nhưng Windows ghi
    # xuống dòng \r\n còn Linux ghi \n. So byte thô sẽ báo động giả.
    try:
        old_text = old_bytes.decode("utf-8")
        same_content = normalize_line_endings(old_text) == normalize_line_endings(text)
    except UnicodeDecodeError:
        # File cũ không phải UTF-8 (có thể là file nhị phân) -> coi là khác.
        same_content = False

    if same_content:
        # Không ghi lại vì nội dung y hệt, ghi lại chỉ làm mới thời gian sửa
        # đổi và gây nhiễu dấu vết kiểm toán.
        print(f"[KHÔNG ĐỔI] {path} (bỏ qua ghi)")
        return "unchanged"

    # Cảnh báo vì ghi đè có thể làm mất split cũ hoặc kết quả cũ.
    # In đủ thông tin để người dùng đối chiếu trước khi tin kết quả mới.
    old_hash = sha256_of_bytes(old_bytes)
    new_hash = sha256_of_bytes(new_bytes)
    print(f"[CẢNH BÁO GHI ĐÈ] {path}")
    print(f"    cũ : {len(old_bytes):>8} bytes | sha256={old_hash[:12]}")
    print(f"    mới: {len(new_bytes):>8} bytes | sha256={new_hash[:12]}")

    path.write_bytes(new_bytes)
    return "overwritten"


def save_bytes_with_warning(path, data):
    """
    Ghi dữ liệu NHỊ PHÂN xuống path, cảnh báo nếu ghi đè nội dung khác.

    Cần hàm riêng vì model lưu bằng pickle là bytes, không phải chuỗi UTF-8,
    nên không dùng được save_text_with_warning (hàm đó decode/encode văn bản).

    Trả về: "created" | "unchanged" | "overwritten".
    """
    path = Path(path)

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        print(f"[TẠO MỚI] {path}")
        return "created"

    old_bytes = path.read_bytes()
    old_hash = sha256_of_bytes(old_bytes)
    new_hash = sha256_of_bytes(data)

    if old_hash == new_hash:
        print(f"[KHÔNG ĐỔI] {path} (bỏ qua ghi)")
        return "unchanged"

    print(f"[CẢNH BÁO GHI ĐÈ] {path}")
    print(f"    cũ : {len(old_bytes):>8} bytes | sha256={old_hash[:12]}")
    print(f"    mới: {len(data):>8} bytes | sha256={new_hash[:12]}")

    path.write_bytes(data)
    return "overwritten"
