@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo CLEAN LEGACY FINANCIAL FILES
 echo ============================================
echo Chi xoa file cu / output da import. KHONG xoa scanner, config watchlist, source Daily/Intraday.

echo [1] Root BAT/README cu...
for %%F in (
  CLEAN_OLD_542_PIPELINE.bat
  README_FINANCIAL_800.md
  README_FINANCIAL_FINAL_800.md
  RUN_FINALIZE_METADATA.bat
  RUN_FIX_BCTC_BEFORE_SQL.bat
  RUN_REBUILD_SQL_SMALL.bat
  RUN_STEP1_CLASSIFY_542.bat
  RUN_STEP1_METADATA.bat
  RUN_STEP2_BCTC.bat
  RUN_STEP2_FETCH_BCTC_542.bat
  RUN_STEP3_BUILD_SQL.bat
) do if exist "%%F" del /q "%%F"

echo [2] Python 542 cu...
if exist tools\financial\01_classify_missing_542.py del /q tools\financial\01_classify_missing_542.py
if exist tools\financial\02_fetch_fundamental_542.py del /q tools\financial\02_fetch_fundamental_542.py

echo [3] Data snapshot cu...
if exist tools\financial\data\existing_symbols_258.csv del /q tools\financial\data\existing_symbols_258.csv
if exist tools\financial\data\existing_symbols_current.csv del /q tools\financial\data\existing_symbols_current.csv
if exist tools\financial\data\missing_symbols_542.csv del /q tools\financial\data\missing_symbols_542.csv
if exist tools\financial\data\missing_symbols_current.csv del /q tools\financial\data\missing_symbols_current.csv
if exist tools\financial\data\watchlist_800_snapshot.csv del /q tools\financial\data\watchlist_800_snapshot.csv

if exist tools\financial\data rmdir tools\financial\data 2>nul

echo [4] Generated output cu da import Supabase...
if exist tools\financial\output rmdir /s /q tools\financial\output

echo.
echo XONG. GitHub Desktop se hien cac file deleted.
echo Commit cac deletion + toolkit moi cung mot lan.
pause
