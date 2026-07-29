@echo off
echo ==========================================
echo       Shocker Roulette Setup
echo ==========================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in your PATH!
    echo Please install Python 3.10+ and make sure to check
    echo "Add Python to PATH" during installation.
    echo.
    echo Download link: https://www.python.org/downloads/
    echo.
    pause
    exit /b
)

echo [INFO] Python found! Installing packages...
echo.
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Package installation failed!
    echo Please check if you have an active internet connection.
    pause
    exit /b
)

echo.
echo ==========================================
echo [SUCCESS] Setup complete! All packages installed.
echo.
echo To play the game:
echo   1. Start server: python server/server.py
echo   2. Start client: python client/client.py
echo ==========================================
echo.
pause
