@echo off
echo =============================================
echo  Frog Mod Editor - EXE Builder
echo =============================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0source\build_launcher.ps1"

echo.
pause
