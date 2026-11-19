@echo off
REM Start the Multibagger Scout AI dashboard.
setlocal
cd /d "%~dp0\.."
if not exist .venv (
    echo Run scripts\setup.bat first.
    pause
    exit /b 1
)
call .venv\Scripts\activate.bat
streamlit run app.py
pause
