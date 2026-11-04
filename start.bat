@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" jarvis.py
  exit /b 0
)
chcp 65001 >nul
echo Сначала запустите install.bat
pause
