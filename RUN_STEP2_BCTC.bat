@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo STEP 2 - LAY BCTC VIETSTOCK
echo ============================================
if not exist tools\financial\output\industry_new_current_final.csv (
  echo CHUA CO industry_new_current_final.csv.
  echo Phai gui STEP 1 cho ChatGPT duyet truoc.
  pause
  exit /b 1
)
py -m pip install -r tools\financial\requirements-financial.txt
if errorlevel 1 goto :err
py tools\financial\02_fetch_fundamental.py
if errorlevel 1 goto :err
echo.
echo XONG/DA CHAY HET CAC MA CO THE LAY.
echo Neu errors_current.csv con ma loi, chay lai de retry.
pause
exit /b 0
:err
echo CO LOI. Gui errors_current.csv/log cho ChatGPT.
pause
exit /b 1
