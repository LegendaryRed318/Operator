# Phase 4: Voice + Orb UI - Complete

## Summary

Phase 4 adds voice control, an animated 3D orb interface, and enhanced AI capabilities to Operator.

## Features Implemented

### 1. Enhanced Three.js Orb (`src/components/Orb.tsx`)

**4 States with Animations:**
- **Idle** (Pale Blue): Gentle particle breathing, slow rotation
- **Listening** (Blue): Pulse ring animation (expands/contracts), faster rotation
- **Thinking** (Orange): Electron trails orbiting the sphere, particle agitation
- **Speaking** (Teal): Glow effect, smooth rotation

**Technical Details:**
- 2000 core particles with velocity-based movement
- 20 animated electron trail lines (thinking state)
- Pulse ring with sine-wave animation (listening state)
- Color interpolation between state transitions
- Transparent background for HUD integration

### 2. Voice System (`src/voice.ts`)

**MediaRecorder-based (No SpeechRecognition API):**
- Click orb to start 5-second recording
- Audio sent to backend `/transcribe` endpoint
- Transcription displayed in chat panel
- Text sent via WebSocket to AI backend

**Flow:**
1. User clicks orb
2. State → "listening" (blue pulse)
3. Records 5 seconds
4. State → "thinking" (electron trails)
5. Send to `/transcribe` endpoint
6. Send transcribed text to WebSocket
7. State → "speaking" (teal glow)
8. Response displayed + spoken aloud
9. State → "idle"

### 3. Enhanced WebSocket Server (`backend/ws_server.py`)

**Streaming Ollama:**
- Fast model: `qwen2.5-coder:1.5b-base`
- Real-time streaming of response chunks
- Sends `stream_chunk` messages for live UI updates

**Gemini Flash Fallback:**
- Automatically used for complex tasks:
  - Code writing, debugging, refactoring
  - Complex explanations
  - Comparisons and analysis
- Set `GEMINI_API_KEY` env variable to enable

**Jarvis Persona:**
```python
"You are Jarvis, a loyal, dry-witted British AI assistant. 
You address the user as RED. Keep responses concise, helpful, 
and calm under pressure. No markdown or emojis in voice responses."
```

### 4. Hidden Window Launchers

**Three Options:**

1. **Interactive Mode** (default):
   ```batch
   start_operator.bat
   ```

2. **Hidden Mode** (VBS - completely invisible):
   ```batch
   start_operator.bat --hidden
   ```
   - Uses `pythonw.exe` (no console window)
   - VBS script runs all services silently
   - Tray icon is only visible indicator

3. **Silent Mode** (PowerShell):
   ```batch
   start_operator.bat --silent
   ```
   - Hidden PowerShell window
   - Process-based service management

### 5. PWA on Port 8080

**Configuration:**
- Port: `8080` (accessible from any device on WiFi)
- Host: `0.0.0.0` (binds to all network interfaces)
- PWA features:
  - Installable on mobile/desktop
  - Offline support (workbox caching)
  - Theme color: `#0a0a1a`
  - Standalone display mode

**Scripts:**
```json
"dev": "npx tsc && npx vite --host 0.0.0.0 --port 8080"
"dev:local": "npx tsc && npx vite --host localhost --port 5173"
"preview": "vite preview --host 0.0.0.0 --port 8080"
```

**Access:**
- Local: `http://localhost:8080`
- Network: `http://<computer-ip>:8080`
- Install: Add to home screen on mobile for app-like experience

## File Changes

### Frontend
- `src/components/Orb.tsx` - Enhanced with pulse + trails
- `src/voice.ts` - MediaRecorder-based voice system
- `vite.config.ts` - PWA + port 8080 configuration
- `package.json` - Added vite-plugin-pwa, workbox-window
- `index.html` - PWA meta tags
- `public/favicon.svg` - Jarvis orb icon

### Backend
- `backend/ws_server.py` - Streaming Ollama + Gemini fallback
- Added: `aiohttp` for async HTTP streaming

### Launchers
- `start_operator.bat` - Updated with --hidden/--silent options
- `start_operator_hidden.vbs` - VBS hidden launcher
- `start_operator_silent.ps1` - PowerShell hidden launcher

## Environment Variables

```bash
# Optional: Gemini API key for complex tasks
set GEMINI_API_KEY=your_gemini_api_key_here

# Optional: Disable Gemini fallback
set USE_GEMINI_FALLBACK=false

# Optional: Custom Ollama URL
set OLLAMA_URL=http://localhost:11434
```

## Usage

### Start Operator (Hidden)
```batch
cd C:\Projects\Operator
start_operator.bat --hidden
```

### Access Dashboard
- Open browser to `http://localhost:8080`
- Or on phone: `http://<computer-ip>:8080`

### Voice Commands
1. Click the glowing orb
2. Speak for 5 seconds (orb pulses blue)
3. Wait for processing (electron trails - orange)
4. Jarvis responds (teal glow + spoken response)

### Example Commands
- "What's the weather like?"
- "Write a Python function to sort a list"
- "Debug this error: cannot find module 'react'"
- "Explain how async/await works"

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Browser/PWA   │────▶│   Vite Server   │────▶│   React App     │
│   (Port 8080)   │     │   (Port 8080)   │     │   + Three.js    │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Ollama API    │◀────│  WebSocket Srv  │◀────│   voice.ts      │
│   (Port 11434)  │     │   (Port 8765)   │     │   MediaRecorder │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                              │
                              ▼
┌─────────────────┐     ┌─────────────────┐
│  Gemini API     │◀────│  HTTP Server    │
│  (Fallback)     │     │  (Port 5050)    │
└─────────────────┘     └─────────────────┘
                              │
                              ▼
                        ┌─────────────────┐
                        │  Transcribe     │
                        │  Endpoint       │
                        └─────────────────┘
```

## Next Steps (Phase 5)

- Wake word detection using whisper.cpp ("Hey Operator")
- Multi-language support
- Voice activity detection (VAD) instead of fixed 5-second recording
- Error auto-fix execution
- Skill system for custom commands

## Troubleshooting

### Orb not animating
- Check browser console for Three.js errors
- Ensure WebGL is enabled in browser

### Voice not working
- Check microphone permissions in browser
- Ensure backend is running: `python ws_server.py`
- Check logs: `C:\Projects\Operator\logs\`

### PWA not installable
- Must use HTTPS or localhost (use `localhost` for testing)
- Check manifest in DevTools > Application
- Clear browser cache and reload

### Gemini not responding
- Check `GEMINI_API_KEY` environment variable
- Verify key at: https://makersuite.google.com/app/apikey
- Check `USE_GEMINI_FALLBACK` is not set to `false`
