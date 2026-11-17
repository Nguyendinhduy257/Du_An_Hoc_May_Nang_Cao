# Chỉ dẫn mã nguồn

Các file Python đều nằm phẳng trong thư mục này. Mỗi file import trực tiếp
`config`, `db`, `classify`... nên giữ nguyên cách bố trí đó; nếu chuyển vào thư
mục con thì phải sửa import, đường dẫn trong `run_all.py`, BAT và README.

Chạy mọi lệnh từ thư mục gốc dự án, ví dụ `python MaNguon\api_server.py`.

| Nhóm | File | Việc làm |
|---|---|---|
| Nền tảng | `config.py`, `db.py`, `file_safety.py` | Tham số dùng chung, truy cập PostgreSQL, ghi file an toàn |
| Dữ liệu và đặc trưng | `data.py`, `features.py`, `classify.py`, `translate.py` | Đọc/chia tập, TF-IDF, luật phân nhóm, dịch + cache |
| Mô hình chính | `train_baseline.py`, `compare_baselines.py`, `threshold_cost_table.py` | Huấn luyện LR, so baseline, quét ngưỡng theo chi phí |
| Minh hoạ giáo trình | `from_scratch.py`, `measure_translation_bias.py`, `audit_heuristics.py` | GD/Perceptron/MLP cài tay, đo lệch dịch, kiểm chứng luật |
| Cơ sở dữ liệu | `load_db.py`, `export_web_data.py`, `backup_db.py`, `restore_db.py`, `cleanup_uploads.py` | Nạp, xuất web, sao lưu/phục hồi, dọn upload cũ |
| Web và điều phối | `api_server.py`, `run_all.py` | API + phục vụ web, chạy lại pipeline theo cache |
