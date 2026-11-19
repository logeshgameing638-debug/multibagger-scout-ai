@echo off
REM Back up the local SQLite database into the backups folder.
setlocal
cd /d "%~dp0\.."
if not exist .venv (
    echo Run scripts\setup.bat first.
    pause
    exit /b 1
)
call .venv\Scripts\activate.bat
python -c "from config import get_settings; from services.backup import backup_database; print('Backup saved to:', backup_database(get_settings().database_url))"
pause
