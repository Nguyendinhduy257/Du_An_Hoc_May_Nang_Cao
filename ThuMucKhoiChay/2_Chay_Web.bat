@echo off
rem ============================================================================
rem  Duong dan: Du_An_Hoc_May_Nang_Cao\ThuMucKhoiChay\2_Chay_Web.bat
rem  Muc dich : Chay api_server.py (API + phuc vu giao dien) va mo trinh duyet.
rem
rem  Vi sao phai chay qua server thay vi double-click Web\index.html:
rem      Giao thuc file:// chan fetch(), nen o nhap tay va nut tai CSV se khong
rem      goi duoc API. Chay qua http://127.0.0.1:<cong>/ thi cung nguon goc.
rem ============================================================================

chcp 65001 >nul
setlocal

rem Len mot cap: ThuMucKhoiChay\ -> goc du an.
cd /d "%~dp0.."

rem Bat buoc tren Windows: thieu bien nay Python co the loi UnicodeEncodeError
rem khi in tieng Viet ra console.
set "PYTHONIOENCODING=utf-8"

rem Doc dia chi tu config.py thay vi chep cung 127.0.0.1:8000.
rem Vi sao: doi API_PORT trong config.py thi file .bat tu theo, khong lech.
for /f "delims=" %%u in ('python -c "import sys; sys.path.insert(0, 'MaNguon'); from config import API_HOST, API_PORT; print('http://' + str(API_HOST) + ':' + str(API_PORT) + '/')"') do set "DIA_CHI=%%u"

if not defined DIA_CHI goto :loi_config

echo Dia chi web: %DIA_CHI%
echo Nhan Ctrl+C de dung server.
echo.

rem Mo trinh duyet sau khoang 2 giay, du de server kip lang nghe cong.
rem /b: khong mo them cua so console thu hai.
rem Dung ping thay cho timeout: timeout can stdin cua console.
start "" /b cmd /c "ping -n 3 127.0.0.1 >nul && start %DIA_CHI%"

python MaNguon\api_server.py
exit /b %errorlevel%

:loi_config
echo.
echo Khong doc duoc API_HOST / API_PORT tu MaNguon\config.py
exit /b 1
