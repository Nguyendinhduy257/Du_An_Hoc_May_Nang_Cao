@echo off
rem ============================================================================
rem  Duong dan: Du_An_Hoc_May_Nang_Cao\ThuMucKhoiChay\3_Kiem_Tra_Toan_Ven.bat
rem  Muc dich : Kiem tra nhanh du an truoc khi demo hoac nop bai.
rem             Chi DOC va bao loi, khong sua du lieu, khong train lai.
rem ============================================================================

chcp 65001 >nul
setlocal

cd /d "%~dp0.."
set "PYTHONIOENCODING=utf-8"

echo [1/5] Kiem tra cu phap toan bo file Python trong MaNguon\...
python -m compileall -q MaNguon
if errorlevel 1 goto :loi

echo [2/5] Kiem tra cu phap cac file JavaScript trong Web\...
where node >nul 2>nul
if errorlevel 1 (
    echo        Bo qua: may chua cai Node.js.
) else (
    for %%f in (Web\*.js) do (
        node --check "%%f"
        if errorlevel 1 goto :loi
    )
)

echo [3/5] Kiem tra du lieu web co khop PostgreSQL...
python MaNguon\export_web_data.py --check
if errorlevel 1 (
    echo        Du lieu web da cu. Chay: python MaNguon\export_web_data.py
    goto :loi
)

echo [4/5] Kiem tra ket noi PostgreSQL...
rem Khong dung %.1f trong chuoi nay: dau % la ky tu dac biet cua batch.
python -c "import sys; sys.path.insert(0, 'MaNguon'); import db; h = db.check_health(); ok = h['connected']; print(('        Ket noi OK, ' + str(h['latency_ms']) + ' ms') if ok else ('        Khong ket noi duoc: ' + h['error'][:120])); sys.exit(0 if ok else 1)"
if errorlevel 1 goto :loi

echo [5/5] Kiem tra du lieu/model/bao cao da moi chua...
rem Ma thoat 1 o day nghia la "con buoc can chay", KHONG phai loi cu phap.
python MaNguon\run_all.py --check
if errorlevel 1 (
    echo        CANH BAO: con buoc chua chay. Chay: python MaNguon\run_all.py
    echo        hoac bam ThuMucKhoiChay\4_Chay_Tat_Ca.bat
)

echo.
echo TAT CA DEU DAT.
exit /b 0

:loi
echo.
echo CO LOI. Xem thong bao phia tren.
exit /b 1
