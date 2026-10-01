@echo off
title InsightOS Unified Platform
color 0A
cls

echo ================================================================
echo       InsightOS - AUTONOMOUS RETAIL DECISION ENGINE              
echo ================================================================
echo.

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

if exist "%SCRIPT_DIR%.venv\Scripts\python.exe" (
    set PYTHON_CMD="%SCRIPT_DIR%.venv\Scripts\python.exe"
) else if exist "%SCRIPT_DIR%venv\Scripts\python.exe" (
    set PYTHON_CMD="%SCRIPT_DIR%venv\Scripts\python.exe"
) else (
    set PYTHON_CMD=python
)

echo Starting Server on http://127.0.0.1:8080 ...
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:8080"
%PYTHON_CMD% -m uvicorn app.main:app --host 127.0.0.1 --port 8080 --reload

echo.
pause
