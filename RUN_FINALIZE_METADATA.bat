@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo FINALIZE STEP 1 - DUYET 18 MA CON LAI
echo ============================================
py tools\financial\05_finalize_industry_review.py
if errorlevel 1 goto :err
echo.
echo XONG. Da tao:
echo tools\financial\output\industry_new_current_final.csv
echo.
echo CHUA CHAY STEP 2 NEU CHUA COMMIT/PUSH FILE FINAL.
pause
exit /b 0
:err
echo CO LOI. Gui man hinh/log cho ChatGPT.
pause
exit /b 1
