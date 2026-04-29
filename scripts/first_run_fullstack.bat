@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"

pushd "%PROJECT_ROOT%" >nul

set "PYTHON_MODE="
set "BASE_PYTHON_EXE="
set "BASE_PYTHON_ARGS="
set "BASE_PYTHON_LABEL="
set "BASE_PYTHON_PATH="
set "BASE_PYTHON_VERSION="
set "NPM_VERSION="

if /I "%~1"=="--isolated" set "PYTHON_MODE=isolated"
if /I "%~1"=="--system" set "PYTHON_MODE=system"

echo ========================================
echo Aradhya Full-Stack First Run
echo ========================================
echo Project root: %PROJECT_ROOT%
echo.

if not defined PYTHON_MODE (
    call :prompt_python_mode
    if errorlevel 1 goto :fail
)

call :detect_python
if errorlevel 1 goto :fail

call :check_python_version
if errorlevel 1 goto :fail

call :detect_npm
if errorlevel 1 goto :fail

call :ensure_backend_env
if errorlevel 1 goto :fail

call :ensure_frontend_env
if errorlevel 1 goto :fail

if /I "!PYTHON_MODE!"=="isolated" (
    call :prepare_backend_venv
    if errorlevel 1 goto :fail
) else (
    echo [WARN] Backend packages will be installed into the detected Python environment.
)

echo.
echo Installing backend dependencies...
call :run_backend_python -m pip install --upgrade pip
if errorlevel 1 goto :fail

call :run_backend_python -m pip install -r backend\requirements.txt
if errorlevel 1 goto :fail

echo.
echo Installing frontend dependencies...
pushd "frontend" >nul
call npm install
set "NPM_EXIT=!ERRORLEVEL!"
popd >nul
if not "!NPM_EXIT!"=="0" goto :fail

echo.
echo Validating backend imports...
call :run_backend_python -m py_compile backend\server.py
if errorlevel 1 goto :fail

powershell -NoProfile -Command "$pkg = Get-Content 'frontend/package.json' -Raw | ConvertFrom-Json; if (-not $pkg.name -or -not $pkg.scripts) { exit 1 } else { exit 0 }" >nul 2>nul
if errorlevel 1 (
    echo ERROR: frontend\package.json is missing required fields.
    goto :fail
)

echo.
echo Full-stack setup is complete.
echo Backend Python mode: !PYTHON_MODE!
echo Workspace search defaults stay inside the current user's home folder and this cloned repo root.
echo They do not scan the whole drive unless you add custom roots in core\memory\preferences.json.
echo.
echo Next step:
echo   scripts\run_fullstack.bat
echo.

popd >nul
exit /b 0

:fail
echo.
echo Full-stack setup did not complete.
echo Review the error above, install any missing tools, and rerun this script.
popd >nul
exit /b 1

:prompt_python_mode
echo Choose backend Python environment:
echo   [I] Isolated virtual environment (.venv-backend) - recommended
echo   [N] Normal/current Python environment
choice /C IN /D I /T 15 /N /M "Selection"
if errorlevel 2 (
    set "PYTHON_MODE=system"
) else (
    set "PYTHON_MODE=isolated"
)
echo Selected backend mode: !PYTHON_MODE!
echo.
exit /b 0

:detect_python
where py >nul 2>nul
if not errorlevel 1 (
    py -3.12 -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "BASE_PYTHON_EXE=py"
        set "BASE_PYTHON_ARGS=-3.12"
        set "BASE_PYTHON_LABEL=py -3.12"
        goto :detect_python_done
    )

    py -3.11 -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "BASE_PYTHON_EXE=py"
        set "BASE_PYTHON_ARGS=-3.11"
        set "BASE_PYTHON_LABEL=py -3.11"
        goto :detect_python_done
    )

    py -3 -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "BASE_PYTHON_EXE=py"
        set "BASE_PYTHON_ARGS=-3"
        set "BASE_PYTHON_LABEL=py -3"
        goto :detect_python_done
    )
)

where python >nul 2>nul
if not errorlevel 1 (
    python -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "BASE_PYTHON_EXE=python"
        set "BASE_PYTHON_LABEL=python"
        goto :detect_python_done
    )
)

echo ERROR: I could not find a working Python launcher on PATH.
echo Install Python 3.11 or newer, then reopen the terminal and rerun this script.
exit /b 1

:detect_python_done
set "ARADHYA_TMP_FILE=%TEMP%\aradhya_fullstack_python_path.txt"
if defined BASE_PYTHON_ARGS (
    "%BASE_PYTHON_EXE%" %BASE_PYTHON_ARGS% -c "import sys; print(sys.executable)" > "%ARADHYA_TMP_FILE%"
) else (
    "%BASE_PYTHON_EXE%" -c "import sys; print(sys.executable)" > "%ARADHYA_TMP_FILE%"
)
set /p BASE_PYTHON_PATH=<"%ARADHYA_TMP_FILE%"
del "%ARADHYA_TMP_FILE%" >nul 2>nul

echo Base Python launcher: !BASE_PYTHON_LABEL!
echo Base Python path: !BASE_PYTHON_PATH!
exit /b 0

:check_python_version
set "ARADHYA_TMP_FILE=%TEMP%\aradhya_fullstack_python_version.txt"
if defined BASE_PYTHON_ARGS (
    "%BASE_PYTHON_EXE%" %BASE_PYTHON_ARGS% -c "import sys; print('.'.join(str(part) for part in sys.version_info[:3]))" > "%ARADHYA_TMP_FILE%"
    "%BASE_PYTHON_EXE%" %BASE_PYTHON_ARGS% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
) else (
    "%BASE_PYTHON_EXE%" -c "import sys; print('.'.join(str(part) for part in sys.version_info[:3]))" > "%ARADHYA_TMP_FILE%"
    "%BASE_PYTHON_EXE%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
)
set /p BASE_PYTHON_VERSION=<"%ARADHYA_TMP_FILE%"
del "%ARADHYA_TMP_FILE%" >nul 2>nul

if errorlevel 1 (
    echo ERROR: Aradhya expects Python 3.11 or newer. Detected !BASE_PYTHON_VERSION!.
    exit /b 1
)

echo Base Python version: !BASE_PYTHON_VERSION!
exit /b 0

:detect_npm
where npm >nul 2>nul
if errorlevel 1 (
    echo ERROR: npm is not available on PATH.
    echo Install Node.js LTS from https://nodejs.org/ and rerun this script.
    exit /b 1
)

for /f "usebackq delims=" %%I in (`npm --version`) do set "NPM_VERSION=%%I"
echo npm version: !NPM_VERSION!
exit /b 0

:ensure_backend_env
if not exist "backend\.env" (
    copy /Y "backend\.env.example" "backend\.env" >nul
    echo Created backend\.env from backend\.env.example
)
exit /b 0

:ensure_frontend_env
if not exist "frontend\.env.local" (
    copy /Y "frontend\.env.example" "frontend\.env.local" >nul
    echo Created frontend\.env.local from frontend\.env.example
)
exit /b 0

:prepare_backend_venv
if exist ".venv-backend\Scripts\python.exe" (
    ".venv-backend\Scripts\python.exe" -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        echo Reusing existing backend virtual environment.
        exit /b 0
    )

    echo Existing backend virtual environment is broken. Recreating it...
    rmdir /s /q ".venv-backend"
)

echo Creating backend virtual environment at %PROJECT_ROOT%\.venv-backend ...
call :run_base_python -m venv .venv-backend
if errorlevel 1 (
    echo ERROR: Failed to create .venv-backend.
    exit /b 1
)
exit /b 0

:run_base_python
if defined BASE_PYTHON_ARGS (
    "%BASE_PYTHON_EXE%" %BASE_PYTHON_ARGS% %*
) else (
    "%BASE_PYTHON_EXE%" %*
)
exit /b %ERRORLEVEL%

:run_backend_python
if /I "!PYTHON_MODE!"=="isolated" (
    ".venv-backend\Scripts\python.exe" %*
) else (
    call :run_base_python %*
)
exit /b %ERRORLEVEL%
