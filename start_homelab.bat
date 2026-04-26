@echo off
:: start_homelab.bat - Launch JARVIS in homelab mode (dedicated server)
:: Unlocks full features: GPU acceleration, large models, remote access
:: Usage: Double-click this file or run from terminal

echo ================================================
echo   JARVIS Operator - HOMELAB MODE
echo   Full Power Configuration
echo ================================================
echo.

:: Set mode to homelab
set JARVIS_MODE=homelab

:: AI Settings - Full power
set OLLAMA_MODEL=qwen2.5-coder:7b
set MAX_RAM_FOR_OLLAMA=8000

:: Enable GPU acceleration (for CUDA-capable GPUs)
set OLLAMA_ACCELERATE=cuda

:: Enable remote access features
set ENABLE_REMOTE_ACCESS=true

:: Tailscale VPN (optional - set your auth key)
:: set TAILSCALE_AUTHKEY=tskey-auth-xxxxx

:: Python path (use venv if available)
set PYTHON_PATH=%~dp0backend\venv\Scripts\python.exe
if not exist "%PYTHON_PATH%" set PYTHON_PATH=python

:: Launch using launcher.py
echo Starting JARVIS in HOMELAB mode...
echo   Mode: %JARVIS_MODE%
echo   AI Model: %OLLAMA_MODEL%
echo   Max RAM: %MAX_RAM_FOR_OLLAMA%MB
echo   GPU Acceleration: %OLLAMA_ACCELERATE%
echo.
echo Starting all services...
python "%~dp0launcher.py"

:: If launcher.py fails, try direct start
if errorlevel 1 (
    echo.
    echo Launcher failed. Trying direct start...
    echo.

    :: Start backend services in separate windows
    start "JARVIS API" cmd /k "cd /d %~dp0backend && %PYTHON_PATH% server.py"

    timeout /t 2 >nul

    start "JARVIS WS" cmd /k "cd /d %~dp0backend && %PYTHON_PATH% ws_server.py"

    timeout /t 2 >nul

    start "JARVIS Watcher" cmd /k "cd /d %~dp0backend && %PYTHON_PATH% watcher.py"

    timeout /t 2 >nul

    :: Start Tailscale VPN if configured
    :: if defined TAILSCALE_AUTHKEY (
    ::     echo Starting Tailscale VPN...
    ::     start "" tailscale up --authkey=%TAILSCALE_AUTHKEY%
    :: )

    :: Start frontend
    cd /d %~dp0frontend
    call npm run dev

    cd /d %~dp0
)

pause
