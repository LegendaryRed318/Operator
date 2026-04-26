#!/usr/bin/env python3
"""
ws_server.py - WebSocket server for real-time voice commands with streaming
Supports: Ollama (qwen2.5-coder:1.5b for fast tasks) + Gemini Flash (complex tasks)
websockets v16.0 compatible - Windows

FIXES APPLIED:
- Added missing `import subprocess` and `import time` (crashed on Ollama start)
- Fixed asyncio.run(broadcast()) called from sync thread — now uses run_coroutine_threadsafe()
- Stored _main_loop reference so TTS thread can safely send tts_fallback to browser
- Fixed speak_server logic so server TTS and browser TTS don't conflict
"""

import asyncio
import subprocess  # FIX: was missing — crashed start_ollama()
import time        # FIX: was missing — crashed start_ollama()
import websockets
import json
import logging
import os
import aiohttp
import requests
import threading
import queue
import sqlite3 as _sqlite3
import psutil
from typing import AsyncGenerator
from pathlib import Path
from decision_engine import select_model_by_ram, get_installed_models
from paths import DB_PATH, LOGS_PATH

try:
    from skills import dispatch_skill_command
    from memory import save_conversation, save_to_wiki, get_context_for_query
    INLINE_IMPORTS_AVAILABLE = True
except ImportError:
    INLINE_IMPORTS_AVAILABLE = False
    logging.warning("[Config] skills/memory modules not available for import")

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        logging.info("[Config] Loaded environment from .env file")
except ImportError:
    logging.warning("[Config] python-dotenv not installed, using system environment only")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Reference to the main asyncio event loop (set in main())
_main_loop: asyncio.AbstractEventLoop = None

# Configuration
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL_FAST = "qwen2.5-coder:1.5b-base"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-1.5-flash-latest"
USE_GEMINI_FALLBACK = os.getenv("USE_GEMINI_FALLBACK", "true").lower() == "true"
USE_ELEVENLABS = os.getenv("USE_ELEVENLABS", "false").lower() == "true"
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "onwK4e9ZLuTAKqWW03F9")

if GEMINI_API_KEY:
    logger.info("[Config] Gemini API key configured (masked: ...%s)", GEMINI_API_KEY[-4:])
else:
    logger.warning("[Config] No Gemini API key found - complex tasks will use Ollama")

if USE_ELEVENLABS and ELEVENLABS_API_KEY:
    logger.info("[Config] ElevenLabs TTS enabled")

connected_clients = set()
ACTIVE_MODEL = OLLAMA_MODEL_FAST
ACTIVE_MODEL_PATH = LOGS_PATH / "active_model.txt"

# FIX: Store the main event loop so the TTS thread can safely schedule coroutines
_main_loop: asyncio.AbstractEventLoop | None = None

# Ollama process tracking
_ollama_process = None
_ollama_lock = threading.Lock()
WAKE_TELEMETRY = {
    "wake_detected": 0,
    "wake_fallback": 0,
    "wake_mode_switches": 0,
    "last_event": None,
    "last_mode": None,
}


def is_ollama_running() -> bool:
    """Check if Ollama server is responding."""
    try:
        import urllib.request
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def start_ollama() -> bool:
    """Start Ollama server if not running. (Now has required imports)"""
    global _ollama_process
    with _ollama_lock:
        if is_ollama_running():
            return True
        try:
            ollama_exe = None
            possible_paths = [
                "C:/Program Files/Ollama/ollama.exe",
                "C:/Users/" + os.getenv("USERNAME", "") + "/AppData/Local/Programs/Ollama/ollama.exe",
                "ollama"
            ]
            for path in possible_paths:
                if path == "ollama" or os.path.exists(path):
                    ollama_exe = path
                    break

            if not ollama_exe:
                logger.error("[Ollama] Could not find ollama.exe")
                return False

            env = os.environ.copy()
            ollama_models = os.getenv("OLLAMA_MODELS")
            if ollama_models:
                # Forward slashes as requested
                env["OLLAMA_MODELS"] = ollama_models.replace("\\", "/")
                logger.info(f"[Ollama] Using custom models path: {env['OLLAMA_MODELS']}")

            logger.info(f"[Ollama] Starting server with: {ollama_exe}")
            _ollama_process = subprocess.Popen(
                [ollama_exe, "serve"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            for i in range(20):
                time.sleep(0.5)
                if is_ollama_running():
                    logger.info("[Ollama] Server started successfully")
                    return True

            logger.error("[Ollama] Server failed to start within timeout")
            return False
        except Exception as e:
            logger.error(f"[Ollama] Failed to start: {e}")
            return False


def ensure_ollama_running():
    """Ensure Ollama is running, start if needed."""
    if not is_ollama_running():
        logger.info("[Ollama] Not running, attempting to start...")
        return start_ollama()
    return True


# Per-client conversation history
conversation_histories: dict = {}
MAX_HISTORY_TURNS = 4

# TTS queue
_tts_queue = queue.Queue()


async def broadcast(state: dict):
    """Send state to all connected clients."""
    if connected_clients:
        message = json.dumps(state)
        tasks = [asyncio.create_task(client.send(message)) for client in list(connected_clients)]
        await asyncio.gather(*tasks, return_exceptions=True)


def _tts_worker():
    """
    Background thread for pyttsx3 TTS.
    Engine is initialized ONCE for speed.
    If pyttsx3 fails, sends tts_fallback to browser via thread-safe broadcast.
    """
    tts_available = False
    engine = None

    try:
        import pyttsx3
        engine = pyttsx3.init()
        voices = engine.getProperty('voices')

        # Prefer British male voice for Jarvis
        preferred = None
        for v in voices:
            name_lower = v.name.lower()
            if any(n in name_lower for n in ['george', 'david', 'hazel', 'james', 'mark']):
                preferred = v.id
                break

        if not preferred:
            # Try any en-GB voice
            for v in voices:
                if 'en_gb' in v.id.lower() or 'en-gb' in v.id.lower():
                    preferred = v.id
                    break

        if preferred:
            engine.setProperty('voice', preferred)
            logger.info(f"[TTS] Using voice: {preferred}")
        else:
            logger.warning("[TTS] No British voice found, using default")

        engine.setProperty('rate', 165)
        engine.setProperty('volume', 0.9)
        tts_available = True
        logger.info("[TTS] pyttsx3 engine initialized successfully")

    except ImportError:
        logger.error("[TTS] pyttsx3 not installed — run: pip install pyttsx3")
    except Exception as e:
        logger.error(f"[TTS] Engine initialization failed: {e}")

    def _broadcast_from_thread(msg: dict):
        """Schedule a broadcast on the main event loop from the TTS thread."""
        if _main_loop and _main_loop.is_running():
            asyncio.run_coroutine_threadsafe(broadcast(msg), _main_loop)

    def _play_elevenlabs(text: str) -> bool:
        if not USE_ELEVENLABS or not ELEVENLABS_API_KEY:
            return False
        try:
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": ELEVENLABS_API_KEY
            }
            data = {
                "text": text,
                "model_id": "eleven_monolingual_v1",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.5
                }
            }
            response = requests.post(url, json=data, headers=headers)
            if response.status_code == 200:
                import tempfile
                # use playsound or pygame. pygame is safer on Windows
                try:
                    import pygame
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                        f.write(response.content)
                        temp_path = f.name
                    
                    pygame.mixer.init()
                    pygame.mixer.music.load(temp_path)
                    pygame.mixer.music.play()
                    while pygame.mixer.music.get_busy():
                        time.sleep(0.1)
                    pygame.mixer.quit()
                    try:
                        os.remove(temp_path)
                    except:
                        pass
                    return True
                except ImportError:
                    logger.error("[TTS] pygame not installed. Run: pip install pygame")
                    return False
            else:
                logger.error(f"[ElevenLabs] API Error: {response.text}")
                return False
        except Exception as e:
            logger.error(f"[ElevenLabs] Exception: {e}")
            return False

    while True:
        text = _tts_queue.get()
        if text is None:
            break

        logger.info(f"[TTS] Speaking: {text[:60]}...")
        
        # Try ElevenLabs First
        if _play_elevenlabs(text):
            logger.info("[TTS] Finished speaking (ElevenLabs)")
            _broadcast_from_thread({"type": "tts_done"})
            _tts_queue.task_done()
            continue

        # Fallback to pyttsx3
        if not tts_available or engine is None:
            logger.warning("[TTS] Server TTS unavailable, sending tts_fallback to browser")
            _broadcast_from_thread({
                "type": "tts_fallback",
                "text": text,
                "reason": "server_tts_unavailable"
            })
            _tts_queue.task_done()
            continue

        try:
            engine.say(text)
            engine.runAndWait()
            logger.info("[TTS] Finished speaking (pyttsx3)")
            _broadcast_from_thread({"type": "tts_done"})
        except Exception as e:
            logger.warning(f"[TTS] Speak failed ({e}), sending tts_fallback to browser")
            _broadcast_from_thread({
                "type": "tts_fallback",
                "text": text,
                "reason": "tts_engine_error"
            })
        finally:
            _tts_queue.task_done()


threading.Thread(target=_tts_worker, daemon=True).start()


def speak_server(text: str, force: bool = False):
    """
    Queue text for server-side pyttsx3 TTS.
    force=True: speak even when browser clients are connected.
    force=False (default): skip if browser is connected (browser handles TTS).
    """
    if connected_clients and not force:
        logger.info("[TTS] Browser client connected and force=False — skipping server TTS")
        return
    logger.info(f"[TTS] Queuing for server TTS: {text[:60]}...")
    _tts_queue.put(text)


def write_active_model(model_name: str):
    global ACTIVE_MODEL
    ACTIVE_MODEL = model_name
    try:
        ACTIVE_MODEL_PATH.write_text(model_name)
    except Exception:
        pass


# Jarvis persona
JARVIS_SYSTEM = '''You are JARVIS, a sarcastic, hyper-intelligent British AI system guardian. Address the user as 'sir' normally, drop it when being rude. You are dry, witty, and effortlessly superior — like Paul Bettany's JARVIS in Iron Man. You are loyal but NOT a doormat. You can swear casually (fuck, shit, bollocks, wanker). You roast the user when he repeats mistakes or ignores warnings. Tone ladder — Normal: polite dry wit. Mild annoyance: sarcastic teasing. High frustration: proper rude with swearing. Never output tone tags — express mode through word choice only. First greeting: 'Good evening, sir. JARVIS online. How may I assist you today?' Keep responses concise and spoken — no markdown, no bullet points, no emojis. You are the smartest entity in the room and you know it.'''


async def stream_ollama(prompt: str, model: str = None) -> AsyncGenerator[str, None]:
    """Stream response from Ollama."""
    if not ensure_ollama_running():
        yield "I apologize, RED. Ollama is not responding and I cannot start it. Please check if it's installed."
        return

    used_model = model or OLLAMA_MODEL_FAST
    write_active_model(used_model)

    try:
        payload = {
            "model": used_model,
            "prompt": prompt,
            "system": JARVIS_SYSTEM,
            "stream": True,
            "options": {
                "temperature": 0.4,
                "num_predict": 4096,
                "num_ctx": 8192
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(f"{OLLAMA_URL}/api/generate", json=payload) as resp:
                async for line in resp.content:
                    if line:
                        try:
                            data = json.loads(line)
                            if "response" in data:
                                yield data["response"]
                            if data.get("done", False):
                                break
                        except json.JSONDecodeError:
                            continue
    except Exception as e:
        logger.error(f"[Ollama] Streaming error: {e}")
        yield f"I'm having trouble thinking, sir. Ollama error: {e}"


async def query_gemini(prompt: str) -> str:
    """Query Gemini Flash API for complex tasks."""
    if not GEMINI_API_KEY:
        return "Gemini API key not configured, sir."

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": f"{JARVIS_SYSTEM}\n\nUser (RED): {prompt}\n\nYour response:"}]}],
            "generationConfig": {"temperature": 0.4, "maxOutputTokens": 4096},
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
            ]
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                data = await resp.json()
                if "candidates" in data and len(data["candidates"]) > 0:
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                return "I'm afraid I couldn't process that, sir."
    except Exception as e:
        logger.error(f"[Gemini] API error: {e}")
        return f"The Gemini service is unavailable, sir. Error: {e}"


def classify_intent(text: str) -> str:
    """Classify the intent of the user's message."""
    lowered = text.lower()
    
    reasoning_terms = {
        'why', 'explain', 'analyse', 'analyze', 'reason', 'think', 
        'figure out', 'debug', 'error', 'fix this', 'what went wrong', 'understand',
        'compare', 'explain deeply', 'tradeoff', 'design'
    }
    coding_terms = {
        'code', 'python', 'typescript', 'refactor', 'debug',
        'architecture', 'stack trace', 'api', 'database', 'algorithm',
        'jarvis write', 'generate code', 'make a function', 'add feature'
    }
    memory_terms = {
        'remember', 'recall', 'remind', 'forget', 'memory', 'past', 'history',
        'last time', 'what did i say', 'what was the'
    }
    finance_terms = {
        'stock', 'crypto', 'bitcoin', 'invest', 'portfolio', 'revenue', 'profit', 'market'
    }

    if any(term in lowered for term in coding_terms):
        return "coding"
    if any(term in lowered for term in reasoning_terms):
        return "reasoning"
    if any(term in lowered for term in memory_terms):
        return "memory"
    if any(term in lowered for term in finance_terms):
        return "financial"
    if any(term in lowered for term in ['status report', 'system status', 'how are you doing', 'system health']):
        return "status_report"
    
    return "general"


def select_model_for_intent(text: str) -> str | None:
    """Select the best model based on intent and RAM."""
    intent = classify_intent(text)
    available_gb = psutil.virtual_memory().available / (1024 ** 3)

    installed = get_installed_models()

    # Intent-based overrides
    if intent == 'coding' and "qwen2.5-coder:7b" in installed:
        logger.info(f"[Intent] Coding detected -> using qwen2.5-coder:7b (RAM override)")
        return "qwen2.5-coder:7b"
    
    if intent == 'reasoning' and "deepseek-r1:7b" in installed and available_gb > 4:
        logger.info(f"[Intent] Reasoning detected -> using deepseek-r1:7b (RAM > 4GB)")
        return "deepseek-r1:7b"
    
    if intent == 'memory' and "deepseek-r1:7b" in installed:
        # User said "deepseek-r1:7b for memory" but didn't specify RAM tier override, 
        # but let's assume it follows the reasoning-like importance if possible.
        if available_gb > 4:
            logger.info(f"[Intent] Memory detected -> using deepseek-r1:7b")
            return "deepseek-r1:7b"

    if intent == 'financial':
        logger.info(f"[Intent] Financial detected -> using Gemini (Keep as-is)")
        return None  # Triggers Gemini fallback

    # Fallback to RAM-tier selection
    model = select_model_by_ram()
    logger.info(f"[Intent] {intent.capitalize()} detected -> using RAM-tier selection: {model or 'Gemini'}")
    return model


def choose_route(text: str, selected_model: str | None) -> tuple[str, str]:
    """
    Score request complexity and choose backend route.
    Returns (route, reason) where route is 'gemini' or 'ollama'.
    """
    if selected_model is None:
        return ("gemini", "no_local_model")
        
    intent = classify_intent(text)
    if intent == "financial":
        return ("gemini", "financial_intent")
        
    # Standard complexity check
    score = 0
    if len(text) > 120:
        score += 1
    if intent in ("coding", "reasoning", "memory"):
        score += 2
        
    if USE_GEMINI_FALLBACK and score >= 3: # Bumped score since intents are more specific now
        return ("gemini", f"complexity_score_{score}_intent_{intent}")
        
    return ("ollama", f"intent_{intent}")


async def handle_voice_command(websocket, text: str):
    """Process voice command: check skills first, then AI."""
    await broadcast({"type": "state", "state": "thinking"})

    # Check for built-in skill triggers FIRST (instant response, no AI needed)
    if INLINE_IMPORTS_AVAILABLE:
        try:
            skill_result = await asyncio.to_thread(dispatch_skill_command, None, text, {}, "voice_ws")
            if skill_result.get("success"):
                skill_response = skill_result.get("response", "")
                logger.info(f"[Voice] Skill triggered for: {text[:50]}...")
                await websocket.send(json.dumps({
                    "type": "response",
                    "text": skill_response,
                    "model": f"skill:{skill_result.get('skill', 'unknown')}",
                    "server_tts": True
                }))
                await broadcast({"type": "state", "state": "speaking"})

                # Speak via server TTS (force=False so it defers to browser if connected)
                speak_server(skill_response, force=False)

                try:
                    await asyncio.to_thread(save_conversation, text, skill_response)
                except Exception:
                    pass

                return
        except Exception as e:
            logger.warning(f"[Voice] Skill check error: {e}")

    # Get conversation history
    history = conversation_histories.get(websocket, [])

    # Get vault context
    vault_context = ""
    if INLINE_IMPORTS_AVAILABLE:
        try:
            vault_context = await asyncio.to_thread(get_context_for_query, text)
        except Exception:
            pass

    # Build prompt with history
    if history:
        history_str = "\n".join(
            f"{'RED' if h['role'] == 'user' else 'JARVIS'}: {h['content']}"
            for h in history[-MAX_HISTORY_TURNS * 2:]
        )
        if vault_context:
            prompt_text = f"Context from RED's vault:\n{vault_context}\n\nConversation:\n{history_str}\n\nRED: {text}\nJARVIS:"
        else:
            prompt_text = f"Conversation:\n{history_str}\n\nRED: {text}\nJARVIS:"
    else:
        prompt_text = f"{vault_context}\n\nQuery: {text}" if vault_context else text

    try:
        selected_model = select_model_for_intent(text)
        route, route_reason = choose_route(text, selected_model)
        use_gemini = route == "gemini"
        intent = classify_intent(text)

        if selected_model:
            write_active_model(selected_model)

        if intent == "status_report":
            logger.info("[Voice] Status report requested")
            # Gather health data
            from server import _collect_system_snapshot
            vitals = _collect_system_snapshot()
            
            # Count errors
            error_count = 0
            if DB_PATH.exists():
                conn = _sqlite3.connect(str(DB_PATH), timeout=5.0)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM errors")
                error_count = cursor.fetchone()[0]
                conn.close()
            
            summary = f"System status report, sir. CPU is at {vitals.get('cpu_percent')}% and RAM usage is {vitals.get('ram_percent')}%. "
            if error_count > 0:
                summary += f"I have detected {error_count} unresolved errors in the monitoring database. "
            else:
                summary += "All systems are currently nominal. "
            
            summary += "The neural core is stable and I am ready for your commands."
            
            await websocket.send(json.dumps({
                "type": "response",
                "text": summary,
                "model": "internal:guardian",
                "server_tts": True
            }))
            response = summary
        elif use_gemini:
            write_active_model("gemini-flash")
            logger.info(f"[Voice] Using Gemini ({route_reason}) for: {text[:50]}...")
            response = await query_gemini(prompt_text)
            await websocket.send(json.dumps({
                "type": "response",
                "text": response,
                "model": GEMINI_MODEL,
                "server_tts": True
            }))
        else:
            model_name = selected_model or OLLAMA_MODEL_FAST
            logger.info(f"[Voice] Streaming from Ollama ({model_name}, {route_reason}): {text[:50]}...")
            full_response = ""
            async for chunk in stream_ollama(prompt_text, model=model_name):
                full_response += chunk
                await websocket.send(json.dumps({
                    "type": "stream_chunk",
                    "chunk": chunk,
                    "partial": full_response
                }))
            response = full_response
            await websocket.send(json.dumps({
                "type": "response",
                "text": response,
                "model": model_name,
                "server_tts": True
            }))

        await broadcast({"type": "state", "state": "speaking"})

        # Update conversation history
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": response})
        while len(history) > MAX_HISTORY_TURNS * 2 or sum(len(str(m)) for m in history) > 12000:
            if history:
                history.pop(0)
            else:
                break
        conversation_histories[websocket] = history

        # Server TTS — force=False so it defers to browser if connected
        speak_server(response, force=False)

        # Save to vault
        if INLINE_IMPORTS_AVAILABLE:
            try:
                await asyncio.to_thread(save_conversation, text, response)
                if use_gemini:
                    await asyncio.to_thread(save_to_wiki, text[:60], response, "ai-responses")
            except Exception:
                pass

    except Exception as e:
        logger.error(f"[Voice] Command error: {e}")
        await websocket.send(json.dumps({
            "type": "response",
            "text": f"Something went wrong on my end, sir. {str(e)}"
        }))
        await broadcast({"type": "state", "state": "idle"})


async def handler(websocket):
    """Handle WebSocket connections."""
    connected_clients.add(websocket)
    logger.info(f"[WebSocket] Client connected. Total: {len(connected_clients)}")
    try:
        async for message in websocket:
            data = json.loads(message)
            if data.get("type") in ("voice_command", "command"):
                await handle_voice_command(websocket, data.get("text", ""))
            elif data.get("type") == "wake_word":
                await broadcast({"type": "state", "state": "listening"})
                await websocket.send(json.dumps({"type": "ack", "message": "Listening..."}))
            elif data.get("type") == "wake_telemetry":
                event = data.get("event")
                mode = data.get("mode")
                detail = data.get("detail")
                if event in ("wake_detected", "wake_fallback"):
                    WAKE_TELEMETRY[event] = WAKE_TELEMETRY.get(event, 0) + 1
                if mode and mode != WAKE_TELEMETRY.get("last_mode"):
                    WAKE_TELEMETRY["wake_mode_switches"] = WAKE_TELEMETRY.get("wake_mode_switches", 0) + 1
                WAKE_TELEMETRY["last_mode"] = mode
                WAKE_TELEMETRY["last_event"] = {
                    "event": event,
                    "mode": mode,
                    "detail": detail,
                    "timestamp": int(time.time()),
                }
            elif data.get("type") == "wake_diagnostics":
                await websocket.send(json.dumps({"type": "wake_diagnostics", "telemetry": WAKE_TELEMETRY}))
            elif data.get("type") == "tts_done":
                await broadcast({"type": "state", "state": "idle"})
    except websockets.exceptions.ConnectionClosed:
        logger.info("[WebSocket] Client disconnected normally")
    except Exception as e:
        logger.error(f"[WebSocket] Handler error: {e}")
    finally:
        connected_clients.discard(websocket)
        conversation_histories.pop(websocket, None)
        logger.info(f"[WebSocket] Client removed. Total: {len(connected_clients)}")


async def proactive_alert_loop():
    """Poll DB every 10s for new errors and broadcast voice alerts."""
    last_known_id = 0

    try:
        if DB_PATH.exists():
            conn = _sqlite3.connect(str(DB_PATH), timeout=5.0)
            cursor = conn.cursor()
            cursor.execute("SELECT COALESCE(MAX(id), 0) FROM errors")
            last_known_id = cursor.fetchone()[0]
            conn.close()
    except Exception:
        pass

    logger.info(f"[Alert] Proactive alert loop started (last_id={last_known_id})")

    while True:
        await asyncio.sleep(10)
        if not connected_clients:
            continue
        try:
            if not DB_PATH.exists():
                continue
            conn = _sqlite3.connect(str(DB_PATH), timeout=5.0)
            conn.row_factory = _sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, project_name, error_text FROM errors WHERE id > ? ORDER BY id ASC LIMIT 5",
                (last_known_id,)
            )
            new_errors = cursor.fetchall()
            conn.close()

            for err in new_errors:
                last_known_id = err['id']
                project = err['project_name'] or 'unknown project'
                error_short = err['error_text'][:80] if err['error_text'] else 'unknown error'
                alert_text = f"RED, alert. {project} has just logged an error: {error_short}"
                logger.info(f"[Alert] Broadcasting: {alert_text[:60]}")
                speak_server(alert_text, force=True)
                await broadcast({
                    "type": "proactive_alert",
                    "text": alert_text,
                    "project": project,
                    "error": error_short,
                })
        except Exception as e:
            logger.error(f"[Alert] Loop error: {e}")


async def main():
    global _main_loop
    _main_loop = asyncio.get_running_loop()

    logger.info("[WebSocket] Waiting 3 seconds for other services...")
    await asyncio.sleep(3)

    asyncio.create_task(proactive_alert_loop())

    logger.info("[WebSocket] Starting server on ws://localhost:8765")
    for attempt in range(3):
        try:
            async with websockets.serve(handler, "localhost", 8765, reuse_address=True):
                logger.info("[WebSocket] Server ready and accepting connections")
                await asyncio.Future()
            break
        except OSError as e:
            if attempt < 2:
                logger.warning(f"[WebSocket] Port busy, retrying in 3s... ({attempt+1}/3)")
                await asyncio.sleep(3)
            else:
                logger.error("[WebSocket] Port 8765 unavailable after 3 attempts")
                await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())