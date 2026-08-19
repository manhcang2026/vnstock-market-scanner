@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo FINANCIAL 2 - VIETSTOCK BCTC + PRODUCTION CSV
echo ============================================
if not exist tools\financial\work\industry_final.csv (
  echo Chua co industry_final.csv. Chay RUN_FINANCIAL_1_METADATA.bat truoc.
  pause
  exit /b 1
)
py -m pip install -r tools\financial\requirements-financial.txt
if errorlevel 1 goto :err
py tools\financial\02_fetch_fundamental.py
if errorlevel 1 goto :err
py tools\financial\03_build_production_csv.py
if errorlevel 1 goto :err

echo.
echo XONG STEP 2. Neu co errors.csv, co the chay lai BAT de retry.
pause
exit /b 0
:err
echo CO LOI. Gui man hinh/log cho ChatGPT.
pause
exit /b 1
