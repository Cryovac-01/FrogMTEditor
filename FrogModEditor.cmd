@echo off
:: =============================================
::  Frog Mod Editor Launcher
:: =============================================
::  Double-click to launch the editor.
::  To build an optional .exe, run: FrogModEditor.cmd /build
:: =============================================

if /i "%~1"=="/build" goto :build

:: --- Normal launch mode ---
set "PYTHONW=%~dp0source\python\pythonw.exe"
set "PYTHON=%~dp0source\python\python.exe"
set "APP=%~dp0source\src\native_qt_app.py"

if not exist "%APP%" (
    echo ERROR: Could not find %APP%
    echo Make sure this file is next to the 'source' folder.
    pause
    exit /b 1
)

if exist "%PYTHONW%" (
    start "" "%PYTHONW%" "%APP%"
) else if exist "%PYTHON%" (
    start "" "%PYTHON%" "%APP%"
) else (
    echo ERROR: Python runtime not found.
    echo Extract the Runtime Overlay into source\python\
    pause
    exit /b 1
)
exit /b 0

:build
:: --- EXE build mode ---
echo Building FrogModEditor.exe...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0source\build_launcher.ps1"
echo.
pause
exit /b 0
