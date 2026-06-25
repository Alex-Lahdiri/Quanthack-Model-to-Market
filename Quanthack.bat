@echo off
REM Double-click this to open the Quanthack control panel.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0quanthack.ps1"
pause
