#!/usr/bin/env python3
"""
project_launcher.py - Launches React/Vite projects and captures their terminal output for error monitoring.
"""

import subprocess
import json
import os
import time
from datetime import datetime
from paths import CONFIG_PATH, LOGS_PATH

LOGS_DIR = str(LOGS_PATH)


def load_config():
    """Load projects configuration from config.json."""
    if not os.path.exists(CONFIG_PATH):
        print("[ERROR] config.json not found")
        return []
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
        return config.get("projects", [])


def log_error(project_name, line):
    """Write a line to the project's error log if it contains an error keyword."""
    keywords = ["ERROR", "error", "Exception", "TypeError", "ReferenceError", "SyntaxError", "Failed"]
    if any(kw in line for kw in keywords):
        log_path = os.path.join(LOGS_DIR, f"{project_name}.log")
        with open(log_path, "a", encoding="utf-8") as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {line}\n")
        print(f"[{project_name}] Error logged: {line[:100]}...")


def launch_project(project):
    """Launch a project in a new terminal window and capture its output."""
    name = project["name"]
    path = project["path"]
    cmd = project["start_command"]
    
    if not os.path.exists(path):
        print(f"[WARNING] Project '{name}' folder not found: {path}")
        return None
    
    # Split command into executable and args (e.g., "npm run dev" -> ["npm", "run", "dev"])
    cmd_parts = cmd.split()
    
    try:
        # Start the subprocess, capture stdout and stderr in real time
        proc = subprocess.Popen(
            cmd_parts,
            cwd=path,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # combine stderr into stdout
            text=True,
            bufsize=1,
            creationflags=subprocess.CREATE_NEW_CONSOLE  # each project gets its own window
        )
        print(f"[{name}] Started (PID: {proc.pid}) in new window")
        
        # Read output line by line
        for line in iter(proc.stdout.readline, ''):
            if line:
                print(f"[{name}] {line.rstrip()}")
                log_error(name, line.rstrip())
        
        proc.wait()
        print(f"[{name}] Process exited with code {proc.returncode}")
        return proc
    except FileNotFoundError:
        print(f"[ERROR] Command '{cmd_parts[0]}' not found. Is Node.js/npm installed and in PATH?")
        return None
    except Exception as e:
        print(f"[ERROR] Failed to launch {name}: {e}")
        return None


def main():
    # Ensure logs directory exists
    os.makedirs(LOGS_DIR, exist_ok=True)
    
    projects = load_config()
    if not projects:
        print("No projects found in config.json")
        print("Project Launcher will stay alive (idle mode) to prevent guardian restart loop.")
        # Keep the process alive so guardian doesn't restart us
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            print("\nProject Launcher stopping.")
        return
    
    print(f"Launching {len(projects)} project(s)...")
    processes = []
    for proj in projects:
        proc = launch_project(proj)
        if proc:
            processes.append(proc)
    
    print("All projects launched. Press Ctrl+C to stop all.")
    try:
        # Keep the script alive and wait for any process to finish (optional)
        for p in processes:
            p.wait()
    except KeyboardInterrupt:
        print("\nStopping all projects...")
        for p in processes:
            p.terminate()
        time.sleep(1)
        for p in processes:
            if p.poll() is None:
                p.kill()
        print("All projects stopped.")


if __name__ == "__main__":
    main()
