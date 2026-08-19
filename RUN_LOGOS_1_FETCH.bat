@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo LOGOS 1 - FETCH + NORMALIZE 256x256 WEBP
echo ============================================
py -m pip install -r tools\logos\requirements-logos.txt
if errorlevel 1 goto :err
py tools\logos\01_fetch_logos.py
if errorlevel 1 goto :err
py tools\logos\03_verify_logos.py
if errorlevel 1 goto :err
pause
exit /b 0
:err
echo CO LOI. Gui man hinh/log cho ChatGPT.
pause
exit /b 1
