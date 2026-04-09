@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"

pushd "%PROJECT_ROOT%" >nul

set "BASE_PYTHON_EXE="
set "BASE_PYTHON_ARGS="
set "BASE_PYTHON_LABEL="
set "BASE_PYTHON_PATH="
set "BASE_PYTHON_VERSION="
set "HAVE_HEALTHY_VENV=0"

echo ========================================
echo Aradhya First Run
echo ========================================
echo Project root: %PROJECT_ROOT%
echo.

call :venv_is_healthy
if not errorlevel 1 (
    set "HAVE_HEALTHY_VENV=1"
    echo Existing virtual environment looks healthy.
)

if "!HAVE_HEALTHY_VENV!"=="0" (
    call :detect_python
    if errorlevel 1 goto :fail

    call :check_python_version
    if errorlevel 1 goto :fail

    call :prepare_venv
    if errorlevel 1 goto :fail
)

echo.
echo Installing core dependencies into %PROJECT_ROOT%\venv ...
call :run_venv_python -m pip install --upgrade pip
if errorlevel 1 goto :fail

call :run_venv_python -m pip install -r requirements.txt
if errorlevel 1 goto :fail

call :run_venv_python -m pip install -r requirements-dev.txt
if errorlevel 1 goto :fail

call :write_dependency_stamp
if errorlevel 1 goto :fail

echo.
call "scripts\doctor.bat"
set "DOCTOR_EXIT=!ERRORLEVEL!"

echo.
echo Optional next steps:
echo   venv\Scripts\python.exe -m pip install -r requirements-voice.txt
echo   venv\Scripts\python.exe -m pip install -r requirements-voice-activation.txt
echo.

if "!DOCTOR_EXIT!"=="0" (
    echo Base setup is complete.
    echo Start Aradhya with:
    echo   venv\Scripts\python.exe -m core.agent.aradhya
) else (
    echo Base Python setup is complete, but doctor reported remaining blockers.
    echo Resolve the items above, then rerun:
    echo   scripts\doctor.bat
)

popd >nul
exit /b !DOCTOR_EXIT!

:fail
echo.
echo First-run setup did not complete.
echo Review the message above and rerun this script after fixing it.
popd >nul
exit /b 1

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

echo ERROR: I could not find a working Python launcher on PATH.
echo Install Python 3.10 or newer, then reopen the terminal and rerun this script.
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

echo Base Python launcher: !BASE_PYTHON_LABEL!
echo Base Python path: !BASE_PYTHON_PATH!
exit /b 0

:check_python_version
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
    echo ERROR: Aradhya expects Python 3.10 or newer. Detected !BASE_PYTHON_VERSION!.
    exit /b 1
)

echo Base Python version: !BASE_PYTHON_VERSION!
exit /b 0

:venv_is_healthy
if not exist "venv\Scripts\python.exe" exit /b 1

"venv\Scripts\python.exe" -c "import sys" >nul 2>nul
if errorlevel 1 exit /b 1

"venv\Scripts\python.exe" -m pip --version >nul 2>nul
if errorlevel 1 exit /b 1

exit /b 0

:prepare_venv
if exist "venv\Scripts\python.exe" (
    call :venv_is_healthy
    if not errorlevel 1 exit /b 0

    echo Existing virtual environment is broken. Recreating it...
    if exist "%PROJECT_ROOT%\venv" rmdir /s /q "%PROJECT_ROOT%\venv"
)

echo Creating local virtual environment at %PROJECT_ROOT%\venv ...
if defined BASE_PYTHON_ARGS (
    "%BASE_PYTHON_EXE%" %BASE_PYTHON_ARGS% -m venv venv
) else (
    "%BASE_PYTHON_EXE%" -m venv venv
)

if errorlevel 1 (
    echo ERROR: Failed to create the virtual environment.
    exit /b 1
)

exit /b 0

:write_dependency_stamp
> "venv\.aradhya_deps_stamp" (
    echo requirements.txt
    echo requirements-dev.txt
    echo %DATE% %TIME%
)

exit /b 0

:run_venv_python
"venv\Scripts\python.exe" %*
exit /b %ERRORLEVEL%
