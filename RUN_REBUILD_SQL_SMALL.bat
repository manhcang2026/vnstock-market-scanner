@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo REBUILD SQL NHO CHO SUPABASE SQL EDITOR
echo ============================================
py tools\financial\04_build_supabase_sql.py
if errorlevel 1 goto :err
echo.
echo XONG. SQL moi nam trong:
echo tools\financial\output\sql_current\
echo.
echo CHUA TU DONG GHI SUPABASE.
pause
exit /b 0
:err
echo CO LOI. Gui man hinh/log cho ChatGPT.
pause
exit /b 1
