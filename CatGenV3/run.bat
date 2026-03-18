@echo off
setlocal
cd /d "%~dp0"

:: Try to find python.exe using 'where' command
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python not found in system PATH.
    echo Please install Python 3.8+ from https://www.python.org and add it to PATH.
    pause
    exit /b 1
)

:: Run the self-configuring launcher/installer
python launcher.py

endlocal
