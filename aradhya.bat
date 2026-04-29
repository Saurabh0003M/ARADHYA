@echo off
setlocal
cd /d "%~dp0"

if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe -m core.agent.aradhya %*
) else (
    echo [ERROR] Virtual environment not found. Please run scripts\first_run.bat first.
    exit /b 1
)
endlocal
