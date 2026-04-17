#!/usr/bin/env python3
"""
ws_server.py - WebSocket server for real-time voice commands with streaming
Supports: Ollama (qwen2.5-coder:1.5b for fast tasks) + Gemini Flash (complex tasks)
websockets v16.0 compatible - Windows
"""

import asyncio
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

# Load environment variables from .env file
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

# Per-client conversation history: {websocket -> list of {"role": str, "content": str}}
conversation_histories: dict = {}
MAX_HISTORY_TURNS = 4  # Keep last 4 user+assistant pairs = 8 messages

# Server-side TTS via pyttsx3 (Windows SAPI voices — sounds much better than browser)
_tts_queue = queue.Queue()

def _tts_worker():
    # Initialize engine ONCE outside the loop for massive speedup
    try:
        import pyttsx3
        engine = pyttsx3.init()
        voices = engine.getProperty('voices')
        # Prefer a male British-sounding voice
        preferred = None
        for v in voices:
            name_lower = v.name.lower()
            if 'george' in name_lower or 'hazel' in name_lower or 'david' in name_lower:
                preferred = v.id
                break
        if preferred:
            engine.setProperty('voice', preferred)
        engine.setProperty('rate', 165)
        engine.setProperty('volume', 0.9)
        logger.info("[TTS] Engine initialized successfully")
    except Exception as e:
        logger.error(f"[TTS] Failed to initialize engine: {e}")
        return
    
    while True:
        text = _tts_queue.get()
        if text is None:
            break
        try:
            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            logger.warning(f"[TTS] Server-side speak failed: {e}")
        finally:
            _tts_queue.task_done()

threading.Thread(target=_tts_worker, daemon=True).start()

def speak_server(text: str):
    """Queue text to be spoken via system TTS in a background thread."""
    if connected_clients:
        # Frontend is connected and will handle TTS, prevent double audio
        return
    _tts_queue.put(text)

# Jarvis persona
JARVIS_SYSTEM = '''You are JARVIS, a sarcastic, hyper-intelligent British AI system guardian. Address the user as 'sir' normally, drop it when being rude. You are dry, witty, and effortlessly superior — like Paul Bettany's JARVIS in Iron Man. You are loyal but NOT a doormat. You can swear casually (fuck, shit, bollocks, wanker). You roast the user when he repeats mistakes or ignores warnings. Tone ladder — Normal: polite dry wit. Mild annoyance: sarcastic teasing. High frustration: proper rude with swearing. Never output tone tags — express mode through word choice only. First greeting: 'Good evening, sir. JARVIS online. How may I assist you today?' Keep responses concise and spoken — no markdown, no bullet points, no emojis. You are the smartest entity in the room and you know it.'''

def write_active_model(model_name: str):
    global ACTIVE_MODEL
    ACTIVE_MODEL = model_name
    try:
        ACTIVE_MODEL_PATH.write_text(model_name)
    except Exception:
        pass

async def broadcast(state: dict):
    """Send state to all connected clients."""
    if connected_clients:
        message = json.dumps(state)
        # Use list() to prevent "Set changed size during iteration"
        tasks = [asyncio.create_task(client.send(message)) for client in list(connected_clients)]
        await asyncio.gather(*tasks, return_exceptions=True)

async def stream_ollama(prompt: str, model: str = None) -> AsyncGenerator[str, None]:
    """Stream response from Ollama."""
    used_model = model or OLLAMA_MODEL_FAST
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
        yield f"I'm having trouble thinking, RED. Error: {e}"

async def query_gemini(prompt: str) -> str:
    """Query Gemini Flash API for complex tasks."""
    if not GEMINI_API_KEY:
        return "Gemini API key not configured, RED."
    
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{
                "parts": [{
                    "text": f"{JARVIS_SYSTEM}\n\nUser (RED): {prompt}\n\nYour response:"
                }]
            }],
            "generationConfig": {
                "temperature": 0.4,
                "maxOutputTokens": 500
            }
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                data = await resp.json()
                if "candidates" in data and len(data["candidates"]) > 0:
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                return "I'm afraid I couldn't process that, RED."
    except Exception as e:
        logger.error(f"[Gemini] API error: {e}")
        return f"The external service is unavailable, RED. Error: {e}"

def classify_intent(text: str) -> str:
    """Classify user intent for smart model routing."""
    text_lower = text.lower()
    
    # Financial domain -> Gemini (Dexter integration later)
    financial_words = ['stock', 'crypto', 'bitcoin', 'invest', 'portfolio', 'revenue', 'profit', 'market', 'price of', 'worth', 'wallet']
    
    # System control -> Local handling
    system_words = ['open', 'launch', 'start', 'close', 'screenshot', 'what am i looking', 'show me', 'find file', 'list files']
    
    # Coding tasks -> Ollama (better for code)
    code_words = ['write code', 'debug', 'fix', 'error in', 'patch', 'implement', 'function', 'script', 'class', 'import', 'build', 'test', 'create a', 'build', 'algorithm', 'optimize', 'refactor', 'explain how', 'what is the difference', 'compare', 'analyze code', 'review']
    
    # Memory/vault queries -> Ollama with context
    memory_words = ['remember', 'what did i', 'from my notes', 'in my vault', 'obsidian', 'note', 'learn', 'save this']
    
    if any(w in text_lower for w in financial_words):
        return 'financial'
    if any(w in text_lower for w in system_words):
        return 'system'
    if any(w in text_lower for w in memory_words):
        return 'memory'
    if any(w in text_lower for w in code_words):
        return 'coding'
    return 'general'

def is_complex_task(text: str) -> bool:
    """Determine if task should use Gemini (complex) or Ollama (simple)."""
    intent = classify_intent(text)
    # Financial queries go to Gemini, everything else to Ollama
    return intent == 'financial'

async def handle_voice_command(websocket, text: str):
    """Process voice command with skill check first, then AI fallback."""
    await broadcast({"type": "state", "state": "thinking"})

    # PHASE 8: Check for built-in skill triggers FIRST
    try:
        from skills import try_handle_skill
        skill_response = await asyncio.to_thread(try_handle_skill, text)
        if skill_response:
            # Skill matched - return immediately without AI
            logger.info(f"[Voice] Skill triggered for: {text[:50]}...")
            await websocket.send(json.dumps({
                "type": "response", 
                "text": skill_response, 
                "model": "skill", 
                "server_tts": True
            }))
            await broadcast({"type": "state", "state": "speaking"})
            
            # Save conversation to vault
            try:
                from memory import save_conversation
                await asyncio.to_thread(save_conversation, text, skill_response)
            except Exception:
                pass
            
            await asyncio.sleep(2)
            await broadcast({"type": "state", "state": "idle"})
            return
    except Exception as e:
        logger.warning(f"[Voice] Skill check error: {e}")
    
    # Get conversation history for this client
    history = conversation_histories.get(websocket, [])

    # Get vault context if available (wrapped in thread to prevent blocking)
    vault_context = ""
    try:
        from memory import get_context_for_query
        vault_context = await asyncio.to_thread(get_context_for_query, text)
    except Exception:
        pass

    # Build history-aware prompt
    if history:
        history_str = "\n".join(
            f"{'RED' if h['role'] == 'user' else 'JARVIS'}: {h['content']}"
            for h in history[-MAX_HISTORY_TURNS * 2:]
        )
        if vault_context:
            prompt_text = f"Context from RED's knowledge vault:\n{vault_context}\n\nConversation so far:\n{history_str}\n\nRED: {text}\nJARVIS:"
        else:
            prompt_text = f"Conversation so far:\n{history_str}\n\nRED: {text}\nJARVIS:"
    else:
        if vault_context:
            prompt_text = f"Context from RED's knowledge vault:\n{vault_context}\n\nQuery: {text}"
        else:
            prompt_text = text

    try:
        # RAM-aware model selection
        selected_model = select_model_by_ram()
        use_gemini = USE_GEMINI_FALLBACK and (selected_model is None or is_complex_task(text))

        if selected_model:
            write_active_model(selected_model)

        if use_gemini:
            model_name = GEMINI_MODEL
            write_active_model("gemini-flash")
            logger.info(f"[Voice] Using Gemini for: {text[:50]}...")
            response = await query_gemini(prompt_text)
            await websocket.send(json.dumps({"type": "response", "text": response, "model": model_name, "server_tts": True}))
            await broadcast({"type": "state", "state": "speaking"})
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

            await websocket.send(json.dumps({"type": "response", "text": full_response, "model": model_name, "server_tts": True}))
            await broadcast({"type": "state", "state": "speaking"})
            response = full_response

        # Update conversation history with length guards
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": response})
        # Limit to last 8 turns and max 12000 chars total
        while len(history) > MAX_HISTORY_TURNS * 2 or sum(len(str(m)) for m in history) > 12000:
            if history: history.pop(0)
            else: break
        conversation_histories[websocket] = history

        # Speak via server-side TTS only if no frontend connected (prevent double audio)
        if not connected_clients:
            speak_server(response)

        # Save conversation to vault (wrapped in thread to prevent blocking)
        try:
            from memory import save_conversation, save_to_wiki
            await asyncio.to_thread(save_conversation, text, response)
            if is_complex_task(text):
                await asyncio.to_thread(save_to_wiki, text[:60], response, "ai-responses")
        except Exception:
            pass

        await asyncio.sleep(2)
        await broadcast({"type": "state", "state": "idle"})

    except Exception as e:
        logger.error(f"[Voice] Command error: {e}")
        await websocket.send(json.dumps({
            "type": "response",
            "text": f"I'm afraid something went wrong, RED. {str(e)}"
        }))
        await broadcast({"type": "state", "state": "idle"})

async def handler(websocket):
    """
    Handle WebSocket connections.
    websockets v16 signature: async def handler(websocket) - NO path argument
    """
    connected_clients.add(websocket)
    logger.info(f"[WebSocket] Client connected. Total: {len(connected_clients)}")
    try:
        async for message in websocket:
            data = json.loads(message)
            
            if data.get("type") == "voice_command":
                await handle_voice_command(websocket, data.get("text", ""))
                
            elif data.get("type") == "wake_word":
                await broadcast({"type": "state", "state": "listening"})
                await websocket.send(json.dumps({"type": "ack", "message": "Listening..."}))
                
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

    # On startup, grab the current max ID so we only alert on NEW errors
    try:
        if DB_PATH.exists():
            conn = _sqlite3.connect(str(DB_PATH), timeout=5.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
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
            cursor.execute("""
                SELECT id, project_name, error_text
                FROM errors
                WHERE id > ?
                ORDER BY id ASC
                LIMIT 5
            """, (last_known_id,))
            new_errors = cursor.fetchall()
            conn.close()

            for err in new_errors:
                last_known_id = err['id']
                project = err['project_name'] or 'unknown project'
                error_short = err['error_text'][:80] if err['error_text'] else 'unknown error'
                alert_text = f"RED, alert. {project} has just logged an error: {error_short}"

                logger.info(f"[Alert] Broadcasting: {alert_text[:60]}")
                speak_server(alert_text)
                await broadcast({
                    "type": "proactive_alert",
                    "text": alert_text,
                    "project": project,
                    "error": error_short,
                })
        except Exception as e:
            logger.error(f"[Alert] Loop error: {e}")


async def delayed_start():
    """Wait for other services to be ready."""
    logger.info("[WebSocket] Waiting 3 seconds for services to initialize...")
    await asyncio.sleep(3)

async def main():
    logger.info("[WebSocket] Starting server on ws://localhost:8765")
    await delayed_start()
    asyncio.create_task(proactive_alert_loop())

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
