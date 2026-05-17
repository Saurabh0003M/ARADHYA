@echo off
cd /d "%~dp0"

if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe -c "import rich, loguru, requests, yaml, dotenv" >nul 2>nul
    if not errorlevel 1 (
        venv\Scripts\python.exe -m src.aradhya.main %*
        exit /b %ERRORLEVEL%
    )
    echo Local venv is missing runtime packages. Falling back to PATH python.
    echo Run scripts\first_run.bat to repair the venv.
)

python -m src.aradhya.main %*
