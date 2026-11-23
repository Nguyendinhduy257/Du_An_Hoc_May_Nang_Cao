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

## Gắn kết với Phân tích và trực quan hóa dữ liệu 004759

`ve_bieu_do_chan_doan.py` vẽ bảy hình trong `KetQuaChay/figures/`. Histogram và boxplot xác suất theo nhãn bám 004759 Chương 1 slide 14-16 và Chương 2 slide 17; slide 23 của Chương 2 nêu rõ Matplotlib là công cụ của học phần. Ma trận nhầm dạng nhiệt, ROC/AUC, Precision-Recall, trọng số TF-IDF, đường cong học và biên quyết định 2 chiều bám đúng sáu biểu đồ 004759 Chương 4 slide 52-54. Danh sách sáu biểu đồ nằm ở slide 53; CLO4/CLO6 và Rubric R2 ghi ở trang đầu của PDF Chương 4.

Phần giảm chiều trong `pca_lda_tu_cai.py` khớp 004759 Chương 2 mục 2.3-2.4 về tích hợp, chuyển hóa và giảm chiều dữ liệu. Chương 3 của 004759 (CLO3/CLO6, Rubric R1) không có đối tượng tương ứng ở đây: bước kiểm tra trùng lặp trong `data.py` là so chuỗi đã chuẩn hóa, không phải khai phá luật kết hợp.

PDF `Chuong4_DacTrung_4.1-4.3_70slides.pdf` nằm cùng thư mục tài liệu 004759 nhưng thực chất là tài liệu 004295 Chương 4, nên không được trích làm 004759 Chương 4.
