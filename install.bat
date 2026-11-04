@echo off
chcp 65001 >nul
cd /d "%~dp0"
title J.A.R.V.I.S. v2 setup
python --version >nul 2>&1
if %errorlevel%==0 (python setup_jarvis.py) else (py setup_jarvis.py)
echo.
pause
