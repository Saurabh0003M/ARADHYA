@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"

pushd "%PROJECT_ROOT%" >nul

set /a FAILURES=0
set /a WARNINGS=0
set "BASE_PYTHON_EXE="
set "BASE_PYTHON_ARGS="
set "BASE_PYTHON_LABEL="
set "BASE_PYTHON_PATH="
set "BASE_PYTHON_VERSION="
set "CONFIGURED_MODEL="

echo ========================================
echo Aradhya Doctor
echo ========================================
echo Project root: %PROJECT_ROOT%
echo.

call :detect_python
if errorlevel 1 (
    echo [WARN] Base Python launcher not found on PATH.
    echo        The current venv can still run Aradhya, but you will need Python 3.10 or newer on PATH to recreate it later.
    set /a WARNINGS+=1
) else (
    call :report_python
)

call :report_venv
call :report_requirements_freshness
call :read_configured_model
call :report_ollama

echo.
echo Summary: !FAILURES! failure(s), !WARNINGS! warning(s).
if !FAILURES! GTR 0 (
    echo Doctor found blocking setup issues.
    popd >nul
    exit /b 1
)

if !WARNINGS! GTR 0 (
    echo Doctor found non-blocking setup warnings.
    popd >nul
    exit /b 0
)

echo Doctor found no setup issues.
popd >nul
exit /b 0

:detect_python
where py >nul 2>nul
if not errorlevel 1 (
    py -3.10 -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "BASE_PYTHON_EXE=py"
        set "BASE_PYTHON_ARGS=-3.10"
        set "BASE_PYTHON_LABEL=py -3.10"
        goto :detect_python_done
    )

    py -3 -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "BASE_PYTHON_EXE=py"
        set "BASE_PYTHON_ARGS=-3"
        set "BASE_PYTHON_LABEL=py -3"
        goto :detect_python_done
    )

    py -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "BASE_PYTHON_EXE=py"
        set "BASE_PYTHON_LABEL=py"
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

exit /b 1

:detect_python_done
set "ARADHYA_TMP_FILE=%TEMP%\aradhya_base_python_path.txt"
if defined BASE_PYTHON_ARGS (
    "%BASE_PYTHON_EXE%" %BASE_PYTHON_ARGS% -c "import sys; print(sys.executable)" > "%ARADHYA_TMP_FILE%"
) else (
    "%BASE_PYTHON_EXE%" -c "import sys; print(sys.executable)" > "%ARADHYA_TMP_FILE%"
)
set /p BASE_PYTHON_PATH=<"%ARADHYA_TMP_FILE%"
del "%ARADHYA_TMP_FILE%" >nul 2>nul

exit /b 0

:report_python
set "ARADHYA_TMP_FILE=%TEMP%\aradhya_base_python_version.txt"
if defined BASE_PYTHON_ARGS (
    "%BASE_PYTHON_EXE%" %BASE_PYTHON_ARGS% -c "import sys; print('.'.join(str(part) for part in sys.version_info[:3]))" > "%ARADHYA_TMP_FILE%"
    "%BASE_PYTHON_EXE%" %BASE_PYTHON_ARGS% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
) else (
    "%BASE_PYTHON_EXE%" -c "import sys; print('.'.join(str(part) for part in sys.version_info[:3]))" > "%ARADHYA_TMP_FILE%"
    "%BASE_PYTHON_EXE%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
)
set /p BASE_PYTHON_VERSION=<"%ARADHYA_TMP_FILE%"
del "%ARADHYA_TMP_FILE%" >nul 2>nul

if errorlevel 1 (
    echo [FAIL] Base Python is !BASE_PYTHON_VERSION! at !BASE_PYTHON_PATH!.
    echo        Aradhya expects Python 3.10 or newer.
    set /a FAILURES+=1
    exit /b 0
)

echo [PASS] Base Python is !BASE_PYTHON_VERSION! at !BASE_PYTHON_PATH!.
exit /b 0

:report_venv
if not exist "venv\Scripts\python.exe" (
    echo [FAIL] Local virtual environment is missing.
    echo        Next step: scripts\first_run.bat
    set /a FAILURES+=1
    exit /b 0
)

"venv\Scripts\python.exe" -c "import sys" >nul 2>nul
if errorlevel 1 (
    echo [FAIL] Local virtual environment exists, but its interpreter is broken.
    echo        Next step: scripts\first_run.bat
    set /a FAILURES+=1
    exit /b 0
)

echo [PASS] Virtual environment interpreter is available.

"venv\Scripts\python.exe" -m pip --version >nul 2>nul
if errorlevel 1 (
    echo [FAIL] pip is missing from the local virtual environment.
    echo        Next step: scripts\first_run.bat
    set /a FAILURES+=1
) else (
    echo [PASS] pip is available inside the local virtual environment.
)

"venv\Scripts\python.exe" -c "import requests, dotenv, yaml, loguru" >nul 2>nul
if errorlevel 1 (
    echo [FAIL] Core runtime dependencies are missing from the local virtual environment.
    echo        Next step: scripts\first_run.bat
    set /a FAILURES+=1
) else (
    echo [PASS] Core runtime dependencies are installed.
)

"venv\Scripts\python.exe" -c "import pytest" >nul 2>nul
if errorlevel 1 (
    echo [WARN] Development test dependencies are not installed.
    echo        Next step: venv\Scripts\python.exe -m pip install -r requirements-dev.txt
    set /a WARNINGS+=1
) else (
    echo [PASS] Development test dependencies are installed.
)

exit /b 0

:report_requirements_freshness
if not exist "venv\Scripts\python.exe" exit /b 0

if not exist "venv\.aradhya_deps_stamp" (
    echo [WARN] Dependency freshness stamp is missing.
    echo        Next step: scripts\first_run.bat
    set /a WARNINGS+=1
    exit /b 0
)

powershell -NoProfile -Command "$stamp = Get-Item -LiteralPath 'venv/.aradhya_deps_stamp'; $requirements = @('requirements.txt', 'requirements-dev.txt') | ForEach-Object { Get-Item -LiteralPath $_ }; if ($requirements | Where-Object { $_.LastWriteTime -gt $stamp.LastWriteTime }) { exit 1 } else { exit 0 }" >nul 2>nul
if errorlevel 1 (
    echo [WARN] requirements files changed after the last recorded install.
    echo        Next step: scripts\first_run.bat
    set /a WARNINGS+=1
) else (
    echo [PASS] requirements files are not newer than the last recorded install.
)

exit /b 0

:read_configured_model
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$ErrorActionPreference = 'Stop'; $model = ''; $sharedPath = 'core/memory/profile.json'; if (Test-Path $sharedPath) { $shared = Get-Content $sharedPath -Raw | ConvertFrom-Json; if ($shared.model -and $shared.model.model_name) { $model = $shared.model.model_name } }; $localPath = 'core/memory/profile.local.json'; if (Test-Path $localPath) { $local = Get-Content $localPath -Raw | ConvertFrom-Json; if ($local.model -and $local.model.model_name) { $model = $local.model.model_name } }; if (-not $model) { $model = 'gemma4:e4b' }; Write-Output $model"`) do set "CONFIGURED_MODEL=%%I"

if defined CONFIGURED_MODEL (
    echo [INFO] Configured model: !CONFIGURED_MODEL!
)

exit /b 0

:report_ollama
where ollama >nul 2>nul
if errorlevel 1 (
    echo [WARN] Ollama is not available on PATH.
    echo        Install Ollama from https://ollama.com/download
    set /a WARNINGS+=1
    exit /b 0
)

echo [PASS] Ollama command is available.

ollama list >nul 2>nul
if errorlevel 1 (
    echo [WARN] Ollama is installed, but the local service is not responding yet.
    echo        Start Ollama, then rerun: scripts\doctor.bat
    set /a WARNINGS+=1
    exit /b 0
)

echo [PASS] Ollama responds to local model queries.

if not defined CONFIGURED_MODEL exit /b 0

ollama list | findstr /I /C:"!CONFIGURED_MODEL!" >nul
if errorlevel 1 (
    echo [WARN] Configured model !CONFIGURED_MODEL! is not installed locally.
    echo        Next step: ollama pull !CONFIGURED_MODEL!
    set /a WARNINGS+=1
) else (
    echo [PASS] Configured model !CONFIGURED_MODEL! is installed locally.
)

exit /b 0
