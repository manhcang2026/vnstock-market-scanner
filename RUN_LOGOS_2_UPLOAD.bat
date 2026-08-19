@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo LOGOS 2 - UPLOAD SUPABASE STORAGE
 echo ============================================
if not exist tools\logos\.env (
  echo Chua co tools\logos\.env. Copy .env.example thanh .env va dien SUPABASE_URL + SUPABASE_SECRET_KEY.
  pause
  exit /b 1
)
py -m pip install -r tools\logos\requirements-logos.txt
if errorlevel 1 goto :err
py tools\logos\02_upload_supabase.py
if errorlevel 1 goto :err
pause
exit /b 0
:err
echo CO LOI. Gui man hinh/log cho ChatGPT.
pause
exit /b 1
