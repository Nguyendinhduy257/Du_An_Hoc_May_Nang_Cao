@echo off
rem ============================================================================
rem  Duong dan: Du_An_Hoc_May_Nang_Cao\ThuMucKhoiChay\4_Chay_Tat_Ca.bat
rem  Muc dich : Chay MOT lan: cap nhat du lieu/model/bao cao (buoc 1-7 trong
rem             README), roi mo web + API (buoc 5).
rem
rem  Vi sao chi chay phan da cu: xem chu thich dau MaNguon\run_all.py.
rem  Muon chay lai tat ca: 4_Chay_Tat_Ca.bat --full
rem  Muon bo qua buoc goi mang: 4_Chay_Tat_Ca.bat --no-network
rem ============================================================================

chcp 65001 >nul
setlocal

rem Len mot cap: ThuMucKhoiChay\ -> goc du an.
cd /d "%~dp0.."

rem Bat buoc tren Windows: thieu bien nay Python co the loi UnicodeEncodeError
rem khi in tieng Viet ra console.
set "PYTHONIOENCODING=utf-8"

echo === BUOC 1-7: cap nhat du lieu, model, bao cao ===
echo.
python MaNguon\run_all.py %*
if errorlevel 1 goto :loi

echo.
echo === BUOC 5: mo web + API ===
echo.
rem Goi lai file da duoc kiem tra, khong chep lai logic mo trinh duyet.
call "%~dp02_Chay_Web.bat"
exit /b %errorlevel%

:loi
echo.
echo [DUNG] Khong chay tiep (ma thoat khac 0). Xem thong bao phia tren.
pause
exit /b 1
