@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo AI Research Lab Diagnostic
echo ========================================
set "PY_EXE=%~dp0.venv\Scripts\python.exe"
echo [INFO] Python: "%PY_EXE%"
if not exist "%PY_EXE%" (
    echo [FAIL] .venv\Scripts\python.exe not found.
    echo [INFO] Run the installer again and make sure package installation succeeds.
    pause
    exit /b 1
)
"%PY_EXE%" -u scripts\diagnose.py
set "EXIT_CODE=%ERRORLEVEL%"
echo.
echo ========================================
echo Diagnostic exit code: %EXIT_CODE%
echo ========================================
pause
exit /b %EXIT_CODE%
