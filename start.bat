@echo off
chcp 65001 >nul
title DveriApp - Zaichka dver (odna knopka)
cd /d "%~dp0"

echo ============================================
echo   DVERIAPP - ZAPUSK SAITA V ODNU KNOPKU
echo ============================================
echo.

REM --- 1. Proverka Python ---
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [OShIBKA] Python ne nayden. Ustanovite ego s python.org
    echo i OBYAZATELNO postavte galochku "Add Python to PATH".
    echo Skachat': https://www.python.org/downloads/
    pause
    exit /b 1
)

REM --- 2. Sozdanie virtualnogo okruzhaniya (pri pervom zapuske) ---
if not exist ".venv" (
    echo [Shag 1/3] Sozdanie virtualnogo okruzhaniya...
    python -m venv .venv
)
call ".venv\Scripts\activate.bat"

REM --- 3. Ustanovka zavysimostey (pri pervom zapuske) ---
pip show flask >nul 2>nul
if %errorlevel% neq 0 (
    echo [Shag 2/3] Ustanovka zavisimostey flask, requests...
    pip install --quiet flask requests pyngrok
) else (
    echo [Shag 2/3] Zavisimosti uzhe ustanovleny.
)

REM --- 4. Zapusk saita + publichnaya ssylka dlya druzei ---
echo [Shag 3/3] Zapusk saita...
echo.
python run.py
echo.
echo Sayt ostanovlen. Naxhati lyobuyu klipish, chtoby zakryt' okno...
pause >nul
