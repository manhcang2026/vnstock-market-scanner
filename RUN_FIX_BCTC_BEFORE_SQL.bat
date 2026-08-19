@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo FIX BCTC - CHUNG KHOAN + COVERAGE 543
echo ============================================
echo.
echo [1/2] Chay lai RIENG nhom CHUNG KHOAN...
py tools\financial\02_fetch_fundamental.py --force-model SECURITIES
if errorlevel 1 goto :err
echo.
echo [2/2] Build production CSV va tao placeholder cho ma khong co BCTC...
py tools\financial\03_build_production_csv.py
if errorlevel 1 goto :err
echo.
echo ============================================
echo XONG PATCH BCTC.
echo CHUA CHAY RUN_STEP3_BUILD_SQL.bat.
echo Commit/push output roi gui ChatGPT check.
echo ============================================
pause
exit /b 0
:err
echo CO LOI. Gui man hinh/log cho ChatGPT.
pause
exit /b 1
