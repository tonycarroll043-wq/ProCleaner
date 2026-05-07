@echo off
title ProCleaner
cd /d "%~dp0"
python main.py
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] ProCleaner failed to start.
    echo  Make sure dependencies are installed: run install.bat
    pause
)
