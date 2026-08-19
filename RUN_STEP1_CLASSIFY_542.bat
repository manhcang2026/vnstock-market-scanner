@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo STEP 1 - PHAN NGANH 542 MA MOI TU VIETSTOCK
echo ============================================
echo.
py -m pip install -r tools\financial\requirements-financial.txt
if errorlevel 1 goto :err
echo.
py tools\financial\01_classify_missing_542.py
if errorlevel 1 goto :err
echo.
echo XONG STEP 1.
echo Gui 2 file sau cho ChatGPT:
echo tools\financial\output\industry_new_542_raw.csv
echo tools\financial\output\industry_review_542.csv
pause
exit /b 0
:err
echo.
echo CO LOI. Chup man hinh hoac gui log cho ChatGPT.
pause
exit /b 1
