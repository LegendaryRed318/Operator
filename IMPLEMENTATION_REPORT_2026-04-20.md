# Operator Implementation Report

Date: 2026-04-20

This document records everything implemented, changed, fixed, and improved during the recent Jarvis upgrade pass.

## 1) Speech and Voice Reliability

### Problem addressed
- Voice transcription was hardcoded to `http://localhost:5050/transcribe`, which breaks when accessed through ngrok/remote host setups.

### Changes made
- Updated `frontend/src/contexts/VoiceContext.tsx`
  - Added dynamic `getApiBaseUrl()` resolver.
  - Added optional `VITE_OPERATOR_API_URL` override.
  - Added optional `VITE_OPERATOR_WS_URL` override.
  - Replaced hardcoded transcription URLs with `${getApiBaseUrl()}/transcribe`.
- Updated `frontend/src/voice.ts`
  - Added dynamic `getApiBaseUrl()` resolver.
  - Added optional `VITE_OPERATOR_API_URL` and `VITE_OPERATOR_WS_URL` overrides.
  - Replaced hardcoded transcription URL with `${getApiBaseUrl()}/transcribe`.

### Outcome
- Speech transcription now works in local and remote/ngrok contexts without manual code edits.

## 2) Skills System Core Upgrades

### Problem addressed
- Skill handling was basic and missing operational controls (matching modes, cooldowns, validation, execution controls, audit trail).

### Changes made
- Updated `backend/skills.py`:
  - Added configurable TOML metadata support:
    - `aliases`
    - `trigger_mode` (`contains`, `exact`, `regex`)
    - `enabled`
    - `priority`
    - `requires_online`
    - `cooldown_seconds`
    - `timeout_seconds`
  - Added action support for TOML skills:
    - `action.type = response`
    - `action.type = command`
  - Added cooldown enforcement.
  - Added timeout enforcement for skill execution.
  - Added online requirement checks.
  - Added structured dispatch source tracking.
  - Added skill runtime state tracking.
  - Added audit logging to `logs/skills_audit.jsonl`.
  - Added new helpers:
    - `reload_skills_cache()`
    - `list_skills_snapshot()`
    - `validate_skills_files()`

### Outcome
- Skills are now safer, more flexible, and production-friendly.

## 3) Skills API and Operations

### Problem addressed
- No full operational API for reload/validation and richer listing.

### Changes made
- Updated `backend/server.py`:
  - Improved `POST /skills/trigger` to pass params + source.
  - Enhanced `GET /skills` to return a full snapshot (built-in + loaded TOML metadata).
  - Added `POST /skills/reload`.
  - Added `GET /skills/validate`.
  - Updated `POST /skills/import-zip` response to include `reloaded_count`.
- Updated `backend/ws_server.py`:
  - Skill dispatch now tags source (`voice_ws`).

### Outcome
- Skills can be validated and reloaded live from API/UI.

## 4) Skills Path and Vault Defaults

### Problem addressed
- External vault usage required manual env configuration every time.

### Changes made
- Updated `backend/paths.py`:
  - Added preferred external vault detection: `E:/JarvisVault`.
  - If available, default vault path becomes `E:/JarvisVault`.
  - If available, default skills path becomes `E:/JarvisVault/skills`.
  - Env vars still override defaults (`OPERATOR_VAULT_PATH`, `OPERATOR_SKILLS_PATH`).

### Outcome
- Jarvis automatically aligns with external vault storage when present.

## 5) Phase Tracking Endpoint

### Problem addressed
- Phase status existed mostly in docs, not exposed as a runtime API.

### Changes made
- Added `GET /phases/status` in `backend/server.py`.

### Outcome
- Frontend/tools can query current phase progress programmatically.

## 6) Jarvis Brain Profile System (Editable Memory)

### Problem addressed
- No dedicated editable profile memory model for user identity/preferences and long-term behavior context.

### Changes made
- Updated `backend/memory.py`:
  - Added profile persistence:
    - JSON profile file: `raw_sources/jarvis_brain_profile.json`
    - Markdown mirror: `wiki/user-profile/RED_Profile.md`
  - Added defaults scaffold for brain profile.
  - Added helpers:
    - `get_brain_profile()`
    - `set_brain_profile(profile, mode="replace|merge")`
    - `append_brain_profile_note(note)`
  - Added deep merge support for profile updates.
  - Added profile markdown regeneration.
- Updated `backend/server.py`:
  - Added `GET /brain/profile`
  - Added `PUT /brain/profile` (replace/merge mode via payload)
  - Added `PATCH /brain/profile` (merge)
  - Added `POST /brain/profile/note`
- Seeded profile data using the shared user context.
- Added imported memory export file:
  - `vault/raw_sources/red_profile_export_2026-04-20.md`

### Outcome
- Jarvis brain profile is now persistent, editable, and expandable over time.

## 7) HUD Upgrades (Skills + Brain Editor)

### Problem addressed
- No UI controls for skill operations or profile editing.

### Changes made
- Updated `frontend/src/components/dashboard/OperatorHUD.tsx`:
  - Added Skills Admin panel:
    - Live summary (built-in/imported/validation counts)
    - Validate action
    - Reload action
  - Added Jarvis Brain Editor panel:
    - Load profile JSON
    - Edit JSON in place
    - Save merged updates
    - Add quick notes to brain journal
    - Status messages for operations

### Outcome
- Core skills and brain memory operations are now directly manageable from HUD.

## 8) New Files Added

- `skills/template.skill.toml`
- `vault/raw_sources/red_profile_export_2026-04-20.md`
- `IMPLEMENTATION_REPORT_2026-04-20.md`

## 9) Validation and Checks Run

- Python compile checks were run on modified backend modules:
  - `backend/paths.py`
  - `backend/memory.py`
  - `backend/skills.py`
  - `backend/server.py`
  - `backend/ws_server.py`
- Lint checks for modified frontend/backend files returned no new linter errors.
- Brain profile persistence was smoke-tested (`name RED`, `updated_at` present).
- Skills helper snapshot/validation functions were smoke-tested successfully.

## 10) Behavior and Safety Constraints Enforced

- Location tracking and device surveillance are explicitly disabled in profile rules.
- Financial support is represented as guidance mode, not autonomous fund control.
- Offensive slurs are not allowed.
- Editable profile design keeps long-term memory structured and user-controlled.

## 11) Next Recommended Steps

- Add a dedicated Settings view for Brain and Skills (instead of overlay-only HUD controls).
- Add auth token headers to admin endpoints in HUD calls if admin token is enabled.
- Add profile schema validation + friendly field-level editor UI (instead of raw JSON).
- Add export/import profile backup endpoints.
You are working on the Jarvis/Operator project. The user has just installed new Ollama models on D:\OllamaModels\.ollama\models and needs them wired into Jarvis properly.

## Installed models (all on D: drive)
- qwen2.5-coder:1.5b-base  — fast, lightweight, simple tasks
- qwen2.5-coder:7b          — strong coding, complex code tasks  
- deepseek-r1:7b            — best reasoning, thinking, analysis
- llama3.2:3b               — fast general conversation

## TASK 1 — Fix backend/decision_engine.py

Update select_model_by_ram() with this exact priority logic:

| Available RAM | Preferred model       | Fallback            |
|---------------|-----------------------|---------------------|
| > 6GB         | deepseek-r1:7b        | qwen2.5-coder:7b    |
| > 4GB         | qwen2.5-coder:7b      | llama3.2:3b         |
| > 2GB         | llama3.2:3b           | qwen2.5-coder:1.5b-base |
| <= 2GB        | qwen2.5-coder:1.5b-base | None (use Gemini) |

Rules:
- Always check installed models via GET http://localhost:11434/api/tags before selecting
- If preferred not installed, try fallback, then next tier down
- If nothing installed, return None so ws_server.py uses Gemini fallback
- Add OLLAMA_MODELS env var support: read from os.getenv("OLLAMA_MODELS") and pass to Ollama if set
- Log which model was selected and why (RAM amount + model name)

## TASK 2 — Update backend/ws_server.py

Update classify_intent() to route tasks to the right model:

| Intent type | Best model          | Why                        |
|-------------|---------------------|----------------------------|
| coding      | qwen2.5-coder:7b    | Specialist coding model     |
| reasoning   | deepseek-r1:7b      | Best at thinking/analysis   |
| general     | llama3.2:3b         | Fast, good enough           |
| financial   | Gemini (existing)   | Keep as-is                  |
| memory      | deepseek-r1:7b      | Needs reasoning to recall   |

Add these keywords to classify_intent():
- reasoning: 'why', 'explain', 'analyse', 'analyze', 'reason', 'think', 'figure out', 'debug', 'error', 'fix this', 'what went wrong', 'understand'
- coding: existing list + 'jarvis write', 'generate code', 'make a function', 'add feature'
- memory: existing list

New function: select_model_for_intent(text: str) -> str | None
- Calls classify_intent() to get intent
- Calls select_model_by_ram() to get best available model
- If intent is 'coding' and qwen2.5-coder:7b is available → use it regardless of RAM tier (it's worth the RAM)
- If intent is 'reasoning' and deepseek-r1:7b is available and RAM > 4GB → use it
- Otherwise use RAM-tier selection
- Returns model name string or None for Gemini

Replace the existing model selection in handle_voice_command() with select_model_for_intent(text)

## TASK 3 — Update backend/.env

Add these lines if not already present:
OLLAMA_MODELS=D:\OllamaModels\.ollama\models
OLLAMA_URL=http://localhost:11434

## TASK 4 — Update frontend/src/components/dashboard/OperatorHUD.tsx

In the existing system diagnostics panel (left side gauges), add an "AI MODEL" display:
- Fetches GET /models every 10 seconds (endpoint already exists)
- Shows the currently active model name in short form:
  - "deepseek-r1:7b" → "DeepSeek R1"
  - "qwen2.5-coder:7b" → "Qwen Coder 7B"  
  - "qwen2.5-coder:1.5b-base" → "Qwen Coder 1.5B"
  - "llama3.2:3b" → "Llama 3.2"
  - "gemini-flash" → "Gemini Flash"
- Green colour when using 7b models, yellow for smaller, blue for Gemini
- Shows all installed models as small dots below the active one

## CONSTRAINTS
- Do not change any existing endpoint signatures
- All Python must pass: python -m py_compile backend/decision_engine.py backend/ws_server.py
- Keep the existing Gemini fallback path — do not remove it
- OLLAMA_MODELS path must use forward slashes in the Python code (replace backslashes)
- No new npm packages
- Jarvis should never crash if Ollama is offline — always fall back to Gemini gracefully

## FILES TO MODIFY
- backend/decision_engine.py
- backend/ws_server.py  
- backend/.env
- frontend/src/components/dashboard/OperatorHUD.tsx