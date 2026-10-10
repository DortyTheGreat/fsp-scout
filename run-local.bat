@echo off
rem FSP Scout - local run without Docker (needs Python 3.10+ and Node.js 20+)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dev.ps1"
pause
