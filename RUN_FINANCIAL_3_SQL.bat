@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo FINANCIAL 3 - BUILD SQL NHO CHO SUPABASE
 echo ============================================
py tools\financial\04_build_supabase_sql.py
if errorlevel 1 goto :err

echo.
echo SQL nam trong tools\financial\work\sql\
echo KHONG script nao tu ghi Supabase.
pause
exit /b 0
:err
echo CO LOI. Gui man hinh/log cho ChatGPT.
pause
exit /b 1
