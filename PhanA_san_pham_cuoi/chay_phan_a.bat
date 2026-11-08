@echo off
setlocal
cd /d "%~dp0"

echo ====================================================================
echo    CHUONG TRINH CHAY TU DONG THUC NGHIEM GEMINI 3.8 (PHAN A)
echo    Mo hinh su dung: Gemini 3.8 Flash (gemini-3.8-flash)
echo ====================================================================
echo.

set SCRIPT=
if exist "%~dp005_scripts\chay_gemini_va_danh_gia.py" set SCRIPT=%~dp005_scripts\chay_gemini_va_danh_gia.py
if exist "%~dp0chay_gemini_va_danh_gia.py" set SCRIPT=%~dp0chay_gemini_va_danh_gia.py
if exist "%~dp0final\05_scripts\chay_gemini_va_danh_gia.py" set SCRIPT=%~dp0final\05_scripts\chay_gemini_va_danh_gia.py

if "%SCRIPT%"=="" (
    echo [LOI] Khong tim thay tep chay_gemini_va_danh_gia.py!
    echo Vui long kiem tra lai thu muc chua file chay_phan_a.bat.
    echo.
    pause
    exit /b 1
)

set KEY=
set /p KEY="Nhap Gemini API Key (Enter neu da set GEMINI_API_KEY): "
if "%KEY%"=="" set KEY=%GEMINI_API_KEY%

if "%KEY%"=="" (
    echo.
    echo [LOI] Chua co API Key! Vui long nhap API Key de tiep tuc.
    echo.
    pause
    exit /b 1
)

echo.
echo Da tim thay script: %SCRIPT%
echo Dang bat dau chay thuc nghiem toan bo cac tap du lieu...
echo.

python "%SCRIPT%" --api-key "%KEY%" --model "gemini-3.8-flash"

echo.
echo ====================================================================
echo  HOAN TAT THUC NGHIEM! Kiem tra ket qua tai: 06_reports\metrics.csv
echo ====================================================================
echo.
pause
