@echo off
setlocal EnableDelayedExpansion

cd /d C:\Projects\Operator

REM Check for help flag
if "%~1"=="--help" goto :show_help

REM Default: Launch via launcher.py (silent background mode)
goto :launch

:show_help
echo.
echo Usage: start_operator.bat [option]
echo.
echo Options:
echo   --help       Show this help message
echo   (none)       Launch all services silently in background (default)
echo.
echo Features:
echo   - No visible console windows for services
echo   - All output logged to C:\Projects\Operator\logs\
echo   - Graceful shutdown on Ctrl+C
echo.
echo Dashboard URLs:
echo   - http://localhost:8080 (Frontend)
echo   - http://localhost:5050 (API)
echo   - ws://localhost:8765 (WebSocket)
echo.
pause
exit /b

:launch
echo Starting Operator (Jarvis) in silent mode...
echo All services will run in the background.
echo Logs: C:\Projects\Operator\logs\
echo.
echo Press Ctrl+C to stop all services gracefully.
echo.

REM Create required directories
if not exist "database" mkdir database
if not exist "logs" mkdir logs
if not exist "test_logs" mkdir test_logs
if not exist "models" mkdir models
if not exist "skills" mkdir skills

REM Run the launcher (this will show output but services are hidden)
python launcher.py

exit /b
