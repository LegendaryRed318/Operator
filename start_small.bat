@echo off
:: start_small.bat - Launch JARVIS in small mode (current machine)
:: Sets conservative limits for low-end hardware
:: Usage: Double-click this file or run from terminal

echo ================================================
echo   JARVIS Operator - SMALL MODE
echo   Current Machine Configuration
echo ================================================
echo.

:: Set mode to small
set JARVIS_MODE=small

:: AI Settings - Small machine limits
set OLLAMA_MODEL=qwen2.5-coder:1.5b-base
set MAX_RAM_FOR_OLLAMA=1500

:: Disable GPU acceleration (not available on most small machines)
set OLLAMA_ACCELERATE=off

:: Disable remote access features
set ENABLE_REMOTE_ACCESS=false

:: Python path (use venv if available)
set PYTHON_PATH=%~dp0backend\venv\Scripts\python.exe
if not exist "%PYTHON_PATH%" set PYTHON_PATH=python

:: Launch using launcher.py
echo Starting JARVIS in SMALL mode...
echo   Mode: %JARVIS_MODE%
echo   AI Model: %OLLAMA_MODEL%
echo   Max RAM: %MAX_RAM_FOR_OLLAMA%MB
echo.
echo Starting all services...
python "%~dp0launcher.py"

:: If launcher.py fails, try direct start
if errorlevel 1 (
    echo.
    echo Launcher failed. Trying direct start...
    echo.

    :: Start backend services in separate windows (visible for debugging)
    start "JARVIS API" cmd /k "cd /d %~dp0backend && %PYTHON_PATH% server.py"

    timeout /t 2 >nul

    start "JARVIS WS" cmd /k "cd /d %~dp0backend && %PYTHON_PATH% ws_server.py"

    timeout /t 2 >nul

    start "JARVIS Watcher" cmd /k "cd /d %~dp0backend && %PYTHON_PATH% watcher.py"

    timeout /t 2 >nul

    :: Start frontend
    cd /d %~dp0frontend
    call npm run dev

    cd /d %~dp0
)

pause
