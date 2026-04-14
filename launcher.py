#!/usr/bin/env python3
"""
launcher.py - Silent background launcher for Operator (Jarvis)
Starts all services without visible console windows.
Optimized for 8GB machines with proper logging.
"""

import subprocess
import sys
import os
import time
import signal
import webbrowser
from pathlib import Path
from datetime import datetime

# Configuration
ROOT_DIR = Path(__file__).parent.resolve()
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
LOGS_DIR = ROOT_DIR / "logs"

# Ensure logs directory exists
LOGS_DIR.mkdir(exist_ok=True)

# Service configurations
SERVICES = {
    "api": {
        "name": "HTTP API Server",
        "cmd": [sys.executable, str(BACKEND_DIR / "server.py")],
        "cwd": str(BACKEND_DIR),
        "log": LOGS_DIR / "api.log",
        "delay": 0,
    },
    "websocket": {
        "name": "WebSocket Server",
        "cmd": [sys.executable, str(BACKEND_DIR / "ws_server.py")],
        "cwd": str(BACKEND_DIR),
        "log": LOGS_DIR / "ws.log",
        "delay": 2,
    },
    "watcher": {
        "name": "File Watcher",
        "cmd": [sys.executable, str(BACKEND_DIR / "watcher.py")],
        "cwd": str(BACKEND_DIR),
        "log": LOGS_DIR / "watcher.log",
        "delay": 2,
    },
    "project_launcher": {
        "name": "Project Launcher",
        "cmd": [sys.executable, str(BACKEND_DIR / "project_launcher.py")],
        "cwd": str(BACKEND_DIR),
        "log": LOGS_DIR / "project_launcher.log",
        "delay": 2,
    },
    "sleep_manager": {
        "name": "Sleep Manager",
        "cmd": [sys.executable, str(BACKEND_DIR / "sleep_manager.py")],
        "cwd": str(BACKEND_DIR),
        "log": LOGS_DIR / "sleep.log",
        "delay": 3,
    },
    "frontend": {
        "name": "Frontend (Vite)",
        "cmd": ["npm", "run", "dev"],
        "cwd": str(FRONTEND_DIR),
        "log": LOGS_DIR / "frontend.log",
        "delay": 8,  # Wait for WebSocket to be ready
    },
}

# Track running processes
processes = {}
# Restart attempt counters per service
restart_counts: dict = {}


def log_message(message: str):
    """Log to main launcher log."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {message}"
    print(log_line)
    
    # Also write to launcher log
    launcher_log = LOGS_DIR / "launcher.log"
    with open(launcher_log, "a", encoding="utf-8") as f:
        f.write(log_line + "\n")


def start_service(service_id: str, config: dict) -> subprocess.Popen:
    """Start a service with hidden window and log output to file."""
    log_file = config["log"]
    
    # Write header to log file
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*60}\n")
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting {config['name']}\n")
        f.write(f"{'='*60}\n")
    
    # Open log file for subprocess stdout/stderr
    log_handle = open(log_file, "a", encoding="utf-8")
    
    # Windows creation flags for hidden window
    creationflags = subprocess.CREATE_NO_WINDOW
    
    try:
        # Use shell=True on Windows for non-executable commands like npm
        use_shell = os.name == 'nt' and config["cmd"][0] == "npm"
        
        process = subprocess.Popen(
            config["cmd"],
            cwd=config["cwd"],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            start_new_session=False,
            shell=use_shell
        )
        
        processes[service_id] = {
            "process": process,
            "config": config,
            "log_handle": log_handle,
        }
        
        log_message(f"✓ Started {config['name']} (PID: {process.pid})")
        return process
        
    except Exception as e:
        log_message(f"✗ Failed to start {config['name']}: {e}")
        log_handle.close()
        raise


def stop_all_services():
    """Gracefully stop all running services."""
    log_message("\nShutting down all services...")
    
    # Stop in reverse order
    for service_id in reversed(list(processes.keys())):
        info = processes[service_id]
        process = info["process"]
        config = info["config"]
        
        log_message(f"Stopping {config['name']} (PID: {process.pid})...")
        
        try:
            # Try graceful termination first
            process.terminate()
            
            # Wait up to 5 seconds for graceful shutdown
            try:
                process.wait(timeout=5)
                log_message(f"  ✓ {config['name']} stopped gracefully")
            except subprocess.TimeoutExpired:
                # Force kill if not terminated
                log_message(f"  ⚠ {config['name']} not responding, forcing kill...")
                process.kill()
                process.wait()
                log_message(f"  ✓ {config['name']} killed")
                
        except Exception as e:
            log_message(f"  ✗ Error stopping {config['name']}: {e}")
        finally:
            # Close log file handle
            try:
                info["log_handle"].close()
            except:
                pass
    
    processes.clear()
    log_message("All services stopped.")


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    log_message(f"\nReceived signal {signum}, initiating shutdown...")
    stop_all_services()
    sys.exit(0)


MAX_RESTARTS = 3
RESTART_BACKOFF = [5, 15, 30]  # seconds between restart attempts


def check_service_health():
    """Check if any services have crashed; restart them with exponential backoff."""
    crashed = []
    for service_id, info in list(processes.items()):
        process = info["process"]
        if process.poll() is not None:
            exit_code = process.returncode
            config = info["config"]
            log_message(f"⚠ {config['name']} has exited (code: {exit_code})")
            crashed.append(service_id)

            try:
                info["log_handle"].close()
            except Exception:
                pass

    for service_id in crashed:
        del processes[service_id]
        attempts = restart_counts.get(service_id, 0)
        if attempts < MAX_RESTARTS:
            delay = RESTART_BACKOFF[min(attempts, len(RESTART_BACKOFF) - 1)]
            config = SERVICES[service_id]
            log_message(f"↻ Restarting {config['name']} in {delay}s (attempt {attempts + 1}/{MAX_RESTARTS})...")
            time.sleep(delay)
            try:
                start_service(service_id, config)
                restart_counts[service_id] = attempts + 1
            except Exception as e:
                log_message(f"✗ Failed to restart {config['name']}: {e}")
        else:
            log_message(f"✗ {SERVICES[service_id]['name']} has crashed {MAX_RESTARTS} times — giving up.")

    return len(crashed) == 0


def main():
    """Main launcher function."""
    log_message("=" * 60)
    log_message("Operator (Jarvis) Silent Launcher")
    log_message(f"Root Directory: {ROOT_DIR}")
    log_message(f"Logs Directory: {LOGS_DIR}")
    log_message("=" * 60)
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # On Windows, also handle CTRL_CLOSE_EVENT
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, signal_handler)
    
    try:
        # Ensure required directories exist
        for dir_name in ["database", "models", "skills", "test_logs"]:
            (ROOT_DIR / dir_name).mkdir(exist_ok=True)
        
        # Create default config if missing
        config_file = BACKEND_DIR / "config.json"
        if not config_file.exists():
            config_file.write_text('{"watched_folders": ["C:/Projects/Operator/test_logs"]}')
            log_message("Created default config.json")
        
        # Activate virtual environment if it exists
        venv_python = BACKEND_DIR / "venv" / "Scripts" / "python.exe"
        if venv_python.exists():
            log_message("Using virtual environment Python")
            # Update Python path for services
            for service in SERVICES.values():
                if service["cmd"][0] == sys.executable:
                    service["cmd"][0] = str(venv_python)
        
        # Start services in order
        log_message("\nStarting services...")
        
        for service_id, config in SERVICES.items():
            # Wait for specified delay before starting
            if config["delay"] > 0:
                log_message(f"Waiting {config['delay']}s before starting {config['name']}...")
                time.sleep(config["delay"])
            
            start_service(service_id, config)
        
        log_message("\n╔══════════════════════════════════════╗")
        log_message("║     JARVIS SYSTEM GUARDIAN v1.0      ║")
        log_message("║          OPERATOR ONLINE             ║")
        log_message("╠══════════════════════════════════════╣")
        log_message("║  Dashboard: http://localhost:8081    ║")
        log_message("║  API:       http://localhost:5050    ║")
        log_message("║  WebSocket: ws://localhost:8765      ║")
        log_message("╚══════════════════════════════════════╝\n")
        log_message("Press Ctrl+C to stop all services gracefully.")

        # Auto-open dashboard once the frontend dev server is ready
        log_message("Waiting 12s for frontend to initialise before opening browser...")
        time.sleep(12)
        webbrowser.open("http://localhost:8081")
        log_message("Browser opened → http://localhost:8081")
        
        # Monitor services
        while True:
            time.sleep(5)
            check_service_health()
            
    except KeyboardInterrupt:
        log_message("\nKeyboard interrupt received...")
        stop_all_services()
        
    except Exception as e:
        log_message(f"\nLauncher error: {e}")
        stop_all_services()
        sys.exit(1)


if __name__ == "__main__":
    main()
