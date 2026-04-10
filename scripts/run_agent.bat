@echo off
setlocal EnableExtensions

pushd "%~dp0.." >nul

if not exist "venv\Scripts\python.exe" (
    echo Local virtual environment not found.
    echo Run scripts\first_run.bat first.
    popd >nul
    pause
    exit /b 1
)

echo Starting Aradhya Agent...
venv\Scripts\python.exe -m core.agent.aradhya
set "EXIT_CODE=%ERRORLEVEL%"

popd >nul
pause
exit /b %EXIT_CODE%
