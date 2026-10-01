@echo off
title InsightOS Single Unified Engine
cls
echo ============================================================
echo   InsightOS Autonomous Retail Decision Engine & AI Platform
echo ============================================================
echo.
echo Starting InsightOS Unified Server on http://127.0.0.1:8080 ...
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

start "" cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:8080"
%PYTHON_CMD% -m uvicorn app.main:app --host 127.0.0.1 --port 8080 --reload

echo.
pause
