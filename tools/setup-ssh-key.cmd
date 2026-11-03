@echo off
rem Double-click to run the veil SSH key setup.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-ssh-key.ps1"
echo.
pause
