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
:: Available smart small models (1.5B-3B params, ~2-4GB RAM):
::   - llama3.2:3b (default, good for conversation)
::   - qwen2.5-coder:1.5b-base (coding only, no chat)
::   - guzesqdro/Claude_Sonnet_4.6_Reduced:latest (smarter, Claude-based)
set OLLAMA_MODEL=llama3.2:3b
set MAX_RAM_FOR_OLLAMA=1500

:: Disable GPU acceleration (not available on most small machines)
set OLLAMA_ACCELERATE=off

:: Use D: drive for Ollama models (where your models are installed)
set OLLAMA_MODELS=D:\OllamaModels\.ollama\models
set OLLAMA_HOST=127.0.0.1:11434

:: Use E: drive for HuggingFace cache (Whisper needs ~500MB)
set HF_HOME=E:\.huggingface
set TRANSFORMERS_CACHE=E:\.cache\transformers

:: Use E: drive for JARVIS Vault (notes, memory, skills)
set OPERATOR_VAULT_EXTERNAL=E:\JarvisVault

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
echo   Ollama Models: D:\OllamaModels\.ollama\models
echo   Vault: E:\JarvisVault
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
