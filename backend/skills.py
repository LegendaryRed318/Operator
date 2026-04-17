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
        "this is not a skill",
    ]
    
    for test in test_cases:
        result = try_handle_skill(test)
        print(f"'{test}' -> {result if result else 'Not a skill'}")
