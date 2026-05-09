# JARVIS Operator System

A locally-hosted, voice-controlled AI system guardian. JARVIS (Just A Rather Very Intelligent System) is designed to act as your digital brain, project monitor, and personal knowledge manager. He operates entirely on your local hardware for maximum privacy, with zero latency, and syncs his memories to your devices globally via an encrypted Tailscale mesh.

---

## The AI Brain Architecture

JARVIS is not a single AI; he is a composite of several highly specialized models working together in real-time.

1. **The Reasoning Engine (Ollama)**
   - **Primary Model:** `llama3.2:3b`. We use the 3B parameter model because it is the perfect balance of speed and intelligence. It can run on standard consumer GPUs with minimal lag, allowing JARVIS to respond to voice commands in under 2 seconds.
   - **Fallback Engine:** Google Gemini API. If the local Ollama model crashes or encounters a task too complex for 3B parameters (like massive code refactoring), JARVIS seamlessly falls back to the cloud.

2. **The Hearing Engine (Whisper)**
   - Uses `faster-whisper` for lightning-fast, local voice-to-text transcription.
   - Constantly listens for the wake words: *"Jarvis"* or *"Operator"*.

3. **The Vision Engine (MediaPipe & OpenCV)**
   - **Face Detection:** JARVIS uses your webcam to track human presence. If you leave your desk and return 60 seconds later, his Vision Service detects your face and triggers a proactive greeting (e.g., *"Welcome back, sir. I've been monitoring the system while you were away."*).
   - **Hand Gestures:** Supports MediaPipe hand-tracking to wake the system with a wave instead of a voice command.

4. **The Voice Engine (pyttsx3)**
   - Uses native Windows TTS APIs configured for a sarcastic, British personality.

---

## System Capabilities & Skills

JARVIS's actions are driven by a dynamic `TOML`-based Skill Engine. You can teach him new skills simply by dropping a text file into his `skills/` folder.

**Current Core Capabilities:**
- **Obsidian Memory Injection:** When you tell JARVIS to "take a note" or "add a task", he does not just save raw text. He formats the data using strict Markdown and YAML Frontmatter and injects it directly into your Obsidian Daily Notes.
- **Hardware Health:** Ask *"How are the systems holding up?"* and he will read your CPU temperatures, RAM usage, and Disk space.
- **Web Search Engine:** He can autonomously browse DuckDuckGo, scrape articles, and synthesize the information to answer complex questions.
- **Application Control:** Can launch or kill any process on your PC (e.g., *"Kill Discord"*).
- **Proactive Error Monitoring:** If your code throws an error in your terminal, JARVIS intercepts the log file and speaks out loud to warn you.

---

## Phase 1: Core Ecosystem Prerequisites

To build the complete JARVIS ecosystem, you need to install the following foundational software on your PC:

1. **Python 3.10+**: The backend engine.
2. **Node.js 18+**: The frontend dashboard engine.
3. **Ollama**: Download from `ollama.com`. Once installed, open a terminal and run `ollama run llama3.2:3b`.
4. **Tailscale**: The secure VPN mesh. This allows JARVIS and your phone to communicate securely without exposing ports to the public internet.
5. **Apache CouchDB**: The synchronization database (used for phone syncing). Download the native Windows `.msi` installer from `couchdb.apache.org`.
6. **Obsidian**: Your Personal Knowledge Management app.

---

## Phase 2: The JARVIS Vault

JARVIS does not store his memories in hidden, proprietary databases. He writes them as human-readable Markdown files so you always own your data.

1. Create a folder anywhere on your PC (e.g., `E:\JarvisVault`).
2. Inside this folder, create a folder named `daily`.
3. This vault will serve as the shared workspace between you and JARVIS. 

---

## Phase 3: Operator Installation

1. **Clone the repository:**
```bash
git clone https://github.com/LegendaryRed318/Operator.git
cd Operator
```

2. **Install Python dependencies (Backend):**
```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

3. **Install Frontend dependencies:**
```bash
cd ../frontend
npm install
```

4. **Configure Environment:**
Navigate to the `backend` folder and create a `.env` file with the following variables:
```env
# Required
OLLAMA_URL=http://localhost:11434
VAULT_PATH=E:/JarvisVault

# Optional: Cloud Fallback
GEMINI_API_KEY=your_gemini_api_key_here
USE_GEMINI_FALLBACK=true

# Optional: Tailscale Remote Access
ENABLE_REMOTE_ACCESS=true
TAILSCALE_AUTHKEY=tskey-auth-your-key-here
```

---

## Phase 4: Obsidian LiveSync Configuration

To achieve real-time synchronization between JARVIS, your PC Obsidian, and your Phone Obsidian, we use the **Self-hosted LiveSync** community plugin backed by CouchDB.

### Step A: Configure CouchDB
1. Install Apache CouchDB on your PC. Create an admin username and password during setup.
2. Open your browser and go to `http://127.0.0.1:5984/_utils` (The Fauxton UI) and log in.
3. **Open the Network:** Go to the Gear Icon (Configuration) -> Main Config. Find `chttpd` -> `bind_address` and change `127.0.0.1` to `0.0.0.0`.
4. **Enable CORS:** Go to the CORS tab, click "Enable CORS", and select "All domains (*)".

### Step B: Open the Windows Firewall
Your phone needs to reach CouchDB via Tailscale. You must punch a hole in the firewall.
1. Open Command Prompt **as Administrator**.
2. Run this exact command:
   ```cmd
   netsh advfirewall firewall add rule name="CouchDB" dir=in action=allow protocol=TCP localport=5984
   ```

### Step C: Configure Obsidian (PC)
1. Open Obsidian on your PC and open `E:\JarvisVault` as your vault.
2. Turn off Safe Mode and install the **Self-hosted LiveSync** community plugin.
3. In the plugin settings, set the URI to `http://127.0.0.1:5984`.
4. Enter your CouchDB username and password. Set the database name to `obsidian-sync`.
5. Click **Test Database Connection** and then **Check and Create Database**.
6. Turn on **End-to-End Encryption** and create a Passphrase.
7. Enable LiveSync.
8. Scroll to the bottom of the settings and click **Copy setup URI**.

### Step D: Configure Obsidian (Phone)
1. On your phone, ensure the **Tailscale VPN is turned ON**.
2. Create a **brand new, empty vault** in the Obsidian mobile app.
3. Install the Self-hosted LiveSync plugin in this empty vault.
4. **CRITICAL STEP:** In the plugin settings, check the box that says **"Use Internal API"**. (Mobile operating systems block HTTP connections; this bypasses that restriction).
5. Paste the Setup URI from your PC into the phone.
6. The URI currently says `127.0.0.1`. **Change it to your PC's Tailscale IP address** (e.g., `100.x.x.x`).
7. Enter your Passphrase.
8. When asked, select *"This vault is empty or contains only new files that are not on the server"* to pull JARVIS's data down to your phone.

---

## Phase 5: Launching JARVIS

Once everything is installed, starting JARVIS is as simple as running the unified launcher:

```bash
cd Operator
python launcher.py
```

The launcher will automatically start the Backend API, the WebSocket Server, the Frontend Dashboard, and initialize the Vision Service for face detection. 

**JARVIS is always listening. Try saying "Good morning, Jarvis."**