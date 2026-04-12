#!/usr/bin/env python3
"""
server.py - HTTP API server for the Operator dashboard with audio transcription.
"""

import sqlite3
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import psutil
import platform

DB_PATH = Path("C:/Projects/Operator/database/errors.db")
LOGS_PATH = Path("C:/Projects/Operator/logs")
TEMP_AUDIO_PATH = LOGS_PATH / "temp_audio.wav"
PORT = 5050

# Ensure directories exist
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
LOGS_PATH.mkdir(parents=True, exist_ok=True)


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
    
    def do_GET(self):
        if self.path == "/errors":
            self._handle_get_errors()
        elif self.path == "/system":
            self._handle_get_system()
        elif self.path == "/":
            self._handle_root()
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        if self.path == "/transcribe":
            self._handle_transcribe()
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
            
            # Temperatures - Use WMI on Windows (psutil doesn't work well on Windows)
            cpu_temp = None
            gpu_temp = None
            
            if platform.system() == "Windows":
                try:
                    import subprocess
                    # Try WMI query for thermal zone temperature
                    result = subprocess.run(
                        ['wmic', '/namespace:\\root\wmi', 'PATH', 'MSAcpi_ThermalZoneTemperature', 'get', 'CurrentTemperature', '/value'],
                        capture_output=True, text=True, timeout=5
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
                                        cpu_temp = round(temp_c, 1)
                                        break
                except Exception as e:
                    print(f"[System] WMI temperature query failed: {e}")
            
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
        """
        Handle audio transcription from frontend.
        Receives audio blob, saves it, and returns mock transcription.
        """
        try:
            # Get content type and boundary
            content_type = self.headers.get('Content-Type', '')
            
            # Read the raw POST data
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            print(f"[Transcribe] Received {len(post_data)} bytes of audio data")
            
            # Parse multipart form data
            if 'multipart/form-data' in content_type:
                # Extract boundary
                boundary = content_type.split('boundary=')[1].split(';')[0].strip()
                
                # Parse the multipart data
                parts = post_data.split(f'--{boundary}'.encode())
                
                audio_data = None
                for part in parts:
                    if b'Content-Disposition' in part and b'filename=' in part:
                        # Extract the file data (after the headers)
                        header_end = part.find(b'\r\n\r\n')
                        if header_end != -1:
                            audio_data = part[header_end + 4:]
                            # Remove trailing \r\n if present
                            if audio_data.endswith(b'\r\n'):
                                audio_data = audio_data[:-2]
                            break
                
                if audio_data:
                    # Save to temp file
                    TEMP_AUDIO_PATH.write_bytes(audio_data)
                    print(f"[Transcribe] Saved audio to {TEMP_AUDIO_PATH} ({len(audio_data)} bytes)")
                else:
                    print("[Transcribe] No audio data found in multipart request")
            else:
                # Raw binary data
                TEMP_AUDIO_PATH.write_bytes(post_data)
                print(f"[Transcribe] Saved raw audio to {TEMP_AUDIO_PATH}")
            
            # Mock transcription response (replace with actual Whisper/Ollama later)
            # For now, return a mock response to test the pipeline
            mock_text = "Hello Jarvis, what is the system status?"
            
            # In the future, this will call Whisper or Ollama:
            # result = call_whisper(TEMP_AUDIO_PATH)
            
            response = {
                "text": mock_text,
                "confidence": 0.95,
                "duration": 5.0
            }
            
            self._set_headers()
            self.wfile.write(json.dumps(response).encode())
            print(f"[Transcribe] Returned mock transcription: {mock_text}")
            
        except Exception as e:
            print(f"[Transcribe] Error: {e}")
            self._set_headers(status=500)
            error_response = {"error": str(e), "text": ""}
            self.wfile.write(json.dumps(error_response).encode())


def main():
    server = HTTPServer(("0.0.0.0", PORT), ErrorHandler)
    print(f"[INFO] API server running on http://localhost:{PORT}")
    print(f"[INFO] Endpoints:")
    print(f"  GET  http://localhost:{PORT}/           - Health check")
    print(f"  GET  http://localhost:{PORT}/errors     - Last 10 errors")
    print(f"  GET  http://localhost:{PORT}/system     - System vitals (CPU, RAM, disk)")
    print(f"  POST http://localhost:{PORT}/transcribe - Audio transcription")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] Server stopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
