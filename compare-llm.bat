@echo off
rem FSP Scout - compare rule-based parsing with a local LLM (start llama-server first)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\compare-llm.ps1" %*
pause
