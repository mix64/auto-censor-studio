@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto install
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -m venv .venv
) else (
    python -m venv .venv
)
if errorlevel 1 (
    echo Install Python 3.12 or later, then run build_win.bat again.
    goto fail
)

:install
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -e ".[dev]"
if errorlevel 1 (
    echo Could not install the build dependencies.
    goto fail
)

".venv\Scripts\python.exe" tools\build_exe.py
if errorlevel 1 (
    echo Build failed.
    goto fail
)

echo.
echo Built: dist\AutoCensorStudio\AutoCensorStudio.exe
pause
exit /b 0

:fail
pause
exit /b 1
