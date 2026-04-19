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
from typing import AsyncGenerator
from decision_engine import DecisionEngine, select_model_by_ram
from pathlib import Path

try:
    from skills import try_handle_skill
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

if GEMINI_API_KEY:
    logger.info("[Config] Gemini API key configured (masked: ...%s)", GEMINI_API_KEY[-4:])
else:
    logger.warning("[Config] No Gemini API key found - complex tasks will use Ollama")

engine = DecisionEngine()
connected_clients = set()
ACTIVE_MODEL = OLLAMA_MODEL_FAST
ACTIVE_MODEL_PATH = Path(__file__).parent.parent / "logs" / "active_model.txt"

# FIX: Store the main event loop so the TTS thread can safely schedule coroutines
_main_loop: asyncio.AbstractEventLoop | None = None

# Ollama process tracking
_ollama_process = None
_ollama_lock = threading.Lock()


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

            logger.info(f"[Ollama] Starting server with: {ollama_exe}")
            _ollama_process = subprocess.Popen(
                [ollama_exe, "serve"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
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

    while True:
        text = _tts_queue.get()
        if text is None:
            break

        if not tts_available or engine is None:
            logger.warning("[TTS] Server TTS unavailable, sending tts_fallback to browser")
            _broadcast_from_thread({
                "type": "tts_fallback",
                "text": text,
                "reason": "server_tts_unavailable"
            })
            _tts_queue.task_done()
            continue

        logger.info(f"[TTS] Speaking: {text[:60]}...")
        try:
            engine.say(text)
            engine.runAndWait()
            logger.info("[TTS] Finished speaking")
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


def is_complex_task(text: str) -> bool:
    """Route financial queries to Gemini, everything else to Ollama."""
    financial_words = ['stock', 'crypto', 'bitcoin', 'invest', 'portfolio', 'revenue', 'profit', 'market']
    return any(w in text.lower() for w in financial_words)


async def handle_voice_command(websocket, text: str):
    """Process voice command: check skills first, then AI."""
    await broadcast({"type": "state", "state": "thinking"})

    # Check for built-in skill triggers FIRST (instant response, no AI needed)
    if INLINE_IMPORTS_AVAILABLE:
        try:
            skill_response = await asyncio.to_thread(try_handle_skill, text)
            if skill_response:
                logger.info(f"[Voice] Skill triggered for: {text[:50]}...")
                await websocket.send(json.dumps({
                    "type": "response",
                    "text": skill_response,
                    "model": "skill",
                    "server_tts": True
                }))
                await broadcast({"type": "state", "state": "speaking"})

                # Speak via server TTS (force=True so it speaks even with browser connected)
                speak_server(skill_response, force=True)

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
        selected_model = select_model_by_ram()
        use_gemini = USE_GEMINI_FALLBACK and (selected_model is None or is_complex_task(text))

        if selected_model:
            write_active_model(selected_model)

        if use_gemini:
            write_active_model("gemini-flash")
            logger.info(f"[Voice] Using Gemini for: {text[:50]}...")
            response = await query_gemini(prompt_text)
            await websocket.send(json.dumps({
                "type": "response",
                "text": response,
                "model": GEMINI_MODEL,
                "server_tts": True
            }))
        else:
            model_name = selected_model or OLLAMA_MODEL_FAST
            logger.info(f"[Voice] Streaming from Ollama ({model_name}): {text[:50]}...")
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

        # Server TTS — force=True so pyttsx3 speaks via computer speakers
        speak_server(response, force=True)

        # Save to vault
        if INLINE_IMPORTS_AVAILABLE:
            try:
                await asyncio.to_thread(save_conversation, text, response)
                if is_complex_task(text):
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
    DB_PATH = Path(__file__).parent.parent / "database" / "errors.db"
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