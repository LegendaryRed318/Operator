# start_operator_silent.ps1 - Launch Operator with hidden windows
# Run with: powershell -WindowStyle Hidden -File "C:\Projects\Operator\start_operator_silent.ps1"

$ErrorActionPreference = "SilentlyContinue"

# Change to Operator directory
Set-Location -Path "C:\Projects\Operator"

# Create required directories
@("database", "logs", "test_logs", "models", "skills") | ForEach-Object {
    if (!(Test-Path $_)) { New-Item -ItemType Directory -Path $_ -Force | Out-Null }
}

# Environment Configuration for Ollama
$env:OLLAMA_MODELS = "D:\OllamaModels\.ollama\models"
$env:OLLAMA_URL = "http://localhost:11434"

# Get pythonw path
$pythonw = "C:\Projects\Operator\backend\venv\Scripts\pythonw.exe"
$python = "C:\Projects\Operator\backend\venv\Scripts\python.exe"

# Helper function to start hidden process
function Start-HiddenProcess {
    param(
        [string]$FilePath,
        [string]$Arguments,
        [string]$WorkingDirectory = "C:\Projects\Operator"
    )
    
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.Arguments = $Arguments
    $psi.WorkingDirectory = $WorkingDirectory
    $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $psi.CreateNoWindow = $true
    $psi.UseShellExecute = $false
    
    [System.Diagnostics.Process]::Start($psi) | Out-Null
}

Write-Host "[Operator] Starting services silently..."

# 1. HTTP API Server
Start-HiddenProcess -FilePath $pythonw -Arguments "backend\server.py" -WorkingDirectory "C:\Projects\Operator"
Write-Host "[Operator] API Server started (port 5050)"
Start-Sleep -Seconds 2

# 2. WebSocket Server
Start-HiddenProcess -FilePath $pythonw -Arguments "backend\ws_server.py" -WorkingDirectory "C:\Projects\Operator"
Write-Host "[Operator] WebSocket Server started (port 8765)"
Start-Sleep -Seconds 2

# 3. File Watcher
Start-HiddenProcess -FilePath $pythonw -Arguments "backend\watcher.py" -WorkingDirectory "C:\Projects\Operator"
Write-Host "[Operator] File Watcher started"
Start-Sleep -Seconds 2

# 4. Project Launcher
Start-HiddenProcess -FilePath $pythonw -Arguments "backend\project_launcher.py" -WorkingDirectory "C:\Projects\Operator"
Write-Host "[Operator] Project Launcher started"
Start-Sleep -Seconds 3

# 5. Frontend (Vite) - using npm with hidden window
$npmCmd = "cd C:\Projects\Operator\frontend && npm run dev"
Start-HiddenProcess -FilePath "cmd.exe" -Arguments "/c $npmCmd" -WorkingDirectory "C:\Projects\Operator"
Write-Host "[Operator] Frontend started (port 8081)"
Start-Sleep -Seconds 3

# 6. Tray Icon (try pythonw first, fall back to python)
Start-HiddenProcess -FilePath $pythonw -Arguments "backend\tray.py" -WorkingDirectory "C:\Projects\Operator"
Write-Host "[Operator] Tray Icon started"

# Keep script running to maintain tray
Write-Host "Press Ctrl+C to stop all services..."
Write-Host "- Dashboard: http://localhost:8081"
Write-Host "- WebSocket: ws://localhost:8765"
Write-Host "- API: http://localhost:5050"
Write-Host "- Jarvis ready (click orb to speak)`n"

# Keep script running to maintain tray
Write-Host "Press Ctrl+C to stop all services..."
while ($true) {
    Start-Sleep -Seconds 60
}
