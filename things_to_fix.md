# Jarvis (ws_server.py) - Things to Fix

## 🔴 Core Problems & Bugs

1. **Event Loop Blocking (Critical)**
   - **Issue:** Synchronous file operations (`get_context_for_query()`, `save_conversation()`, `save_to_wiki()`, and `sqlite3.connect()`) are running directly inside `async def` functions. This freezes the entire WebSocket server for all connected clients while the disk spins.
   - **Fix:** Wrap these operations in `await asyncio.to_thread(func, args...)` so they run in a non-blocking background thread.

2. **Constant TTS Delay (Performance)**
   - **Issue:** Inside `_tts_worker()`, `engine = pyttsx3.init()` and system voice scanning happen *every single time* a message is queued. Initializing SAPI5 takes 0.5-1s.
   - **Fix:** Move the `pyttsx3.init()` logic to execute strictly *once*, placing it outside the `while True:` loop.

3. **Gemini Safety Filter Crashes**
   - **Issue:** The `JARVIS_SYSTEM` prompt instructs the AI to swear (e.g., "fuck", "shit"). Google's default Gemini API limits will detect this as a Content Safety Violation and refuse to answer.
   - **Fix:** Add a `"safetySettings"` block to the Gemini REST payload, explicitly setting thresholds like `HARM_CATEGORY_HARASSMENT` to `BLOCK_NONE`.

4. **Severe Token Truncation**
   - **Issue:** `maxOutputTokens` for Gemini and `num_predict` for Ollama are both currently capped at `500`.
   - **Fix:** Raise them to at least `4096` or `8192` to prevent AI responses (especially coding tasks) from cutting off abruptly mid-sentence.

## 🗑️ What needs to be REMOVED

1. **Inline Imports**
   - **Issue:** Imports like `from memory import get_context_for_query` are used inside standard functions.
   - **Fix:** Remove them from the functions and place all standard imports cleanly at the top of the file.

2. **Brittle Keyword Routing**
   - **Issue:** The `is_complex_task` router strictly checks for simple static words like "write code" to decide if it should route to the smart AI. If you say "Can you patch this script?", it fails and goes to the dumb AI.
   - **Fix:** Remove this dictionary array. Consider a lightweight LLM intent classifier or routing primarily based on server capability.

## ✨ What needs to be ADDED / IMPROVED

1. **Conversation History Context Management**
   - **Issue:** `conversation_histories` keeps appending raw conversation turns (the last 8 messages). When passing massive chunks of code back and forth, you could overflow the context window.
   - **Fix:** Add a character or token-length limit function that truncates the strings before concatenating the `history_str`.

2. **Database Lock Mitigation**
   - **Issue:** `proactive_alert_loop()` connects to the local SQLite database every 10 seconds. If `watcher.py` triggers a write action at the precise microsecond this loop reads, SQLite will crash with a "Database Locked" exception.
   - **Fix:** Add `timeout=5.0` to the `sqlite3.connect()` calls so they wait gracefully instead of crashing instantly.

# Jarvis (Operator) System Audit

A comprehensive audit of the current Jarvis platform based on the codebase. Here is everything wrong with the system, the root causes, and how to improve it, categorized by area.

## 🚨 Security & Hardcoding Warnings
1. **Secret Leakage in Frontend:** The lock screen password (`VITE_LOCK_PASSWORD`) is compiled directly into the frontend bundle. Anyone inspecting the JavaScript source in the browser can simply read the password.
2. **Hardcoded API Keys:** The `backend/.env` file contains a live Gemini API key (`AIzaSy...`). Similarly, `telegram_config.json` contains a live Telegram Bot Token and Chat ID. These should be removed from source control immediately.
3. **Hardcoded Absolute Paths:** `server.py` and `config.json` rely heavily on absolute paths specific to your machine (e.g., `C:/Projects/...`, `E:/JarvisVault/...`, `C:/Users/olami/...`). This breaks portability.

## 🏗️ Architecture & Communication Flaws
1. **Double Audio Output (Echo):** When Jarvis responds, `ws_server.py` executes `speak_server(response)` to play audio via `pyttsx3` on the host machine. Simultaneously, `VoiceContext.tsx` on the frontend calls `speak(data.text)` to play via ElevenLabs or Browser TTS. This causes two overlapping, conflicting voices playing the same response if the backend and browser are on the same machine.
2. **Synchronous Server Blocking:** `server.py` uses Python's standard `HTTPServer`, which handles one request at a time (synchronously). If the Whisper transcription endpoint (`/transcribe`) takes 5 seconds to process audio, **all other endpoints** (like the `/system` vitals polling every 5 seconds) are completely blocked until transcription finishes.
3. **Inefficient System Monitoring:** In `server.py`, the system vitals endpoint uses `subprocess.run(['wmic', ...])` to get CPU temperatures on Windows. Because the frontend polls `/system` every 5 seconds, this spawns a new `wmic.exe` process every 5 seconds, causing unnecessary CPU spikes and system overhead.

## 💻 Backend (Python) Bugs & Concurrency Issues
1. **Thread-Unsafe WebSocket Broadcast:** In `ws_server.py`, `connected_clients` is a Python `set()`. The `broadcast()` function iterates over it without copying or locking it. If a client connects or disconnects during a broadcast, Python will throw a "Set changed size during iteration" runtime exception, crashing the asyncio loop.
2. **Thread-Unsafe TTS Queue:** `ws_server.py` launches a new daemon thread for every `pyttsx3` TTS playback (`speak_server`). `pyttsx3` is not continuously thread-safe, and if Jarvis speaks rapidly, multiple threads will try to initialize the COM engine and speak simultaneously, leading to overlapping audio or access violation crashes.
3. **Thread-Unsafe Watcher State:** In `watcher.py`, `notification_timestamps` is modified across multiple background threads without thread locks, leading to race conditions under heavy log loads.
4. **Zombie Processes in Launcher:** `launcher.py` restarts failed processes, but the `check_service_health` loop assumes processes clean up well. Under edge cases, force-killing node or npm tasks may leave lingering phantom node processes consuming RAM.

## ⚛️ Frontend (React & Vite) Issues
1. **Camera Leak (HandTracker):** `HandTracker.tsx` initiates the MediaPipe `Camera` continuously. However, in the `useEffect` cleanup return block `() => { // No cleanup }`, the camera and video streams are never stopped. If the user navigates away or the component unmounts, the webcam stays on permanently.
2. **ElevenLabs Fallback Death Trap:** In `VoiceContext.tsx`, `elevenLabsFailCount` increments on failure, but it is rarely reset (only when manually activating hotword). If it passes `MAX_ELEVENLABS_FAILS`, it permanently locks you into the lower-quality browser TTS until the entire page is manually reloaded.
3. **Strict Mode Double execution:** `HandTracker.tsx` guards script injection with `isInitialized.current = true`, but does so deep inside an async call. React Strict Mode runs `useEffect` twice rapidly, leading to race conditions where MediaPipe scripts might be loaded or executed multiple times unpredictably.

## 📈 Improvement Opportunities (How to fix and improve)

### Stability & Performance
*   **ThreadingHTTPServer:** Upgrade `server.py` to use `ThreadingHTTPServer` so long-running audio transcriptions don't freeze the system and HUD updates.
*   **WMI Persistent Query:** Use the `wmi` python package to keep a persistent COM connection to read temperatures, or drop Windows WMI polling altogether in favor of `psutil` or `OpenHardwareMonitor` integration.
*   **TTS Queue:** Implement a `queue.Queue` in `ws_server.py` for `speak_server`. Have a single daemon worker consume messages sequentially, completely stopping overlapping backend dialogue. Better yet—turn off backend TTS completely if the frontend is connected!

### React & UX Enhancements
*   **Proper Unmounting:** Add `cameraRef.current?.stop()` to the `HandTracker.tsx` unmount phase.
*   **WebSocket Set iteration:** Change `connected_clients` logic in `ws_server.py` to iterate over `list(connected_clients)` or `connected_clients.copy()`.
*   **Frontend Authentication:** Move the password verification step to a tiny backend endpoint. Send the lock screen payload, and have the backend return an auth token (or generic success).

### Hotword Architecture
*   Instead of switching rapidly between frontend native Speech Recognition and POSTing wav files to Whisper (which is slow and CPU intensive), consider integrating **Porcupine (Picovoice)** locally on the frontend or backend for true, lightweight, instantaneous wake-word detection before activating the heavier transcription pipelines.

 JARVIS Comprehensive Code Review
🚨 CRITICAL ISSUES (Fix Immediately)
1. ElevenLabs Still Wrapping App (Runtime Error Risk)
@main.tsx:5

typescript
import { ConversationProvider } from '@elevenlabs/react'
Problem: ConversationProvider wraps your entire app but ElevenLabs was removed from VoiceContext.tsx
Risk: Package may try to initialize and fail silently or crash
Fix: Remove import and wrapper from main.tsx
2. Dead Code: useWebSocket.ts
@hooks/useWebSocket.ts

Problem: File exists but is no longer imported anywhere after WebSocket consolidation
Fix: Delete the file
3. Dead Components
After the OperatorHUD refactor, these are likely unused:

@components/DashboardView.tsx
@components/ProjectsView.tsx
@components/SystemView.tsx
@components/Sidebar.tsx
@components/TopBar.tsx
@components/SystemVitals.tsx
Verify: Check if imported anywhere. If not, delete to reduce bundle size.

4. Missing types.ts
Referenced in App.tsx:7 but file doesn't exist at @frontend/src/types.ts

⚠️ HIGH PRIORITY (Fix Soon)
5. Memory Leak: conversation_histories
@ws_server.py:52

python
conversation_histories: dict = {}  # {websocket -> list of messages}
Problem: No cleanup when clients disconnect. Grows forever.
Fix: Add cleanup in disconnect handler
6. Hardcoded Paths Throughout
File	Path
server.py:18	E:/JarvisVault
server.py:17	C:/Projects/Operator/database
memory.py:13	E:/JarvisVault
watcher.py:28	c:\Projects\Operator/database/errors.db
Problem: Won't work on other machines or if you move folders
Fix: Use relative paths or environment variables
7. No CORS Configuration
@server.py - API accepts requests from any origin

Risk: CSRF attacks if you expose to internet
Fix: Add Access-Control-Allow-Origin headers limited to your domains
8. Password in .env But No Validation
@LockScreen.tsx:5

typescript
const SECRET_PASSWORD = import.meta.env.VITE_LOCK_PASSWORD
Problem: If .env missing, app warns but still runs (fail-open)
Current: Line 28 fails closed ✓ (good!)
Suggestion: Add .env.example to repo so users know to create it
🔧 MEDIUM PRIORITY (Improvements)
9. 3-Hour Hotword Timeout Excessive
@VoiceContext.tsx:22

typescript
const HOTWORD_TIMEOUT_MS = 3 * 60 * 60 * 1000; // 3 hours
Problem: If you leave desk, JARVIS listens for 3 hours wasting CPU
Suggestion: 30 minutes is plenty
10. Audio Recording Fixed at 5 Seconds
@VoiceContext.tsx:292

typescript
setTimeout(() => { mediaRecorder.current?.stop(); }, 5000);
Problem: Always records full 5s even for "stop" command
Fix: Add silence detection or make it interruptible
11. No Request Size Limit on ZIP Upload
@server.py:634 - _handle_import_zip

Risk: Someone could upload multi-GB ZIP and crash server
Fix: Add MAX_CONTENT_LENGTH = 10 * 1024 * 1024 (10MB)
12. SQLite No Encryption
@watcher.py:44 - Database stores errors in plain SQLite

Suggestion: Add SQLCipher if errors may contain sensitive info
13. TTS Rate Hardcoded
@ws_server.py:76

python
engine.setProperty('rate', 165)
Suggestion: Make configurable per user preference
🏗️ ARCHITECTURE ISSUES
14. Skills System Half-Built
Feature	Status
ZIP import	✅ Working
TOML storage	✅ Working
Voice triggers	❌ Not wired
Action execution	❌ Not built
POST /skills/{name}/trigger	❌ Missing
Current: You can import skills but can't execute them.

15. No Health Check Aggregation
Each service (API, WebSocket, Watcher) runs separately but there's no single endpoint to check if JARVIS is fully healthy.

Suggestion: Add GET /health that checks:

API responding
WebSocket accepting connections
Ollama reachable
Database writable
16. No Graceful Shutdown
@launcher.py:150 - process.terminate() sends SIGTERM but services don't handle it for cleanup.

📦 DEPENDENCY ISSUES
17. ElevenLabs Package Still Installed
@package.json:23

json
"@elevenlabs/react": "^1.1.1"
Fix: npm uninstall @elevenlabs/react (save 2MB+ bundle)
18. Unused Python Imports
Several files import modules they don't use. Run autoflake to clean.

🎨 CODE QUALITY
19. Duplicate Documentation
@AGENTS.md and @CLAUDE.md are identical (both 5479 bytes)
Fix: Delete one, symlink, or keep one as canonical
20. Inconsistent Error Handling
Some places use logger.error(), others use print(), others use console.error()

21. Magic Numbers
IDLE_TIMEOUT_SECONDS = 3 * 60 * 60 (3 hours) - should be named constant
MAX_HISTORY_TURNS = 4 - undocumented why 4
✅ WHAT'S WORKING WELL
Component	Status
TypeScript compilation	✅ Clean
WebSocket deduplication	✅ Fixed
Camera retry logic	✅ Added
ZIP import	✅ Working
Voice feedback loop prevention	✅ isSpeakingRef working
Password from env	✅ Secure
Vault integration	✅ Good abstraction
📋 RECOMMENDED ACTION PLAN
Phase 1: Critical (Today)
Remove @elevenlabs/react from main.tsx and package.json
Delete hooks/useWebSocket.ts
Create frontend/src/types.ts (or remove import)
Add conversation_histories cleanup in ws_server.py
Phase 2: High Priority (This Week)
Add CORS headers to server.py
Add MAX_CONTENT_LENGTH to ZIP upload
Move hardcoded paths to .env
Reduce hotword timeout to 30 min
Phase 3: Features (Next)
Build POST /skills/{name}/trigger endpoint
Add voice trigger detection in VoiceContext.tsx
Create GET /health endpoint
Delete unused dashboard components
Strong additions. You've identified real technical debt that I missed. Here's my assessment:

✅ Your New Issues Are Valid
Your Finding	Severity	Why It's Important
Event Loop Blocking	🔴 Critical	Every sync file operation freezes ALL WebSocket clients. Very real on Windows with slow disks.
TTS Re-initialization	🔴 Critical	0.5-1s delay × every response = painful UX. Easy 10x speedup.
Gemini Safety Filter	🔴 Critical	Your JARVIS_SYSTEM prompt has "fuck", "shit" → Gemini will refuse and return empty. Breaking bug.
Token Truncation (500)	⚠️ High	Code explanations cut off mid-function. Should be 4K minimum.
Brittle Keyword Routing	⚠️ High	"Patch this script" → dumb AI. Needs intent classifier.
SQLite Locking	⚠️ High	database locked crashes are real under load.
Inline Imports	🟡 Medium	Style issue, but affects startup time slightly.
🎯 My Prioritized Fix Order
Immediate (Tonight)
Gemini Safety Settings — Add to ws_server.py or JARVIS goes mute
TTS Init Once — 5-line fix, massive UX improvement
Token Limits — Change 500 → 4096
This Weekend
Event Loop Blocking — Wrap sync ops in asyncio.to_thread()
SQLite Timeouts — Add timeout=5.0 to connections
Keyword → Intent Router — Small LLM call for routing decisions
📁 File Organization Suggestion
Your things_to_fix.md has duplicate content (my review mixed with yours). Suggest restructure:

markdown
# JARVIS Fix Backlog
 
## 🔴 Blockers (Fix Now)
1. [ws_server] Gemini safety filter blocking swearing persona
2. [ws_server] TTS re-initializes every speak (500ms+ delay)
3. [ws_server] Sync file ops block event loop
4. [frontend] ElevenLabs provider still wrapping app
 
## ⚠️ High Impact
5. Token truncation at 500 (should be 4K)
6. Brittle keyword routing → need intent classifier
7. SQLite database lock timeouts
8. WebSocket set iteration not thread-safe
 
## 🛠️ Architecture
9. Skills system execution (triggers + actions)
10. Health check aggregation endpoint
11. Hardcoded paths → env vars
 
## 🧹 Cleanup
12. Delete dead components (Sidebar, TopBar, etc.)
13. Remove @elevenlabs/react package
14. Inline imports → top of file
🚀 Want Me To Fix The Critical Ones Now?
I can knock out #1, #2, #3 in 10 minutes:

Gemini safety settings in ws_server.py
Move pyttsx3.init() outside the while loop
Raise token limits to 4096
Wrap sync ops in threads
Should I start with those 4?

