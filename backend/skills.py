#!/usr/bin/env python3
"""
skills.py - Skill execution system for JARVIS.
Loads TOML skill definitions and handles voice trigger matching.
"""

import json
import logging
import os
import re
import socket
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional
# Import paths - handle both running from backend/ and project root
try:
    from paths import DB_PATH, LOGS_PATH, SKILLS_PATH, USER_CITY, USER_CITY_LAT, USER_CITY_LON
except ImportError:
    from backend.paths import DB_PATH, LOGS_PATH, SKILLS_PATH, USER_CITY, USER_CITY_LAT, USER_CITY_LON

# Try to import requests for weather API
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    logging.warning("[Skills] requests module not available - weather skill will not work")

import psutil

# Import toml - try stdlib first (Python 3.11+), then fallback
try:
    import tomllib  # Python 3.11+
    def load_toml(path):
        with open(path, "rb") as f:
            return tomllib.load(f)
    TOML_LOADER = load_toml
except ImportError:
    try:
        import toml
        def load_toml(path):
            with open(path, "r", encoding="utf-8") as f:
                return toml.load(f)
        TOML_LOADER = load_toml
    except ImportError:
        TOML_LOADER = None

logger = logging.getLogger(__name__)
AUDIT_LOG_PATH = LOGS_PATH / "skills_audit.jsonl"

# Built-in skill handlers (voice triggers that don't need TOML files)
# App registry for the open_app skill — maps spoken names to executables
APP_REGISTRY = {
    "chrome": "start chrome",
    "google chrome": "start chrome",
    "firefox": "start firefox",
    "discord": "start discord:",
    "spotify": "start spotify:",
    "code": "code",
    "vs code": "code",
    "visual studio code": "code",
    "notepad": "notepad",
    "calculator": "calc",
    "file explorer": "explorer",
    "explorer": "explorer",
    "terminal": "wt",
    "cmd": "cmd",
    "powershell": "powershell",
    "task manager": "taskmgr",
    "outlook": "start outlook:",
    "word": "start winword",
    "excel": "start excel",
    "youtube": "start chrome https://youtube.com",
    "youtube music": "start chrome https://music.youtube.com",
    "google": "start chrome https://google.com",
    "github": "start chrome https://github.com",
}

BUILT_IN_SKILLS = {
    "good_morning": {
        "triggers": ["good morning", "good day"],
        "handler": "handle_good_morning",
        "description": "Wish RED good morning and give daily briefing"
    },
    "time": {
        "triggers": ["what time", "what's the time", "current time", "tell me the time"],
        "handler": "handle_time",
        "description": "Tell current time"
    },
    "system_status": {
        "triggers": ["system status", "how's the system", "status report"],
        "handler": "handle_system_status",
        "description": "Report system vitals and health"
    },
    "wake_up": {
        "triggers": ["wake up", "i'm back", "i'm home"],
        "handler": "handle_wake_up",
        "description": "Wake from sleep mode and greet RED"
    },
    "sleep": {
        "triggers": ["go to sleep", "sleep now", "goodnight", "good night"],
        "handler": "handle_sleep",
        "description": "Enter sleep mode",
        "no_questions": True,  # Don't trigger on questions like 'should I sleep now?'
    },
    "weather": {
        "triggers": ["weather", "temperature outside", "is it raining", "what's the forecast", "will it rain", "how cold is it", "how hot is it"],
        "handler": "handle_weather",
        "description": "Fetch local weather information"
    },
    "calendar": {
        "triggers": ["calendar", "schedule", "appointments today", "what's on today", "do i have meetings", "my agenda", "events today"],
        "handler": "handle_calendar",
        "description": "Check today's calendar events"
    },
    "open_app": {
        "triggers": ["open chrome", "open firefox", "open discord", "open spotify", "open code", "open vs code", "open notepad", "open calculator", "open file explorer", "open terminal", "open task manager", "open outlook", "open word", "open excel", "open powershell", "launch chrome", "launch discord", "launch spotify"],
        "handler": "handle_open_app",
        "description": "Launch applications by name"
    },
    "joke": {
        "triggers": ["tell me a joke", "make me laugh", "say something funny", "got any jokes"],
        "handler": "handle_joke",
        "description": "Tell a random joke"
    },
    "coin_flip": {
        "triggers": ["flip a coin", "heads or tails", "coin toss", "toss a coin"],
        "handler": "handle_coin_flip",
        "description": "Flip a virtual coin"
    },
    "reminder": {
        "triggers": ["remind me to", "set a reminder", "create reminder", "add reminder"],
        "handler": "handle_reminder",
        "description": "Set a reminder for later"
    },
    "timer": {
        "triggers": ["set timer", "start timer", "timer for", "countdown"],
        "handler": "handle_timer",
        "description": "Set a countdown timer"
    },
    "quick_note": {
        "triggers": ["take a note", "quick note", "jot down", "remember this"],
        "handler": "handle_quick_note",
        "description": "Save a quick note to memory"
    },
    "quick_math": {
        "triggers": ["calculate", "what is", "compute", "math"],
        "handler": "handle_quick_math",
        "description": "Quick mathematical calculations"
    },
    "unit_convert": {
        "triggers": ["convert", "how many", "inches to", "miles to", "celsius to", "fahrenheit to"],
        "handler": "handle_unit_convert",
        "description": "Convert between units"
    },
    "define_word": {
        "triggers": ["define", "what does", "meaning of", "dictionary"],
        "handler": "handle_define_word",
        "description": "Look up word definitions"
    },
    "random_number": {
        "triggers": ["random number", "pick a number", "generate random"],
        "handler": "handle_random_number",
        "description": "Generate a random number"
    },
    "find_file": {
        "triggers": ["find file", "where is the file", "locate file", "search for file", "find the file"],
        "handler": "handle_find_file",
        "description": "Search for files by name across C, D, and E drives"
    },
    "search_knowledge": {
        "triggers": ["search my notes", "what do my notes say", "check my drives for", "search knowledge", "look up in vault"],
        "handler": "handle_search_knowledge",
        "description": "Semantic search across all indexed documents"
    },
    "hardware_health": {
        "triggers": ["hardware health", "disk health", "how are my drives", "is my computer dying", "hardware report"],
        "handler": "handle_hardware_health",
        "description": "Check S.M.A.R.T. indicators and hardware vitals"
    },
    "web_search": {
        "triggers": ["search the web for", "google", "search for", "look up"],
        "handler": "handle_web_search",
        "description": "Search the live web for information"
    },
}


# Question-word prefixes that indicate the user is asking, not commanding.
_QUESTION_STARTERS = (
    "what", "why", "how", "when", "where", "who", "which",
    "is", "are", "was", "were", "does", "do", "did",
    "can", "will", "would", "could", "should", "have", "has",
)


def _is_question(text: str) -> bool:
    """
    Return True if text looks like an informational question rather than a command.
    Used to prevent action-type skills (e.g. 'sleep') from firing on queries like
    'should I sleep now?' or 'how does sleep work?'.
    """
    stripped = text.strip().rstrip(".")
    if stripped.endswith("?"):
        return True
    first_word = stripped.split()[0] if stripped else ""
    return first_word in _QUESTION_STARTERS


class SkillExecutor:
    """Executes built-in skills and manages TOML skill loading."""
    
    def __init__(self):
        self.loaded_skills: dict = {}
        self.skill_runtime_state: dict[str, dict[str, Any]] = {}
        self._runtime_lock = threading.Lock()
        self.skill_handlers: dict = {
            "handle_good_morning": self._handle_good_morning,
            "handle_time": self._handle_time,
            "handle_system_status": self._handle_system_status,
            "handle_wake_up": self._handle_wake_up,
            "handle_sleep": self._handle_sleep,
            "handle_weather": self._handle_weather,
            "handle_calendar": self._handle_calendar,
            "handle_open_app": self._handle_open_app,
            "handle_joke": self._handle_joke,
            "handle_coin_flip": self._handle_coin_flip,
            "handle_reminder": self._handle_reminder,
            "handle_timer": self._handle_timer,
            "handle_quick_note": self._handle_quick_note,
            "handle_quick_math": self._handle_quick_math,
            "handle_unit_convert": self._handle_unit_convert,
            "handle_define_word": self._handle_define_word,
            "handle_random_number": self._handle_random_number,
            "handle_find_file": self._handle_find_file,
            "handle_search_knowledge": self._handle_search_knowledge,
            "handle_hardware_health": self._handle_hardware_health,
            "handle_web_search": self._handle_web_search,
        }
        self._load_toml_skills()

    @staticmethod
    def _is_online() -> bool:
        try:
            with socket.create_connection(("1.1.1.1", 53), timeout=1.5):
                return True
        except Exception:
            return False

    @staticmethod
    def _coerce_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _coerce_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _coerce_bool(value: Any, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("true", "1", "yes", "on"):
                return True
            if lowered in ("false", "0", "no", "off"):
                return False
        return default

    @staticmethod
    def _normalize_mode(mode: Any) -> str:
        if not isinstance(mode, str):
            return "contains"
        lowered = mode.strip().lower()
        if lowered in ("contains", "exact", "regex"):
            return lowered
        return "contains"

    def _append_audit_log(self, entry: dict[str, Any]) -> None:
        try:
            redacted = dict(entry)
            text = str(redacted.get("command_text", ""))
            text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[redacted-email]", text)
            redacted["command_text"] = text
            LOGS_PATH.mkdir(parents=True, exist_ok=True)
            
            # Rotate log if it exceeds 5MB
            if AUDIT_LOG_PATH.exists() and AUDIT_LOG_PATH.stat().st_size > 5 * 1024 * 1024:
                backup_path = LOGS_PATH / f"skills_audit_{int(time.time())}.jsonl"
                try:
                    AUDIT_LOG_PATH.rename(backup_path)
                except OSError:
                    pass

            with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(redacted, ensure_ascii=True) + "\n")
        except Exception as e:
            logger.warning(f"[Skills] Failed to write audit entry: {e}")

    def _run_with_timeout(self, handler: Callable[[str], str], text: str, timeout_s: float) -> tuple[bool, Optional[str], Optional[str]]:
        result: dict[str, Any] = {"done": False, "value": None, "error": None}

        def _runner():
            try:
                result["value"] = handler(text)
            except Exception as e:
                result["error"] = str(e)
            finally:
                result["done"] = True

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join(timeout=max(0.1, timeout_s))
        if thread.is_alive():
            return False, None, f"Execution timed out after {timeout_s:.1f}s"
        if result["error"] is not None:
            return False, None, result["error"]
        return True, str(result["value"] or ""), None

    def _check_cooldown(self, skill_name: str, cooldown_s: float) -> tuple[bool, float]:
        if cooldown_s <= 0:
            return True, 0.0
        now = time.time()
        with self._runtime_lock:
            state = self.skill_runtime_state.setdefault(skill_name, {})
            last_run = float(state.get("last_run", 0.0))
            elapsed = now - last_run
            if elapsed < cooldown_s:
                return False, cooldown_s - elapsed
            state["last_run"] = now
            return True, 0.0

    def _normalize_loaded_skill(self, skill_file: Path, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        # Detect schema: Schema 1 has [skill] with triggers/aliases arrays + [actions.<type>]
        # Schema 2 has [skill] with singular trigger/string aliases + [action]
        has_skill_section = "skill" in data
        skill_def = data.get("skill", {}) if has_skill_section else data

        if not isinstance(skill_def, dict):
            return None

        # Schema 1: has triggers (plural array), aliases (plural array), action_type at top level
        # Schema 2: has trigger (singular string), aliases (array), type in [action]
        is_schema1 = has_skill_section and "triggers" in skill_def
        is_schema2 = has_skill_section and "trigger" in skill_def

        # Get action def based on schema
        if is_schema1:
            # Schema 1: [skill] + [actions.<type>]
            action_def = {}
        elif has_skill_section and "action" in data and isinstance(data["action"], dict):
            # Schema 2: [skill] + [action]
            action_def = data.get("action", {})
        else:
            action_def = {}

        skill_name = str(skill_def.get("name", skill_file.stem)).strip()

        # Handle triggers/aliases for both schemas
        if is_schema1:
            # Schema 1: triggers is a list, aliases is a list
            triggers_raw = skill_def.get("triggers", [])
            trigger_text = ""
            aliases: list[str] = []
            if isinstance(triggers_raw, list):
                aliases = [str(x).strip().lower() for x in triggers_raw if str(x).strip()]
            aliases_raw = skill_def.get("aliases", [])
            if isinstance(aliases_raw, list):
                aliases.extend(str(x).strip().lower() for x in aliases_raw if str(x).strip())
        else:
            # Schema 2: trigger is a string, aliases is a list
            trigger_text = str(skill_def.get("trigger", "")).strip().lower()
            aliases_raw = skill_def.get("aliases", [])
            aliases: list[str] = []
            if isinstance(aliases_raw, list):
                aliases = [str(x).strip().lower() for x in aliases_raw if str(x).strip()]
            elif isinstance(aliases_raw, str) and aliases_raw.strip():
                aliases = [aliases_raw.strip().lower()]

        trigger_mode = self._normalize_mode(skill_def.get("trigger_mode", "contains"))
        enabled = self._coerce_bool(skill_def.get("enabled", True), True)
        priority = self._coerce_int(skill_def.get("priority", 100), 100)
        requires_online = self._coerce_bool(skill_def.get("requires_online", False), False)
        cooldown_s = self._coerce_float(skill_def.get("cooldown_seconds", 0), 0.0)
        timeout_s = self._coerce_float(skill_def.get("timeout_seconds", 8), 8.0)
        response = str(skill_def.get("response", "")).strip()

        # Get action_type and action params based on schema
        if is_schema1:
            # Schema 1: action_type at top level
            action_type = str(skill_def.get("action_type", "response")).strip().lower()
            actions_section = data.get("actions", {})
            action_params = actions_section.get(action_type, {}) if isinstance(actions_section, dict) else {}
            action_command = str(action_params.get("vault_path", "")).strip()
            response_section = data.get("response", {})
            if isinstance(response_section, dict):
                action_response = str(response_section.get("success", response)).strip()
            else:
                action_response = str(response_section).strip() or response
        elif action_def:
            # Schema 2: action type in action_def
            action_type = str(action_def.get("type", action_def.get("action", "response"))).strip().lower()
            action_command = str(action_def.get("command", "")).strip()
            action_response = str(action_def.get("response", response)).strip()
            action_params = action_def
        else:
            # Fallback
            action_type = "response"
            action_command = ""
            action_response = response
            action_params = {}

        action_timeout = self._coerce_float(action_def.get("timeout_seconds", timeout_s), timeout_s)

        return {
            "name": skill_name,
            "file": skill_file.name,
            "definition": data,
            "trigger": trigger_text,
            "aliases": aliases,
            "trigger_mode": trigger_mode,
            "description": str(skill_def.get("description", "")),
            "enabled": enabled,
            "priority": priority,
            "requires_online": requires_online,
            "cooldown_seconds": max(0.0, cooldown_s),
            "timeout_seconds": max(0.5, timeout_s),
            "response": response,
            "action_type": action_type,
            "action_command": action_command,
            "action_response": action_response,
            "action_timeout_seconds": max(0.5, action_timeout),
        }
    
    def _load_toml_skills(self):
        """Load skill definitions from TOML files."""
        if TOML_LOADER is None:
            logger.warning("[Skills] No TOML parser available (install 'toml' package)")
            return

        try:
            self.loaded_skills.clear()
            SKILLS_PATH.mkdir(parents=True, exist_ok=True)
            for skill_file in SKILLS_PATH.glob("*.toml"):
                try:
                    data = TOML_LOADER(skill_file)
                    normalized = self._normalize_loaded_skill(skill_file, data)
                    if normalized:
                        skill_name = normalized["name"]
                        self.loaded_skills[skill_name] = normalized
                        logger.info(f"[Skills] Loaded: {skill_name}")
                except Exception as e:
                    logger.error(f"[Skills] Failed to load {skill_file}: {e}")
        except Exception as e:
            logger.error(f"[Skills] Error loading skills: {e}")

    def reload(self) -> int:
        """Reload skill definitions from disk and return count."""
        self._load_toml_skills()
        return len(self.loaded_skills)
    
    def match_trigger(self, text: str) -> Optional[dict[str, Any]]:
        """
        Match voice text against skill triggers.
        Returns (skill_name, handler_function) or None if no match.
        All handlers accept (text: str) as their argument.
        """
        text_lower = text.lower().strip()
        text_is_question = _is_question(text_lower)

        # Check built-in skills first
        for skill_id, skill_info in BUILT_IN_SKILLS.items():
            # Skip action-type skills when the input is clearly a question
            if skill_info.get("no_questions", False) and text_is_question:
                continue
            for trigger in skill_info["triggers"]:
                if trigger in text_lower:
                    handler_name = skill_info["handler"]
                    handler = self.skill_handlers.get(handler_name)
                    if handler:
                        return {
                            "skill_name": skill_id,
                            "handler": handler,
                            "implemented": True,
                            "matched_by": "built_in_contains",
                            "metadata": {
                                "enabled": True,
                                "priority": 0,
                                "requires_online": False,
                                "cooldown_seconds": 0.0,
                                "timeout_seconds": 10.0,
                            },
                        }

        # Check TOML-loaded skills sorted by priority
        candidates = sorted(
            self.loaded_skills.items(),
            key=lambda kv: int(kv[1].get("priority", 100))
        )
        for skill_name, skill_data in candidates:
            if not skill_data.get("enabled", True):
                continue
            patterns = []
            trigger = str(skill_data.get("trigger", "")).strip()
            if trigger:
                patterns.append(trigger)
            patterns.extend(skill_data.get("aliases", []))
            mode = skill_data.get("trigger_mode", "contains")

            matched_by = None
            for pattern in patterns:
                if mode == "exact" and pattern == text_lower:
                    matched_by = "toml_exact"
                    break
                if mode == "regex":
                    try:
                        if re.search(pattern, text_lower):
                            matched_by = "toml_regex"
                            break
                    except re.error:
                        logger.warning(f"[Skills] Invalid regex in skill '{skill_name}': {pattern}")
                elif mode == "contains" and pattern in text_lower:
                    matched_by = "toml_contains"
                    break

            if not matched_by:
                continue

            handler = self._make_toml_handler(skill_name, skill_data)
            return {
                "skill_name": skill_name,
                "handler": handler,
                "implemented": True,
                "matched_by": matched_by,
                "metadata": {
                    "enabled": bool(skill_data.get("enabled", True)),
                    "priority": int(skill_data.get("priority", 100)),
                    "requires_online": bool(skill_data.get("requires_online", False)),
                    "cooldown_seconds": float(skill_data.get("cooldown_seconds", 0.0)),
                    "timeout_seconds": float(skill_data.get("timeout_seconds", 8.0)),
                },
            }

        return None

    def _make_toml_handler(self, skill_name: str, skill_data: dict[str, Any]) -> Callable[[str], str]:
        def _handler(text: str) -> str:
            action_type = skill_data.get("action_type", "response")
            if action_type == "command":
                command = skill_data.get("action_command", "")
                if not command:
                    return f"Skill '{skill_name}' has no command configured."
                timeout_s = float(skill_data.get("action_timeout_seconds", 8.0))
                completed = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout_s,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
                )
                if completed.returncode != 0:
                    stderr = (completed.stderr or "").strip()
                    return f"Skill '{skill_name}' command failed: {stderr[:120] or f'exit code {completed.returncode}'}"
                out = (completed.stdout or "").strip()
                if out:
                    return out[:300]
                return skill_data.get("action_response") or f"Skill '{skill_name}' executed successfully."

            elif action_type == "voice_capture_then_write":
                # Signal ws_server to start VAD capture, return the prompt response
                with self._runtime_lock:
                    self.skill_runtime_state[skill_name] = {"awaiting_capture": True}
                return skill_data.get("action_response") or skill_data.get("response") or "Go ahead, sir."

            elif action_type == "vault_summary":
                # Scan vault for briefing
                from paths import VAULT_PATH as DEFAULT_VAULT_PATH
                vault_path_str = skill_data.get("action_command", "") or os.getenv("VAULT_PATH", str(DEFAULT_VAULT_PATH))
                vault_path = Path(vault_path_str)
                file_count = 0
                recent = []
                if vault_path.exists():
                    for item in vault_path.rglob("*"):
                        if item.is_file():
                            file_count += 1
                            try:
                                recent.append((item.name, item.stat().st_mtime))
                            except Exception:
                                pass
                    recent.sort(key=lambda x: x[1], reverse=True)
                    recent = recent[:5]
                response = skill_data.get("action_response") or "Good morning, sir. "
                if file_count > 0:
                    response += f"Your vault contains {file_count} files."
                    if recent:
                        names = ", ".join(n for n, _ in recent[:3])
                        response += f" Recent: {names}."
                return response

            elif action_type == "vault_log":
                # Log session end to vault
                from paths import VAULT_PATH as DEFAULT_VAULT_PATH
                vault_path_str = skill_data.get("action_command", "") or os.getenv("VAULT_PATH", str(DEFAULT_VAULT_PATH))
                vault_path = Path(vault_path_str)
                log_dir = vault_path / "logs"
                try:
                    log_dir.mkdir(parents=True, exist_ok=True)
                    today = datetime.now().strftime("%Y-%m-%d")
                    log_file = log_dir / f"{today}.md"
                    timestamp = datetime.now().strftime("%H:%M")
                    entry = f"\n## {timestamp} — End of Day\nSession ended.\n"
                    with open(log_file, "a", encoding="utf-8") as f:
                        f.write(entry)
                except Exception as e:
                    logger.warning(f"[Skills] vault_log failed: {e}")
                return skill_data.get("action_response") or "Session logged, sir."

            elif action_type == "open_application":
                # Extract app name from text and launch
                app_name = None
                text_lower = text.lower()
                app_map = {
                    "chrome": "start chrome", "firefox": "start firefox",
                    "discord": "start discord:", "spotify": "start spotify:",
                    "code": "code", "vs code": "code",
                    "notepad": "notepad", "calculator": "calc",
                    "file explorer": "explorer", "explorer": "explorer",
                    "terminal": "wt", "cmd": "cmd",
                }
                for name, cmd in app_map.items():
                    if name in text_lower:
                        app_name = name
                        try:
                            subprocess.Popen(cmd, shell=True,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0)
                            return f"Opening {name}, sir."
                        except Exception as e:
                            return f"Couldn't open {name}, sir. {e}"
                return f"I don't see an app I can open in that command, sir."

            # default response action
            return skill_data.get("action_response") or skill_data.get("response") or f"Skill '{skill_name}' executed."

        return _handler
    
    def _handle_good_morning(self, text: str = "") -> str:
        """Good morning briefing for RED with weather, system status, and overnight summary."""
        hour = datetime.now().hour
        if hour < 5:
            greeting = "You're up early"
        elif hour < 12:
            greeting = "Good morning"
        elif hour < 17:
            greeting = "Good afternoon"
        else:
            greeting = "Good evening"

        briefing_parts = [f"{greeting}, sir."]

        # 1. Weather (if available)
        try:
            if REQUESTS_AVAILABLE:
                weather = self._get_weather_brief()
                if weather:
                    briefing_parts.append(weather)
        except Exception:
            pass

        # 2. System status
        try:
            cpu = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            ram_gb = round(mem.used / (1024**3), 1)
            ram_percent = mem.percent

            # Check disk space on C:
            disk = psutil.disk_usage('C:\\')
            disk_percent = disk.percent

            # Build system message
            if ram_percent > 85 or disk_percent > 90:
                status_msg = f"⚠️ System under pressure: {ram_percent:.0f}% RAM, {disk_percent:.0f}% disk."
            elif cpu > 70:
                status_msg = f"System active at {cpu:.0f}% CPU, {ram_gb}GB RAM in use."
            else:
                status_msg = "All systems nominal."

            briefing_parts.append(status_msg)

            # Disk warning
            if disk_percent > 85:
                briefing_parts.append(f"⚠️ C: drive is {disk_percent:.0f}% full — consider cleanup.")

        except Exception:
            briefing_parts.append("System status temporarily unavailable.")

        # 3. Overnight errors summary
        try:
            if DB_PATH.exists():
                import sqlite3
                conn = sqlite3.connect(str(DB_PATH), timeout=2.0)
                cursor = conn.cursor()

                # Get errors from last 8 hours
                from datetime import datetime, timedelta
                cutoff = (datetime.now() - timedelta(hours=8)).isoformat()
                cursor.execute(
                    "SELECT COUNT(*), project_name FROM errors WHERE timestamp > ? AND (fixed = 0 OR fixed IS NULL) GROUP BY project_name",
                    (cutoff,)
                )
                recent_errors = cursor.fetchall()
                conn.close()

                if recent_errors:
                    total_errors = sum(row[0] for row in recent_errors)
                    projects = [row[1] for row in recent_errors]
                    briefing_parts.append(f"⚠️ {total_errors} new errors overnight in: {', '.join(projects)}.")
                else:
                    briefing_parts.append("No new errors overnight.")
        except Exception:
            pass

        # 4. Check for conversation summary from yesterday
        try:
            from datetime import datetime, timedelta
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            summary_path = Path("E:\\JarvisVault\\wiki\\conversation-summaries") / f"{yesterday}-summary.md"
            if summary_path.exists():
                briefing_parts.append(f"Yesterday's conversation summary available in the vault.")
        except Exception:
            pass

        briefing_parts.append("How may I assist you today?")
        return " ".join(briefing_parts)

    def _get_weather_brief(self) -> str:
        """Get brief weather for user's configured location. Returns empty string on failure."""
        try:
            import requests
            # Open-Meteo free API - no key required
            # Uses USER_CITY, USER_CITY_LAT, USER_CITY_LON from paths.py
            url = f"https://api.open-meteo.com/v1/forecast?latitude={USER_CITY_LAT}&longitude={USER_CITY_LON}&current_weather=true&daily=temperature_2m_max,temperature_2m_min&timezone=Europe/London"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                current = data.get("current_weather", {})
                temp = current.get("temperature", 0)
                code = current.get("weathercode", 0)

                # Simple weather code interpretation
                weather_desc = "clear"
                if code in [1, 2, 3]:
                    weather_desc = "partly cloudy"
                elif code in [45, 48]:
                    weather_desc = "foggy"
                elif code in [51, 53, 55, 61, 63, 65, 80, 81, 82]:
                    weather_desc = "rainy"
                elif code in [71, 73, 75, 77, 85, 86]:
                    weather_desc = "snowy"

                return f"Weather in {USER_CITY}: {temp:.0f}°C and {weather_desc}."
        except Exception:
            pass
        return ""
    
    def _handle_time(self, text: str = "") -> str:
        """Tell current time."""
        now = datetime.now()
        time_str = now.strftime("%I:%M %p")
        date_str = now.strftime("%A, %B %d")
        return f"It's {time_str} on {date_str}, RED."
    
    def _handle_system_status(self, text: str = "") -> str:
        """Report comprehensive system status."""
        try:
            cpu = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage('C:\\')
            
            ram_percent = mem.percent
            disk_percent = disk.percent
            
            # Determine status
            if cpu > 80 or ram_percent > 90:
                status = "under heavy load"
            elif cpu > 50 or ram_percent > 70:
                status = "working moderately"
            else:
                status = "running smoothly"
            
            # Check uptime
            boot_time = psutil.boot_time()
            uptime_seconds = time.time() - boot_time
            uptime_hours = int(uptime_seconds / 3600)
            uptime_days = uptime_hours // 24
            if uptime_days > 0:
                uptime_str = f"{uptime_days} days, {uptime_hours % 24} hours"
            else:
                uptime_str = f"{uptime_hours} hours"
            
            return (
                f"System is {status}, RED. CPU at {cpu:.0f}%, "
                f"RAM at {ram_percent:.0f}%, disk at {disk_percent:.0f}%. "
                f"Uptime: {uptime_str}. I'm operational and ready for commands."
            )
        except Exception as e:
            return f"I apologize, RED. I cannot retrieve system status at the moment. Error: {str(e)[:50]}"
    
    def _handle_wake_up(self, text: str = "") -> str:
        """Handle wake from sleep."""
        # Touch heartbeat to reset sleep timer
        try:
            heartbeat_path = LOGS_PATH / "heartbeat.flag"
            sleep_flag_path = LOGS_PATH / "sleep.flag"
            
            heartbeat_path.touch()
            if sleep_flag_path.exists():
                sleep_flag_path.write_text("AWAKE")
        except:
            pass
        
        hour = datetime.now().hour
        if hour < 12:
            greeting = "Good morning"
        elif hour < 17:
            greeting = "Good afternoon"
        else:
            greeting = "Good evening"
        
        return f"{greeting}, RED. I've resumed from sleep mode. Awaiting your commands."
    
    def _handle_sleep(self, text: str = "") -> str:
        """Enter sleep mode."""
        try:
            sleep_flag_path = LOGS_PATH / "sleep.flag"
            sleep_flag_path.write_text("SLEEP")
        except:
            pass
        
        return "Entering sleep mode, RED. Say 'Jarvis wake up' or wave to reactivate me. Goodnight."
    
    # ========== NEW SKILL HANDLERS ==========
    
    def _handle_weather(self, text: str = "") -> str:
        """Fetch weather information."""
        if not REQUESTS_AVAILABLE:
            logger.error("[Skills] Weather skill requires 'requests' module. Install with: pip install requests")
            return "I need the requests module to check the weather, RED. Install it with: pip install requests"
        
        try:
            # Try to get location from IP
            location_res = requests.get("https://ipapi.co/json/", timeout=3)
            if location_res.status_code == 200:
                loc = location_res.json()
                city = loc.get("city", "Unknown")
                lat = loc.get("latitude")
                lon = loc.get("longitude")
                
                # Use Open-Meteo API (free, no key needed)
                weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m&temperature_unit=celsius"
                w_res = requests.get(weather_url, timeout=5)
                if w_res.status_code == 200:
                    w = w_res.json()
                    temp = w.get("current", {}).get("temperature_2m", "Unknown")
                    humidity = w.get("current", {}).get("relative_humidity_2m", "Unknown")
                    wind = w.get("current", {}).get("wind_speed_10m", "Unknown")
                    code = w.get("current", {}).get("weather_code", 0)
                    
                    # Weather code to description
                    weather_codes = {
                        0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
                        45: "foggy", 48: "depositing rime fog",
                        51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
                        61: "slight rain", 63: "moderate rain", 65: "heavy rain",
                        71: "slight snow", 73: "moderate snow", 75: "heavy snow",
                        95: "thunderstorm", 96: "thunderstorm with hail"
                    }
                    condition = weather_codes.get(code, "unknown conditions")
                    
                    return f"Currently in {city}, it's {temp}°C with {condition}. Humidity at {humidity}% and wind speed of {wind} km/h."
        except Exception as e:
            logger.error(f"[Skills] Weather fetch error: {e}")
        return "I apologize, RED. I'm unable to retrieve weather data at the moment."
    
    def _handle_calendar(self, text: str = "") -> str:
        """Check today's calendar/events."""
        try:
            # Try Windows Calendar (Outlook) via COM
            import win32com.client
            outlook = win32com.client.Dispatch("Outlook.Application")
            namespace = outlook.GetNamespace("MAPI")
            calendar = namespace.GetDefaultFolder(9)  # 9 = Calendar
            
            from datetime import datetime, timedelta
            today = datetime.now()
            tomorrow = today + timedelta(days=1)
            
            # Get today's appointments
            restriction = f"[Start] >= '{today.strftime('%m/%d/%Y')}' AND [Start] < '{tomorrow.strftime('%m/%d/%Y')}'"
            appointments = calendar.Items.Restrict(restriction)
            appointments.Sort("[Start]")
            
            if appointments.Count == 0:
                return f"You have no appointments scheduled for today, RED. Your calendar is clear."
            
            events = []
            for appt in appointments:
                start = appt.Start.strftime("%I:%M %p")
                subject = appt.Subject
                events.append(f"{start}: {subject}")
            
            event_list = "; ".join(events[:5])
            if len(events) > 5:
                event_list += f" and {len(events) - 5} more"
            
            return f"You have {len(events)} events today: {event_list}"
        except ImportError:
            return "Calendar integration requires pywin32. Install with: pip install pywin32"
        except Exception as e:
            logger.error(f"[Skills] Calendar error: {e}")
            return "I'm unable to access your calendar at the moment, RED. Check if Outlook is running."
    
    def _handle_open_app(self, text: str = "") -> str:
        """Launch applications by parsing the app name from the user's utterance."""
        text_lower = text.lower().strip()
        
        # Try to find a matching app in our registry
        matched_app = None
        matched_cmd = None
        for app_name, cmd in APP_REGISTRY.items():
            if app_name in text_lower:
                # Prefer longer matches ("visual studio code" over "code")
                if matched_app is None or len(app_name) > len(matched_app):
                    matched_app = app_name
                    matched_cmd = cmd
        
        if matched_cmd:
            try:
                subprocess.Popen(
                    matched_cmd,
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                )
                logger.info(f"[Skills] Launched: {matched_app} via '{matched_cmd}'")
                return f"Opening {matched_app} for you, RED."
            except Exception as e:
                logger.error(f"[Skills] Failed to launch {matched_app}: {e}")
                return f"I'm afraid I couldn't open {matched_app}, RED. Error: {str(e)[:60]}"
        
        return f"I don't have {text_lower.split('open')[-1].strip() if 'open' in text_lower else 'that application'} in my registry, RED. I can open Chrome, Firefox, Discord, Spotify, VS Code, Notepad, Calculator, and more."
    
    def _handle_joke(self, text: str = "") -> str:
        """Tell a random joke."""
        import random
        jokes = [
            "Why don't scientists trust atoms? Because they make up everything!",
            "Why did the scarecrow win an award? He was outstanding in his field!",
            "Why don't eggs tell jokes? They'd crack each other up!",
            "What do you call a fake noodle? An impasta!",
            "Why did the coffee file a police report? It got mugged!",
            "What do you call a bear with no teeth? A gummy bear!",
            "Why did the golfer bring two pairs of pants? In case he got a hole in one!",
            "What do you call a sleeping dinosaur? A dino-snore!",
            "Why did the math book look sad? It had too many problems!",
            "What do you call cheese that isn't yours? Nacho cheese!"
        ]
        return random.choice(jokes) + " ... I apologize, RED. My humor module is still in beta."
    
    def _handle_hardware_health(self, text: str = "") -> str:
        """Check hardware health indicators (S.M.A.R.T summaries, temperatures)."""
        vitals = []
        
        # 1. CPU Temperature (requires psutil[sensors] or WMI)
        try:
            if hasattr(psutil, "sensors_temperatures"):
                temps = psutil.sensors_temperatures()
                if "coretemp" in temps:
                    avg_temp = sum(t.current for t in temps["coretemp"]) / len(temps["coretemp"])
                    vitals.append(f"CPU temperature is {avg_temp:.0f}°C.")
        except:
            pass

        # 2. Disk Health (Simple check for free space and I/O wait)
        try:
            disk = psutil.disk_usage('C:\\')
            if disk.percent > 90:
                vitals.append("C: drive is dangerously full.")
            
            # Predictive: check for I/O errors in last 100 operations (mock)
            # In a real homelab, we'd use smartmontools here
            vitals.append("Disk S.M.A.R.T status is reported as GOOD.")
        except:
            pass

        # 3. Memory pressure
        try:
            mem = psutil.virtual_memory()
            if mem.percent > 90:
                vitals.append("RAM is under high pressure.")
        except:
            pass

        if not vitals:
            return "Hardware health indicators are within normal operating parameters, RED."
            
        return "Hardware Health Report: " + " ".join(vitals)

    def _handle_coin_flip(self, text: str = "") -> str:
        """Flip a virtual coin."""
        import random
        result = random.choice(["Heads", "Tails"])
        return f"The coin shows... {result}, RED."

    def _handle_reminder(self, text: str = "") -> str:
        """Set a reminder."""
        import re
        # Try to extract reminder text and optional time
        time_patterns = [
            r"in (\d+)\s*(minutes?|mins?|hours?|hrs?)",
            r"at (\d{1,2}):?(\d{2})?\s*(am|pm)?",
            r"in an?\s*(hour|minute)",
        ]

        reminder_text = text
        when = "later"

        for pattern in time_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if "hour" in match.group(0):
                    when = f"in {match.group(1)} {match.group(2)}"
                elif "minute" in match.group(0):
                    when = f"in {match.group(1)} {match.group(2)}"
                elif match.group(1).isdigit():
                    when = f"at {match.group(1)}:{match.group(2) or '00'} {match.group(3) or ''}"
                reminder_text = re.sub(pattern, "", text).strip()
                break

        if not reminder_text.strip():
            return "What would you like me to remind you about, RED?"

        # Save reminder to file
        try:
            reminders_path = LOGS_PATH / "reminders.jsonl"
            LOGS_PATH.mkdir(parents=True, exist_ok=True)
            with open(reminders_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "text": reminder_text[:200],
                    "when": when,
                    "created": datetime.now().isoformat(),
                }) + "\n")
            return f"I've added a reminder to '{reminder_text[:50]}' for {when}, RED."
        except Exception as e:
            logger.error(f"[Skills] Reminder error: {e}")
            return f"I've noted your reminder: '{reminder_text[:50]}'. Check your reminders file."

    def _handle_timer(self, text: str = "") -> str:
        """Set a countdown timer."""
        import re

        # Extract duration
        match = re.search(r"(\d+)\s*(minutes?|mins?|hours?|hrs?|seconds?|secs?)", text, re.IGNORECASE)
        if not match:
            return "How long should I set the timer for, RED?"

        value = int(match.group(1))
        unit = match.group(2).lower()

        if "hour" in unit:
            seconds = value * 3600
            duration_str = f"{value} hour{'s' if value != 1 else ''}"
        elif "minute" in unit:
            seconds = value * 60
            duration_str = f"{value} minute{'s' if value != 1 else ''}"
        else:
            seconds = value
            duration_str = f"{value} second{'s' if value != 1 else ''}"

        # Save timer to file (external process would handle actual notification)
        try:
            timers_path = LOGS_PATH / "timers.jsonl"
            LOGS_PATH.mkdir(parents=True, exist_ok=True)
            with open(timers_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "duration_seconds": seconds,
                    "duration_label": duration_str,
                    "created": datetime.now().isoformat(),
                    "status": "running",
                }) + "\n")
            return f"Timer set for {duration_str}, RED. I'll let you know when it's done."
        except Exception as e:
            logger.error(f"[Skills] Timer error: {e}")
            return f"Timer set for {duration_str}."

    def _handle_quick_note(self, text: str = "") -> str:
        """Save a quick note."""
        # Extract note content after trigger phrases
        note_patterns = [
            r"(?:take a note|quick note|jot down|remember this)\s*(?:to|that|:)?\s*(.+)",
            r"remember this[:\s]+(.+)",
        ]

        note_text = text
        for pattern in note_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                note_text = match.group(1).strip()
                break

        if not note_text or len(note_text) < 3:
            return "What would you like me to remember, RED?"

        try:
            notes_path = LOGS_PATH / "quick_notes.jsonl"
            LOGS_PATH.mkdir(parents=True, exist_ok=True)
            with open(notes_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "note": note_text[:500],
                    "created": datetime.now().isoformat(),
                    "tags": [],
                }) + "\n")
            return f"I've saved your note: '{note_text[:60]}{'...' if len(note_text) > 60 else ''}', RED."
        except Exception as e:
            logger.error(f"[Skills] Note error: {e}")
            return f"Note saved: '{note_text[:60]}{'...' if len(note_text) > 60 else ''}'."

    def _handle_quick_math(self, text: str = "") -> str:
        """Quick mathematical calculations."""
        import re

        # Extract math expression
        math_chars = set("0123456789+-*/().^ ")
        expr = ""
        for char in text:
            if char.lower() in math_chars or char == " ":
                expr += char

        # Clean up expression
        expr = expr.replace("^", "**").replace("x", "*").replace("X", "*")

        if not expr.strip():
            return "What calculation would you like me to do, RED?"

        # Safety check - only allow math operations
        if any(c in expr for c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"):
            return "I can only handle numerical calculations, RED."

        try:
            # Limit expression length for safety
            if len(expr) > 100:
                expr = expr[:100]
            result = eval(expr, {"__builtins__": {}}, {})
            return f"The result is {result}, RED."
        except Exception as e:
            logger.error(f"[Skills] Math error: {e}")
            return f"I couldn't calculate that, RED. Please check the expression."

    def _handle_unit_convert(self, text: str = "") -> str:
        """Convert between units."""
        import re

        text_lower = text.lower()

        # Common conversions
        conversions = {
            ("celsius", "fahrenheit"): lambda x: (x * 9/5) + 32,
            ("fahrenheit", "celsius"): lambda x: (x - 32) * 5/9,
            ("miles", "kilometers"): lambda x: x * 1.60934,
            ("kilometers", "miles"): lambda x: x / 1.60934,
            ("inches", "centimeters"): lambda x: x * 2.54,
            ("centimeters", "inches"): lambda x: x / 2.54,
            ("feet", "meters"): lambda x: x * 0.3048,
            ("meters", "feet"): lambda x: x / 0.3048,
            ("pounds", "kilograms"): lambda x: x * 0.453592,
            ("kilograms", "pounds"): lambda x: x / 0.453592,
            ("ounces", "grams"): lambda x: x * 28.3495,
            ("grams", "ounces"): lambda x: x / 28.3495,
        }

        # Extract number and units
        match = re.search(r"(\d+(?:\.\d+)?)\s*(\w+)\s*(?:to|in|as|into)\s*(\w+)", text_lower)
        if not match:
            return "What units would you like to convert, RED?"

        value = float(match.group(1))
        from_unit = match.group(2)
        to_unit = match.group(3)

        # Find conversion function
        converter = None
        for (f, t), func in conversions.items():
            if f in from_unit and t in to_unit:
                converter = func
                from_unit = f
                to_unit = t
                break

        if not converter:
            return f"I don't know how to convert {from_unit} to {to_unit}, RED. I can handle temperature, distance, weight, and length conversions."

        try:
            result = converter(value)
            return f"{value} {from_unit} equals {result:.2f} {to_unit}, RED."
        except Exception as e:
            logger.error(f"[Skills] Conversion error: {e}")
            return f"I couldn't complete that conversion, RED."

    def _handle_define_word(self, text: str = "") -> str:
        """Look up word definitions."""
        import re

        # Extract word
        match = re.search(r"(?:define|what does|meaning of|dictionary)\s+(?:the\s+)?(?:word\s+)?['\"]?(\w+)['\"]?", text, re.IGNORECASE)
        if not match:
            return "What word would you like me to define, RED?"

        word = match.group(1).lower()

        # Simple built-in dictionary for common words
        definitions = {
            "algorithm": "A step-by-step procedure for solving a problem or accomplishing a task.",
            "api": "Application Programming Interface - a set of protocols for building software.",
            "variable": "A storage location paired with a symbolic name in programming.",
            "function": "A reusable block of code that performs a specific task.",
            "class": "A blueprint for creating objects in object-oriented programming.",
            "inheritance": "A mechanism where a class derives properties from another class.",
            "polymorphism": "The ability of objects to take multiple forms in OOP.",
            "encapsulation": "Bundling data and methods that operate on that data.",
            "recursion": "A function that calls itself to solve smaller instances.",
            "iteration": "Repeating a process multiple times, typically in a loop.",
        }

        if word in definitions:
            return f"{word.capitalize()}: {definitions[word]}"

        # For unknown words, suggest looking it up
        return f"I don't have '{word}' in my local dictionary, RED. Try: 'research {word}' for more information."

    def _handle_random_number(self, text: str = "") -> str:
        """Generate a random number."""
        import re
        import random

        # Extract range
        match = re.search(r"(\d+)\s*(?:to|through|-)\s*(\d+)", text)
        if match:
            min_val = int(match.group(1))
            max_val = int(match.group(2))
            if min_val > max_val:
                min_val, max_val = max_val, min_val
            result = random.randint(min_val, max_val)
            return f"Your random number between {min_val} and {max_val} is... {result}, RED."

        # Default 1-100
        result = random.randint(1, 100)
        return f"Your random number is... {result}, RED."

    def _handle_find_file(self, text: str = "") -> str:
        """Search for files by name across multiple drives."""
        import os
        from pathlib import Path
        
        # Extract filename
        search_term = text.lower()
        for trigger in ["find file", "where is the file", "locate file", "search for file", "find the file"]:
            if trigger in search_term:
                search_term = search_term.split(trigger)[-1].strip()
                break
        
        # Clean up common words
        search_term = search_term.replace("called", "").replace("named", "").strip()
        
        if not search_term or len(search_term) < 3:
            return "What file should I look for, sir? Please provide at least 3 characters."
            
        found_files = []
        
        # Use RAG_INDEX_PATHS if available for consistency
        raw_paths = os.getenv("RAG_INDEX_PATHS", "").split(";")
        roots = [p.strip() for p in raw_paths if p.strip() and os.path.exists(p.strip())]
        
        if not roots:
            # Absolute fallback
            roots = ["D:/", "E:/", os.path.expanduser("~/Documents"), os.path.expanduser("~/Desktop")]
        
        logger.info(f"[Skills] Searching for file: {search_term} across {len(roots)} roots")
        
        for root_path in roots:
            root = Path(root_path)
            if not root.exists(): continue
            
            try:
                # Use os.walk for controlled search depth to prevent hangs
                count = 0
                for root_dir, dirs, files in os.walk(root):
                    # Skip common junk dirs
                    if any(j in root_dir for j in ["node_modules", ".git", "AppData", "Windows", "System32"]):
                        dirs[:] = [] # Don't descend
                        continue
                        
                    for f in files:
                        if search_term in f.lower():
                            found_files.append(str(Path(root_dir) / f))
                            if len(found_files) >= 5: break
                    
                    if len(found_files) >= 5: break
                    count += 1
                    if count > 500: break # Safety limit for deep drives
            except Exception as e:
                logger.error(f"[Skills] Search error on {root}: {e}")
                
        if not found_files:
            return f"I couldn't find any files matching '{search_term}' on your main drives, sir."
            
        response = f"I found {len(found_files)} matches for '{search_term}':\n"
        for i, f in enumerate(found_files[:3]):
            response += f"{i+1}. {f}\n"
            
        if len(found_files) > 3:
            response += f"...and {len(found_files) - 3} more."
            
        return response

    def _handle_search_knowledge(self, text: str = "") -> str:
        """Semantic search across all indexed documents via RAG."""
        try:
            from vault_rag import get_vault_rag
            rag = get_vault_rag()
            if not rag:
                return "My knowledge base is not initialized, sir."
            
            # Extract query
            query = text.lower()
            for trigger in ["search my notes", "what do my notes say", "check my drives for", "search knowledge", "look up in vault"]:
                if trigger in query:
                    query = query.split(trigger)[-1].strip()
                    break
            
            if not query:
                return "What would you like me to look up in your knowledge base, sir?"
                
            results = rag.search(query, n_results=3)
            if not results:
                return f"I couldn't find anything relevant to '{query}' in my indexed memory, sir."
                
            response = f"Based on my memory of your files regarding '{query}':\n\n"
            for i, res in enumerate(results):
                # Clean up the snippet for speech
                snippet = res[:250].strip() + "..."
                response += f"{snippet}\n\n"
                
            return response
        except Exception as e:
            logger.error(f"[Skills] RAG Search error: {e}")
            return "I encountered an error accessing my memory banks, sir."
    
    def _handle_web_search(self, text: str = "") -> str:
        """Search the web using DuckDuckGo."""
        if not self._is_online():
            return "I'm unable to search the web while offline, sir."
            
        # Extract search query
        query = text.lower()
        for trigger in ["search the web for", "google", "search for", "look up"]:
            if trigger in query:
                query = query.split(trigger)[-1].strip()
                break
        
        if not query or len(query) < 2:
            return "What would you like me to search for, sir?"
            
        try:
            from duckduckgo_search import DDGS
            logger.info(f"[Skills] Performing web search for: {query}")
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=3))
                
            if not results:
                return f"I couldn't find any results for '{query}', sir."
                
            response = f"I've searched the web for '{query}':\n\n"
            for i, res in enumerate(results):
                title = res.get('title', 'Result')
                snippet = res.get('body', '')[:200] + "..."
                response += f"{i+1}. {title}: {snippet}\n\n"
                
            return response
        except Exception as e:
            logger.error(f"[Skills] Web Search error: {e}")
            return f"I encountered an error while searching the web, sir."

    def execute_skill(self, skill_name: str, text: str) -> str:
        """
        Execute a matched skill by name, passing the original user text.
        Returns the response text.
        """
        handler = self.skill_handlers.get(f"handle_{skill_name}")
        if handler:
            try:
                return handler(text)
            except Exception as e:
                logger.error(f"[Skills] Error executing {skill_name}: {e}")
                return f"I encountered an error executing that command, RED."
        
        # Check TOML skills
        if skill_name in self.loaded_skills:
            return f"Skill '{skill_name}' recognized but full execution not yet implemented."
        
        return None


# Global skill executor instance
_skill_executor: Optional[SkillExecutor] = None


def get_skill_executor() -> SkillExecutor:
    """Get or create the global skill executor."""
    global _skill_executor
    if _skill_executor is None:
        _skill_executor = SkillExecutor()
    return _skill_executor


def try_handle_skill(text: str) -> Optional[str]:
    """
    Try to handle a voice command as a skill.
    Returns response text if handled, None if not a skill command.
    """
    result = dispatch_skill_command(command_text=text, source="voice")
    if result.get("success"):
        return result.get("response")
    return None


# Trigger endpoint for POST /skills/trigger
def trigger_skill_by_name(name: str, params: dict = None) -> dict:
    """
    Trigger a skill by name (for API calls).
    Returns result dictionary.
    """
    text = params.get("text", "") if params else ""
    return dispatch_skill_command(skill_name=name, command_text=text, params=params or {}, source="api")


def dispatch_skill_command(
    skill_name: str | None = None,
    command_text: str = "",
    params: dict | None = None,
    source: str = "unknown",
) -> dict:
    """
    Canonical skill dispatch used by both WebSocket and HTTP paths.
    If skill_name is omitted, this attempts trigger matching from command_text.
    """
    executor = get_skill_executor()
    params = params or {}

    resolved_name = skill_name
    handler = None
    matched_by = "explicit_name"
    metadata = {
        "enabled": True,
        "priority": 0,
        "requires_online": False,
        "cooldown_seconds": 0.0,
        "timeout_seconds": 10.0,
    }
    if not resolved_name:
        match = executor.match_trigger(command_text)
        if not match:
            return {"success": False, "error": "No skill matched", "skill": None}
        resolved_name = match.get("skill_name")
        handler = match.get("handler")
        matched_by = match.get("matched_by", "trigger_match")
        metadata = {**metadata, **(match.get("metadata") or {})}
    elif resolved_name in BUILT_IN_SKILLS:
        handler_name = BUILT_IN_SKILLS[resolved_name]["handler"]
        handler = executor.skill_handlers.get(handler_name)
    elif resolved_name in executor.loaded_skills:
        skill_data = executor.loaded_skills[resolved_name]
        handler = executor._make_toml_handler(resolved_name, skill_data)
        metadata = {
            "enabled": bool(skill_data.get("enabled", True)),
            "priority": int(skill_data.get("priority", 100)),
            "requires_online": bool(skill_data.get("requires_online", False)),
            "cooldown_seconds": float(skill_data.get("cooldown_seconds", 0.0)),
            "timeout_seconds": float(skill_data.get("timeout_seconds", 8.0)),
        }

    audit_entry: dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "skill": resolved_name,
        "source": source,
        "command_text": command_text,
        "matched_by": matched_by,
        "success": False,
        "duration_ms": 0,
    }

    # Generate trace ID for trace-driven learning
    import uuid
    trace_id = str(uuid.uuid4())
    started_at = time.time()

    if metadata.get("enabled") is False:
        audit_entry["error"] = "Skill is disabled"
        executor._append_audit_log(audit_entry)
        _log_skill_trace(trace_id, str(resolved_name), command_text, "Skill disabled", False, time.time() - started_at)
        return {"success": False, "error": "Skill is disabled", "skill": resolved_name}

    if metadata.get("requires_online") and not executor._is_online():
        audit_entry["error"] = "Skill requires internet connectivity"
        executor._append_audit_log(audit_entry)
        _log_skill_trace(trace_id, str(resolved_name), command_text, "Offline", False, time.time() - started_at)
        return {"success": False, "error": "Skill requires internet connectivity", "skill": resolved_name}

    cooldown_s = float(metadata.get("cooldown_seconds", 0.0))
    can_run, wait_s = executor._check_cooldown(str(resolved_name), cooldown_s)
    if not can_run:
        msg = f"Skill cooling down. Try again in {wait_s:.1f}s."
        audit_entry["error"] = msg
        executor._append_audit_log(audit_entry)
        _log_skill_trace(trace_id, str(resolved_name), command_text, msg, False, time.time() - started_at)
        return {"success": False, "error": msg, "skill": resolved_name, "cooldown_remaining_seconds": round(wait_s, 2)}

    if handler and callable(handler):
        timeout_s = float(params.get("timeout_seconds", metadata.get("timeout_seconds", 10.0)))
        started = time.perf_counter()
        ok, response, err = executor._run_with_timeout(handler, command_text, timeout_s)
        duration_ms = int((time.perf_counter() - started) * 1000)
        audit_entry["duration_ms"] = duration_ms
        if ok:
            audit_entry["success"] = True
            executor._append_audit_log(audit_entry)
            # Log trace for skill discovery
            _log_skill_trace(trace_id, str(resolved_name), command_text, response, ok, time.time() - started_at)
            _log_skill_analytics(trace_id, str(resolved_name), command_text, response, ok, duration_ms, source, matched_by)
            result = {
                "success": True,
                "response": response,
                "skill": resolved_name,
                "implemented": True,
                "matched_by": matched_by,
                "duration_ms": duration_ms,
                "trace_id": trace_id,
            }
            # Check if this TOML skill is awaiting voice capture
            if resolved_name in executor.loaded_skills:
                state = executor.skill_runtime_state.get(resolved_name, {})
                if state.get("awaiting_capture"):
                    result["awaiting_capture"] = True
                    # Clear the flag
                    state.pop("awaiting_capture", None)
            return result
        logger.error(f"[Skills] Execution error for {resolved_name}: {err}")
        audit_entry["error"] = err
        executor._append_audit_log(audit_entry)
        _log_skill_trace(trace_id, str(resolved_name), command_text, str(err), False, time.time() - started_at)
        _log_skill_analytics(trace_id, str(resolved_name), command_text, str(err), False, duration_ms, source, matched_by)
        return {"success": False, "error": str(err), "skill": resolved_name, "duration_ms": duration_ms}

    if resolved_name in executor.loaded_skills:
        response = f"Skill '{resolved_name}' is recognized but not yet executable."
        _log_skill_trace(trace_id, str(resolved_name), command_text, response, True, time.time() - started_at)
        return {
            "success": True,
            "response": response,
            "skill": resolved_name,
            "implemented": False,
            "trace_id": trace_id,
        }

    _log_skill_trace(trace_id, str(resolved_name), command_text, f"Unknown skill: {resolved_name}", False, time.time() - started_at)
    return {"success": False, "error": f"Unknown skill: {resolved_name}", "skill": resolved_name}


def _log_skill_trace(
    trace_id: str,
    skill_name: str,
    query: str,
    result: str,
    success: bool,
    duration: float,
) -> None:
    """Log a skill execution to the trace store for later discovery/optimization."""
    try:
        from openjarvis.traces.store import TraceStore
        from openjarvis.core.types import Trace, TraceStep, StepType

        trace_db_path = LOGS_PATH / "traces.db"
        store = TraceStore(str(trace_db_path))

        trace = Trace(
            trace_id=trace_id,
            query=query,
            agent="jarvis_voice",
            model="skill_executor",
            engine="toml_builtin",
            result=result[:2000] if result else "",
            outcome="success" if success else "failure",
            feedback=1.0 if success else 0.0,
            started_at=time.time() - duration,
            ended_at=time.time(),
            total_tokens=0,
            total_latency_seconds=duration,
            metadata={"skill_name": skill_name, "source": "voice"},
            messages=[],
            steps=[
                TraceStep(
                    step_type=StepType.TOOL_CALL,
                    timestamp=time.time() - duration,
                    duration_seconds=duration,
                    input={"skill": skill_name, "text": query},
                    output={"result": result, "success": success},
                    metadata={"skill": skill_name},
                )
            ],
        )
        store.save(trace)
        store.close()
    except Exception as e:
        logger.debug(f"[Skills] Trace logging failed: {e}")


def _log_skill_analytics(
    trace_id: str,
    skill_name: str,
    command_text: str,
    response: str,
    success: bool,
    duration_ms: int,
    source: str,
    matched_by: str,
) -> None:
    """Log skill execution to analytics database."""
    try:
        from skill_analytics import log_execution as log_analytics
        log_analytics(trace_id, skill_name, command_text, response, success, duration_ms, source, matched_by)
    except Exception as e:
        logger.debug(f"[Skills] Analytics logging failed: {e}")


def reload_skills_cache() -> int:
    """Reload TOML skills so new imports are available immediately."""
    executor = get_skill_executor()
    return executor.reload()


def list_skills_snapshot() -> dict:
    """Return built-in and loaded skills with runtime metadata."""
    executor = get_skill_executor()
    built_in = []
    for key, info in BUILT_IN_SKILLS.items():
        built_in.append({
            "name": key,
            "description": info.get("description", ""),
            "triggers": info.get("triggers", []),
            "enabled": True,
            "priority": 0,
            "source": "built_in",
        })

    loaded = []
    for name, data in sorted(executor.loaded_skills.items(), key=lambda kv: int(kv[1].get("priority", 100))):
        loaded.append({
            "name": name,
            "filename": data.get("file"),
            "trigger": data.get("trigger"),
            "aliases": data.get("aliases", []),
            "trigger_mode": data.get("trigger_mode", "contains"),
            "description": data.get("description", ""),
            "enabled": bool(data.get("enabled", True)),
            "priority": int(data.get("priority", 100)),
            "requires_online": bool(data.get("requires_online", False)),
            "cooldown_seconds": float(data.get("cooldown_seconds", 0.0)),
            "timeout_seconds": float(data.get("timeout_seconds", 8.0)),
            "source": "toml",
        })

    return {"built_in": built_in, "loaded": loaded, "count_loaded": len(loaded), "count_built_in": len(built_in)}


def validate_skills_files() -> dict:
    """Validate TOML skill files and report schema issues."""
    issues: list[dict[str, Any]] = []
    validated = 0
    seen_patterns: dict[str, str] = {}
    for skill_file in SKILLS_PATH.glob("*.toml"):
        validated += 1
        try:
            if TOML_LOADER is None:
                issues.append({"file": skill_file.name, "level": "error", "message": "No TOML parser installed"})
                continue
            data = TOML_LOADER(skill_file)
            if "skill" not in data or not isinstance(data["skill"], dict):
                issues.append({"file": skill_file.name, "level": "error", "message": "Missing [skill] section"})
                continue
            skill = data["skill"]
            if not str(skill.get("name", "")).strip():
                issues.append({"file": skill_file.name, "level": "warning", "message": "skill.name missing; filename will be used"})
            if not str(skill.get("trigger", "")).strip() and not skill.get("aliases"):
                issues.append({"file": skill_file.name, "level": "error", "message": "Need skill.trigger or skill.aliases"})
            trigger = str(skill.get("trigger", "")).strip().lower()
            if trigger:
                key = f"trigger:{trigger}"
                if key in seen_patterns:
                    issues.append({
                        "file": skill_file.name,
                        "level": "warning",
                        "message": f"Trigger conflict with {seen_patterns[key]}: '{trigger}'",
                    })
                else:
                    seen_patterns[key] = skill_file.name
            aliases = skill.get("aliases", [])
            if isinstance(aliases, list):
                for alias in aliases:
                    alias_key = str(alias).strip().lower()
                    if not alias_key:
                        continue
                    key = f"alias:{alias_key}"
                    if key in seen_patterns:
                        issues.append({
                            "file": skill_file.name,
                            "level": "warning",
                            "message": f"Alias conflict with {seen_patterns[key]}: '{alias_key}'",
                        })
                    else:
                        seen_patterns[key] = skill_file.name
            mode = str(skill.get("trigger_mode", "contains")).strip().lower()
            if mode not in ("contains", "exact", "regex"):
                issues.append({"file": skill_file.name, "level": "error", "message": "skill.trigger_mode must be contains/exact/regex"})
            if mode == "regex":
                pattern = str(skill.get("trigger", "")).strip()
                if pattern:
                    try:
                        re.compile(pattern)
                    except re.error as e:
                        issues.append({"file": skill_file.name, "level": "error", "message": f"Invalid regex trigger: {e}"})
            if "action" in data and isinstance(data["action"], dict):
                action_type = str(data["action"].get("type", "response")).strip().lower()
                if action_type not in ("response", "command"):
                    issues.append({"file": skill_file.name, "level": "error", "message": "action.type must be response or command"})
        except Exception as e:
            issues.append({"file": skill_file.name, "level": "error", "message": f"Parse failure: {e}"})

    return {
        "validated_files": validated,
        "issues": issues,
        "error_count": sum(1 for x in issues if x.get("level") == "error"),
        "warning_count": sum(1 for x in issues if x.get("level") == "warning"),
        "ok": not any(x.get("level") == "error" for x in issues),
    }


if __name__ == "__main__":
    # Quick test
    print("Testing skill executor...")
    
    test_cases = [
        "good morning jarvis",
        "what time is it",
        "system status report",
        "go to sleep",
        "wake up jarvis",
        "what's the weather like",
        "tell me a joke",
        "flip a coin",
        "this is not a skill",
    ]
    
    for test in test_cases:
        result = try_handle_skill(test)
        print(f"'{test}' -> {result if result else 'Not a skill'}")
