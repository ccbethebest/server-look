@echo off
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0install.ps1" -ChooseDirectory -Launch
if errorlevel 1 pause
