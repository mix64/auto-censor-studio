@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\.installed" goto models

if exist ".venv\Scripts\python.exe" goto install
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -m venv .venv
) else (
    python -m venv .venv
)
if errorlevel 1 (
    echo Install Python 3.12 or later, then run Start.cmd again.
    goto fail
)

:install
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -e .
if errorlevel 1 (
    echo Could not install Auto Censor Studio.
    goto fail
)
type nul > ".venv\.installed"

:models
".venv\Scripts\python.exe" -m auto_censor_studio.models
if errorlevel 1 (
    echo Could not prepare the models.
    goto fail
)

start "" ".venv\Scripts\pythonw.exe" -m auto_censor_studio
exit /b 0

:fail
pause
exit /b 1
