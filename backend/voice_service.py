#!/usr/bin/env python3
"""
voice_service.py - Local Whisper-based voice recognition service
Replaces browser SpeechRecognition with fully offline, local voice processing.

Features:
- WebSocket server on port 8766 for frontend communication
- Continuous microphone monitoring with sounddevice
- Silero VAD for voice activity detection (neural network-based, more accurate)
- Whisper "small" model for transcription
- Fuzzy wake word detection ("jarvis", "hey jarvis", etc.)
- Sends transcripts and wake word events to connected clients
"""

import asyncio
import http
import json
import logging
import os
import queue
import sys
import tempfile
import wave
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
import torch
import websockets
import whisper
from scipy import signal

# Configure logging FIRST (before any logger calls)
LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOGS_DIR / "voice.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

# Load Silero VAD model (neural network-based VAD, no compiler needed)
logger.info("[VAD] Loading Silero VAD model...")
silero_model, silero_utils = torch.hub.load(
    repo_or_dir='snakers4/silero-vad',
    model='silero_vad',
    force_reload=False,
    onnx=False
)
(get_speech_timestamps, _, read_audio, *_) = silero_utils
logger.info("[VAD] Silero VAD model loaded")

# Configuration
WEBSOCKET_PORT = 8766
SAMPLE_RATE = 16000  # Required by Whisper
CHANNELS = 1
FRAME_DURATION_MS = 32  # Silero VAD works best with 32ms chunks
SILERO_THRESHOLD = 0.5  # Speech probability threshold (0.0-1.0)
SILENCE_THRESHOLD_S = 1.5  # Seconds of silence before utterance ends
MIN_SPEECH_DURATION_S = 0.3  # Minimum speech to process (ignore clicks/noise)
CHUNK_SAMPLES = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)

# Wake word variants for fuzzy matching
WAKE_WORDS = [
    "jarvis",
    "hey jarvis",
    "oi jarvis",
    "yo jarvis",
    "ok jarvis",
    "okay jarvis",
    "hi jarvis",
    "hello jarvis"
]
WAKE_WORD_THRESHOLD = 0.7  # Difflib ratio threshold

class VoiceService:
    """Local voice recognition service using Whisper and Silero VAD."""
    
    def __init__(self):
        self.clients = set()
        self.model: Optional[whisper.Whisper] = None
        self.is_recording = False
        self.audio_buffer = []
        self.silence_start = None
        self.speech_start = None
        self.stream = None
        self.loop = None  # Will be set from main()
        self._utterance_queue = queue.Queue()  # Thread-safe queue for audio buffers
        
    def is_speech_silero(self, audio_chunk: np.ndarray) -> bool:
        """Check if audio chunk contains speech using Silero VAD."""
        try:
            # Convert to torch tensor and normalize
            tensor = torch.FloatTensor(audio_chunk)
            # Get speech probability
            speech_prob = silero_model(tensor, SAMPLE_RATE).item()
            return speech_prob > SILERO_THRESHOLD
        except Exception as e:
            logger.debug(f"[VAD] Silero error: {e}")
            return False
        
    async def load_model(self):
        """Load Whisper model once at startup."""
        logger.info("Loading Whisper model (small)...")
        try:
            self.model = whisper.load_model("small")
            logger.info("Whisper model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            # Fallback to tiny if small fails
            logger.info("Falling back to tiny model...")
            self.model = whisper.load_model("tiny")
            logger.info("Whisper tiny model loaded successfully")
    
    def fuzzy_contains_wake_word(self, text: str) -> tuple[bool, str, str]:
        """
        Check if text contains wake word using fuzzy matching.
        Returns: (has_wake_word, wake_word_found, text_after_wake_word)
        """
        text_lower = text.lower().strip()
        
        for wake_word in WAKE_WORDS:
            # Try exact match first
            if wake_word in text_lower:
                idx = text_lower.find(wake_word)
                after = text[idx + len(wake_word):].strip()
                return True, wake_word, after
            
            # Try fuzzy match on the first few words
            words = text_lower.split()
            first_words = ' '.join(words[:3])  # Check first 3 words
            
            ratio = SequenceMatcher(None, wake_word, first_words).ratio()
            if ratio >= WAKE_WORD_THRESHOLD:
                # Found fuzzy match - return everything after the wake word
                after = ' '.join(words[2:]) if len(words) > 2 else ''
                return True, wake_word, after
                
        return False, "", text
    
    def audio_callback(self, indata, frames, time_info, status):
        """Callback for audio stream - processes audio chunks."""
        if status:
            logger.warning(f"Audio status: {status}")
            
        # Get audio data as float32 (Silero works with float32)
        audio_float32 = indata[:, 0]
        
        # Process in VAD-sized chunks (32ms for Silero)
        for i in range(0, len(audio_float32), CHUNK_SAMPLES):
            chunk = audio_float32[i:i + CHUNK_SAMPLES]
            if len(chunk) < CHUNK_SAMPLES:
                continue
                
            # Use Silero VAD for speech detection
            try:
                is_speech = self.is_speech_silero(chunk)
            except Exception as e:
                logger.debug(f"[VAD] Error: {e}")
                continue
            
            if is_speech:
                if not self.is_recording:
                    # Speech started
                    self.is_recording = True
                    self.speech_start = datetime.now()
                    self.audio_buffer = []
                    logger.info("VAD: Speech detected, starting recording")
                    if self.loop and self.loop.is_running():
                        self.loop.call_soon_threadsafe(
                            self.loop.create_task,
                            self.broadcast({
                                "type": "vad_start",
                                "timestamp": datetime.now().isoformat()
                            })
                        )
                
                self.silence_start = None
                self.audio_buffer.extend(chunk)
            else:
                if self.is_recording:
                    self.audio_buffer.extend(chunk)
                    
                    if self.silence_start is None:
                        self.silence_start = datetime.now()
                    else:
                        silence_duration = (datetime.now() - self.silence_start).total_seconds()
                        
                        if silence_duration >= SILENCE_THRESHOLD_S:
                            # Speech ended
                            self.is_recording = False
                            speech_duration = (datetime.now() - self.speech_start).total_seconds()
                            
                            if speech_duration >= MIN_SPEECH_DURATION_S:
                                logger.info(f"VAD: Speech ended ({speech_duration:.1f}s), queuing for transcription")
                                # Put audio buffer in queue for async processing
                                self._utterance_queue.put_nowait(self.audio_buffer.copy())
                            else:
                                logger.debug(f"Ignoring short utterance ({speech_duration:.1f}s)")
                            
                            self.audio_buffer = []
                            self.silence_start = None
    
    async def _process_queue(self):
        """Continuously drain the utterance queue and transcribe."""
        while True:
            try:
                # Block with timeout to allow clean shutdown
                audio_buffer = await asyncio.get_event_loop().run_in_executor(
                    None, self._utterance_queue.get, True, 0.1
                )
                await self.process_utterance(audio_buffer)
            except queue.Empty:
                await asyncio.sleep(0.01)
                continue
            except Exception as e:
                logger.error(f"Queue processing error: {e}")
    
    async def process_utterance(self, audio_buffer):
        """Process recorded audio buffer through Whisper."""
        if not audio_buffer or self.model is None:
            return
        
        try:
            # Convert buffer to numpy array (already float32 from Silero VAD)
            audio_float = np.array(audio_buffer, dtype=np.float32)
            
            # Resample to 16kHz if needed (should already be 16kHz)
            if len(audio_float) > 0:
                # Save to temporary WAV file
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    temp_path = f.name
                
                # Write WAV file (convert float32 back to int16 for WAV format)
                audio_int16 = (audio_float * 32767).astype(np.int16)
                with wave.open(temp_path, 'wb') as wav_file:
                    wav_file.setnchannels(CHANNELS)
                    wav_file.setsampwidth(2)  # 16-bit
                    wav_file.setframerate(SAMPLE_RATE)
                    wav_file.writeframes(audio_int16.tobytes())
                
                try:
                    # Transcribe with Whisper (run in thread pool to avoid blocking event loop)
                    result = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self.model.transcribe(
                            temp_path,
                            language="en",
                            initial_prompt="Jarvis computer assistant commands:",
                            fp16=False
                        )
                    )
                    
                    transcript = result["text"].strip()
                    
                    if transcript:
                        # Calculate confidence from Whisper's avg_logprob
                        confidence = min(1.0, max(0.0, 1.0 + result.get("avg_logprob", -0.5)))
                        
                        logger.info(f"Transcript: '{transcript}' (confidence: {confidence:.2f})")
                        
                        # Check for wake word
                        has_wake, wake_word, after_wake = self.fuzzy_contains_wake_word(transcript)
                        
                        if has_wake:
                            logger.info(f"Wake word detected: '{wake_word}'")
                            await self.broadcast({
                                "type": "wake_word",
                                "transcript": after_wake or transcript,
                                "full_text": transcript,
                                "wake_word": wake_word,
                                "confidence": confidence
                            })
                        else:
                            await self.broadcast({
                                "type": "transcript",
                                "transcript": transcript,
                                "confidence": confidence
                            })
                finally:
                    # Clean up temp file
                    try:
                        os.unlink(temp_path)
                    except:
                        pass
                        
        except Exception as e:
            logger.error(f"Error processing utterance: {e}", exc_info=True)
        
        finally:
            await self.broadcast({
                "type": "vad_end",
                "timestamp": datetime.now().isoformat()
            })
    
    async def broadcast(self, message: dict):
        """Send message to all connected WebSocket clients."""
        if not self.clients:
            return
        
        message_json = json.dumps(message)
        disconnected = set()
        
        for client in self.clients:
            try:
                await client.send(message_json)
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(client)
            except Exception as e:
                logger.error(f"Error broadcasting to client: {e}")
                disconnected.add(client)
        
        # Remove disconnected clients
        self.clients -= disconnected
    
    async def handle_client(self, websocket):
        """Handle WebSocket client connections."""
        self.clients.add(websocket)
        client_ip = websocket.remote_address[0] if websocket.remote_address else "unknown"
        logger.info(f"Client connected from {client_ip}. Total clients: {len(self.clients)}")
        
        try:
            # Send welcome message
            await websocket.send(json.dumps({
                "type": "connected",
                "message": "Voice service connected",
                "sample_rate": SAMPLE_RATE,
                "vad_aggressiveness": VAD_AGGRESSIVENESS
            }))
            
            # Keep connection alive and handle any client messages
            async for message in websocket:
                try:
                    data = json.loads(message)
                    logger.debug(f"Received from client: {data}")
                    
                    # Handle any client commands here
                    if data.get("action") == "ping":
                        await websocket.send(json.dumps({"type": "pong"}))
                        
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from client: {message}")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Client {client_ip} disconnected")
        except Exception as e:
            logger.error(f"Error handling client {client_ip}: {e}")
        finally:
            self.clients.discard(websocket)
            logger.info(f"Client removed. Total clients: {len(self.clients)}")
    
    def start_audio_stream(self):
        """Start the microphone audio stream."""
        try:
            self.stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=np.float32,
                blocksize=CHUNK_SAMPLES,
                callback=self.audio_callback
            )
            self.stream.start()
            logger.info(f"Audio stream started: {SAMPLE_RATE}Hz, {CHANNELS}ch, blocksize={CHUNK_SAMPLES}")
        except Exception as e:
            logger.error(f"Failed to start audio stream: {e}")
            raise
    
    def stop_audio_stream(self):
        """Stop the microphone audio stream."""
        if self.stream:
            self.stream.stop()
            self.stream.close()
            logger.info("Audio stream stopped")

async def main():
    """Main entry point for voice service."""
    service = VoiceService()
    service.loop = asyncio.get_running_loop()  # Capture event loop for threadsafe callbacks
    
    # Load Whisper model
    await service.load_model()
    
    # Start audio stream
    service.start_audio_stream()
    
    # Start queue processor
    asyncio.create_task(service._process_queue())
    
    # Add process_request handler to reject non-WS connections gracefully
    async def process_request(connection, request):
        if request.headers.get("Upgrade", "").lower() != "websocket":
            return connection.respond(http.HTTPStatus.OK, "Voice Service Running\n")
        # Return None to let websockets handle the WebSocket upgrade normally
        return None
    
    # Start WebSocket server
    logger.info(f"Starting WebSocket server on port {WEBSOCKET_PORT}")
    server = await websockets.serve(
        service.handle_client,
        "localhost",
        WEBSOCKET_PORT,
        ping_interval=20,
        ping_timeout=10,
        process_request=process_request
    )
    
    logger.info(f"Voice service ready on ws://localhost:{WEBSOCKET_PORT}")
    logger.info("Listening for voice commands...")
    
    try:
        await asyncio.Future()  # Run forever
    except KeyboardInterrupt:
        logger.info("Shutting down voice service...")
    finally:
        service.stop_audio_stream()
        server.close()
        await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
