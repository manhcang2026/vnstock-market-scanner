@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo STEP 2 - LAY BCTC VIETSTOCK CHO 542 MA
echo ============================================
echo.
if not exist tools\financial\output\industry_new_542_final.csv (
  echo CHUA CO industry_new_542_final.csv.
  echo Hay gui output STEP 1 cho ChatGPT de duyet truoc.
  pause
  exit /b 1
)
py -m pip install -r tools\financial\requirements-financial.txt
if errorlevel 1 goto :err
py tools\financial\02_fetch_fundamental_542.py
if errorlevel 1 goto :err
echo.
echo XONG/HOAC DA CHAY HET CAC MA CO THE LAY.
echo Neu errors_542.csv con ma loi, chay lai file nay de retry.
pause
exit /b 0
:err
echo.
echo CO LOI. Chup man hinh hoac gui errors_542.csv cho ChatGPT.
pause
exit /b 1
