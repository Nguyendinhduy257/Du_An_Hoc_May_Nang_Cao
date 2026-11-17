# Cấu trúc thư mục dự án

Đường dẫn: `Du_An_Hoc_May_Nang_Cao\TaiLieu\CAU_TRUC_THU_MUC.md`

Tài liệu này giải thích **mỗi thư mục dùng để làm gì**, **ai ghi vào đó**, và
**có được sửa tay hay không**. Mọi đường dẫn trong tài liệu đều tính từ thư mục
gốc `Du_An_Hoc_May_Nang_Cao\`.

## 1. Sơ đồ tổng thể

```
Du_An_Hoc_May_Nang_Cao\
├── MaNguon\              mã Python (chạy bằng python MaNguon\<file>.py)
├── Notebook\             1 notebook minh hoạ công thức giáo trình
├── DuLieuDeHoc\
│   ├── DuLieuTho\        dữ liệu gốc, chỉ đọc
│   ├── DuLieuDaXuLy\     train / val / test sau khi chia
│   └── README.md         nguồn, giấy phép, mô tả cột
├── DuLieuDemo\           dữ liệu cho web: 2 file .js máy sinh + 4 .csv mẫu
├── Web\                  giao diện: index.html, style.css, app.js
├── MoHinh\               model đã huấn luyện (.pkl)
├── KetQuaChay\           kết quả chạy thuật toán (.json, .csv)
├── ThuMucChienKhai\      cấu hình chạy: docker-compose.yml, .env, db\schema.sql
├── ThuMucKhoiChay\       3 file .bat bấm đúp để chạy
├── TaiLieu\              tài liệu cấu trúc và hướng dẫn đẩy repo
├── SaoLuu\               file sao lưu database (.dump)
├── README.md             hướng dẫn triển khai nhanh
└── requirements.txt      phiên bản thư viện được ghim
```

## 2. Chi tiết từng thư mục

### `MaNguon\` — mã nguồn Python

Tất cả mã chạy được nằm ở đây, không chia thư mục con. Mỗi file là một việc.
`config.py` là nơi **duy nhất** khai báo đường dẫn và tham số; các file khác
import từ đó chứ không tự ghép đường dẫn.

Chạy: `python MaNguon\<tên_file>.py` từ thư mục gốc. Không dùng
`python -m MaNguon.<tên_file>` vì các module dùng `from config import ...`.

### `Notebook\` — minh hoạ công thức

`from_scratch_gd_lr.ipynb` cài tay gradient descent, momentum, SGD, sigmoid +
BCE, Perceptron, MLP để đối chiếu với giáo trình. Notebook **không** tạo ra model
dùng trong web và không tái tạo được F1 của model chính.

### `DuLieuDeHoc\DuLieuTho\` — dữ liệu gốc (chỉ đọc)

Không sửa, không xoá, không ghi đè. Giữ nguyên để còn đối chiếu SHA256 và chạy
lại từ đầu. Gồm CSV gốc, file zip tải về và `SOURCE.json`.

### `DuLieuDeHoc\DuLieuDaXuLy\` — dữ liệu sau chia

`train.csv`, `val.csv`, `test.csv`. Do `MaNguon\data.py` sinh ra; chạy lại
`train_baseline.py` sẽ ghi đè. Đây là nơi **duy nhất** trong `DuLieuDeHoc\` được
phép ghi.

### `DuLieuDemo\` — dữ liệu cho trang web

`data_meta.js` (khoảng 10 KB) và `data_reviews.js` (khoảng 4,3 MB). Cả hai do
`MaNguon\export_web_data.py` sinh ra từ PostgreSQL. **Không sửa tay**: lần xuất
sau sẽ ghi đè, và số liệu sẽ lệch với database.

Vì sao là `.js` chứ không phải `.json`: mở trang bằng double-click dùng giao
thức `file://`, lúc đó `fetch()` bị chặn, còn thẻ `<script src>` thì vẫn nạp được.

Ngoài hai file máy sinh, thư mục còn có bốn file `.csv` để thử chức năng tải
file lên: `ReviewDemo_TongHop.csv` (100 dòng, đủ 5 nhóm),
`ReviewDemo_DaDang_1.csv` và `ReviewDemo_DaDang_2.csv` (400 dòng mỗi file),
`ReviewDemo_ChayNhanh.csv` (200 dòng, bản rút gọn để chạy nhanh). Ba file sau
lấy câu từ dataset, có thêm câu ngoại ngữ đã dịch máy, xác suất trải đều 0–99%
và khoảng 1/3 số dòng tự tin ≥ 80%; cụm dưới 5 từ được soạn tay. Cả bốn file
phủ đủ 5 nhóm hiển thị. Chúng là đầu vào, không script nào ghi đè; giải thích
cột và cách dùng ở `README.md` mục 5.2 và 5.3.

### `Web\` — giao diện

Chỉ có mã giao diện viết tay: `index.html`, `style.css`, `app.js`. Không chứa dữ
liệu. Trang nạp dữ liệu bằng `../DuLieuDemo/data_meta.js`.

Cách mở:

- Double-click `Web\index.html`: xem được bảng và biểu đồ, nhưng ô nhập tay và
  nút tải CSV **không hoạt động** (bị chặn `fetch`).
- Chạy `api_server.py` rồi mở `http://127.0.0.1:8000/`: đầy đủ chức năng.

### `MoHinh\` — model đã lưu

`baseline_lr_tfidf.pkl` chứa vectorizer TF-IDF, classifier và ngưỡng quyết định.
Do `train_baseline.py` sinh ra; `api_server.py` chỉ đọc. Sao lưu file này nếu
định sửa `features.py`, vì đổi cách tạo đặc trưng sẽ làm model cũ không dùng được.

### `KetQuaChay\` — kết quả chạy thuật toán

JSON/CSV sinh ra bởi các script đo. Không sửa tay vì mọi con số trong báo cáo
phải truy được về một lần chạy cụ thể.

Riêng `baseline_metrics_v1.json` là bản **trước hiệu chuẩn**, chỉ ghi một lần để
đối chiếu. Không script nào được ghi đè file này.

`run_state.json` là **bộ nhớ đệm của `MaNguon\run_all.py`**, không phải kết quả
đo: nó lưu dấu vết nội dung các file nguồn để biết bước nào đã chạy với đúng
phiên bản đó. Xóa file này không làm mất số liệu, chỉ khiến lần chạy sau làm
lại nhiều hơn.

### `ThuMucChienKhai\` — cấu hình triển khai

`docker-compose.yml`, `.env` (thật, không đưa lên mạng), `.env.example` (mẫu), và
`db\schema.sql`. `docker compose` phải chạy **trong thư mục này** để tự đọc
`.env` cùng cấp.

Cổng PostgreSQL là **5434** (không phải 5432), chỉ mở trên `127.0.0.1`.

### `ThuMucKhoiChay\` — lối tắt cho Windows

| File | Việc nó làm |
|---|---|
| `2_Chay_Web.bat` | chạy `api_server.py`, mở sẵn trình duyệt (không bật DB) |
| `3_Kiem_Tra_Toan_Ven.bat` | kiểm tra cú pháp, dữ liệu web, kết nối DB, mức độ "đã cũ" |
| `4_Chay_Tat_Ca.bat` | chạy `run_all.py` (bước 1-7) rồi gọi `2_Chay_Web.bat` |

Ba file này viết **không dấu** vì `cmd.exe` đọc file `.bat` theo từng byte; chữ
có dấu (UTF-8 nhiều byte) làm lệch bộ đọc và sinh lỗi khó hiểu. Chương trình
Python vẫn in tiếng Việt có dấu bình thường.

`2_Chay_Web.bat` và `4_Chay_Tat_Ca.bat` dùng `%~dp0` (thư mục chứa file `.bat`)
để tìm dự án, nên chép cả thư mục sang máy khác vẫn chạy.

### `TaiLieu\` — tài liệu

- `CAU_TRUC_THU_MUC.md`: tài liệu này.
- `GITHUB.md`: kiểm tra trước khi đẩy và các lệnh Git.

### `SaoLuu\` — sao lưu database

File `.dump` do `MaNguon\backup_db.py` sinh ra. Không nằm trong `Web\` để tránh bị
phục vụ công khai qua HTTP. Mỗi file khoảng 2,5 MB.

## 3. Ba quy tắc dễ vi phạm nhất

1. **`DuLieuDeHoc\DuLieuTho\` chỉ đọc.** Ghi đè dữ liệu gốc là mất khả năng tái
   lập kết quả.
2. **`DuLieuDemo\` và `KetQuaChay\` là đầu ra, không phải đầu vào.** Sửa tay sẽ bị
   lần chạy sau ghi đè, và số liệu trên web sẽ không còn khớp database. Ngoại lệ:
   bốn file `.csv` mẫu trong `DuLieuDemo\` là dữ liệu soạn sẵn, không bị ghi đè.
3. **Không đổi tên file/thư mục mà không chạy lại `3_Kiem_Tra_Toan_Ven.bat`.**
   Đường dẫn được khai báo tập trung ở `MaNguon\config.py`; nếu đổi cấu trúc mà
   quên cập nhật, lỗi sẽ chỉ hiện ra lúc chạy.
