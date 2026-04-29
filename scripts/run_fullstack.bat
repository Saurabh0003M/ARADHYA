@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"

pushd "%PROJECT_ROOT%" >nul

set "BASE_PYTHON_EXE="
set "BASE_PYTHON_ARGS="
set "BACKEND_LAUNCH="

echo ========================================
echo Aradhya Full-Stack Run
echo ========================================
echo Project root: %PROJECT_ROOT%
echo.

if not exist "backend\.env" copy /Y "backend\.env.example" "backend\.env" >nul
if not exist "frontend\.env.local" copy /Y "frontend\.env.example" "frontend\.env.local" >nul

where npm >nul 2>nul
if errorlevel 1 (
    echo ERROR: npm is not available on PATH.
    echo Run scripts\first_run_fullstack.bat after installing Node.js LTS.
    goto :fail
)

if not exist "frontend\node_modules" (
    echo ERROR: Frontend dependencies are missing.
    echo Run scripts\first_run_fullstack.bat first.
    goto :fail
)

if exist ".venv-backend\Scripts\python.exe" (
    set "BACKEND_LAUNCH=""%PROJECT_ROOT%\.venv-backend\Scripts\python.exe"" -m uvicorn backend.server:app --host 127.0.0.1 --port 8001 --reload"
    echo Using isolated backend environment.
) else (
    call :detect_python
    if errorlevel 1 goto :fail

    if defined BASE_PYTHON_ARGS (
        set "BACKEND_LAUNCH=%BASE_PYTHON_EXE% %BASE_PYTHON_ARGS% -m uvicorn backend.server:app --host 127.0.0.1 --port 8001 --reload"
    ) else (
        set "BACKEND_LAUNCH=%BASE_PYTHON_EXE% -m uvicorn backend.server:app --host 127.0.0.1 --port 8001 --reload"
    )
    echo Using system/current Python backend environment.
)

echo.
echo Starting backend on http://localhost:8001
start "Aradhya Backend" cmd /k "cd /d ""%PROJECT_ROOT%"" && !BACKEND_LAUNCH!"

echo Starting frontend on http://localhost:3000
start "Aradhya Frontend" cmd /k "cd /d ""%PROJECT_ROOT%\frontend"" && call npm start"

echo.
echo Two windows were opened:
echo   Aradhya Backend  - http://localhost:8001
echo   Aradhya Frontend - http://localhost:3000
echo.

popd >nul
exit /b 0

:fail
echo.
echo Unable to start the full-stack app.
popd >nul
exit /b 1

:detect_python
where py >nul 2>nul
if not errorlevel 1 (
    py -3.12 -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "BASE_PYTHON_EXE=py"
        set "BASE_PYTHON_ARGS=-3.12"
        exit /b 0
    )

    py -3.11 -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "BASE_PYTHON_EXE=py"
        set "BASE_PYTHON_ARGS=-3.11"
        exit /b 0
    )

    py -3 -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "BASE_PYTHON_EXE=py"
        set "BASE_PYTHON_ARGS=-3"
        exit /b 0
    )
)

where python >nul 2>nul
if not errorlevel 1 (
    python -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "BASE_PYTHON_EXE=python"
        set "BASE_PYTHON_ARGS="
        exit /b 0
    )
)

echo ERROR: No usable Python launcher was found on PATH.
echo Run scripts\first_run_fullstack.bat after installing Python 3.11 or newer.
exit /b 1
