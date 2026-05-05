# JARVIS Operator

A voice-controlled AI system guardian with real-time project monitoring, code analysis, and system integration. Built with React, FastAPI, WebSockets, and Ollama.

## What is JARVIS?

JARVIS (Just A Rather Very Intelligent System) is a locally-hosted AI assistant designed for developers. It monitors your projects, alerts you to errors, helps debug code, and responds to voice commands with a sarcastic British personality inspired by Iron Man's JARVIS.

## Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- Ollama (local LLM server)
- Windows 10/11 (Linux support planned)

### Installation

1. **Clone the repository:**
```bash
git clone https://github.com/LegendaryRed318/Operator.git
cd Operator
```

2. **Install Python dependencies:**
```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

3. **Install frontend dependencies:**
```bash
cd ../frontend
npm install
```

4. **Configure environment:**
```bash
cd ../backend
copy .env.example .env
# Edit .env with your settings
```

5. **Start the system:**
```bash
# Option 1: Using the launcher (recommended)
python launcher.py

# Option 2: Manual start
cd backend && python server.py      # Terminal 1
cd backend && python ws_server.py    # Terminal 2
cd frontend && npm run dev           # Terminal 3
```

6. **Open the dashboard:**
```
http://localhost:8080
```

## Architecture

### Ports
- **Frontend:** 8080 (Vite dev server)
- **API:** 5050 (FastAPI)
- **WebSocket:** 8765 (Real-time voice commands)
- **Ollama:** 11434 (Local LLM)

### Key Components

| Component | Tech | Purpose |
|-----------|------|---------|
| Frontend | React 19 + TypeScript + Vite | Dashboard UI, voice activation |
| Backend API | FastAPI | REST endpoints, transcription |
| WebSocket | Python `websockets` | Real-time bidirectional communication |
| AI Models | Ollama (local) + Gemini (cloud fallback) | Natural language processing |
| Database | SQLite | Error tracking, conversation history |

## Features

### Voice Control
- Wake word detection ("Jarvis", "Operator")
- Hand gesture activation (wave to wake)
- Voice Activity Detection (VAD) - auto-stops on silence
- British TTS with sarcastic personality

### Project Monitoring
- Real-time error log scanning
- Proactive voice alerts for new errors
- System vitals dashboard (CPU, RAM, disk, temperature)

### AI Capabilities
- Code analysis and debugging
- Error explanation and fix suggestions
- Conversation history with context
- Skills system for custom commands

### Gaming Mode
- Kill background processes (Discord, Teams, Chrome)
- Set foreground app to HIGH priority
- One-click activation from dashboard

### Offline Mode
- Automatic detection of internet connectivity
- Falls back to local Ollama when offline
- Visual indicator in UI when disconnected

## Remote Access (Tailscale)

Access JARVIS from anywhere in the world using Tailscale's free tier.

### Setup

1. **Install Tailscale:**
   - On your PC (Jarvis host): https://tailscale.com/download
   - On your phone: App Store / Play Store

2. **Get your auth key:**
   - Go to https://login.tailscale.com/admin/settings/keys
   - Click "Generate auth key..."
   - Copy the key (starts with `tskey-auth-`)

3. **Configure JARVIS:**
   Edit `backend/.env`:
   ```env
   ENABLE_REMOTE_ACCESS=true
   TAILSCALE_AUTHKEY=tskey-auth-your-key-here
   ```

4. **Start JARVIS:**
   ```bash
   python launcher.py
   ```
   The launcher will auto-start Tailscale if configured.

5. **Access from your phone:**
   - Open the Tailscale app on your phone
   - Note the IP address shown for your PC (e.g., `100.x.x.x`)
   - Open browser and go to: `http://100.x.x.x:8081`

**Note:** Both devices must have Tailscale running. The connection is private and encrypted - no port forwarding or public IPs required.

## Environment Variables

Create `backend/.env`:

```env
# Required
OLLAMA_URL=http://localhost:11434
GEMINI_API_KEY=your_gemini_api_key_here

# Optional
USE_GEMINI_FALLBACK=true
VAULT_PATH=E:/JarvisVault
OPERATOR_API_PORT=5050
```

## Project Structure

```
Operator/
├── backend/
│   ├── server.py           # FastAPI HTTP server
│   ├── ws_server.py        # WebSocket server
│   ├── decision_engine.py  # AI model selection
│   ├── skills_engine.py    # Dynamic skill loading
│   └── skills/             # TOML skill definitions
├── frontend/
│   ├── src/
│   │   ├── contexts/
│   │   │   └── VoiceContext.tsx  # Voice state management
│   │   ├── components/
│   │   │   ├── HandTracker.tsx   # MediaPipe hand gestures
│   │   │   └── dashboard/
│   │   └── types.ts        # TypeScript definitions
│   └── package.json
├── skills/                 # TOML skill files
├── launcher.py             # Unified service launcher
└── README.md
```

## Skills System

Skills are defined in TOML files and loaded dynamically:

```toml
[skill]
name = "Open App"
triggers = ["open", "launch", "start"]
action_type = "open_application"

[response]
success = "Opening {app_name}, sir."
```

Built-in skills:
- **Good Morning** - Vault summary briefing
- **End of Day** - Log session summary
- **Add to Notes** - Voice-to-note capture
- **Open App** - Launch applications

## API Endpoints

### Health Check
```
GET /health/detailed
```
Returns service status and connectivity information.

### Voice
```
POST /transcribe
Content-Type: multipart/form-data
audio: <webm blob>
```

### Vault
```
GET /vault/search?q=<query>
POST /vault/voice-note
POST /vault/save
```

### System
```
GET /system           # Current vitals
GET /errors           # Recent errors
POST /clear-errors    # Wipe error database
```

## Development

### Type Checking
```bash
cd frontend
npx tsc --noEmit
```

### Python Syntax Check
```bash
cd backend
python -m py_compile *.py
```

## Troubleshooting

### WebSocket Connection Issues
- Check port 8765 is not in use: `netstat -ano | findstr 8765`
- Verify ws_server.py is running
- Check browser console for connection errors

### Ollama Not Responding
- Verify Ollama is installed: `ollama --version`
- Check if Ollama server is running: `curl http://localhost:11434/api/tags`
- Restart Ollama service

### Voice Not Working
- Check microphone permissions in browser
- Verify `pyttsx3` is installed: `pip install pyttsx3`
- Check browser TTS fallback in console

### Hand Tracking Not Working
- Ensure camera permissions granted
- Check browser WebGL support
- Verify MediaPipe libraries loaded (CDN)

## License

MIT License - See LICENSE file for details.

## Credits

- Built with [React](https://react.dev/), [FastAPI](https://fastapi.tiangolo.com/), [Ollama](https://ollama.com/)
- Voice powered by [faster-whisper](https://github.com/SYSTRAN/faster-whisper) and Web Speech API
- Hand tracking via [MediaPipe Hands](https://developers.google.com/mediapipe/solutions/vision/hand_landmarker)

---

**JARVIS is always listening. Try saying "Good morning, Jarvis."**