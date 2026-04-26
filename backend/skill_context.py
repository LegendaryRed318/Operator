#!/usr/bin/env python3
"""
skill_context.py - Context-aware skills that adapt based on situation.
Considers time of day, location, active application, and user state.
"""

import json
import logging
import subprocess
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from paths import LOGS_PATH

logger = logging.getLogger(__name__)

CONTEXT_FILE = LOGS_PATH / "skill_context.json"


class ContextManager:
    """Manage and evaluate context for skill execution."""

    def __init__(self):
        self.context_rules: Dict[str, Any] = {}
        self._current_context: Dict[str, Any] = {}
        self._load_rules()
        self._update_current_context()

    def _load_rules(self):
        """Load context rules from disk."""
        if CONTEXT_FILE.exists():
            try:
                with open(CONTEXT_FILE, "r", encoding="utf-8") as f:
                    self.context_rules = json.load(f)
            except Exception as e:
                logger.error(f"[Context] Load error: {e}")
                self.context_rules = {}

    def _save_rules(self):
        """Save context rules to disk."""
        try:
            LOGS_PATH.mkdir(parents=True, exist_ok=True)
            with open(CONTEXT_FILE, "w", encoding="utf-8") as f:
                json.dump(self.context_rules, f, indent=2)
        except Exception as e:
            logger.error(f"[Context] Save error: {e}")

    def _update_current_context(self):
        """Update the current context state."""
        now = datetime.now()

        self._current_context = {
            "hour": now.hour,
            "day_of_week": now.weekday(),
            "is_weekend": now.weekday() >= 5,
            "is_work_hours": 9 <= now.hour <= 17 and now.weekday() < 5,
            "time_of_day": self._get_time_of_day(now.hour),
            "date": now.strftime("%Y-%m-%d"),
            "active_app": self._get_active_application(),
            "is_online": self._check_online(),
            "location": self._get_location(),
        }

    def _get_time_of_day(self, hour: int) -> str:
        """Get time of day category."""
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 21:
            return "evening"
        else:
            return "night"

    def _get_active_application(self) -> str:
        """Get the currently active application (Windows)."""
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-Command",
                    "Add-Type -AssemblyName Microsoft.VisualBasic; "
                    "[Microsoft.VisualBasic.Interaction]::AppActivate((Get-Process | Where-Object {$_.MainWindowTitle -ne ''} | Select-Object -First 1).Id)"
                ],
                capture_output=True,
                text=True,
                timeout=2,
            )
            # Simplified: just return a generic indicator
            return "unknown"
        except Exception:
            return "unknown"

    def _check_online(self) -> bool:
        """Check if system is online."""
        try:
            import socket
            socket.create_connection(("1.1.1.1", 53), timeout=2)
            return True
        except Exception:
            return False

    def _get_location(self) -> str:
        """Get approximate location (simplified)."""
        # Could be expanded with IP geolocation or GPS
        return "home"  # Default

    def get_context(self) -> Dict[str, Any]:
        """Get the current context."""
        self._update_current_context()
        return dict(self._current_context)

    def add_context_rule(
        self,
        rule_id: str,
        skill_name: str,
        conditions: Dict[str, Any],
        modifications: Dict[str, Any],
    ) -> bool:
        """
        Add a context rule that modifies skill behavior.

        Example:
            {
                "rule_id": "no_music_at_work",
                "skill_name": "play_music",
                "conditions": {"is_work_hours": true},
                "modifications": {"enabled": false, "response": "Music disabled during work hours"}
            }
        """
        self.context_rules[rule_id] = {
            "skill_name": skill_name,
            "conditions": conditions,
            "modifications": modifications,
            "created_at": datetime.now().isoformat(),
        }
        self._save_rules()
        return True

    def remove_context_rule(self, rule_id: str) -> bool:
        """Remove a context rule."""
        if rule_id in self.context_rules:
            del self.context_rules[rule_id]
            self._save_rules()
            return True
        return False

    def evaluate_conditions(self, conditions: Dict[str, Any], context: Optional[Dict] = None) -> bool:
        """Check if all conditions are met."""
        if context is None:
            context = self.get_context()

        for key, expected_value in conditions.items():
            actual_value = context.get(key)

            if isinstance(expected_value, dict):
                # Complex condition (e.g., {"gte": 9, "lte": 17})
                if not self._evaluate_complex_condition(actual_value, expected_value):
                    return False
            elif actual_value != expected_value:
                return False

        return True

    def _evaluate_complex_condition(self, actual: Any, condition: Dict[str, Any]) -> bool:
        """Evaluate a complex condition."""
        if "gte" in condition and actual < condition["gte"]:
            return False
        if "lte" in condition and actual > condition["lte"]:
            return False
        if "gt" in condition and actual <= condition["gt"]:
            return False
        if "lt" in condition and actual >= condition["lt"]:
            return False
        if "in" in condition and actual not in condition["in"]:
            return False
        if "not" in condition and actual == condition["not"]:
            return False
        return True

    def apply_context_to_skill(
        self,
        skill_name: str,
        skill_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Apply context rules to a skill configuration."""
        context = self.get_context()
        modified_config = dict(skill_config)

        for rule_id, rule in self.context_rules.items():
            if rule.get("skill_name") != skill_name:
                continue

            if self.evaluate_conditions(rule.get("conditions", {}), context):
                # Apply modifications
                for key, value in rule.get("modifications", {}).items():
                    modified_config[key] = value

                logger.debug(f"[Context] Applied rule '{rule_id}' to skill '{skill_name}'")

        return modified_config

    def get_contextual_skills(self, available_skills: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter and modify skills based on current context."""
        context = self.get_context()
        contextual_skills = []

        for skill in available_skills:
            modified = self.apply_context_to_skill(skill.get("name", ""), skill)

            # Skip disabled skills
            if not modified.get("enabled", True):
                continue

            # Skip skills that require online when offline
            if modified.get("requires_online", False) and not context.get("is_online"):
                continue

            contextual_skills.append(modified)

        return contextual_skills

    def suggest_skills(
        self,
        available_skills: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Suggest skills that are relevant to the current context."""
        if context is None:
            context = self.get_context()

        suggestions = []
        time_of_day = context.get("time_of_day", "day")
        is_weekend = context.get("is_weekend", False)
        hour = context.get("hour", 12)

        # Time-based suggestions
        if time_of_day == "morning" and 7 <= hour <= 10:
            suggestions.append({"skill": "morning_routine", "reason": "Good morning! Ready for your daily briefing?"})

        if time_of_day == "evening" and 18 <= hour <= 22:
            suggestions.append({"skill": "system_health", "reason": "Evening system check recommended."})

        # Day-based suggestions
        if not is_weekend and hour == 9:
            suggestions.append({"skill": "calendar", "reason": "You have meetings today. Check your schedule?"})

        if is_weekend and time_of_day == "afternoon":
            suggestions.append({"skill": "file_organizer", "reason": "Good day to organize your files."})

        # Context-aware: if online, suggest research
        if context.get("is_online"):
            suggestions.append({"skill": "quick_research", "reason": "Need to look something up?"})

        return suggestions


# Predefined context rules
PREDEFINED_RULES = {
    "no_music_during_work": {
        "skill_name": "play_music",
        "conditions": {"is_work_hours": True},
        "modifications": {"enabled": False, "response": "Music playback disabled during work hours."},
    },
    "quiet_mode_night": {
        "skill_name": "proactive_alert",
        "conditions": {"time_of_day": "night"},
        "modifications": {"enabled": False, "response": "Alerts silenced during night hours."},
    },
    "weekend_backup": {
        "skill_name": "backup_now",
        "conditions": {"is_weekend": True, "hour": {"gte": 10, "lte": 12}},
        "modifications": {"priority": 80},
    },
}


def setup_predefined_rules(manager: Optional[ContextManager] = None) -> None:
    """Set up predefined context rules."""
    if manager is None:
        manager = get_context_manager()

    for rule_id, rule in PREDEFINED_RULES.items():
        if rule_id not in manager.context_rules:
            manager.add_context_rule(
                rule_id,
                rule["skill_name"],
                rule["conditions"],
                rule["modifications"],
            )

    logger.info(f"[Context] {len(PREDEFINED_RULES)} predefined rules configured")


# Global manager instance
_manager: Optional[ContextManager] = None


def get_context_manager() -> ContextManager:
    """Get or create the global context manager."""
    global _manager
    if _manager is None:
        _manager = ContextManager()
    return _manager


def get_current_context() -> Dict[str, Any]:
    """Get the current context."""
    return get_context_manager().get_context()


def apply_context_to_skill(skill_name: str, skill_config: Dict[str, Any]) -> Dict[str, Any]:
    """Apply context rules to a skill."""
    return get_context_manager().apply_context_to_skill(skill_name, skill_config)


def suggest_skills(available_skills: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Get skill suggestions for the current context."""
    return get_context_manager().suggest_skills(available_skills)


if __name__ == "__main__":
    # Test context manager
    logging.basicConfig(level=logging.INFO)

    print("Testing context manager...")

    manager = get_context_manager()
    context = manager.get_context()

    print(f"\nCurrent context:")
    for key, value in context.items():
        print(f"  {key}: {value}")

    # Add a test rule
    manager.add_context_rule(
        "test_rule",
        "test_skill",
        {"is_work_hours": True},
        {"enabled": False},
    )

    print(f"\nContext rules: {list(manager.context_rules.keys())}")

    # Get suggestions
    test_skills = [
        {"name": "morning_routine", "enabled": True},
        {"name": "system_health", "enabled": True},
        {"name": "quick_research", "requires_online": True},
    ]
    suggestions = manager.suggest_skills(test_skills)
    print(f"\nSuggestions: {suggestions}")
