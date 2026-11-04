@echo off
chcp 65001 >nul
cd /d "%~dp0"
title J.A.R.V.I.S. selftest
".venv\Scripts\python.exe" selftest.py
