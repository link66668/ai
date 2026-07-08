@echo off
echo ========================================
echo   Course Agent Platform - Start
echo ========================================
echo.

REM Check Python
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

REM Enter backend directory
cd /d "%~dp0backend"

REM Install dependencies
echo [1/3] Installing dependencies...
pip install -r requirements.txt -q
if errorlevel 1 (
    echo [ERROR] Install failed!
    pause
    exit /b 1
)

echo [2/3] Dependencies OK
echo [3/3] Starting server...
echo.
echo ========================================
echo   URL:      http://localhost:5000
echo   Account:  demo / 123456
echo   Press Ctrl+C to stop
echo ========================================
echo.
echo NOTE: If you see database errors, please run:
echo   python %~dp0setup_db.py
echo   to initialize the database first.
echo.

python app.py
pause
