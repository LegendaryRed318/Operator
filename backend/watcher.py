#!/usr/bin/env python3
"""
watcher.py - Monitors log files for errors and sends them to Ollama for fix suggestions.
"""

import os
import sys
import json
import sqlite3
import subprocess
import time
import re
from datetime import datetime
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from notifier import notify_new_error

# Configuration
CONFIG_PATH = Path(__file__).parent / "config.json"
DB_PATH = Path("C:/Projects/Operator/database/errors.db")
ALERT_FLAG_PATH = Path("C:/Projects/Operator/logs/alert.flag")
OLLAMA_MODEL = "qwen2.5-coder:1.5b-base"

# Rate limiting: max 3 notifications per project per 60 seconds
notification_timestamps = {}  # {project_name: [timestamp1, timestamp2, ...]}
MAX_NOTIFICATIONS_PER_MINUTE = 3
NOTIFICATION_WINDOW_SECONDS = 60

# Ensure database directory exists
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
ALERT_FLAG_PATH.parent.mkdir(parents=True, exist_ok=True)


def init_database():
    """Initialize the SQLite database with the errors table."""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            project_name TEXT,
            file_path TEXT,
            error_text TEXT,
            suggested_fix TEXT
        )
    """)
    conn.commit()
    conn.close()


def load_config():
    """Load configuration from config.json."""
    if not CONFIG_PATH.exists():
        # Create default config
        default_config = {"watched_folders": ["C:/Projects/Operator/test_logs"]}
        with open(CONFIG_PATH, "w") as f:
            json.dump(default_config, f, indent=2)
        return default_config
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def extract_error_context(file_path, error_line_num, context_lines=10):
    """Extract error context (lines before and after the error)."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        
        start_line = max(0, error_line_num - context_lines - 1)
        end_line = min(len(lines), error_line_num + context_lines)
        
        context = lines[start_line:end_line]
        context_str = "".join(context)
        
        # Brute-force: keep only printable ASCII, newline, and tab
        context_str = re.sub(r'[^\x20-\x7E\n\t]', '', context_str)
        
        return context_str
    except Exception as e:
        return f"Error reading context: {str(e)}"


def get_error_lines(file_path, start_line=1):
    """Scan file for error patterns starting from start_line."""
    error_patterns = [
        re.compile(r'\bERROR\b', re.IGNORECASE),
        re.compile(r'\bException\b', re.IGNORECASE),
        re.compile(r'\bTraceback\b', re.IGNORECASE),
    ]
    
    error_lines = []
    
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            # Skip to start_line
            for _ in range(start_line - 1):
                next(f, None)
            
            for line_num, line in enumerate(f, start_line):
                for pattern in error_patterns:
                    if pattern.search(line):
                        error_lines.append((line_num, line))
                        break
    except Exception as e:
        print(f"[ERROR] Failed to read {file_path}: {e}")
    
    return error_lines


def get_project_name(file_path):
    """Extract project name from file path."""
    path = Path(file_path)
    # Try to find project name from parent directories
    parts = path.parts
    for i, part in enumerate(parts):
        if part.lower() in ['projects', 'src', 'app']:
            if i + 1 < len(parts):
                return parts[i + 1]
    return path.parent.name if path.parent.name != "." else "unknown"


def query_ollama(error_text):
    """Send error to Ollama and get fix suggestion."""
    import re
    # Brute-force: keep only printable ASCII, newline, and tab
    cleaned = re.sub(r'[^\x20-\x7E\n\t]', '', error_text)
    if len(cleaned) > 2000:
        cleaned = cleaned[:2000] + "... (truncated)"
    try:
        prompt = f"Error: {cleaned}\n\nProvide a code fix as a unified diff."
        result = subprocess.run(
            ["ollama", "run", OLLAMA_MODEL, prompt],
            capture_output=True,
            text=True,
            timeout=30,
            encoding='utf-8',
            errors='replace'
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            return f"Ollama error: {result.stderr}"
    except subprocess.TimeoutExpired:
        return "Ollama query timed out (30s)"
    except FileNotFoundError:
        return "Ollama not found. Is it installed and in PATH?"
    except Exception as e:
        return f"Failed to query Ollama: {str(e)}"


def should_notify(project_name):
    """Check if we should send notification for this project (rate limiting)."""
    global notification_timestamps
    
    now = time.time()
    
    # Get timestamps for this project
    timestamps = notification_timestamps.get(project_name, [])
    
    # Remove timestamps older than the window
    timestamps = [ts for ts in timestamps if now - ts < NOTIFICATION_WINDOW_SECONDS]
    
    # Check if under limit
    if len(timestamps) < MAX_NOTIFICATIONS_PER_MINUTE:
        timestamps.append(now)
        notification_timestamps[project_name] = timestamps
        return True
    else:
        notification_timestamps[project_name] = timestamps
        return False


def store_error(project_name, file_path, error_text):
    """Store error in database and query Ollama for fix."""
    error_id = None
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        # Insert error without fix first
        cursor.execute("""
            INSERT INTO errors (project_name, file_path, error_text, suggested_fix)
            VALUES (?, ?, ?, ?)
        """, (project_name, file_path, error_text, None))
        
        error_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        print(f"[NEW ERROR] ID {error_id} - {project_name} - {error_text[:100]}")
    except Exception as e:
        print(f"[ERROR] Failed to insert error into database: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Trigger tray alert
    try:
        with open(ALERT_FLAG_PATH, "w") as f:
            f.write("RED")
        print(f"[ALERT] Tray flag set to RED")
    except Exception as e:
        print(f"[WARNING] Could not write alert flag: {e}")
    
    # Send Windows toast + Telegram notifications (with rate limiting)
    try:
        if should_notify(project_name):
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            notify_new_error(project_name, error_text, timestamp)
        else:
            print(f"[NOTIFIER] Rate limit reached for {project_name}, skipping notification (error still stored)")
    except Exception as e:
        print(f"[WARNING] Notification failed: {e}")
    
    # Query Ollama for fix suggestion
    print(f"[INFO] Querying Ollama for fix suggestion...")
    suggested_fix = query_ollama(error_text)
    
    # Update database with fix
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE errors SET suggested_fix = ? WHERE id = ?
        """, (suggested_fix, error_id))
        conn.commit()
        conn.close()
        
        print(f"[FIX GENERATED] Stored for error ID {error_id}")
    except Exception as e:
        print(f"[ERROR] Failed to update fix in database: {e}")


class LogFileHandler(FileSystemEventHandler):
    """Watchdog event handler for log files."""
    
    def __init__(self, watched_folders):
        self.watched_folders = watched_folders
        self.processed_errors = {}  # Track processed errors to avoid duplicates
        self.file_line_counts = {}  # Track last known line count per file: {file_path: line_count}
    
    def on_modified(self, event):
        if event.is_directory:
            return
        
        if not event.src_path.endswith('.log'):
            return
            
        # Ignore Operator's own logs to prevent infinite loops and false alarms on startup
        if "Operator\\logs" in str(Path(event.src_path)) or "Operator/logs" in str(Path(event.src_path)):
            return
        
        print(f"[DEBUG] File modified: {event.src_path}")
        
        # Check if file is in watched folders
        file_path = Path(event.src_path)
        is_watched = any(
            str(file_path).startswith(str(Path(folder).resolve()))
            for folder in self.watched_folders
        )
        
        if not is_watched:
            print(f"[DEBUG] File not in watched folders, skipping")
            return
        
        print(f"[DEBUG] File is watched, scanning for errors...")
        
        # Get current file line count
        try:
            with open(event.src_path, "r", encoding="utf-8", errors="ignore") as f:
                current_line_count = sum(1 for _ in f)
        except Exception as e:
            print(f"[ERROR] Could not count lines in {event.src_path}: {e}")
            return
        
        # Get last known line count (default to 0 for new files)
        last_line_count = self.file_line_counts.get(event.src_path, 0)
        
        # Only scan lines AFTER the last known line count
        if current_line_count > last_line_count:
            print(f"[DEBUG] File grew from {last_line_count} to {current_line_count} lines, scanning new lines {last_line_count + 1} to {current_line_count}")
            error_lines = get_error_lines(event.src_path, start_line=last_line_count + 1)
            print(f"[DEBUG] Found {len(error_lines)} error lines in new content")
        else:
            print(f"[DEBUG] No new lines added (was {last_line_count}, now {current_line_count}), skipping")
            error_lines = []
        
        # Update line count for next check
        self.file_line_counts[event.src_path] = current_line_count
        
        for line_num, error_line in error_lines:
            # Create unique key for this error
            error_key = f"{event.src_path}:{line_num}:{hash(error_line)}"
            
            # Skip if already processed (check last 100 errors)
            if error_key in self.processed_errors:
                continue
            
            # Mark as processed
            self.processed_errors[error_key] = time.time()
            
            # Clean old entries to prevent memory bloat
            if len(self.processed_errors) > 100:
                current_time = time.time()
                self.processed_errors = {
                    k: v for k, v in self.processed_errors.items()
                    if current_time - v < 300  # Keep only last 5 minutes
                }
            
            # Extract context
            context = extract_error_context(event.src_path, line_num)
            
            # Get project name
            project_name = get_project_name(event.src_path)
            
            # Store in database
            print(f"[DEBUG] Storing error from line {line_num}: {error_line[:50]}...")
            store_error(project_name, str(file_path), context)


def main():
    print("[INFO] Starting Operator Watcher...")
    print(f"[INFO] Database: {DB_PATH}")
    
    # Initialize database
    init_database()
    
    # Load configuration
    config = load_config()
    watched_folders = config.get("watched_folders", [])
    
    if not watched_folders:
        print("[ERROR] No watched folders configured!")
        sys.exit(1)
    
    print(f"[INFO] Watching folders: {watched_folders}")
    
    # Ensure watched folders exist
    for folder in watched_folders:
        Path(folder).mkdir(parents=True, exist_ok=True)
    
    # Set up observer
    event_handler = LogFileHandler(watched_folders)
    observer = Observer()
    
    for folder in watched_folders:
        observer.schedule(event_handler, folder, recursive=True)
    
    observer.start()
    print("[INFO] Watcher started. Monitoring for errors...")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[INFO] Stopping watcher...")
        observer.stop()
    
    observer.join()
    print("[INFO] Watcher stopped.")


if __name__ == "__main__":
    main()
