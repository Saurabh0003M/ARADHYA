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

echo Running tests...
venv\Scripts\python.exe -m pytest tests\unit
set "EXIT_CODE=%ERRORLEVEL%"

popd >nul
pause
exit /b %EXIT_CODE%
