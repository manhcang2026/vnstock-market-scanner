@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo STEP 3 - PRODUCTION CSV + SQL SUPABASE
echo ============================================
py tools\financial\03_build_production_csv.py
if errorlevel 1 goto :err
py tools\financial\04_build_supabase_sql.py
if errorlevel 1 goto :err
echo.
echo SQL nam trong tools\financial\output\sql_current\
echo KHONG script nao tu ghi Supabase.
pause
exit /b 0
:err
echo CO LOI. Gui output/log cho ChatGPT.
pause
exit /b 1
