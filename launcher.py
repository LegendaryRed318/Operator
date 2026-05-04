#!/usr/bin/env python3
"""
launcher.py - Silent background launcher for Operator (Jarvis)
Starts all services without visible console windows.
Mode-aware: reads JARVIS_MODE env var to adjust for small/homelab.
"""

import subprocess
import sys
import os
import time
import signal
from pathlib import Path
from datetime import datetime

# Detect mode before anything else
_JARVIS_MODE = os.getenv("JARVIS_MODE", "small").lower()
_IS_HOMELAB = _JARVIS_MODE == "homelab"

# Configuration
ROOT_DIR = Path(__file__).parent.resolve()
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
LOGS_DIR = ROOT_DIR / "logs"

# Ensure logs directory exists
LOGS_DIR.mkdir(exist_ok=True)

# Check if Ollama is already running
def is_ollama_running():
    """Check if Ollama is already running on port 11434."""
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('localhost', 11434))
        sock.close()
        return result == 0
    except:
        return False

# Service configurations
SERVICES = {
    "api": {
        "name": "HTTP API Server",
        "cmd": [sys.executable, str(BACKEND_DIR / "server.py")],
        "cwd": str(BACKEND_DIR),
        "log": LOGS_DIR / "api.log",
        "delay": 0,
    },
    "ollama": {
        "name": "Ollama LLM Server",
        "cmd": ["ollama", "serve"],
        "cwd": str(ROOT_DIR),
        "log": LOGS_DIR / "ollama.log",
        "delay": 3,
        "skip_if": is_ollama_running,  # Don't start if already running
    },
    "voice_service": {
        "name": "Voice Service (Whisper)",
        "cmd": [sys.executable, str(BACKEND_DIR / "voice_service.py")],
        "cwd": str(BACKEND_DIR),
        "log": LOGS_DIR / "voice.log",
        "delay": 5,
    },
    "websocket": {
        "name": "WebSocket Server",
        "cmd": [sys.executable, str(BACKEND_DIR / "ws_server.py")],
        "cwd": str(BACKEND_DIR),
        "log": LOGS_DIR / "ws.log",
        "delay": 15,  # Give time for ChromaDB to fully load
    },
    # DISABLED - non-essential services consuming RAM
    # "watcher": {
    #     "name": "File Watcher",
    #     "cmd": [sys.executable, str(BACKEND_DIR / "watcher.py")],
    #     "cwd": str(BACKEND_DIR),
    #     "log": LOGS_DIR / "watcher.log",
    #     "delay": 6,
    # },
    # "project_launcher": {
    #     "name": "Project Launcher",
    #     "cmd": [sys.executable, str(BACKEND_DIR / "project_launcher.py")],
    #     "cwd": str(BACKEND_DIR),
    #     "log": LOGS_DIR / "project_launcher.log",
    #     "delay": 6,
    # },
    # "sleep_manager": {
    #     "name": "Sleep Manager",
    #     "cmd": [sys.executable, str(BACKEND_DIR / "sleep_manager.py")],
    #     "cwd": str(BACKEND_DIR),
    #     "log": LOGS_DIR / "sleep.log",
    #     "delay": 7,
    # },
    "frontend": {
        "name": "Frontend (Vite)",
        # Use cmd.exe /c to run npm without spawning PowerShell window
        "cmd": ["cmd.exe", "/c", "npm", "run", "dev"],
        "cwd": str(FRONTEND_DIR),
        "log": LOGS_DIR / "frontend.log",
        "delay": 60,  # Wait for ws_server RAG indexing to finish
    },
}

# Track running processes
processes = {}
# Restart attempt counters per service
restart_counts: dict = {}
# Service start times for restart count reset (reset after 5 min of stability)
service_start_times: dict = {}
# Time after which restart count resets (5 minutes)
RESTART_RESET_SECONDS = 300


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
        # Merge service env with parent env
        service_env = {**os.environ, **(config.get("env", {}) or {})}
        process = subprocess.Popen(
            config["cmd"],
            cwd=config["cwd"],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            start_new_session=False,
            shell=False,
            env=service_env
        )
        
        processes[service_id] = {
            "process": process,
            "config": config,
            "log_handle": log_handle,
        }

        # Track start time for restart count reset logic (5 min stability = reset)
        service_start_times[service_id] = time.time()

        log_message(f"[OK] Started {config['name']} (PID: {process.pid})")
        return process
        
    except Exception as e:
        log_message(f"[FAIL] Failed to start {config['name']}: {e}")
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
                log_message(f"  [OK] {config['name']} stopped gracefully")
            except subprocess.TimeoutExpired:
                # Force kill if not terminated
                log_message(f"  [WARN] {config['name']} not responding, forcing kill...")
                process.kill()
                process.wait()
                log_message(f"  [OK] {config['name']} killed")
                
        except Exception as e:
            log_message(f"  [FAIL] Error stopping {config['name']}: {e}")
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
    """Check if any services have crashed; restart them with exponential backoff.
    Reset restart count after 5 minutes of stable operation."""
    crashed = []
    for service_id, info in list(processes.items()):
        process = info["process"]
        if process.poll() is not None:
            exit_code = process.returncode
            config = info["config"]
            log_message(f"[WARN] {config['name']} has exited (code: {exit_code})")
            crashed.append(service_id)

            try:
                info["log_handle"].close()
            except Exception:
                pass
        else:
            # Service is running — check if we should reset restart count
            start_time = service_start_times.get(service_id)
            if start_time:
                elapsed = time.time() - start_time
                if elapsed > RESTART_RESET_SECONDS and restart_counts.get(service_id, 0) > 0:
                    log_message(f"[OK] {info['config']['name']} stable for {RESTART_RESET_SECONDS//60}min — reset restart count")
                    restart_counts[service_id] = 0

    for service_id in crashed:
        del processes[service_id]
        # Remove start time tracking for crashed service
        if service_id in service_start_times:
            del service_start_times[service_id]

        attempts = restart_counts.get(service_id, 0)
        if attempts < MAX_RESTARTS:
            delay = RESTART_BACKOFF[min(attempts, len(RESTART_BACKOFF) - 1)]
            config = SERVICES[service_id]
            log_message(f"RESTARTING {config['name']} in {delay}s (attempt {attempts + 1}/{MAX_RESTARTS})...")
            time.sleep(delay)
            try:
                start_service(service_id, config)
                restart_counts[service_id] = attempts + 1
                # Track start time for restart count reset logic
                service_start_times[service_id] = time.time()
            except Exception as e:
                log_message(f"[FAIL] Failed to restart {config['name']}: {e}")
        else:
            log_message(f"[FAIL] {SERVICES[service_id]['name']} has crashed {MAX_RESTARTS} times -- giving up.")


def wait_for_port(port: int, timeout: int = 30) -> bool:
    """Wait for a local port to become active."""
    import socket
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.create_connection(("localhost", port), timeout=1):
                return True
        except (ConnectionRefusedError, socket.timeout):
            time.sleep(1)
    return False


def main():
    """Main launcher function."""
    mode_label = "HOMELAB" if _IS_HOMELAB else "SMALL"
    log_message("=" * 60)
    log_message(f"Operator (Jarvis) Silent Launcher - {mode_label} MODE")
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
            config_file.write_text('{"watched_folders": ["' + str(ROOT_DIR / "test_logs") + '"]}')
            log_message("Created default config.json")

        # Activate virtual environment if it exists
        venv_python = BACKEND_DIR / "venv" / "Scripts" / "python.exe"
        if venv_python.exists():
            log_message("Using virtual environment Python")
            # Update Python path for services
            for service in SERVICES.values():
                if service["cmd"][0] == sys.executable:
                    service["cmd"][0] = str(venv_python)

        # FIX: Add PYTHONPATH so backend modules can find each other
        env = os.environ.copy()
        env["PYTHONPATH"] = str(BACKEND_DIR)
        for service in SERVICES.values():
            if "env" not in service:
                service["env"] = env
            else:
                service["env"]["PYTHONPATH"] = str(BACKEND_DIR)

        # Start services in order
        log_message("\nStarting services...")

        for service_id, config in SERVICES.items():
            # Check skip_if condition
            if "skip_if" in config:
                try:
                    if config["skip_if"]():
                        log_message(f"[SKIP] {config['name']} is already running")
                        continue
                except Exception as e:
                    log_message(f"[WARN] Error checking skip_if for {config['name']}: {e}")

            # Wait for specified delay before starting
            if config["delay"] > 0:
                log_message(f"Waiting {config['delay']}s before starting {config['name']}...")
                time.sleep(config["delay"])

            start_service(service_id, config)

        log_message("\n+--------------------------------------+")
        log_message(f"|     JARVIS SYSTEM GUARDIAN v{mode_label}    |")
        log_message("|          OPERATOR ONLINE             |")
        log_message("+--------------------------------------+")
        log_message("|  Dashboard: http://localhost:8081    |")
        log_message("|  API:       http://localhost:5050    |")
        log_message("|  WebSocket: ws://localhost:8765      |")
        log_message("+--------------------------------------+")
        log_message(f"Mode: {mode_label}")
        log_message("Press Ctrl+C to stop all services gracefully.")

        # Auto-open dashboard once the frontend dev server is ready
        log_message("Waiting for frontend to initialise (port 8081)...")
        if wait_for_port(8081, timeout=45):
            # Force Brave browser instead of system default
            brave_path = os.path.expandvars(r"C:\Users\%USERNAME%\AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe")
            if os.path.exists(brave_path):
                subprocess.Popen([brave_path, "http://localhost:8081"])
                log_message("Browser opened (Brave) -> http://localhost:8081")
            else:
                log_message("[WARN] Brave not found, falling back to system default")
                import webbrowser
                webbrowser.open("http://localhost:8081")
        else:
            log_message("[WARN] Frontend did not respond on port 8081 after 45s")

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
