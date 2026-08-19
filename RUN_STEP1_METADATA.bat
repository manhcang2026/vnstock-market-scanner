@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo STEP 1 - CHUAN BI + TEN CONG TY + PHAN NGANH
echo ============================================
py -m pip install -r tools\financial\requirements-financial.txt
if errorlevel 1 goto :err
py tools\financial\00_prepare_targets.py
if errorlevel 1 goto :err
py tools\financial\01_classify_missing.py
if errorlevel 1 goto :err
echo.
echo XONG STEP 1.
echo Gui 2 file cho ChatGPT:
echo tools\financial\output\industry_new_current_raw.csv
echo tools\financial\output\industry_review_current.csv
pause
exit /b 0
:err
echo CO LOI. Gui log/anh cho ChatGPT.
pause
exit /b 1
