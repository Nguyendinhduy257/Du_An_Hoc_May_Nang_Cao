# Đẩy dự án lên GitHub

Làm theo thứ tự dưới đây trên PowerShell, ngay tại thư mục gốc
`Du_An_Hoc_May_Nang_Cao`.

## 1. Kiểm tra trước khi đẩy

```powershell
$env:PYTHONIOENCODING='utf-8'
python -m compileall -q MaNguon
cmd /c ThuMucKhoiChay\3_Kiem_Tra_Toan_Ven.bat
```

Bước cuối phải in `TAT CA DEU DAT.`. Dòng `CANH BAO: con buoc chua chay` chỉ là
cache của `run_all.py`; nếu muốn hết cảnh báo, chạy thêm `python MaNguon\run_all.py`.

Kiểm tra thủ công ba điểm nhạy cảm:

- `ThuMucChienKhai\.env` là file thật, **không được đẩy**; chỉ đẩy
  `ThuMucChienKhai\.env.example` với mật khẩu mẫu.
- `SaoLuu\fakereview_seed.dump` là bản seed phải đẩy; các file dump khác,
  `__pycache__` và `KetQuaChay\run_state.json` đã bị `.gitignore` chặn.
- `DuLieuDeHoc\DuLieuTho\fake-reviews-dataset.zip` cũng bị chặn; file CSV đã
  chuẩn hoá vẫn được đẩy để clone về chạy ngay.

Nếu định công khai repo, tự quyết định thêm file `LICENSE`. Dự án chưa có file
này; không tự gán giấy phép cho code.

## 2. Tạo repo trống trên GitHub

Vào https://github.com/new, đặt tên repo, để trống các mục **Add a README**,
**Add .gitignore**, **Add a license** để tránh xung đột lịch sử.

## 3. Các lệnh Git

```powershell
cd D:\OneDrive\Desktop\Du_An_Hoc_May_Nang_Cao

git init
git config user.name "Ten cua ban"
git config user.email "email@cua-ban.com"

git status --short

git add .
git status --short
```

Đọc kỹ danh sách sau `git add .`: phải có `SaoLuu\fakereview_seed.dump`, nhưng
không được có `.env`, dump khác, `__pycache__` hay `*.zip`. Nếu có file thừa,
gỡ bằng `git restore --staged <file>` rồi sửa `.gitignore`.

```powershell
git commit -m "Initial commit: pipeline fake review detection"
git branch -M main
git remote add origin https://github.com/<tai-khoan>/<ten-repo>.git
git push -u origin main
```

Khi GitHub hỏi đăng nhập, dùng **Personal Access Token** thay cho mật khẩu
(vào Settings → Developer settings → Personal access tokens).

## 4. Sau khi đẩy

Mở repo trên GitHub và kiểm tra:

- Có `README.md`, `requirements.txt`, các thư mục `MaNguon`, `Web`, `DuLieuDeHoc`,
  `KetQuaChay`, `TaiLieu`, `ThuMucChienKhai`, `ThuMucKhoiChay`.
- Không có `ThuMucChienKhai\.env`; trong `SaoLuu\` chỉ có `fakereview_seed.dump`.
- `ThuMucChienKhai\.env.example` có mặt để người khác tự tạo `.env`.

Lần sau chỉ cần `git add .`, `git commit -m "..."`, `git push`.
