@echo off
REM Disease2Gene — One-click launcher for Windows
REM Double-click this file to start

echo.
echo   Disease2Gene — Research Pipeline
echo   ================================
echo.

REM Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo   ERROR: Python not found!
    echo.
    echo   Please install Python 3.8+ from https://www.python.org/downloads/
    echo   Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do echo   Using %%i

REM Install dependencies
echo   Checking dependencies...
python -m pip install -q -r requirements.txt 2>nul || (
    echo   Installing dependencies (first run only)...
    python -m pip install --user -r requirements.txt
)
echo   All dependencies installed
echo.

REM Launch
echo   Starting Disease2Gene...
echo   Your browser will open automatically
echo   To stop: close this window or press Ctrl+C
echo.
python gui\app_server.py

pause
