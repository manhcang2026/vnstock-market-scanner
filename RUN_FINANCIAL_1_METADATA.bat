@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo FINANCIAL 1 - TARGETS + TEN + PHAN NGANH
echo ============================================
py -m pip install -r tools\financial\requirements-financial.txt
if errorlevel 1 goto :err
py tools\financial\00_prepare_targets.py
if errorlevel 1 goto :err
py tools\financial\01_classify_missing.py
if errorlevel 1 goto :err
py tools\financial\05_finalize_industry_review.py
if errorlevel 1 goto :review

echo.
echo XONG STEP 1. industry_final.csv da san sang.
pause
exit /b 0
:review
echo.
echo CON MA CAN REVIEW. Gui file:
echo tools\financial\work\industry_unresolved.csv
echo cho ChatGPT, bo sung override, roi chay lai file BAT nay.
pause
exit /b 2
:err
echo CO LOI. Gui man hinh/log cho ChatGPT.
pause
exit /b 1
