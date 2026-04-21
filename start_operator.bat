@echo off
setlocal EnableDelayedExpansion

cd /d C:\Projects\Operator

REM Environment Configuration for Ollama
set OLLAMA_MODELS=D:\OllamaModels\.ollama\models
set OLLAMA_URL=http://localhost:11434

REM Check for help flag
if "%~1"=="--help" goto :show_help

goto :launch

:show_help
echo.
echo Usage: start_operator.bat [option]
echo.
echo Options:
echo   --help       Show this help message
echo   (none)       Launch all services + remote access
echo.
echo Your permanent JARVIS URL:
echo   https://dry-handcraft-dusk.ngrok-free.dev
echo.
echo Username: olami
echo Password: Red2026 
pause
exit /b

:launch
echo Starting Operator (JARVIS) + Remote Access...
echo.

REM Create folders
if not exist "database" mkdir database
if not exist "logs" mkdir logs
if not exist "test_logs" mkdir test_logs
if not exist "models" mkdir models
if not exist "skills" mkdir skills

REM Start all normal services
python launcher.py

echo.
echo ========================================
echo Starting ngrok remote access...
echo ========================================
echo Permanent URL: https://dry-handcraft-dusk.ngrok-free.dev
echo.

REM Start ngrok with your permanent easy URL
start "" cmd /k "ngrok http 8081 --basic-auth olami:Red2026 --url dry-handcraft-dusk.ngrok-free.dev"

echo.
echo ✅ JARVIS is now running locally AND remotely!
echo Open https://dry-handcraft-dusk.ngrok-free.dev on your phone or at school.
pause
exit /b