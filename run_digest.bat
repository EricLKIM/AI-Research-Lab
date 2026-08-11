@echo off
chcp 65001 >nul
setlocal
set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"
cd /d "D:\ai-research-lab"
set "UV_EXE="
if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV_EXE=%USERPROFILE%\.local\bin\uv.exe"
if not defined UV_EXE if exist "%USERPROFILE%\.cargo\bin\uv.exe" set "UV_EXE=%USERPROFILE%\.cargo\bin\uv.exe"
if not defined UV_EXE for /f "delims=" %%U in ('where uv.exe 2^>nul') do if not defined UV_EXE set "UV_EXE=%%U"
if not defined UV_EXE (
    echo [Error] uv.exe could not be found.
    echo "%USERPROFILE%\.local\bin\uv.exe"
    echo "%USERPROFILE%\.cargo\bin\uv.exe"
    pause
    exit /b 1
)
echo.
echo   Running AI Research Digest...
echo.
"%UV_EXE%" run python scripts\research_digest.py --vault-name "AI_research" --output-dir "C:\Users\ericl\Desktop\AI_research" --model "gpt-5.4-nano" --output-language "English"
if errorlevel 1 (
    echo [Error] Something went wrong while running.
    pause
)
endlocal
