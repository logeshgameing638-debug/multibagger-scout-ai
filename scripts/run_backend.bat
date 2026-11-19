@echo off
REM Start the FastAPI backend (optional; the dashboard works without it).
setlocal
cd /d "%~dp0\.."
if not exist .venv (
    echo Run scripts\setup.bat first.
    pause
    exit /b 1
)
call .venv\Scripts\activate.bat
python backend.py
pause
