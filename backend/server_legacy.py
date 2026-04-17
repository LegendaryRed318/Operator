#!/usr/bin/env python3
"""
server.py - HTTP API server for the Operator dashboard with audio transcription.
"""

import sqlite3
import json
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import psutil
import platform
import urllib.request
import time
import subprocess
import threading

DB_PATH = Path("C:/Projects/Operator/database/errors.db")
SKILLS_PATH = Path("E:/JarvisVault/skills")
LOGS_PATH = Path("C:/Projects/Operator/logs")
VAULT_PATH = Path("E:/JarvisVault")
TEMP_AUDIO_PATH = LOGS_PATH / "temp_audio.wav"
HEARTBEAT_PATH = LOGS_PATH / "heartbeat.flag"
SLEEP_FLAG_PATH = LOGS_PATH / "sleep.flag"
ACTIVE_MODEL_PATH = LOGS_PATH / "active_model.txt"
IDLE_TIMEOUT_SECONDS = 3 * 60 * 60  # 3 hours
PORT = 5050

# Ensure directories exist
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
LOGS_PATH.mkdir(parents=True, exist_ok=True)

_whisper_model = None
_whisper_lock = threading.Lock()

def _get_whisper_model():
    global _whisper_model
    with _whisper_lock:
        if _whisper_model is None:
            try:
                from faster_whisper import WhisperModel
                _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
                print("[Whisper] Model loaded (base, cpu, int8)")
            except Exception as e:
                print(f"[Whisper] Failed to load model: {e}")
        return _whisper_model

def _get_ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


class ErrorHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the errors API and audio transcription."""
    
    def log_message(self, format, *args):
        # Suppress default logging
        pass
    
    def _set_headers(self, content_type="application/json", status=200):
        self.send_response(status)
        self.send_header("Content-type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
    
    def do_OPTIONS(self):
        self._set_headers()
    
    def _touch_heartbeat(self):
        """Reset the sleep-manager idle timer on every request."""
        try:
            HEARTBEAT_PATH.touch()
        except Exception:
            pass

    def do_GET(self):
        self._touch_heartbeat()
        if self.path == "/errors":
            self._handle_get_errors()
        elif self.path == "/system":
            self._handle_get_system()
        elif self.path == "/":
            self._handle_root()
        elif self.path == "/models":
            self._handle_get_models()
        elif self.path.startswith("/vault/search"):
            self._handle_vault_search()
        elif self.path == "/vault/recent":
            self._handle_vault_recent()
        elif self.path == "/sleep/status":
            self._handle_sleep_status()
        elif self.path == "/projects":
            self._handle_get_projects()
        elif self.path == "/skills":
            self._handle_get_skills()
        elif self.path.startswith("/skills/"):
            self._handle_get_skill_file()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        self._touch_heartbeat()
        if self.path == "/transcribe":
            self._handle_transcribe()
        elif self.path == "/clear-errors":
            self._handle_clear_errors()
        elif self.path == "/sleep/wake":
            self._handle_sleep_wake()
        elif self.path == "/sleep/sleep":
            self._handle_sleep_sleep()
        elif self.path == "/vault/save":
            self._handle_vault_save()
        elif self.path == "/errors/clear-test":
            self._handle_clear_test_errors()
        elif self.path == "/skills/import-zip":
            self._handle_import_zip()
        else:
            self.send_response(404)
            self.end_headers()
    
    def _handle_root(self):
        """Root endpoint for health check."""
        self._set_headers()
        response = {"status": "ok", "service": "Operator API"}
        self.wfile.write(json.dumps(response).encode())
    
    def _handle_get_system(self):
        """Return real hardware system vitals as JSON."""
        try:
            # CPU
            cpu_percent = psutil.cpu_percent(interval=0.5)
            
            # RAM
            mem = psutil.virtual_memory()
            ram_percent = mem.percent
            ram_used_gb = round(mem.used / (1024**3), 1)
            ram_total_gb = round(mem.total / (1024**3), 1)
            
            # Disk usage - dynamically discover all drives
            disks = []
            if platform.system() == "Windows":
                # Get all drive letters (C:, D:, E:, etc.)
                import string
                from ctypes import windll
                for letter in string.ascii_uppercase:
                    drive = f"{letter}:\\"
                    # Check if drive exists and is accessible via psutil
                    try:
                        usage = psutil.disk_usage(drive)
                        disks.append({
                            "mount": drive,
                            "total": usage.total,
                            "used": usage.used,
                            "free": usage.free,
                            "percent": usage.percent
                        })
                    except:
                        pass
            else:
                for part in psutil.disk_partitions():
                    try:
                        usage = psutil.disk_usage(part.mountpoint)
                        disks.append({
                            "mount": part.mountpoint,
                            "total": usage.total,
                            "used": usage.used,
                            "free": usage.free,
                            "percent": usage.percent
                        })
                    except:
                        pass
            
            # Temperatures - Cache WMI on Windows to prevent CPU spikes
            cpu_temp = None
            gpu_temp = None
            
            if platform.system() == "Windows":
                global _last_temp, _last_temp_time
                if '_last_temp' not in globals():
                    _last_temp = None
                    _last_temp_time = 0
                
                now = time.time()
                if now - _last_temp_time > 30:
                    try:
                        import subprocess
                        # Try WMI query for thermal zone temperature
                        result = subprocess.run(
                            ['wmic', r'/namespace:\\root\wmi', 'PATH', 'MSAcpi_ThermalZoneTemperature', 'get', 'CurrentTemperature', '/value'],
                            capture_output=True, text=True, timeout=5, creationflags=0x08000000
                        )
                        if result.returncode == 0:
                            # Parse output - temperature is in tenths of Kelvin
                            for line in result.stdout.strip().split('\n'):
                                if 'CurrentTemperature=' in line:
                                    temp_val = line.split('=')[1].strip()
                                    if temp_val and temp_val.isdigit():
                                        # Convert from tenths of Kelvin to Celsius
                                        temp_c = (int(temp_val) / 10) - 273.15
                                        if temp_c > 0 and temp_c < 120:  # Sanity check
                                            _last_temp = round(temp_c, 1)
                                            break
                    except Exception as e:
                        print(f"[System] WMI temperature query failed: {e}")
                    _last_temp_time = now
                
                cpu_temp = _last_temp
            
            # Legacy drive fields for backward compatibility
            disk_c = next((d for d in disks if d['mount'] == 'C:\\'), None)
            disk_d = next((d for d in disks if d['mount'] == 'D:\\'), None)
            disk_e = next((d for d in disks if d['mount'] == 'E:\\'), None)
            
            response = {
                "cpu_percent": cpu_percent,
                "ram_percent": ram_percent,
                "ram_used_gb": ram_used_gb,
                "ram_total_gb": ram_total_gb,
                "disks": disks,
                # Legacy fields for backward compatibility
                "disk_c_label": "Windows (C:)",
                "disk_c_percent": disk_c['percent'] if disk_c else None,
                "disk_c_used_gb": int(round(disk_c['used'] / (1024**3), 0)) if disk_c else None,
                "disk_c_total_gb": int(round(disk_c['total'] / (1024**3), 0)) if disk_c else None,
                "disk_d_label": "Micro SSD (D:)",
                "disk_d_percent": disk_d['percent'] if disk_d else None,
                "disk_d_used_gb": int(round(disk_d['used'] / (1024**3), 0)) if disk_d else None,
                "disk_d_total_gb": int(round(disk_d['total'] / (1024**3), 0)) if disk_d else None,
                "disk_e_label": "HDD (E:)",
                "disk_e_percent": disk_e['percent'] if disk_e else None,
                "disk_e_used_gb": int(round(disk_e['used'] / (1024**3), 0)) if disk_e else None,
                "disk_e_total_gb": int(round(disk_e['total'] / (1024**3), 0)) if disk_e else None,
                # Temperatures (may be None on Windows)
                "cpu_temp": cpu_temp,
                "gpu_temp": gpu_temp,
                "has_temperatures": cpu_temp is not None or gpu_temp is not None
            }
            
            self._set_headers()
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            self._set_headers(status=500)
            error_response = {"error": str(e)}
            self.wfile.write(json.dumps(error_response).encode())
    
    def _handle_get_errors(self):
        """Return the last 10 errors as JSON."""
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, timestamp, project_name, file_path, error_text, suggested_fix
                FROM errors
                ORDER BY timestamp DESC
                LIMIT 10
            """)
            
            rows = cursor.fetchall()
            conn.close()
            
            errors = []
            for row in rows:
                error = {
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "project_name": row["project_name"],
                    "file_path": row["file_path"],
                    "error_text": row["error_text"],
                    "suggested_fix": row["suggested_fix"]
                }
                errors.append(error)
            
            self._set_headers()
            self.wfile.write(json.dumps(errors).encode())
            
        except Exception as e:
            self._set_headers()
            error_response = {"error": str(e)}
            self.wfile.write(json.dumps(error_response).encode())
    
    def _handle_transcribe(self):
        """Receive audio blob, transcribe with Whisper, return text."""
        try:
            content_type = self.headers.get('Content-Type', '')
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)

            # Parse multipart form data
            audio_data = None
            if 'multipart/form-data' in content_type:
                boundary = content_type.split('boundary=')[1].split(';')[0].strip()
                parts = post_data.split(f'--{boundary}'.encode())
                for part in parts:
                    if b'Content-Disposition' in part and b'filename=' in part:
                        header_end = part.find(b'\r\n\r\n')
                        if header_end != -1:
                            audio_data = part[header_end + 4:]
                            if audio_data.endswith(b'\r\n'):
                                audio_data = audio_data[:-2]
                            break
            else:
                audio_data = post_data

            if not audio_data or len(audio_data) < 1000:
                self._set_headers()
                self.wfile.write(json.dumps({"text": "", "confidence": 0}).encode())
                return

            # Save webm to temp file
            webm_path = LOGS_PATH / "temp_audio.webm"
            wav_path = LOGS_PATH / "temp_audio.wav"
            webm_path.write_bytes(audio_data)

            # Convert webm -> wav 16kHz mono with ffmpeg
            ffmpeg_exe = _get_ffmpeg_exe()
            conv = subprocess.run(
                [ffmpeg_exe, '-y', '-i', str(webm_path), '-ar', '16000', '-ac', '1', str(wav_path)],
                capture_output=True, timeout=30
            )
            if conv.returncode != 0:
                raise Exception(f"ffmpeg failed: {conv.stderr.decode()[:200]}")

            # Transcribe
            model = _get_whisper_model()
            if model is None:
                raise Exception("Whisper model not available")

            segments, _ = model.transcribe(str(wav_path), language='en', beam_size=5)
            text = " ".join(seg.text for seg in segments).strip()

            # Cleanup temp files
            try: webm_path.unlink(missing_ok=True)
            except: pass
            try: wav_path.unlink(missing_ok=True)
            except: pass

            print(f"[Whisper] Transcribed: {text[:80]}")
            self._set_headers()
            self.wfile.write(json.dumps({"text": text, "confidence": 0.95}).encode())

        except Exception as e:
            print(f"[Transcribe] Error: {e}")
            self._set_headers(status=500)
            self.wfile.write(json.dumps({"error": str(e), "text": ""}).encode())


    def _handle_clear_errors(self):
        """DELETE all rows from the errors table (test-data wipe)."""
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            cursor.execute("DELETE FROM errors")
            deleted = cursor.rowcount
            conn.commit()
            conn.close()
            self._set_headers()
            self.wfile.write(json.dumps({"status": "ok", "deleted": deleted}).encode())
            print(f"[ClearErrors] Deleted {deleted} error(s)")
        except Exception as e:
            self._set_headers(status=500)
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def _handle_get_models(self):
        """Return available Ollama models and the currently active model."""
        models = []
        active = "qwen2.5-coder:1.5b-base"

        # Read active model from file
        try:
            if ACTIVE_MODEL_PATH.exists():
                active = ACTIVE_MODEL_PATH.read_text().strip()
        except Exception:
            pass

        # Fetch available models from Ollama
        try:
            with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as resp:
                data = json.loads(resp.read())
                models = [m["name"] for m in data.get("models", [])]
        except Exception:
            pass

        self._set_headers()
        self.wfile.write(json.dumps({
            "models": models,
            "active": active,
        }).encode())

    def _handle_vault_search(self):
        """Search the Obsidian vault."""
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        query = params.get("q", [""])[0]

        try:
            import sys
            sys.path.insert(0, str(Path(__file__).parent))
            from memory import search_vault
            results = search_vault(query)
            self._set_headers()
            self.wfile.write(json.dumps(results).encode())
        except Exception as e:
            self._set_headers()
            self.wfile.write(json.dumps({"error": str(e), "results": []}).encode())

    def _handle_vault_recent(self):
        """Return last 10 recently modified vault files."""
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).parent))
            from memory import get_recent_files
            results = get_recent_files(10)
            self._set_headers()
            self.wfile.write(json.dumps(results).encode())
        except Exception as e:
            self._set_headers()
            self.wfile.write(json.dumps({"error": str(e), "files": []}).encode())

    def _handle_vault_save(self):
        """Save content to the vault."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length)
            body = json.loads(raw_body)

            import sys
            sys.path.insert(0, str(Path(__file__).parent))
            from memory import save_to_wiki
            ok = save_to_wiki(
                body.get("title", "Untitled"),
                body.get("content", ""),
                body.get("category", "general"),
            )
            self._set_headers()
            self.wfile.write(json.dumps({"status": "ok" if ok else "error"}).encode())
        except Exception as e:
            self._set_headers(status=500)
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def _handle_sleep_status(self):
        """Return current sleep status and time remaining."""
        try:
            sleeping = False
            try:
                if SLEEP_FLAG_PATH.exists():
                    flag = SLEEP_FLAG_PATH.read_text().strip()
                    sleeping = flag == "SLEEP"
            except Exception:
                pass

            # Compute idle time from heartbeat
            last_activity = time.time()
            try:
                if HEARTBEAT_PATH.exists():
                    last_activity = HEARTBEAT_PATH.stat().st_mtime
            except Exception:
                pass

            idle_secs = time.time() - last_activity
            time_remaining = max(0, int(IDLE_TIMEOUT_SECONDS - idle_secs))

            from datetime import datetime
            last_interaction_str = datetime.fromtimestamp(last_activity).strftime("%Y-%m-%d %H:%M:%S")

            self._set_headers()
            self.wfile.write(json.dumps({
                "sleeping": sleeping,
                "time_remaining_seconds": time_remaining,
                "last_interaction": last_interaction_str,
                "idle_seconds": int(idle_secs),
            }).encode())
        except Exception as e:
            self._set_headers(status=500)
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def _handle_sleep_wake(self):
        """Manually wake Jarvis by resetting the heartbeat."""
        try:
            HEARTBEAT_PATH.touch()
            try:
                SLEEP_FLAG_PATH.write_text("AWAKE")
            except Exception:
                pass
            self._set_headers()
            self.wfile.write(json.dumps({"status": "ok", "state": "AWAKE"}).encode())
        except Exception as e:
            self._set_headers(status=500)
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def _handle_sleep_sleep(self):
        """Manually send Jarvis to sleep."""
        try:
            SLEEP_FLAG_PATH.write_text("SLEEP")
            self._set_headers()
            self.wfile.write(json.dumps({"status": "ok", "state": "SLEEP"}).encode())
        except Exception as e:
            self._set_headers(status=500)
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def _handle_get_projects(self):
        """Return project status derived from recent errors in the DB."""
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get error counts per project from the last 24 hours
            cursor.execute("""
                SELECT project_name,
                       COUNT(*) as error_count,
                       MAX(timestamp) as last_error,
                       SUM(CASE WHEN suggested_fix IS NULL THEN 1 ELSE 0 END) as pending_fixes
                FROM errors
                WHERE timestamp >= datetime('now', '-24 hours')
                GROUP BY project_name
            """)
            rows = cursor.fetchall()
            conn.close()

            projects_map = {}
            for row in rows:
                name = row['project_name']
                if row['pending_fixes'] > 0:
                    status = 'fixing'
                elif row['error_count'] > 0:
                    status = 'error'
                else:
                    status = 'healthy'
                projects_map[name] = {
                    'name': name,
                    'status': status,
                    'error_count': row['error_count'],
                    'last_error': row['last_error'],
                }

            self._set_headers()
            self.wfile.write(json.dumps(list(projects_map.values())).encode())
        except Exception as e:
            self._set_headers()
            self.wfile.write(json.dumps([]).encode())

    def _handle_clear_test_errors(self):
        """Delete errors that look like test data (contain 'test' or were early dev errors)."""
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()

            from datetime import date
            today = date.today().isoformat()

            cursor.execute("""
                DELETE FROM errors
                WHERE LOWER(error_text) LIKE '%test%'
                   OR (project_name = 'Operator' AND error_text LIKE 'ERROR:%' AND DATE(timestamp) < ?)
            """, (today,))
            deleted = cursor.rowcount
            conn.commit()
            conn.close()

            self._set_headers()
            self.wfile.write(json.dumps({"status": "ok", "deleted": deleted}).encode())
            print(f"[ClearTestErrors] Deleted {deleted} test error(s)")
        except Exception as e:
            self._set_headers(status=500)
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def _handle_get_skills(self):
        """List all .toml skill files in the vault."""
        try:
            # Ensure vault exists first
            if not VAULT_PATH.exists():
                import setup_vault
                setup_vault.setup_vault()
            
            skills = []
            if SKILLS_PATH.exists():
                for f in SKILLS_PATH.glob("*.toml"):
                    skills.append({
                        "name": f.stem,
                        "filename": f.name,
                        "size": f.stat().st_size,
                        "modified": f.stat().st_mtime
                    })
            
            self._set_headers()
            self.wfile.write(json.dumps({"skills": skills, "path": str(SKILLS_PATH)}).encode())
            print(f"[Skills] Listed {len(skills)} skill files")
        except Exception as e:
            self._set_headers(status=500)
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def _handle_get_skill_file(self):
        """Return content of a specific skill file."""
        try:
            # Extract skill name from path /skills/{name}
            path_parts = self.path.split('/')
            if len(path_parts) < 3:
                self.send_response(400)
                self.end_headers()
                return
            
            skill_name = path_parts[2]
            # Sanitize name to prevent path traversal
            skill_name = ''.join(c for c in skill_name if c.isalnum() or c in '_-')
            
            skill_file = SKILLS_PATH / f"{skill_name}.toml"
            
            if not skill_file.exists():
                self._set_headers(status=404)
                self.wfile.write(json.dumps({"error": f"Skill '{skill_name}' not found"}).encode())
                return
            
            content = skill_file.read_text(encoding='utf-8')
            self._set_headers()
            self.wfile.write(json.dumps({
                "name": skill_name,
                "content": content,
                "filename": skill_file.name
            }).encode())
            print(f"[Skills] Retrieved: {skill_file.name}")
        except Exception as e:
            self._set_headers(status=500)
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def _handle_import_zip(self):
        """Import skills from uploaded ZIP file (from GitHub or local)."""
        try:
            import zipfile
            import io
            import shutil
            
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self._set_headers(status=400)
                self.wfile.write(json.dumps({"error": "No file uploaded"}).encode())
                return
            
            # Read uploaded ZIP data
            zip_data = self.rfile.read(content_length)
            
            # Ensure skills directory exists
            SKILLS_PATH.mkdir(parents=True, exist_ok=True)
            
            imported = []
            errors = []
            
            # Extract ZIP
            with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zf:
                for file_info in zf.infolist():
                    # Skip directories and non-TOML files
                    if file_info.is_dir():
                        continue
                    if not file_info.filename.endswith('.toml'):
                        continue
                    
                    # Clean filename (remove path, keep only name)
                    filename = Path(file_info.filename).name
                    if not filename or filename.startswith('.'):
                        continue
                    
                    # Read and save
                    try:
                        content = zf.read(file_info.filename)
                        dest_path = SKILLS_PATH / filename
                        dest_path.write_bytes(content)
                        imported.append(filename)
                        print(f"[Skills] Imported: {filename}")
                    except Exception as e:
                        errors.append(f"{filename}: {str(e)}")
            
            self._set_headers()
            response = {
                "imported": imported,
                "count": len(imported),
                "errors": errors,
                "path": str(SKILLS_PATH)
            }
            self.wfile.write(json.dumps(response).encode())
            print(f"[Skills] ZIP import complete: {len(imported)} files, {len(errors)} errors")
            
        except zipfile.BadZipFile:
            self._set_headers(status=400)
            self.wfile.write(json.dumps({"error": "Invalid ZIP file"}).encode())
        except Exception as e:
            self._set_headers(status=500)
            self.wfile.write(json.dumps({"error": str(e)}).encode())


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), ErrorHandler)
    print(f"[INFO] API server running on http://localhost:{PORT}")
    print(f"[INFO] Endpoints:")
    print(f"  GET  http://localhost:{PORT}/           - Health check")
    print(f"  GET  http://localhost:{PORT}/errors     - Last 10 errors")
    print(f"  GET  http://localhost:{PORT}/system     - System vitals (CPU, RAM, disk)")
    print(f"  POST http://localhost:{PORT}/transcribe - Audio transcription")
    print(f"  GET  http://localhost:{PORT}/models       - Available AI models")
    print(f"  GET  http://localhost:{PORT}/vault/search - Search Obsidian vault")
    print(f"  GET  http://localhost:{PORT}/vault/recent - Recent vault files")
    print(f"  POST http://localhost:{PORT}/vault/save   - Save to vault")
    print(f"  GET  http://localhost:{PORT}/sleep/status - Sleep status")
    print(f"  POST http://localhost:{PORT}/sleep/wake   - Wake Jarvis")
    print(f"  POST http://localhost:{PORT}/sleep/sleep  - Sleep Jarvis")
    print(f"  POST http://localhost:{PORT}/errors/clear-test - Clear test errors")
    print(f"  GET  http://localhost:{PORT}/skills       - List all skills")
    print(f"  GET  http://localhost:{PORT}/skills/{{name}} - Get skill content")
    print(f"  POST http://localhost:{PORT}/skills/import-zip - Import skills from ZIP")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] Server stopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
