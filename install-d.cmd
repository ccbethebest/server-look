@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -InstallDirectory "D:\ServerLook" -Launch
if errorlevel 1 pause
