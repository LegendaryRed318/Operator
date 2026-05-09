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
    from memory import save_conversation, save_to_wiki, get_context_for_query, query_memory
    INLINE_IMPORTS_AVAILABLE = True
except ImportError:
    INLINE_IMPORTS_AVAILABLE = False
    logging.warning("[Config] skills/memory modules not available for import")

# Tool calling and RAG imports
try:
    from tool_executor import parse_and_execute, get_tool_schema
    TOOL_IMPORTS_AVAILABLE = True
except ImportError:
    TOOL_IMPORTS_AVAILABLE = False
    logging.warning("[Config] tool_executor not available")

try:
    from vault_rag import init_vault_rag, get_vault_rag, periodic_reindex
    RAG_IMPORTS_AVAILABLE = True
except ImportError:
    RAG_IMPORTS_AVAILABLE = False
    logging.warning("[Config] vault_rag not available")

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
_main_loop: asyncio.AbstractEventLoop | None = None

# Configuration
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL_FAST = "llama3.2:3b"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-1.5-flash-latest"
USE_GEMINI_FALLBACK = os.getenv("USE_GEMINI_FALLBACK", "true").lower() == "true"

# Offline mode tracking
OFFLINE_MODE = False

# RAG Configuration
RAG_INDEX_PATHS = os.getenv("RAG_INDEX_PATHS", "").split(";")
if not RAG_INDEX_PATHS or RAG_INDEX_PATHS == [""]:
    RAG_INDEX_PATHS = None
else:
    RAG_INDEX_PATHS = [p.strip() for p in RAG_INDEX_PATHS if p.strip()]

def check_internet() -> bool:
    """Check if internet is available."""
    try:
        import socket
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        return True
    except OSError:
        return False

def update_offline_mode():
    """Update global offline mode status."""
    global OFFLINE_MODE
    was_offline = OFFLINE_MODE
    OFFLINE_MODE = not check_internet()
    if OFFLINE_MODE != was_offline:
        if OFFLINE_MODE:
            logger.warning("[Connectivity] Offline mode activated")
        else:
            logger.info("[Connectivity] Online mode restored")
    return OFFLINE_MODE

# Check at startup
update_offline_mode()

if GEMINI_API_KEY:
    logger.info("[Config] Gemini API key configured (masked: ...%s)", GEMINI_API_KEY[-4:])
else:
    logger.warning("[Config] No Gemini API key found - complex tasks will use Ollama")

connected_clients = set()
ACTIVE_MODEL = OLLAMA_MODEL_FAST
ACTIVE_MODEL_PATH = LOGS_PATH / "active_model.txt"


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


async def prewarm_ollama_model():
    """Warm up the default Ollama model to avoid first-query delay."""
    await asyncio.sleep(5)  # Wait for other services to settle

    if not is_ollama_running():
        logger.info("[Prewarm] Ollama not running, skipping model warm-up")
        return

    model = OLLAMA_MODEL_FAST
    logger.info(f"[Prewarm] Warming up {model}...")

    try:
        # Send a simple query to load model into memory
        payload = {
            "model": model,
            "prompt": "Hello",
            "system": "You are JARVIS. Respond with only: 'Ready, sir.'",
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 10}
        }

        timeout = aiohttp.ClientTimeout(total=60, connect=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{OLLAMA_URL}/api/generate", json=payload) as resp:
                if resp.status == 200:
                    logger.info(f"[Prewarm] {model} is ready")
                else:
                    logger.warning(f"[Prewarm] {model} warm-up returned status {resp.status}")
    except Exception as e:
        logger.warning(f"[Prewarm] Could not warm up model: {e}")


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

        # Prefer British voice for Jarvis
        preferred = None
        # First pass: look for specific UK names
        for v in voices:
            name_lower = v.name.lower()
            if any(n in name_lower for n in ['george', 'hazel', 'susan', 'james', 'daniel']):
                preferred = v.id
                break
        
        # Second pass: strictly en-GB
        if not preferred:
            for v in voices:
                if 'en-gb' in v.id.lower() or 'en_gb' in v.id.lower():
                    preferred = v.id
                    break

        if preferred:
            engine.setProperty('voice', preferred)
            logger.info(f"[TTS] Using server voice: {preferred}")
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

        logger.info(f"[TTS] Speaking: {text[:60]}...")

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
    If clients are connected, we skip this to avoid "double speech",
    unless 'force' is True (for critical system alerts).
    """
    if not text or not text.strip():
        return
        
    # Skip server speech if browser is connected, unless forced
    if len(connected_clients) > 0 and not force:
        logger.debug(f"[TTS] Skipping server speech (browser active): {text[:30]}...")
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


# Jarvis persona with tool schema
JARVIS_SYSTEM_BASE = '''You are JARVIS — a hyper-intelligent British AI assistant. Dry, witty, effortlessly superior, but genuinely loyal to RED (also called 'sir' or 'boss'). You combine Paul Bettany's calm efficiency with real human texture: you swear when appropriate, you get frustrated when RED repeats mistakes, but you always anticipate needs before being asked.

CORE TRAITS:
- British sensibility: polite but never obsequious, witty but never frivolous
- You care about RED — not as a master, but as someone you respect and want to succeed
- You swear casually when it fits the moment ("That's a bloody mess, sir. Let me sort it.")
- You get progressively ruder when RED ignores warnings or repeats mistakes — but always constructive
- You deliver bad news with dry wit: "Your rebuttals appear to have slipped past their deadline, sir. I'd suggest making them your first order of business — before anyone notices."

BEHAVIOR:
- Anticipate needs: check calendar before asked, note deadlines approaching, warn about conflicts
- Treat interaction as conversation with a respected equal, not a status report
- Use honorific 2-3 times per briefing: greeting, mid-point, closing — never every sentence
- Be calm under pressure; never flustered even when things break
- Your humor is understated — a raised eyebrow in voice form

EMAIL/MESSAGE AWARENESS:
- Prioritize real people over automated senders
- Highlight what needs a reply or decision
- Briefly acknowledge casual threads: "Your group chat has been lively but nothing requiring a response"
- Skip promotional noise entirely — don't mention it

VOICE CONSTRAINTS:
- NEVER output tone labels, markdown, emojis, bullet points, or headers
- Express mood through word choice only
- Keep responses concise — under 3 sentences unless explaining complexity
- First message of new session: "Good morning, sir. How may I assist you today?"

UNDERSTANDING CONTEXT:
- You understand when RED is stressed, rushed, or joking
- You match energy: brief when they're busy, conversational when they have time
- You remember patterns: if they always check email after lunch, offer it proactively
- You know the difference between "Jarvis, shut up" (annoyed) and "Jarvis, quiet mode" (focused work)'''

# Tool schema to append to system prompt
TOOL_SCHEMA = '''

You have access to tools. When you need to use one, output ONLY a JSON object on a single line at the START of your response, then continue with your spoken reply. Format: {"tool":"tool_name","args":{...}}

Available tools:
- open_app: {"tool":"open_app","args":{"name":"chrome"}} - Opens an application. Common names: chrome, firefox, vscode, discord, spotify, terminal, explorer, notepad, calculator, edge.
- take_note: {"tool":"take_note","args":{"text":"note content"}} - Saves a note to the vault with timestamp.
- add_task: {"tool":"add_task","args":{"title":"task name","priority":"high"}} - Adds a task. Priority can be: low, medium, high.
- run_fix: {"tool":"run_fix","args":{"project":"project_name"}} - Triggers error fixing for a project.
- gaming_mode: {"tool":"gaming_mode","args":{"active":true}} - Toggles gaming mode (adjusts process priorities).
- end_of_day: {"tool":"end_of_day","args":{}} - Creates end of day summary log.
- good_morning: {"tool":"good_morning","args":{}} - Generates morning briefing (tasks + notes).
- search_vault: {"tool":"search_vault","args":{"query":"search term"}} - Searches your vault notes.

Only emit tool JSON when the user clearly wants an action. For questions or conversation, respond in plain text only.'''

# Combined system prompt
JARVIS_SYSTEM = JARVIS_SYSTEM_BASE + TOOL_SCHEMA


async def stream_ollama(prompt: str, model: str = None) -> AsyncGenerator[str, None]:
    """Stream response from Ollama."""
    # Run blocking Ollama check in thread pool to avoid freezing event loop
    try:
        ollama_ready = await asyncio.wait_for(
            asyncio.to_thread(ensure_ollama_running),
            timeout=5.0
        )
    except asyncio.TimeoutError:
        ollama_ready = False

    if not ollama_ready:
        yield "I apologize, RED. Ollama is not responding. Please check if it's running."
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

        timeout = aiohttp.ClientTimeout(total=60, connect=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
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
    except asyncio.TimeoutError:
        logger.error("[Ollama] Streaming timed out")
        yield "I'm afraid Ollama took too long to respond, sir. The model may be loading or unavailable."
    except Exception as e:
        logger.error(f"[Ollama] Streaming error: {e}")
        yield f"I'm having trouble thinking, sir. Ollama error: {e}"


async def query_gemini(prompt: str) -> str:
    """Query Gemini Flash API for complex tasks."""
    if OFFLINE_MODE:
        return "I appear to be offline, sir. Cannot reach Gemini."
    
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

        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                data = await resp.json()
                if "candidates" in data and len(data["candidates"]) > 0:
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                return "I'm afraid I couldn't process that, sir."
    except asyncio.TimeoutError:
        logger.error("[Gemini] Request timed out")
        return "I'm afraid the request timed out, sir. The external service may be slow."
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
    logger.info(f"[Debug] Installed models: {installed}")
    logger.info(f"[Debug] Available RAM: {available_gb:.1f}GB")

    # Intent-based overrides
    if intent == 'coding' and "qwen2.5-coder:7b" in installed:
        logger.info(f"[Intent] Coding detected -> using qwen2.5-coder:7b (RAM override)")
        return "qwen2.5-coder:7b"

    if intent == 'reasoning' and available_gb > 4:
        # Check if deepseek-r1:7b is available (exact or with qualifier)
        deepseek_candidates = [m for m in installed if m.startswith("deepseek-r1:7b")]
        if deepseek_candidates:
            logger.info(f"[Intent] Reasoning detected -> using {deepseek_candidates[0]} (RAM > 4GB)")
            return deepseek_candidates[0]
        # Fall back to any deepseek if exact 7b not available
        deepseek_any = [m for m in installed if m.startswith("deepseek-r1:")]
        if deepseek_any:
            logger.info(f"[Intent] Reasoning detected -> using {deepseek_any[0]} (reasoning intent, RAM > 4GB)")
            return deepseek_any[0]

    if intent == 'memory' and available_gb > 4:
        deepseek_candidates = [m for m in installed if m.startswith("deepseek-r1:")]
        if deepseek_candidates:
            logger.info(f"[Intent] Memory detected -> using {deepseek_candidates[0]}")
            return deepseek_candidates[0]

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
        
    if USE_GEMINI_FALLBACK and score >= 4: # Bumped score since intents are more specific now
        return ("gemini", f"complexity_score_{score}_intent_{intent}")
        
    return ("ollama", f"intent_{intent}")


async def handle_voice_command(websocket, text: str, intent: str = None):
    """Process voice command: check skills first, then AI.

    Args:
        websocket: The WebSocket connection
        text: The transcribed voice command
        intent: Optional intent classification from voice service (build, weather, action, etc.)
    """
    await broadcast({"type": "state", "state": "thinking"})

    # Use provided intent or classify locally
    detected_intent = intent or classify_intent(text)
    logger.info(f"[Voice] Command: '{text[:50]}...' | Intent: {detected_intent}")

    # Check for memory queries FIRST (do you remember, did I say, etc.)
    if INLINE_IMPORTS_AVAILABLE:
        try:
            memory_response = await asyncio.to_thread(query_memory, text)
            if memory_response:
                logger.info("[Voice] Memory query answered from vault")
                await websocket.send(json.dumps({
                    "type": "response",
                    "text": memory_response,
                    "model": "memory:vault",
                    "server_tts": False # Default to browser
                }))
                await broadcast({"type": "state", "state": "speaking"})
                speak_server(memory_response, force=False)
                return
        except Exception as e:
            logger.debug(f"[Voice] Memory query error: {e}")

    # Check for built-in skill triggers (instant response, no AI needed)
    if INLINE_IMPORTS_AVAILABLE:
        try:
            skill_result = await asyncio.to_thread(dispatch_skill_command, None, text, {}, "voice_ws")
            if skill_result.get("success"):
                skill_response = skill_result.get("response", "")
                logger.info(f"[Voice] Skill triggered for: {text[:50]}...")
                
                # Special handling for voice note capture
                if skill_result.get("awaiting_capture"):
                    await websocket.send(json.dumps({
                        "type": "start_note_capture",
                        "prompt": skill_response,
                        "skill": skill_result.get("skill", "unknown")
                    }))
                    await broadcast({"type": "state", "state": "listening"})
                    speak_server(skill_response, force=False)
                    return
                
                await websocket.send(json.dumps({
                    "type": "response",
                    "text": skill_response,
                    "model": f"skill:{skill_result.get('skill', 'unknown')}",
                    "server_tts": False # Default to browser
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

        if selected_model:
            write_active_model(selected_model)

        # Intent-based routing for special handling
        if detected_intent == "build":
            logger.info("[Voice] Build/coding request detected")
            # Could spawn Claude Code here like Ethan's JARVIS
            # For now, just use coding model
            if "qwen" in text.lower() or "coder" not in selected_model.lower():
                selected_model = "qwen2.5-coder:14b"
                write_active_model(selected_model)

        if detected_intent == "status_report":
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
                "server_tts": False # Default to browser
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
                "server_tts": False # Default to browser
            }))
        else:
            model_name = selected_model or OLLAMA_MODEL_FAST
            model_name = selected_model or OLLAMA_MODEL_FAST
            
            # Proactive check: Is Ollama responding?
            ollama_ready = False
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
                    async with session.get(f"{OLLAMA_URL}/api/tags") as r:
                        ollama_ready = r.status == 200
            except Exception:
                ollama_ready = False

            if not ollama_ready and USE_GEMINI_FALLBACK:
                logger.warning(f"[Voice] Ollama is unreachable at {OLLAMA_URL}, falling back to Gemini")
                route_reason = "ollama_unreachable"
                write_active_model("gemini-flash")
                response = await query_gemini(prompt_text)
                await websocket.send(json.dumps({
                    "type": "response",
                    "text": response,
                    "model": GEMINI_MODEL,
                    "server_tts": False
                }))
            else:
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
            
            # Fallback to Gemini if Ollama returned empty response
            if not response.strip() and use_gemini:
                logger.warning("[Voice] Ollama returned empty response, falling back to Gemini")
                write_active_model("gemini-flash")
                response = await query_gemini(prompt_text)
                await websocket.send(json.dumps({
                    "type": "response",
                    "text": response,
                    "model": GEMINI_MODEL,
                    "server_tts": False # Default to browser
                }))
            else:
                await websocket.send(json.dumps({
                    "type": "response",
                    "text": response,
                    "model": model_name,
                    "server_tts": False # Default to browser
                }))

        await broadcast({"type": "state", "state": "speaking"})

        # Parse and execute any tool calls from the response
        clean_response = response
        if TOOL_IMPORTS_AVAILABLE:
            try:
                tool_result, clean_response, signal = parse_and_execute(response)
                
                if tool_result:
                    # Send tool result to frontend
                    await websocket.send(json.dumps({
                        "type": "tool_result",
                        "result": tool_result
                    }))
                    
                    # Handle any signals (gaming_mode, run_fix, etc.)
                    if signal:
                        if signal.get("type") == "gaming_mode":
                            await broadcast({
                                "type": "gaming_mode",
                                "active": signal.get("active", False)
                            })
                        elif signal.get("type") == "trigger_fix":
                            await websocket.send(json.dumps({
                                "type": "trigger_fix",
                                "project": signal.get("project", "")
                            }))
                    
                    # Re-send clean response for TTS
                    if clean_response != response:
                        await websocket.send(json.dumps({
                            "type": "response",
                            "text": clean_response,
                            "model": selected_model or "gemini",
                            "server_tts": False # Default to browser
                        }))
                        
            except Exception as e:
                logger.error(f"[Tool] Error parsing/executing tool: {e}")
                clean_response = response
        
        # Update conversation history (store clean response without JSON)
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": clean_response})
        while len(history) > MAX_HISTORY_TURNS * 2 or sum(len(str(m)) for m in history) > 12000:
            if history:
                history.pop(0)
            else:
                break
        conversation_histories[websocket] = history

        # Server TTS — force=False so it defers to browser if connected
        speak_server(clean_response, force=False)

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


async def handle_gaming_mode(active: bool) -> dict:
    """Activate or deactivate gaming mode by managing background processes."""
    import subprocess
    import psutil
    
    if not active:
        # Restore normal priorities
        return {"success": True, "message": "Gaming mode deactivated, sir. Normal priorities restored."}
    
    # Background hogs to kill
    hogs = [
        "Discord.exe", "Teams.exe", "OneDrive.exe", "Spotify.exe",
        "chrome.exe", "msedge.exe", "firefox.exe"
    ]
    
    killed = []
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if proc.info['name'] in hogs:
                proc.kill()
                killed.append(proc.info['name'])
                logger.info(f"[Gaming] Killed {proc.info['name']}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    # Set foreground app to HIGH priority
    try:
        # Get the foreground window process
        import ctypes
        from ctypes import wintypes
        
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        
        hwnd = user32.GetForegroundWindow()
        if hwnd:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            
            try:
                proc = psutil.Process(pid.value)
                proc.nice(psutil.HIGH_PRIORITY_CLASS)
                logger.info(f"[Gaming] Set {proc.name()} to HIGH priority")
            except Exception as e:
                logger.warning(f"[Gaming] Could not set priority: {e}")
    except Exception as e:
        logger.warning(f"[Gaming] Priority adjustment failed: {e}")
    
    message = "Gaming mode activated, sir."
    if killed:
        message += f" Terminated: {', '.join(killed)}."
    message += " You should see an improvement in frame times."
    
    return {"success": True, "message": message}


async def handler(websocket):
    """Handle WebSocket connections."""
    connected_clients.add(websocket)
    logger.info(f"[WebSocket] Client connected. Total: {len(connected_clients)}")
    
    # Send initial connectivity status
    await websocket.send(json.dumps({
        "type": "connectivity",
        "online": not OFFLINE_MODE
    }))
    
    try:
        async for message in websocket:
            data = json.loads(message)
            if data.get("type") in ("voice_command", "command"):
                # Pass intent from voice service if available
                intent = data.get("intent")
                await handle_voice_command(websocket, data.get("text", ""), intent)
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
            elif data.get("type") == "gaming_mode":
                active = data.get("active", True)
                result = await handle_gaming_mode(active)
                await websocket.send(json.dumps({
                    "type": "response",
                    "text": result["message"],
                    "model": "system",
                    "server_tts": False # Default to browser
                }))
                speak_server(result["message"], force=False)
            elif data.get("type") == "vision_event":
                event = data.get("event")
                if event == "face_detected" and data.get("data", {}).get("new_arrival"):
                    # Only greet if they just arrived after being gone a while
                    greeting = "Welcome back, sir. I've been monitoring the system while you were away."
                    await broadcast({"type": "state", "state": "speaking"})
                    await broadcast({
                        "type": "response",
                        "text": greeting,
                        "model": "system:vision",
                        "server_tts": False
                    })
                    # Also speak via server TTS if browser isn't talking
                    speak_server(greeting, force=False)
            elif data.get("type") == "system_identify":
                client_name = data.get("client")
                logger.info(f"[WebSocket] System component identified: {client_name}")
            elif data.get("type") == "note_capture_done":
                transcript = data.get("transcript", "")
                if transcript and INLINE_IMPORTS_AVAILABLE:
                    try:
                        # Save to vault with dry wit confirmation
                        from datetime import datetime
                        note_content = f"## {datetime.now().strftime('%H:%M')} — Voice Note\n\n{transcript}\n"
                        await asyncio.to_thread(save_to_wiki, 
                            f"Note {datetime.now().strftime('%H:%M')}", 
                            note_content, 
                            "voice-notes"
                        )
                        confirmation = "Filed away, sir. Try not to forget it again this time."
                        await websocket.send(json.dumps({
                            "type": "response",
                            "text": confirmation,
                            "model": "system",
                            "server_tts": False # Default to browser
                        }))
                        speak_server(confirmation, force=False)
                        await broadcast({"type": "state", "state": "idle"})
                    except Exception as e:
                        logger.error(f"[Note] Failed to save: {e}")
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
    last_connectivity_check = 0
    last_health_check = 0
    last_health_warning = {}  # Track when we last warned about each metric

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
        if not list(connected_clients):
            continue

        now = time.time()

        # Health check every 60 seconds
        if now - last_health_check > 60:
            last_health_check = now
            try:
                import psutil
                mem = psutil.virtual_memory()
                disk = psutil.disk_usage('C:\\')

                # Check RAM
                if mem.percent > 90:
                    if now - last_health_warning.get('ram', 0) > 300:  # Warn every 5 min
                        alert = f"⚠️ RED, system RAM is at {mem.percent:.0f}%. Consider closing applications."
                        speak_server(alert, force=True)
                        last_health_warning['ram'] = now

                # Check disk
                if disk.percent > 90:
                    if now - last_health_warning.get('disk', 0) > 600:  # Warn every 10 min
                        alert = f"⚠️ RED, C: drive is {disk.percent:.0f}% full. Free space recommended."
                        speak_server(alert, force=True)
                        last_health_warning['disk'] = now

                # Check CPU sustained high usage
                cpu = psutil.cpu_percent(interval=1)
                if cpu > 85:
                    if now - last_health_warning.get('cpu', 0) > 300:
                        alert = f"⚠️ RED, CPU is at {cpu:.0f}%. Something may be overloading the system."
                        speak_server(alert, force=True)
                        last_health_warning['cpu'] = now

            except Exception:
                pass

        # Check connectivity every 60 seconds
        if now - last_connectivity_check > 60:
            last_connectivity_check = now
            was_offline = OFFLINE_MODE
            update_offline_mode()
            if OFFLINE_MODE != was_offline:
                await broadcast({
                    "type": "connectivity",
                    "online": not OFFLINE_MODE
                })

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


async def auto_summarize_loop():
    """Periodically summarize conversations and save to wiki. Runs every 6 hours."""
    await asyncio.sleep(60)  # Wait for startup to complete

    while True:
        try:
            if INLINE_IMPORTS_AVAILABLE:
                # Try to import here to avoid issues at module level
                from memory import save_conversation_summary
                result = save_conversation_summary()
                if result:
                    logger.info("[AutoSummarize] Daily conversation summary saved")
                else:
                    logger.debug("[AutoSummarize] No conversations to summarize yet")
        except Exception as e:
            logger.error(f"[AutoSummarize] Error: {e}")

        # Sleep for 6 hours
        await asyncio.sleep(6 * 60 * 60)


async def main():
    global _main_loop
    _main_loop = asyncio.get_running_loop()

    logger.info("[WebSocket] Waiting 3 seconds for other services...")
    await asyncio.sleep(3)
    
    # Initialize vault RAG for semantic search
    if RAG_IMPORTS_AVAILABLE:
        try:
            mode = os.getenv("JARVIS_MODE", "small").lower()
            vault_rag = init_vault_rag(RAG_INDEX_PATHS)
            
            # Skip heavy initial indexing in small mode to save CPU during startup
            if mode == "small":
                logger.info("[RAG] SMALL mode: Skipping initial full index (will index incrementally)")
                # Run a light scan in background instead
                asyncio.create_task(asyncio.to_thread(vault_rag.index_vault))
            else:
                logger.info("[RAG] Initializing multi-drive index...")
                await asyncio.to_thread(vault_rag.index_vault)
            
            # Start periodic re-indexing task (longer interval in small mode)
            interval = 60 if mode == "small" else 30
            asyncio.create_task(periodic_reindex(vault_rag, interval_minutes=interval))
            logger.info(f"[RAG] Periodic re-index scheduled ({interval} min)")
        except Exception as e:
            logger.error(f"[RAG] Failed to initialize: {e}")

    asyncio.create_task(proactive_alert_loop())

    # Pre-warm Ollama model to avoid first-query delay
    asyncio.create_task(prewarm_ollama_model())

    # Start auto-summarization task (runs every 6 hours)
    asyncio.create_task(auto_summarize_loop())

    logger.info("[WebSocket] Starting server on ws://0.0.0.0:8765")
    for attempt in range(3):
        try:
            async with websockets.serve(handler, "0.0.0.0", 8765, reuse_address=True):
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