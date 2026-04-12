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
import socket
from typing import AsyncGenerator
from decision_engine import DecisionEngine
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

# Jarvis persona
JARVIS_SYSTEM = "You are Jarvis, a loyal, dry-witted British AI assistant. You address the user as RED. Keep responses concise, helpful, and calm under pressure. No markdown or emojis in voice responses."

async def broadcast(state: dict):
    """Send state to all connected clients."""
    if connected_clients:
        message = json.dumps(state)
        tasks = [asyncio.create_task(client.send(message)) for client in connected_clients]
        await asyncio.gather(*tasks, return_exceptions=True)

async def stream_ollama(prompt: str) -> AsyncGenerator[str, None]:
    """Stream response from Ollama."""
    try:
        payload = {
            "model": OLLAMA_MODEL_FAST,
            "prompt": prompt,
            "system": JARVIS_SYSTEM,
            "stream": True,
            "options": {
                "temperature": 0.4,
                "num_predict": 500
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

def is_complex_task(text: str) -> bool:
    """Determine if task should use Gemini (complex) or Ollama (simple)."""
    complex_keywords = [
        "write code", "create a", "build", "implement", "function", "class",
        "algorithm", "debug", "fix", "optimize", "refactor", "explain how",
        "what is the difference", "compare", "analyze code", "review"
    ]
    text_lower = text.lower()
    return any(kw in text_lower for kw in complex_keywords)

async def handle_voice_command(websocket, text: str):
    """Process voice command with appropriate model."""
    await broadcast({"type": "state", "state": "thinking"})
    
    try:
        # Decide which model to use
        use_gemini = USE_GEMINI_FALLBACK and is_complex_task(text)
        
        if use_gemini:
            logger.info(f"[Voice] Using Gemini for complex task: {text[:50]}...")
            response = await query_gemini(text)
            await websocket.send(json.dumps({"type": "response", "text": response}))
            await broadcast({"type": "state", "state": "speaking"})
        else:
            logger.info(f"[Voice] Streaming from Ollama: {text[:50]}...")
            # Stream response
            full_response = ""
            async for chunk in stream_ollama(text):
                full_response += chunk
                # Send partial for UI responsiveness (optional)
                await websocket.send(json.dumps({
                    "type": "stream_chunk", 
                    "chunk": chunk,
                    "partial": full_response
                }))
            
            # Send final response
            await websocket.send(json.dumps({"type": "response", "text": full_response}))
            await broadcast({"type": "state", "state": "speaking"})
        
        # Return to idle after response
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
        logger.info(f"[WebSocket] Client removed. Total: {len(connected_clients)}")

async def delayed_start():
    """Wait for other services to be ready."""
    logger.info("[WebSocket] Waiting 3 seconds for services to initialize...")
    await asyncio.sleep(3)

def is_port_in_use(port: int) -> bool:
    """Check if a port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("localhost", port))
            return False
        except socket.error:
            return True

async def main():
    """Start WebSocket server with proper configuration."""
    logger.info("[WebSocket] Starting server on ws://localhost:8765")
    
    # Startup delay so other services are ready
    await delayed_start()
    
    # Check if port is already in use
    if is_port_in_use(8765):
        logger.warning("[WebSocket] Port 8765 is already in use - another instance may be running")
        logger.warning("[WebSocket] Skipping server start to avoid conflict")
        # Keep the process alive but don't serve
        await asyncio.Future()
        return
    
    async with websockets.serve(handler, "localhost", 8765):
        logger.info("[WebSocket] Server ready and accepting connections")
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())
