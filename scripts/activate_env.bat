@echo off
setlocal EnableExtensions

pushd "%~dp0.." >nul

if not exist "venv\Scripts\activate.bat" (
    echo Local virtual environment not found.
    echo Run scripts\first_run.bat first.
    popd >nul
    exit /b 1
)

echo Activating Aradhya virtual environment...
call venv\Scripts\activate.bat
echo.
echo Environment activated from %CD%\venv
echo Python:
python --version
echo.
cmd /k

popd >nul
