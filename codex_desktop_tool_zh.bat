@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0codex_desktop_tool_zh.ps1"
if errorlevel 1 pause
