@echo off
REM Multibagger Scout AI - Windows setup (Windows 10/11)
REM Double-click this file once. It checks Python, creates a virtual
REM environment, installs dependencies, initialises the database and runs tests.

setlocal
cd /d "%~dp0\.."

echo === Checking Python ===
where python >nul 2>&1
if errorlevel 1 (
    echo Python not found. Install Python 3.10 or newer from https://www.python.org/downloads/
    echo During install, tick "Add python.exe to PATH". Then run this file again.
    pause
    exit /b 1
)
python --version

echo === Creating virtual environment ===
if not exist .venv (
    python -m venv .venv
)
call .venv\Scripts\activate.bat

echo === Installing dependencies ===
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo Dependency install failed. Check your internet connection and retry.
    pause
    exit /b 1
)

echo === Creating environment configuration ===
if not exist .env copy .env.example .env

echo === Initialising database ===
python -c "from database.connection import init_db; init_db(); print('database ready')"

echo === Running automated tests ===
python -m pytest tests -q
if errorlevel 1 (
    echo Some tests failed - see output above. The app may still run, but read README.md.
) else (
    echo All tests passed.
)

echo.
echo Setup complete. Start the app with run_dashboard.bat
pause
