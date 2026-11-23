r"""
Hằng số riêng cho phần tính tay (Phụ lục A) và bootstrap (B9.1).

Để riêng khỏi config.py vì config.py nằm trong fingerprint của nhiều bước
trong run_all.py: chỉ thêm một hằng số ở đó cũng làm cache của các bước đó
thành cũ. File này không ai trong pipeline đọc, nên thêm đổi ở đây không làm
thay đổi dữ liệu hay kết quả đã lưu.

Theo đề 004295, mọi phép ngẫu nhiên khi chọn mẫu tính tay dùng SEED = 2026 + G.
Đổi GROUP_CODE thành mã nhóm thật trước khi lấy số cuối cho báo cáo.
"""

# Mã nhóm G của nhóm; ví dụ nhóm 07 thì đặt 7.
GROUP_CODE = 1

# Seed bắt buộc của đề cho chọn mẫu tính tay và bootstrap.
HAND_CALC_SEED = 2026 + GROUP_CODE

# Số lần lặp bootstrap tối thiểu cho khoảng tin cậy 95% của chỉ số chính.
BOOTSTRAP_ITERATIONS = 1000
