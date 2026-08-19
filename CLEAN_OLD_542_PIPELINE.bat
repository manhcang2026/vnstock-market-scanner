@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Chi xoa cac file pipeline 542 CU, KHONG xoa scanner.
del /q RUN_STEP1_CLASSIFY_542.bat 2>nul
del /q RUN_STEP2_FETCH_BCTC_542.bat 2>nul
del /q tools\financial\01_classify_missing_542.py 2>nul
del /q tools\financial\02_fetch_fundamental_542.py 2>nul
del /q tools\financial\data\existing_symbols_258.csv 2>nul
del /q tools\financial\data\missing_symbols_542.csv 2>nul
del /q tools\financial\data\watchlist_800_snapshot.csv 2>nul
del /q tools\financial\output\industry_new_542_raw.csv 2>nul
del /q tools\financial\output\industry_review_542.csv 2>nul
echo XONG. Neu dung GitHub Desktop, commit cac file deleted cung voi pipeline moi.
pause
