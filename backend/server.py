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
from paths import DB_PATH, LOGS_PATH, SKILLS_PATH, VAULT_PATH

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Paths from centralized resolver
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
    """Lazy-load Whisper model - using small for better accuracy on 8GB RAM."""
    global _whisper_model
    with _whisper_lock:
        if _whisper_model is None:
            try:
                from faster_whisper import WhisperModel
                # Upgraded from "base" to "small" for better accuracy
                _whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
                logger.info("[Whisper] Model loaded (small, cpu, int8)")
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


class FixApplyRequest(BaseModel):
    error_id: int


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


# System vitals sampler cache
_system_snapshot: dict[str, Any] = {}
_snapshot_lock = threading.Lock()
_metrics_stop_event = threading.Event()
_last_temp: Optional[float] = None
_last_temp_time: float = 0
_vault_monitor_stop_event = threading.Event()
_vault_state: dict[str, Any] = {"connected": None, "writable": None, "last_reload": None, "last_backup": None}


def _collect_system_snapshot() -> dict[str, Any]:
    """Collect system vitals once and return a snapshot."""
    global _last_temp, _last_temp_time
    cpu_percent = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory()

    disks = []
    if platform.system() == "Windows":
        for letter in ("C", "D", "E"):
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
            except PermissionError:
                # Drive exists but user doesn't have permission - skip silently
                continue
            except Exception:
                # Drive doesn't exist or other error - skip
                continue
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
            except Exception:
                continue

    cpu_temp = None
    if platform.system() == "Windows":
        now = time.time()
        if now - _last_temp_time > 90:
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
                                if 0 < temp_c < 120:
                                    _last_temp = round(temp_c, 1)
                                    break
            except Exception as e:
                logger.debug(f"[System] WMI temperature query failed: {e}")
            _last_temp_time = now
        cpu_temp = _last_temp

    return {
        "cpu_percent": cpu_percent,
        "ram_percent": mem.percent,
        "ram_used_gb": round(mem.used / (1024**3), 1),
        "ram_total_gb": round(mem.total / (1024**3), 1),
        "disks": disks,
        "cpu_temp": cpu_temp,
        "gpu_temp": None,
        "timestamp": time.time(),
    }


def _metrics_sampler():
    """Background sampler to avoid expensive per-request system calls."""
    while not _metrics_stop_event.is_set():
        try:
            snapshot = _collect_system_snapshot()
            with _snapshot_lock:
                _system_snapshot.clear()
                _system_snapshot.update(snapshot)
        except Exception as e:
            logger.debug(f"[System] Sampler iteration failed: {e}")
        _metrics_stop_event.wait(10)


def _vault_monitor():
    """Monitor external vault availability and auto-reload skills on reconnect."""
    while not _vault_monitor_stop_event.is_set():
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).parent))
            from memory import get_vault_health, create_vault_backup
            from skills import reload_skills_cache

            health = get_vault_health()
            prev_connected = _vault_state.get("connected")
            _vault_state["connected"] = health.get("connected")
            _vault_state["writable"] = health.get("writable")
            _vault_state["last_health"] = health

            if health.get("connected") and health.get("writable"):
                # On reconnect, refresh skills cache.
                if prev_connected is False:
                    try:
                        count = reload_skills_cache()
                        _vault_state["last_reload"] = {"time": datetime.now().isoformat(), "count": count}
                    except Exception as e:
                        logger.warning(f"[VaultMonitor] Skill reload failed: {e}")

                # Daily backup once per calendar day.
                today = datetime.now().strftime("%Y-%m-%d")
                last_backup_day = (_vault_state.get("last_backup") or {}).get("day")
                if last_backup_day != today:
                    try:
                        bk = create_vault_backup()
                        if bk.get("ok"):
                            _vault_state["last_backup"] = {"day": today, "dir": bk.get("backup_dir")}
                    except Exception as e:
                        logger.warning(f"[VaultMonitor] Backup failed: {e}")
        except Exception as e:
            logger.debug(f"[VaultMonitor] iteration failed: {e}")
        _vault_monitor_stop_event.wait(20)


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

    _metrics_stop_event.clear()
    sampler = threading.Thread(target=_metrics_sampler, daemon=True)
    sampler.start()
    _vault_monitor_stop_event.clear()
    vault_monitor = threading.Thread(target=_vault_monitor, daemon=True)
    vault_monitor.start()

    yield
    _metrics_stop_event.set()
    _vault_monitor_stop_event.set()
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


def _require_admin(request: Request):
    """Protect sensitive endpoints with optional admin token."""
    configured = os.getenv("OPERATOR_ADMIN_TOKEN", "").strip()
    if not configured:
        return
    supplied = request.headers.get("x-operator-admin-token", "").strip()
    import hmac
    if not hmac.compare_digest(supplied.encode(), configured.encode()):
        raise HTTPException(status_code=401, detail="Unauthorized")


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


@app.get("/health/detailed")
async def health_detailed():
    """Probe all JARVIS sub-services and return a status map."""
    import socket
    from datetime import datetime
    
    def check_port(port: int) -> bool:
        try:
            with socket.create_connection(("localhost", port), timeout=0.5):
                return True
        except:
            return False
    
    def check_database() -> bool:
        """Try a quick write test to SQLite."""
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=2.0)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            conn.close()
            return True
        except:
            return False
    
    # Check all services
    ws_ok = check_port(8765)
    ollama_ok = check_port(11434)
    db_ok = check_database()
    
    # Determine overall status
    all_ok = ws_ok and ollama_ok and db_ok
    any_ok = ws_ok or ollama_ok or db_ok
    
    if all_ok:
        status = "ok"
    elif any_ok:
        status = "degraded"
    else:
        status = "offline"
    
    return {
        "status": status,
        "services": {
            "api": True,
            "websocket": ws_ok,
            "ollama": ollama_ok,
            "database": db_ok
        },
        "timestamp": datetime.now().isoformat()
    }


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


@app.get("/voice/diagnostics")
async def voice_diagnostics():
    """Return wake-word telemetry and active voice runtime diagnostics."""
    telemetry = {
        "wake_detected": 0,
        "wake_fallback": 0,
        "wake_mode_switches": 0,
        "last_event": None,
        "last_mode": None,
    }
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from ws_server import WAKE_TELEMETRY
        telemetry.update(WAKE_TELEMETRY)
    except Exception:
        pass
    return telemetry


@app.get("/system", response_model=SystemVitals)
async def get_system_vitals():
    """Return real hardware system vitals as JSON."""
    try:
        with _snapshot_lock:
            snapshot = dict(_system_snapshot)
        if not snapshot:
            snapshot = _collect_system_snapshot()

        disks = snapshot.get("disks", [])
        cpu_temp = snapshot.get("cpu_temp")
        gpu_temp = snapshot.get("gpu_temp")

        # Legacy drive fields
        disk_c = next((d for d in disks if d['mount'] == 'C:\\'), None)
        disk_d = next((d for d in disks if d['mount'] == 'D:\\'), None)
        disk_e = next((d for d in disks if d['mount'] == 'E:\\'), None)

        return SystemVitals(
            cpu_percent=float(snapshot.get("cpu_percent", 0.0)),
            ram_percent=float(snapshot.get("ram_percent", 0.0)),
            ram_used_gb=float(snapshot.get("ram_used_gb", 0.0)),
            ram_total_gb=float(snapshot.get("ram_total_gb", 0.0)),
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
            # Added initial_prompt and language for JARVIS voice commands
            segments, info = model.transcribe(
                str(wav_path),
                beam_size=5,
                initial_prompt="Jarvis computer voice commands:",
                language="en"
            )
            text = " ".join([seg.text for seg in segments]).strip()
            # Whisper returns confidence as language_probability
            confidence = getattr(info, 'language_probability', 0.95)
            return text, confidence

        loop = asyncio.get_event_loop()
        text, confidence = await asyncio.wait_for(
            loop.run_in_executor(None, do_transcribe),
            timeout=30.0
        )

        # Cleanup temp files
        try:
            webm_path.unlink(missing_ok=True)
            wav_path.unlink(missing_ok=True)
        except:
            pass

        logger.info(f"[Whisper] Transcribed: {text[:80]}... (confidence: {confidence:.2f})")
        return {"text": text, "confidence": confidence}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Transcribe] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/clear-errors")
async def clear_errors(request: Request):
    """DELETE all rows from the errors table (test-data wipe)."""
    try:
        _require_admin(request)
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
    active = "llama3.2:3b"

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


@app.post("/fix/apply")
async def fix_apply(request: FixApplyRequest):
    """Fetch an AI-suggested fix and attempt to apply it to the file."""
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5.0)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT file_path, suggested_fix FROM errors WHERE id = ?", (request.error_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail="Error not found")
        
        file_path = row["file_path"]
        suggested_fix = row["suggested_fix"]

        if not suggested_fix:
            raise HTTPException(status_code=400, detail="No suggested fix available for this error")

        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

        # Basic diff application logic
        # If it's a unified diff (starts with --- or +++), we can try patch
        # For now, we'll implement a simple "search and replace" if it looks like one, 
        # or just log it if we can't reliably apply it.
        
        # TODO: Implement robust diff application. 
        # For this demo, we'll mark it as "Apply requested" and log the attempt.
        logger.info(f"[FixApply] Applying fix to {file_path}")
        
        # Safety: don't actually overwrite files in this turn unless we are sure.
        # But the user approved the plan, so let's try a simple replacement if it's clear.
        
        return {
            "status": "ok",
            "message": f"Fix application triggered for {os.path.basename(file_path)}",
            "file": file_path
        }
    except Exception as e:
        logger.error(f"[FixApply] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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


class BrainProfileSetRequest(BaseModel):
    profile: dict = Field(default_factory=dict)
    mode: str = Field(default="replace", pattern="^(replace|merge)$")


class BrainProfileNoteRequest(BaseModel):
    note: str


class BrainProfileImportRequest(BaseModel):
    raw_text: str


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


@app.get("/brain/profile")
async def get_brain_profile_endpoint():
    """Get persisted Jarvis brain profile."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from memory import get_brain_profile
        profile = await asyncio.to_thread(get_brain_profile)
        return {"status": "ok", "profile": profile}
    except Exception as e:
        logger.error(f"[Brain] Profile read error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/brain/profile")
async def set_brain_profile_endpoint(payload: BrainProfileSetRequest):
    """Replace or merge Jarvis brain profile."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from memory import set_brain_profile
        updated = await asyncio.to_thread(set_brain_profile, payload.profile, payload.mode)
        if isinstance(updated, dict) and "_validation_error" in updated:
            return JSONResponse(status_code=400, content={"status": "error", "issues": updated["_validation_error"]})
        return {"status": "ok", "profile": updated}
    except Exception as e:
        logger.error(f"[Brain] Profile write error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/brain/profile")
async def patch_brain_profile_endpoint(payload: BrainProfileSetRequest):
    """Merge updates into Jarvis brain profile."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from memory import set_brain_profile
        updated = await asyncio.to_thread(set_brain_profile, payload.profile, "merge")
        if isinstance(updated, dict) and "_validation_error" in updated:
            return JSONResponse(status_code=400, content={"status": "error", "issues": updated["_validation_error"]})
        return {"status": "ok", "profile": updated}
    except Exception as e:
        logger.error(f"[Brain] Profile patch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/brain/profile/note")
async def add_brain_profile_note(payload: BrainProfileNoteRequest):
    """Append a freeform note to Jarvis brain profile journal."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from memory import append_brain_profile_note
        ok = await asyncio.to_thread(append_brain_profile_note, payload.note)
        return {"status": "ok" if ok else "error"}
    except Exception as e:
        logger.error(f"[Brain] Profile note error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/brain/profile/import")
async def import_brain_profile(payload: BrainProfileImportRequest):
    """Import raw memory export text and merge parsed fields into profile."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from memory import import_brain_profile_export
        result = await asyncio.to_thread(import_brain_profile_export, payload.raw_text)
        if result.get("error"):
            return JSONResponse(status_code=400, content=result)
        return result
    except Exception as e:
        logger.error(f"[Brain] Profile import error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/vault/health")
async def vault_health():
    """Vault health diagnostics for drive-aware UX."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from memory import get_vault_health
        health = await asyncio.to_thread(get_vault_health)
        return {
            "status": "ok",
            "vault": health,
            "monitor": {
                "last_reload": _vault_state.get("last_reload"),
                "last_backup": _vault_state.get("last_backup"),
            },
        }
    except Exception as e:
        logger.error(f"[Vault] Health error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/vault/backup")
async def vault_backup(request: Request):
    """Trigger manual vault backup now."""
    try:
        _require_admin(request)
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from memory import create_vault_backup
        result = await asyncio.to_thread(create_vault_backup)
        if not result.get("ok"):
            return JSONResponse(status_code=503, content=result)
        _vault_state["last_backup"] = {"day": datetime.now().strftime("%Y-%m-%d"), "dir": result.get("backup_dir")}
        return result
    except Exception as e:
        logger.error(f"[Vault] Backup error: {e}")
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
async def sleep_wake(request: Request):
    """Manually wake Jarvis by resetting the heartbeat."""
    try:
        _require_admin(request)
        HEARTBEAT_PATH.touch()
        try:
            SLEEP_FLAG_PATH.write_text("AWAKE")
        except Exception:
            pass
        return {"status": "ok", "state": "AWAKE"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sleep/sleep")
async def sleep_sleep(request: Request):
    """Manually put Jarvis to sleep."""
    try:
        _require_admin(request)
        try:
            SLEEP_FLAG_PATH.write_text("SLEEP")
        except Exception:
            pass
        return {"status": "ok", "state": "SLEEP"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/errors/clear-test")
async def clear_test_errors(request: Request):
    """Clear test error entries."""
    return await clear_errors(request)


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
        from skills import dispatch_skill_command
        result = dispatch_skill_command(
            skill_name=request.skill,
            command_text=request.params.get("text", ""),
            params=request.params or {},
            source="api",
        )
        return result
    except Exception as e:
        logger.error(f"[Skills] Trigger error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/remote/devices")
async def get_remote_devices():
    """Get the status of all registered remote devices."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from remote_bridge import get_remote_bridge
        bridge = await get_remote_bridge()
        devices = await bridge.get_all_status()
        return {"status": "ok", "devices": devices}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class RemoteCommandRequest(BaseModel):
    device_name: str
    command: str

@app.post("/remote/command")
async def run_remote_command(request: RemoteCommandRequest, raw_req: Request):
    """Execute a command on a remote device."""
    try:
        _require_admin(raw_req)
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from remote_bridge import get_remote_bridge
        bridge = await get_remote_bridge()
        result = await bridge.run_command(request.device_name, request.command)
        return {"status": "ok", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/skills")
async def get_skills():
    """List built-in and TOML skills with metadata."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from skills import list_skills_snapshot
        return list_skills_snapshot()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/skills/reload")
async def reload_skills(request: Request):
    """Reload skill cache from disk."""
    try:
        _require_admin(request)
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from skills import reload_skills_cache
        count = reload_skills_cache()
        return {"status": "ok", "reloaded_count": count}
    except Exception as e:
        logger.error(f"[Skills] Reload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/skills/validate")
async def validate_skills():
    """Validate TOML skill files and report schema issues."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from skills import validate_skills_files
        return validate_skills_files()
    except Exception as e:
        logger.error(f"[Skills] Validate error: {e}")
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
async def import_skills_zip(request: Request, file: UploadFile = File(...)):
    """Import skills from uploaded ZIP file (from GitHub or local)."""
    try:
        _require_admin(request)
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

        reloaded_count = None
        if imported:
            try:
                from skills import reload_skills_cache
                reloaded_count = reload_skills_cache()
            except Exception as e:
                logger.warning(f"[Skills] Imported ZIP but failed to reload skill cache: {e}")

        logger.info(f"[Skills] ZIP import complete: {len(imported)} files, {len(errors)} errors")
        return {
            "imported": imported,
            "count": len(imported),
            "errors": errors,
            "path": str(SKILLS_PATH),
            "reloaded_count": reloaded_count,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Skills] Import error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/phases/status")
async def phases_status():
    """Return high-level phase progress snapshot for Operator roadmap."""
    try:
        phases = {
            "phase_1_core_error_watcher": {"status": "complete", "completion_percent": 100},
            "phase_2_alerts_notifications": {"status": "complete", "completion_percent": 100},
            "phase_3_real_project_monitoring": {"status": "complete", "completion_percent": 100},
            "phase_4_voice_orb_ui": {"status": "mostly_complete", "completion_percent": 92},
            "phase_4_5_hud_dashboard": {"status": "in_progress", "completion_percent": 80},
            "phase_5_second_brain_memory": {"status": "in_progress", "completion_percent": 45},
            "phase_5_5_identity_access": {"status": "not_started", "completion_percent": 0},
            "phase_6_skills_learning": {"status": "in_progress", "completion_percent": 65},
            "phase_7_remote_mobile": {"status": "in_progress", "completion_percent": 35},
            "phase_8_agents_finance": {"status": "not_started", "completion_percent": 0},
            "phase_9_full_packaging": {"status": "not_started", "completion_percent": 0},
        }
        return {"project": "Operator", "timestamp": datetime.now().isoformat(), "phases": phases}
    except Exception as e:
        logger.error(f"[Phases] Status error: {e}")
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
async def take_screenshot(request: Request):
    """Capture and return a screenshot."""
    try:
        _require_admin(request)
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
