@echo off
setlocal EnableExtensions
cd /d "D:\ai-research-lab"
set "PYW_EXE=D:\ai-research-lab\.venv\Scripts\pythonw.exe"
if not exist "%PYW_EXE%" (
    echo [ERROR] Virtual environment pythonw.exe was not found.
    echo Expected: "%PYW_EXE%"
    pause
    exit /b 1
)
start "AI Research Lab" /b "%PYW_EXE%" "D:\ai-research-lab\scripts\app.py"
