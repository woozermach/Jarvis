@echo off
chcp 65001 >nul
cd /d "%~dp0"
title J.A.R.V.I.S. debug
".venv\Scripts\python.exe" jarvis.py --console
echo.
echo Джарвис завершил работу. Ошибки — выше и в jarvis.log
pause
