#!/usr/bin/env python3
"""
server_fastapi.py - FastAPI HTTP server for the Operator dashboard.
Modern async replacement for the legacy ThreadingHTTPServer.
"""

import asyncio
import json
import logging
import os
import platform
import shutil
import sqlite3
import subprocess
import threading
import time
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

import psutil
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Paths from environment or defaults
DB_PATH = Path(os.getenv("OPERATOR_DB_PATH", "C:/Projects/Operator/database/errors.db"))
SKILLS_PATH = Path(os.getenv("OPERATOR_SKILLS_PATH", "E:/JarvisVault/skills"))
LOGS_PATH = Path(os.getenv("OPERATOR_LOGS_PATH", "C:/Projects/Operator/logs"))
VAULT_PATH = Path(os.getenv("OPERATOR_VAULT_PATH", "E:/JarvisVault"))
TEMP_AUDIO_PATH = LOGS_PATH / "temp_audio.wav"
HEARTBEAT_PATH = LOGS_PATH / "heartbeat.flag"
SLEEP_FLAG_PATH = LOGS_PATH / "sleep.flag"
ACTIVE_MODEL_PATH = LOGS_PATH / "active_model.txt"
IDLE_TIMEOUT_SECONDS = int(os.getenv("OPERATOR_IDLE_TIMEOUT", str(3 * 60 * 60)))  # 3 hours default
PORT = int(os.getenv("OPERATOR_API_PORT", "5050"))

# Max upload size: 10MB for ZIP files
MAX_UPLOAD_SIZE = 10 * 1024 * 1024

# Whisper model cache
_whisper_model = None
_whisper_lock = threading.Lock()

# Ensure directories exist
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
LOGS_PATH.mkdir(parents=True, exist_ok=True)
SKILLS_PATH.mkdir(parents=True, exist_ok=True)


def _get_whisper_model():
    """Lazy-load Whisper model."""
    global _whisper_model
    with _whisper_lock:
        if _whisper_model is None:
            try:
                from faster_whisper import WhisperModel
                _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
                logger.info("[Whisper] Model loaded (base, cpu, int8)")
            except Exception as e:
                logger.error(f"[Whisper] Failed to load model: {e}")
        return _whisper_model


def _get_ffmpeg_exe():
    """Get ffmpeg executable path."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


# Pydantic models for request/response validation
class VaultSaveRequest(BaseModel):
    title: str
    content: str
    category: str = "general"


class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: str
    uptime_seconds: float


class ConfigResponse(BaseModel):
    db_path: str
    skills_path: str
    vault_path: str
    logs_path: str
    idle_timeout_seconds: int


class AuthVerifyRequest(BaseModel):
    password: str


class AuthVerifyResponse(BaseModel):
    valid: bool
    message: str


class ErrorItem(BaseModel):
    id: int
    timestamp: str
    project_name: str
    file_path: str
    error_text: str
    suggested_fix: Optional[str]


class SystemVitals(BaseModel):
    cpu_percent: float
    ram_percent: float
    ram_used_gb: float
    ram_total_gb: float
    disks: list[dict]
    disk_c_label: Optional[str]
    disk_c_percent: Optional[float]
    disk_c_used_gb: Optional[int]
    disk_c_total_gb: Optional[int]
    disk_d_label: Optional[str]
    disk_d_percent: Optional[float]
    disk_d_used_gb: Optional[int]
    disk_d_total_gb: Optional[int]
    disk_e_label: Optional[str]
    disk_e_percent: Optional[float]
    disk_e_used_gb: Optional[int]
    disk_e_total_gb: Optional[int]
    cpu_temp: Optional[float]
    gpu_temp: Optional[float]
    has_temperatures: bool


# Temperature cache for Windows WMI
_last_temp: Optional[float] = None
_last_temp_time: float = 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("[FastAPI] Server starting up...")
    
    # Ensure vault folder structure exists on startup
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from memory import ensure_vault
        vault_ok = ensure_vault()
        if vault_ok:
            logger.info(f"[FastAPI] Vault initialized at {VAULT_PATH}")
        else:
            logger.warning(f"[FastAPI] Vault not accessible at {VAULT_PATH}")
    except Exception as e:
        logger.error(f"[FastAPI] Vault initialization error: {e}")
    
    yield
    logger.info("[FastAPI] Server shutting down...")


app = FastAPI(
    title="Operator API",
    description="JARVIS System Guardian HTTP API",
    version="2.0.0",
    lifespan=lifespan
)

# CORS middleware - allow all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def size_limit_middleware(request: Request, call_next):
    """Limit request body size for uploads."""
    if request.method == "POST" and "import-zip" in str(request.url):
        body = await request.body()
        if len(body) > MAX_UPLOAD_SIZE:
            return JSONResponse(
                status_code=413,
                content={"error": f"File too large. Max size: {MAX_UPLOAD_SIZE // (1024*1024)}MB"}
            )
        # Re-create request with body for downstream
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}
        request = Request(request.scope, receive, request.send)
    return await call_next(request)


@app.middleware("http")
async def touch_heartbeat(request: Request, call_next):
    """Reset sleep timer on every request."""
    try:
        HEARTBEAT_PATH.touch()
    except Exception:
        pass
    return await call_next(request)


# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/", response_model=HealthResponse)
async def health_check():
    """Root endpoint for health check."""
    return HealthResponse(
        status="ok",
        service="Operator API (FastAPI)",
        timestamp=datetime.now().isoformat(),
        uptime_seconds=time.time() - getattr(health_check, "_start_time", time.time())
    )


@app.get("/health", response_model=HealthResponse)
async def health():
    """Detailed health check endpoint."""
    return await health_check()


@app.get("/config", response_model=ConfigResponse)
async def get_config():
    """Get server configuration (safe paths only)."""
    return ConfigResponse(
        db_path=str(DB_PATH),
        skills_path=str(SKILLS_PATH),
        vault_path=str(VAULT_PATH),
        logs_path=str(LOGS_PATH),
        idle_timeout_seconds=IDLE_TIMEOUT_SECONDS
    )


@app.get("/system", response_model=SystemVitals)
async def get_system_vitals():
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
            import string
            from ctypes import windll
            for letter in string.ascii_uppercase:
                drive = f"{letter}:\\"
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
        global _last_temp, _last_temp_time

        if platform.system() == "Windows":
            now = time.time()
            if now - _last_temp_time > 30:
                try:
                    result = subprocess.run(
                        ['wmic', r'/namespace:\\root\wmi', 'PATH', 'MSAcpi_ThermalZoneTemperature', 'get', 'CurrentTemperature', '/value'],
                        capture_output=True, text=True, timeout=5, creationflags=0x08000000
                    )
                    if result.returncode == 0:
                        for line in result.stdout.strip().split('\n'):
                            if 'CurrentTemperature=' in line:
                                temp_val = line.split('=')[1].strip()
                                if temp_val and temp_val.isdigit():
                                    temp_c = (int(temp_val) / 10) - 273.15
                                    if temp_c > 0 and temp_c < 120:
                                        _last_temp = round(temp_c, 1)
                                        break
                except Exception as e:
                    logger.debug(f"[System] WMI temperature query failed: {e}")
                _last_temp_time = now
            cpu_temp = _last_temp

        # Legacy drive fields
        disk_c = next((d for d in disks if d['mount'] == 'C:\\'), None)
        disk_d = next((d for d in disks if d['mount'] == 'D:\\'), None)
        disk_e = next((d for d in disks if d['mount'] == 'E:\\'), None)

        return SystemVitals(
            cpu_percent=cpu_percent,
            ram_percent=ram_percent,
            ram_used_gb=ram_used_gb,
            ram_total_gb=ram_total_gb,
            disks=disks,
            disk_c_label="Windows (C:)",
            disk_c_percent=disk_c['percent'] if disk_c else None,
            disk_c_used_gb=int(round(disk_c['used'] / (1024**3), 0)) if disk_c else None,
            disk_c_total_gb=int(round(disk_c['total'] / (1024**3), 0)) if disk_c else None,
            disk_d_label="Micro SSD (D:)",
            disk_d_percent=disk_d['percent'] if disk_d else None,
            disk_d_used_gb=int(round(disk_d['used'] / (1024**3), 0)) if disk_d else None,
            disk_d_total_gb=int(round(disk_d['total'] / (1024**3), 0)) if disk_d else None,
            disk_e_label="HDD (E:)",
            disk_e_percent=disk_e['percent'] if disk_e else None,
            disk_e_used_gb=int(round(disk_e['used'] / (1024**3), 0)) if disk_e else None,
            disk_e_total_gb=int(round(disk_e['total'] / (1024**3), 0)) if disk_e else None,
            cpu_temp=cpu_temp,
            gpu_temp=gpu_temp,
            has_temperatures=cpu_temp is not None or gpu_temp is not None
        )
    except Exception as e:
        logger.error(f"[System] Error fetching vitals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/errors", response_model=list[ErrorItem])
async def get_errors():
    """Return the last 10 errors as JSON."""
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5.0)
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
            errors.append(ErrorItem(
                id=row["id"],
                timestamp=row["timestamp"],
                project_name=row["project_name"],
                file_path=row["file_path"],
                error_text=row["error_text"],
                suggested_fix=row["suggested_fix"]
            ))
        return errors
    except Exception as e:
        logger.error(f"[Errors] Database error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """Receive audio blob, transcribe with Whisper, return text."""
    try:
        # Validate file type
        if not audio.content_type or not audio.content_type.startswith("audio/"):
            raise HTTPException(status_code=400, detail="Invalid file type. Expected audio/*")

        # Read audio data
        audio_data = await audio.read()
        if len(audio_data) < 1000:
            return {"text": "", "confidence": 0}

        # Save webm to temp file
        webm_path = LOGS_PATH / "temp_audio.webm"
        wav_path = LOGS_PATH / "temp_audio.wav"
        webm_path.write_bytes(audio_data)

        # Convert webm -> wav 16kHz mono with ffmpeg
        ffmpeg_exe = _get_ffmpeg_exe()
        try:
            result = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    ffmpeg_exe, '-y', '-i', str(webm_path), '-ar', '16000', '-ac', '1', str(wav_path),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                ),
                timeout=30
            )
            await result.wait()
            if result.returncode != 0:
                raise Exception("ffmpeg conversion failed")
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Audio conversion timeout")

        # Transcribe
        model = _get_whisper_model()
        if model is None:
            raise HTTPException(status_code=503, detail="Whisper model not available")

        # Run transcription in thread pool (blocking IO)
        def do_transcribe():
            segments, _ = model.transcribe(str(wav_path), language='en', beam_size=5)
            return " ".join(seg.text for seg in segments).strip()

        text = await asyncio.to_thread(do_transcribe)

        # Cleanup temp files
        try:
            webm_path.unlink(missing_ok=True)
            wav_path.unlink(missing_ok=True)
        except:
            pass

        logger.info(f"[Whisper] Transcribed: {text[:80]}...")
        return {"text": text, "confidence": 0.95}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Transcribe] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/clear-errors")
async def clear_errors():
    """DELETE all rows from the errors table (test-data wipe)."""
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5.0)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM errors")
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        logger.info(f"[ClearErrors] Deleted {deleted} error(s)")
        return {"status": "ok", "deleted": deleted}
    except Exception as e:
        logger.error(f"[ClearErrors] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/models")
async def get_models():
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
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:11434/api/tags", timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = [m["name"] for m in data.get("models", [])]
    except Exception:
        pass

    return {"models": models, "active": active}


@app.get("/vault/search")
async def vault_search(q: str = ""):
    """Search the Obsidian vault."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from memory import search_vault
        results = await asyncio.to_thread(search_vault, q)
        return {"results": results}
    except Exception as e:
        logger.error(f"[Vault] Search error: {e}")
        return {"error": str(e), "results": []}


@app.get("/vault/recent")
async def vault_recent():
    """Return last 10 recently modified vault files."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from memory import get_recent_files
        results = await asyncio.to_thread(get_recent_files, 10)
        return results
    except Exception as e:
        logger.error(f"[Vault] Recent error: {e}")
        return {"error": str(e), "files": []}


@app.post("/vault/save")
async def vault_save(request: VaultSaveRequest):
    """Save content to the vault."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from memory import save_to_wiki
        ok = await asyncio.to_thread(
            save_to_wiki, request.title, request.content, request.category
        )
        return {"status": "ok" if ok else "error"}
    except Exception as e:
        logger.error(f"[Vault] Save error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class VoiceNoteRequest(BaseModel):
    transcript: str
    tags: list[str] = []


@app.post("/vault/voice-note")
async def save_voice_note_endpoint(request: VoiceNoteRequest):
    """Save a voice note (quick memo) to the vault."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from memory import save_voice_note
        ok = await asyncio.to_thread(
            save_voice_note, request.transcript, request.tags
        )
        if ok:
            return {"status": "ok", "message": "Voice note saved to vault"}
        else:
            raise HTTPException(status_code=500, detail="Failed to save voice note")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Vault] Voice note error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sleep/status")
async def sleep_status():
    """Return current sleep status and time remaining."""
    try:
        sleeping = False
        try:
            if SLEEP_FLAG_PATH.exists():
                flag = SLEEP_FLAG_PATH.read_text().strip()
                sleeping = flag == "SLEEP"
        except Exception:
            pass

        last_activity = time.time()
        try:
            if HEARTBEAT_PATH.exists():
                last_activity = HEARTBEAT_PATH.stat().st_mtime
        except Exception:
            pass

        idle_secs = time.time() - last_activity
        time_remaining = max(0, int(IDLE_TIMEOUT_SECONDS - idle_secs))
        last_interaction_str = datetime.fromtimestamp(last_activity).strftime("%Y-%m-%d %H:%M:%S")

        return {
            "sleeping": sleeping,
            "time_remaining_seconds": time_remaining,
            "last_interaction": last_interaction_str,
            "idle_seconds": int(idle_secs),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sleep/wake")
async def sleep_wake():
    """Manually wake Jarvis by resetting the heartbeat."""
    try:
        HEARTBEAT_PATH.touch()
        try:
            SLEEP_FLAG_PATH.write_text("AWAKE")
        except Exception:
            pass
        return {"status": "ok", "state": "AWAKE"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sleep/sleep")
async def sleep_sleep():
    """Manually put Jarvis to sleep."""
    try:
        try:
            SLEEP_FLAG_PATH.write_text("SLEEP")
        except Exception:
            pass
        return {"status": "ok", "state": "SLEEP"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/errors/clear-test")
async def clear_test_errors():
    """Clear test error entries."""
    return await clear_errors()


class SkillTriggerRequest(BaseModel):
    skill: str
    params: dict = {}


@app.post("/skills/trigger")
async def trigger_skill(request: SkillTriggerRequest):
    """
    Trigger a skill by name.
    Built-in skills: good_morning, time, system_status, wake_up, sleep
    """
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from skills import trigger_skill_by_name
        result = trigger_skill_by_name(request.skill, request.params)
        return result
    except Exception as e:
        logger.error(f"[Skills] Trigger error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/skills")
async def get_skills():
    """List all available skills from the skills directory."""
    try:
        skills = []
        for skill_file in SKILLS_PATH.glob("*.toml"):
            try:
                content = skill_file.read_text(encoding='utf-8')
                # Parse basic TOML for name/trigger
                name = skill_file.stem
                trigger = ""
                for line in content.split('\n'):
                    if line.startswith('trigger'):
                        trigger = line.split('=')[1].strip().strip('"\'')
                    elif line.startswith('name'):
                        name = line.split('=')[1].strip().strip('"\'')
                skills.append({
                    "name": name,
                    "filename": skill_file.name,
                    "trigger": trigger,
                    "size": skill_file.stat().st_size
                })
            except Exception:
                pass
        return {"skills": skills, "count": len(skills)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/skills/{name}")
async def get_skill_file(name: str):
    """Return content of a specific skill file."""
    try:
        # Sanitize name to prevent path traversal
        name = ''.join(c for c in name if c.isalnum() or c in '_-')
        skill_file = SKILLS_PATH / f"{name}.toml"

        if not skill_file.exists():
            raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

        content = skill_file.read_text(encoding='utf-8')
        logger.info(f"[Skills] Retrieved: {skill_file.name}")
        return {"name": name, "content": content, "filename": skill_file.name}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/skills/import-zip")
async def import_skills_zip(file: UploadFile = File(...)):
    """Import skills from uploaded ZIP file (from GitHub or local)."""
    try:
        # Validate file
        if not file.content_type or "zip" not in file.content_type:
            # Check filename as fallback
            if not file.filename or not file.filename.endswith('.zip'):
                raise HTTPException(status_code=400, detail="Invalid file type. Expected .zip")

        # Read and validate size
        zip_data = await file.read()
        if len(zip_data) > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail=f"File too large. Max size: {MAX_UPLOAD_SIZE // (1024*1024)}MB")

        # Ensure skills directory exists
        SKILLS_PATH.mkdir(parents=True, exist_ok=True)

        imported = []
        errors = []

        # Extract ZIP
        try:
            with zipfile.ZipFile(BytesIO(zip_data), 'r') as zf:
                for file_info in zf.infolist():
                    if file_info.is_dir():
                        continue
                    if not file_info.filename.endswith('.toml'):
                        continue

                    # Clean filename
                    filename = Path(file_info.filename).name
                    if not filename or filename.startswith('.'):
                        continue

                    # Read and save
                    try:
                        content = zf.read(file_info.filename)
                        dest_path = SKILLS_PATH / filename
                        dest_path.write_bytes(content)
                        imported.append(filename)
                        logger.info(f"[Skills] Imported: {filename}")
                    except Exception as e:
                        errors.append(f"{filename}: {str(e)}")
        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="Invalid ZIP file")

        logger.info(f"[Skills] ZIP import complete: {len(imported)} files, {len(errors)} errors")
        return {"imported": imported, "count": len(imported), "errors": errors, "path": str(SKILLS_PATH)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Skills] Import error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/projects")
async def get_projects():
    """Return list of monitored projects."""
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5.0)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT project_name, 
                CASE 
                    WHEN MAX(CASE WHEN suggested_fix IS NOT NULL THEN 1 ELSE 0 END) = 1 THEN 'fixing'
                    ELSE 'error' 
                END as status
            FROM errors 
            GROUP BY project_name
        """)
        rows = cursor.fetchall()
        conn.close()

        projects = []
        for row in rows:
            projects.append({
                "name": row["project_name"],
                "status": row["status"]
            })
        return projects
    except Exception as e:
        logger.error(f"[Projects] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/screenshot")
async def take_screenshot():
    """Capture and return a screenshot."""
    try:
        screenshot_path = LOGS_PATH / "screenshot.png"

        if platform.system() == "Windows":
            # Use PIL for cross-platform screenshot
            try:
                from PIL import ImageGrab
                img = ImageGrab.grab()
                img.save(str(screenshot_path))
            except ImportError:
                # Fallback to PowerShell
                ps_cmd = f"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('%{{PRTSC}}'); Start-Sleep -m 250; Add-Type -AssemblyName System.Drawing; $bmp = New-Object System.Drawing.Bitmap(1920, 1080); $graphics = [System.Drawing.Graphics]::FromImage($bmp); $graphics.CopyFromScreen(0, 0, 0, 0, $bmp.Size); $bmp.Save('{screenshot_path}'); $graphics.Dispose(); $bmp.Dispose()"
                subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, timeout=10)
        else:
            raise HTTPException(status_code=501, detail="Screenshot only supported on Windows")

        if screenshot_path.exists():
            return FileResponse(str(screenshot_path), media_type="image/png", filename="screenshot.png")
        else:
            raise HTTPException(status_code=500, detail="Screenshot capture failed")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Screenshot] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/auth/verify", response_model=AuthVerifyResponse)
async def auth_verify(request: AuthVerifyRequest):
    """Verify password (server-side). Returns boolean without exposing the actual password."""
    try:
        # Get expected password from environment
        expected = os.getenv("OPERATOR_PASSWORD", "")
        if not expected:
            # If no password set, reject all attempts (fail secure)
            return AuthVerifyResponse(valid=False, message="Authentication not configured")

        # Simple constant-time comparison to prevent timing attacks
        import hmac
        valid = hmac.compare_digest(request.password.encode(), expected.encode())

        if valid:
            return AuthVerifyResponse(valid=True, message="Authentication successful")
        else:
            return AuthVerifyResponse(valid=False, message="Invalid password")
    except Exception as e:
        logger.error(f"[Auth] Verification error: {e}")
        return AuthVerifyResponse(valid=False, message="Authentication error")


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    logger.info(f"[FastAPI] Starting server on port {PORT}")
    logger.info(f"[FastAPI] Endpoints available at http://localhost:{PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
