@echo off
REM Multibagger Scout AI - one-click run for non-programmers.
REM Installs on first run if needed, then opens the dashboard.
if not exist .venv (
  echo First run: setting up...
  call scripts\setup.bat
)
call scripts\run_dashboard.bat
