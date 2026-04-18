#!/usr/bin/env python3
"""
skills.py - Skill execution system for JARVIS.
Loads TOML skill definitions and handles voice trigger matching.
"""

import json
import logging
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

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
    TOML_LOADER = lambda f: tomllib.load(f)
except ImportError:
    try:
        import toml
        TOML_LOADER = lambda f: toml.load(f)
    except ImportError:
        TOML_LOADER = None

logger = logging.getLogger(__name__)

# Skills directory
SKILLS_PATH = Path(os.getenv("OPERATOR_SKILLS_PATH", "E:/JarvisVault/skills"))

# Built-in skill handlers (voice triggers that don't need TOML files)
BUILT_IN_SKILLS = {
    "good_morning": {
        "triggers": ["good morning", "morning", "good day"],
        "handler": "handle_good_morning",
        "description": "Wish RED good morning and give daily briefing"
    },
    "time": {
        "triggers": ["what time", "what's the time", "current time", "tell me the time"],
        "handler": "handle_time",
        "description": "Tell current time"
    },
    "system_status": {
        "triggers": ["system status", "how's the system", "status report", "how are you doing", "how are you"],
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
        "description": "Enter sleep mode"
    },
    # NEW SKILLS - Phase 1
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
        "triggers": ["open chrome", "launch", "start", "open firefox", "open discord", "open spotify", "open code", "open notepad", "open calculator", "open file explorer"],
        "handler": "handle_open_app",
        "description": "Launch applications by name"
    },
    "web_search": {
        "triggers": ["search for", "google", "look up", "find information about", "search the web for", "what is"],
        "handler": "handle_web_search",
        "description": "Perform quick web search"
    },
    "joke": {
        "triggers": ["tell me a joke", "make me laugh", "say something funny", "got any jokes", "joke"],
        "handler": "handle_joke",
        "description": "Tell a random joke"
    },
    "coin_flip": {
        "triggers": ["flip a coin", "heads or tails", "coin toss", "toss a coin"],
        "handler": "handle_coin_flip",
        "description": "Flip a virtual coin"
    },
    "define": {
        "triggers": ["define", "what does", "mean", "meaning of", "what is the definition of", "dictionary"],
        "handler": "handle_define",
        "description": "Define words using dictionary"
    },
}


class SkillExecutor:
    """Executes built-in skills and manages TOML skill loading."""
    
    def __init__(self):
        self.loaded_skills: dict = {}
        self.skill_handlers: dict = {
            "handle_good_morning": self._handle_good_morning,
            "handle_time": self._handle_time,
            "handle_system_status": self._handle_system_status,
            "handle_wake_up": self._handle_wake_up,
            "handle_sleep": self._handle_sleep,
            # NEW SKILL HANDLERS
            "handle_weather": self._handle_weather,
            "handle_calendar": self._handle_calendar,
            "handle_open_app": self._handle_open_app,
            "handle_web_search": self._handle_web_search,
            "handle_joke": self._handle_joke,
            "handle_coin_flip": self._handle_coin_flip,
            "handle_define": self._handle_define,
        }
        self._load_toml_skills()
    
    def _load_toml_skills(self):
        """Load skill definitions from TOML files."""
        if TOML_LOADER is None:
            logger.warning("[Skills] No TOML parser available (install 'toml' package)")
            return
        
        try:
            SKILLS_PATH.mkdir(parents=True, exist_ok=True)
            for skill_file in SKILLS_PATH.glob("*.toml"):
                try:
                    with open(skill_file, "rb") as f:
                        data = TOML_LOADER(f)
                    
                    if "skill" in data:
                        skill_def = data["skill"]
                        skill_name = skill_def.get("name", skill_file.stem)
                        self.loaded_skills[skill_name] = {
                            "file": skill_file.name,
                            "definition": data,
                            "trigger": skill_def.get("trigger", "").lower(),
                            "description": skill_def.get("description", ""),
                        }
                        logger.info(f"[Skills] Loaded: {skill_name}")
                except Exception as e:
                    logger.error(f"[Skills] Failed to load {skill_file}: {e}")
        except Exception as e:
            logger.error(f"[Skills] Error loading skills: {e}")
    
    def match_trigger(self, text: str) -> Optional[tuple[str, Callable]]:
        """
        Match voice text against skill triggers.
        Returns (skill_name, handler_function) or None if no match.
        """
        text_lower = text.lower().strip()
        
        # Check built-in skills first
        for skill_id, skill_info in BUILT_IN_SKILLS.items():
            for trigger in skill_info["triggers"]:
                if trigger in text_lower:
                    handler_name = skill_info["handler"]
                    return (skill_id, self.skill_handlers.get(handler_name))
        
        # Check TOML-loaded skills
        for skill_name, skill_data in self.loaded_skills.items():
            trigger = skill_data.get("trigger", "")
            if trigger and trigger in text_lower:
                # For now, TOML skills return a placeholder handler
                # Full execution engine can be built later
                return (skill_name, lambda: f"Executing skill: {skill_name}")
        
        return None
    
    def _handle_good_morning(self) -> str:
        """Good morning briefing for RED."""
        hour = datetime.now().hour
        if hour < 12:
            greeting = "Good morning"
        elif hour < 17:
            greeting = "Good afternoon"
        else:
            greeting = "Good evening"
        
        # Get system status
        try:
            cpu = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            ram_gb = round(mem.used / (1024**3), 1)
            ram_total = round(mem.total / (1024**3), 1)
            
            # Check for errors
            from pathlib import Path as P
            db_path = P(os.getenv("OPERATOR_DB_PATH", "C:/Projects/Operator/database/errors.db"))
            error_count = 0
            if db_path.exists():
                import sqlite3
                try:
                    conn = sqlite3.connect(str(db_path), timeout=2.0)
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM errors WHERE fixed = 0 OR fixed IS NULL")
                    error_count = cursor.fetchone()[0]
                    conn.close()
                except:
                    pass
            
            status_msg = f"System is at {cpu:.0f}% CPU, {ram_gb}GB RAM in use."
            if error_count > 0:
                status_msg += f" There are {error_count} unresolved errors."
            else:
                status_msg += " All systems nominal."
            
        except Exception as e:
            status_msg = "System status currently unavailable."
        
        return f"{greeting}, RED. {status_msg} How can I assist you today?"
    
    def _handle_time(self) -> str:
        """Tell current time."""
        now = datetime.now()
        time_str = now.strftime("%I:%M %p")
        date_str = now.strftime("%A, %B %d")
        return f"It's {time_str} on {date_str}, RED."
    
    def _handle_system_status(self) -> str:
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
    
    def _handle_wake_up(self) -> str:
        """Handle wake from sleep."""
        # Touch heartbeat to reset sleep timer
        try:
            logs_path = Path(os.getenv("OPERATOR_LOGS_PATH", "C:/Projects/Operator/logs"))
            heartbeat_path = logs_path / "heartbeat.flag"
            sleep_flag_path = logs_path / "sleep.flag"
            
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
    
    def _handle_sleep(self) -> str:
        """Enter sleep mode."""
        try:
            logs_path = Path(os.getenv("OPERATOR_LOGS_PATH", "C:/Projects/Operator/logs"))
            sleep_flag_path = logs_path / "sleep.flag"
            sleep_flag_path.write_text("SLEEP")
        except:
            pass
        
        return "Entering sleep mode, RED. Say 'Jarvis wake up' or wave to reactivate me. Goodnight."
    
    # ========== NEW SKILL HANDLERS ==========
    
    def _handle_weather(self) -> str:
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
                weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m&temperature_unit=fahrenheit"
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
                    
                    return f"Currently in {city}, it's {temp}°F with {condition}. Humidity at {humidity}% and wind speed of {wind} mph."
        except Exception as e:
            logger.error(f"[Skills] Weather fetch error: {e}")
        return "I apologize, RED. I'm unable to retrieve weather data at the moment."
    
    def _handle_calendar(self) -> str:
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
    
    def _handle_open_app(self) -> str:
        """Launch applications."""
        # This would need the original text to know which app
        # For now return instructions
        return "To open an application, say 'Jarvis, open Chrome' or 'Jarvis, launch Discord'. I can open most common applications."
    
    def _handle_web_search(self) -> str:
        """Perform web search."""
        return "For web searches, I'll use the browser. Say something like 'Jarvis, search for Python tutorials' and I'll find relevant information."
    
    def _handle_joke(self) -> str:
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
    
    def _handle_coin_flip(self) -> str:
        """Flip a virtual coin."""
        import random
        result = random.choice(["Heads", "Tails"])
        return f"The coin shows... {result}, RED."
    
    def _handle_define(self) -> str:
        """Define a word."""
        return "To define a word, say 'Jarvis, define serendipity' or 'Jarvis, what does quantum mean'. I'll fetch the definition."
    
    def execute_skill(self, skill_name: str, text: str) -> str:
        """
        Execute a matched skill by name.
        Returns the response text.
        """
        handler = self.skill_handlers.get(f"handle_{skill_name}")
        if handler:
            try:
                return handler()
            except Exception as e:
                logger.error(f"[Skills] Error executing {skill_name}: {e}")
                return f"I encountered an error executing that command, RED."
        
        # Check TOML skills
        if skill_name in self.loaded_skills:
            # Placeholder for full skill execution engine
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
    executor = get_skill_executor()
    match = executor.match_trigger(text)
    
    if match:
        skill_name, handler = match
        logger.info(f"[Skills] Matched '{text}' to skill: {skill_name}")
        try:
            if callable(handler):
                return handler()
        except Exception as e:
            logger.error(f"[Skills] Execution error: {e}")
            return f"I'm sorry RED, I couldn't complete that action."
    
    return None


# Trigger endpoint for POST /skills/trigger
def trigger_skill_by_name(name: str, params: dict = None) -> dict:
    """
    Trigger a skill by name (for API calls).
    Returns result dictionary.
    """
    executor = get_skill_executor()
    
    # Check if it's a built-in skill
    if name in BUILT_IN_SKILLS:
        handler_name = BUILT_IN_SKILLS[name]["handler"]
        handler = executor.skill_handlers.get(handler_name)
        if handler:
            try:
                result = handler()
                return {"success": True, "response": result, "skill": name}
            except Exception as e:
                return {"success": False, "error": str(e), "skill": name}
    
    # Check TOML skills
    if name in executor.loaded_skills:
        # Placeholder
        return {"success": True, "response": f"Skill '{name}' triggered", "skill": name}
    
    return {"success": False, "error": f"Unknown skill: {name}"}


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
