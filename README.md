# Fake Review Detection — Học máy nâng cao

Phân loại review thật/giả bằng Logistic Regression (`SGDClassifier(loss="log_loss")`) trên TF-IDF. PostgreSQL là nguồn dữ liệu duy nhất; web và API chạy cùng một server tại `http://127.0.0.1:8000/`.

## Triển khai nhanh cho đồng đội

Làm đúng 6 bước dưới đây là chạy được. Thông tin kết nối luôn lấy từ `ThuMucChienKhai\.env`: database `fakereview`, cổng `5434`, container `fakereview_db`, user `postgres`.

**1. Cài đặt.** Windows + PowerShell, Python 3.14.2, Docker Desktop, Git. Từ thư mục gốc đã clone:

```powershell
$env:PYTHONIOENCODING='utf-8'
pip install -r requirements.txt
```

**2. Tạo file cấu hình.** Copy file mẫu rồi đổi `POSTGRES_PASSWORD` thành mật khẩu mạnh. Không commit file `.env`.

```powershell
Copy-Item ThuMucChienKhai\.env.example ThuMucChienKhai\.env
notepad ThuMucChienKhai\.env
```

**3. Bật PostgreSQL.**

```powershell
cd ThuMucChienKhai
docker compose up -d
docker compose ps
```

Đợi service `db` healthy. Không dùng `docker compose down -v` vì sẽ mất toàn bộ dữ liệu.

**4. Khôi phục CSDL mẫu.** Repo kèm `SaoLuu\fakereview_seed.dump`: 1 lần chạy model, 12.124 review test/val và 1.707 bản dịch cache; không có review upload. Từ thư mục gốc:

```powershell
cd ..
python MaNguon\restore_db.py --file SaoLuu\fakereview_seed.dump --database fakereview --allow-production
```

Muốn thử trước khi ghi đè thì bỏ `--database fakereview --allow-production`; script sẽ phục hồi vào database tạm `fakereview_restore_check`.

Nếu không dùng dump, sau bước 3 chạy `python MaNguon\load_db.py` rồi `python MaNguon\export_web_data.py`. Model đã có sẵn tại `MoHinh\baseline_lr_tfidf.pkl`.

**5. Chạy web + API.**

```powershell
python MaNguon\api_server.py
```

Mở `http://127.0.0.1:8000/`. Bảng có sẵn xem được bằng double-click `Web\index.html`, nhưng ô nhập tay và tải CSV chỉ hoạt động qua địa chỉ API này. API tự xóa review upload cũ hơn 21 ngày lúc khởi động và sau đó mỗi 24 giờ.

**6. Kiểm tra.**

```powershell
python MaNguon\export_web_data.py --check
cmd /c ThuMucKhoiChay\3_Kiem_Tra_Toan_Ven.bat
```

Kết quả cuối phải là `TAT CA DEU DAT.`. Dòng `CANH BAO: con buoc chua chay` chỉ là cache của `run_all.py`, không phải lỗi.

## Cấu trúc cần biết

| Đường dẫn | Vai trò |
|---|---|
| `MaNguon\` | Toàn bộ mã Python; chạy lệnh từ thư mục gốc, ví dụ `python MaNguon\api_server.py` |
| `DuLieuDeHoc\` | Dataset gốc CC BY 4.0 + train/val/test đã chia |
| `DuLieuDemo\` | `data_meta.js`, `data_reviews.js` do DB xuất ra cho web tĩnh |
| `Web\` | `index.html`, `style.css`, `app.js`, `csv.js` |
| `MoHinh\baseline_lr_tfidf.pkl` | Model đã huấn luyện, dùng ngay không cần train lại |
| `SaoLuu\fakereview_seed.dump` | CSDL mẫu để phục hồi như bước 4 |
| `KetQuaChay\` | Kết quả chạy: metrics, dự đoán, kiểm chứng |
| `ThuMucChienKhai\` | `docker-compose.yml`, `.env.example`, `db\schema.sql` |
| `ThuMucKhoiChay\` | Các file `.bat` tiện chạy trên Windows |

## Kết quả hiện tại

Ngưỡng 0,41; tập test 6.062 review: accuracy 0,9167, precision 0,9047, recall 0,9313, F1 0,9178. Model chính không vượt baseline LR mặc định (F1 0,9308); báo cáo ghi rõ điều này.

## Nhớ kỹ

- `.env` chứa mật khẩu thật, không đẩy lên GitHub; chỉ đẩy `.env.example`.
- Không dùng `docker compose down -v`.
- Nhóm bot/boost/spam là luật suy luận để hiển thị, không có nhãn ground truth.
- Dataset là tiếng Anh; câu tiếng Việt được dịch sang tiếng Anh trước khi dự đoán.

Tài liệu chi tiết nếu cần: `TaiLieu\CAU_TRUC_THU_MUC.md` (giải thích từng thư mục), `DuLieuDeHoc\README.md` (nguồn và audit dữ liệu), `TaiLieu\GITHUB.md` (các lệnh đẩy repo).
