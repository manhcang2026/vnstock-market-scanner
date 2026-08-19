@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo STEP 3 - TAO CSV PRODUCTION + SQL SUPABASE
echo ============================================
echo.
py tools\financial\03_build_production_csv.py
if errorlevel 1 goto :err
py tools\financial\04_build_supabase_sql.py
if errorlevel 1 goto :err
echo.
echo XONG. SQL nam trong:
echo tools\financial\output\sql_542\
echo.
echo KHONG file nao tu ghi vao Supabase.
echo Ban se chay SQL thu cong trong Supabase SQL Editor.
pause
exit /b 0
:err
echo.
echo CO LOI. Chup man hinh hoac gui file output cho ChatGPT.
pause
exit /b 1
