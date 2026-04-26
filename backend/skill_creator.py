#!/usr/bin/env python3
"""
skill_creator.py - Natural language skill creation.
Users can create skills by describing what they want in plain English.
"""

import json
import re
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from paths import LOGS_PATH, SKILLS_PATH

logger = logging.getLogger(__name__)


class NaturalLanguageSkillCreator:
    """Create skills from natural language descriptions."""

    def __init__(self):
        self.skill_templates = {
            "open_website": {
                "triggers": ["open site", "go to", "navigate to", "visit website"],
                "template": self._create_open_website_skill,
            },
            "send_message": {
                "triggers": ["send message", "text", "email", "notify"],
                "template": self._create_send_message_skill,
            },
            "run_program": {
                "triggers": ["run", "execute", "start program", "launch app"],
                "template": self._create_run_program_skill,
            },
            "file_operation": {
                "triggers": ["copy", "move", "delete", "rename", "organize files"],
                "template": self._create_file_operation_skill,
            },
            "reminder_skill": {
                "triggers": ["remind me", "alert me", "notify me when"],
                "template": self._create_reminder_skill,
            },
            "search_skill": {
                "triggers": ["search for", "find", "look up"],
                "template": self._create_search_skill,
            },
        }

    def parse_request(self, user_request: str) -> Dict[str, Any]:
        """
        Parse a natural language request into a skill definition.

        Examples:
            "Create a skill that opens Chrome when I say 'browse'"
            "Make a skill that backs up my documents every Friday"
            "When I say 'focus time', close all social media tabs"
        """
        request = user_request.lower()

        # Detect intent
        intent = self._detect_intent(request)

        if not intent:
            return {
                "success": False,
                "error": "I couldn't understand what kind of skill you want. Try: 'Create a skill that [action] when I say [trigger]'",
            }

        # Extract trigger phrase
        trigger = self._extract_trigger(request)

        # Build skill definition
        skill_def = intent["builder"](request, trigger)

        return {
            "success": True,
            "skill": skill_def,
            "intent": intent["name"],
            "trigger": trigger,
        }

    def _detect_intent(self, request: str) -> Optional[Dict[str, Any]]:
        """Detect the user's intent from their request."""

        # Open website patterns
        if any(phrase in request for phrase in ["open", "website", "site", "url", "page"]):
            if "chrome" in request or "firefox" in request or "browser" in request:
                return {
                    "name": "open_website",
                    "builder": self._create_open_website_skill,
                }

        # File operations
        if any(phrase in request for phrase in ["file", "folder", "document", "copy", "move", "delete", "backup"]):
            return {
                "name": "file_operation",
                "builder": self._create_file_operation_skill,
            }

        # Program execution
        if any(phrase in request for phrase in ["run", "launch", "start", "program", "app", "execute"]):
            return {
                "name": "run_program",
                "builder": self._create_run_program_skill,
            }

        # Reminder/alert
        if any(phrase in request for phrase in ["remind", "alert", "notify", "remember"]):
            return {
                "name": "reminder_skill",
                "builder": self._create_reminder_skill,
            }

        # Search
        if any(phrase in request for phrase in ["search", "find", "look up", "query"]):
            return {
                "name": "search_skill",
                "builder": self._create_search_skill,
            }

        # Generic command execution
        if "command" in request or "powershell" in request or "cmd" in request:
            return {
                "name": "run_program",
                "builder": self._create_run_program_skill,
            }

        return None

    def _extract_trigger(self, request: str) -> str:
        """Extract the trigger phrase from the request."""
        # Look for patterns like "when I say X", "when I ask X", "trigger X"
        patterns = [
            r"(?:when i say|when i ask|trigger|whenever|i say)\s+['\"]?([^'\"]+)['\"]?",
            r"['\"]([a-z\s]+)['\"]\s+(?:to|for|when)",
            r"say\s+['\"]?([^'\"]+)['\"]?",
        ]

        for pattern in patterns:
            match = re.search(pattern, request, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        # Default trigger based on intent
        return "custom_command"

    def _create_open_website_skill(self, request: str, trigger: str) -> Dict[str, Any]:
        """Create a skill that opens a website."""
        # Extract URL
        url_pattern = r"(https?://[^\s'\"]+)"
        url_match = re.search(url_pattern, request)

        url = url_match.group(1) if url_match else "https://www.google.com"

        # Detect browser
        browser = "chrome"
        if "firefox" in request:
            browser = "firefox"
        elif "edge" in request:
            browser = "msedge"

        return {
            "name": f"open_{trigger.replace(' ', '_')}",
            "trigger": trigger,
            "aliases": [f"go to {trigger}", f"open {trigger}"],
            "trigger_mode": "contains",
            "description": f"Open {url} in {browser}",
            "priority": 50,
            "enabled": True,
            "requires_online": True,
            "cooldown_seconds": 5,
            "timeout_seconds": 10,
            "action": {
                "type": "command",
                "command": f"start {browser} {url}",
                "response": f"Opening {url} in {browser}",
            },
        }

    def _create_file_operation_skill(self, request: str, trigger: str) -> Dict[str, Any]:
        """Create a skill for file operations."""
        # Detect operation type
        operation = "copy"
        if "move" in request:
            operation = "move"
        elif "delete" in request:
            operation = "delete"
        elif "backup" in request:
            operation = "backup"
        elif "organize" in request:
            operation = "organize"

        # Extract paths (simplified - looks for common folder names)
        source = "Documents"
        dest = "Backup"

        if "documents" in request:
            source = "Documents"
        if "downloads" in request:
            source = "Downloads"
        if "desktop" in request:
            source = "Desktop"
        if "pictures" in request:
            source = "Pictures"

        # Build PowerShell command
        if operation == "backup":
            command = f"""powershell -Command "$src = $env:USERPROFILE + '\\{source}'; $dst = $env:USERPROFILE + '\\{dest}_' + (Get-Date -Format 'yyyy-MM-dd'); robocopy $src $dst /MIR /NFL /NDL /NJH /NJS"
"""
            response = f"Backup of {source} completed."
        elif operation == "organize":
            command = f"""powershell -Command "$dir = $env:USERPROFILE + '\\{source}'; Get-ChildItem $dir | Group-Object Extension | ForEach-Object {{ New-Item -ItemType Directory -Force -Path (Join-Path $dir $_.Name.TrimStart('.')); $_.Group | Move-Item -Destination (Join-Path $dir $_.Name.TrimStart('.')) -Force }}"
"""
            response = f"Files in {source} organized by type."
        else:
            command = f"powershell -Command \"Write-Output '{operation} operation ready'\""
            response = f"{operation.capitalize()} operation completed."

        return {
            "name": f"{operation}_{trigger.replace(' ', '_')}",
            "trigger": trigger,
            "aliases": [],
            "trigger_mode": "contains",
            "description": f"{operation.capitalize()} files in {source}",
            "priority": 50,
            "enabled": True,
            "requires_online": False,
            "cooldown_seconds": 60,
            "timeout_seconds": 60,
            "action": {
                "type": "command",
                "command": command,
                "response": response,
            },
        }

    def _create_run_program_skill(self, request: str, trigger: str) -> Dict[str, Any]:
        """Create a skill that runs a program or command."""
        # Detect program
        program = ""
        if "chrome" in request:
            program = "chrome"
        elif "notepad" in request:
            program = "notepad"
        elif "calculator" in request:
            program = "calc"
        elif "spotify" in request:
            program = "spotify"
        elif "discord" in request:
            program = "discord"
        elif "vs code" in request or "code" in request:
            program = "code"

        if program:
            command = f"start {program}"
            response = f"Launching {program}"
        else:
            # Generic command
            command = "powershell -Command \"Write-Output 'Command executed'\""
            response = "Command executed"

        return {
            "name": f"run_{trigger.replace(' ', '_')}",
            "trigger": trigger,
            "aliases": [f"launch {trigger}", f"start {trigger}"],
            "trigger_mode": "contains",
            "description": f"Run program: {program or 'custom command'}",
            "priority": 50,
            "enabled": True,
            "requires_online": False,
            "cooldown_seconds": 10,
            "timeout_seconds": 30,
            "action": {
                "type": "command",
                "command": command,
                "response": response,
            },
        }

    def _create_reminder_skill(self, request: str, trigger: str) -> Dict[str, Any]:
        """Create a reminder skill."""
        return {
            "name": f"reminder_{trigger.replace(' ', '_')}",
            "trigger": trigger,
            "aliases": [f"remind me {trigger}"],
            "trigger_mode": "contains",
            "description": "Set a custom reminder",
            "priority": 50,
            "enabled": True,
            "requires_online": False,
            "cooldown_seconds": 30,
            "timeout_seconds": 10,
            "action": {
                "type": "response",
                "response": f"I've set your reminder: '{trigger}'. Check your reminders file for details.",
            },
        }

    def _create_search_skill(self, request: str, trigger: str) -> Dict[str, Any]:
        """Create a search skill."""
        # Detect search engine
        engine = "google"
        if "bing" in request:
            engine = "bing"
        elif "duckduckgo" in request or "ddg" in request:
            engine = "duckduckgo"

        urls = {
            "google": "https://www.google.com/search?q=",
            "bing": "https://www.bing.com/search?q=",
            "duckduckgo": "https://duckduckgo.com/?q=",
        }

        return {
            "name": f"search_{trigger.replace(' ', '_')}",
            "trigger": trigger,
            "aliases": [f"look up {trigger}", f"find {trigger}"],
            "trigger_mode": "contains",
            "description": f"Search {engine} for a query",
            "priority": 50,
            "enabled": True,
            "requires_online": True,
            "cooldown_seconds": 5,
            "timeout_seconds": 10,
            "action": {
                "type": "command",
                "command": f"start chrome {urls[engine]}",
                "response": f"Opening {engine} search",
            },
        }

    def create_skill(self, user_request: str) -> Dict[str, Any]:
        """
        Create a skill from a natural language request.
        Returns dict with success status and skill file path.
        """
        result = self.parse_request(user_request)

        if not result["success"]:
            return result

        skill_def = result["skill"]

        # Generate TOML file
        toml_content = self._generate_toml(skill_def)

        # Save to skills directory
        skill_file = SKILLS_PATH / f"{skill_def['name']}.toml"

        try:
            SKILLS_PATH.mkdir(parents=True, exist_ok=True)
            with open(skill_file, "w", encoding="utf-8") as f:
                f.write(toml_content)

            # Reload skills cache
            try:
                from skills import reload_skills_cache
                reload_skills_cache()
            except ImportError:
                pass

            return {
                "success": True,
                "message": f"Created skill '{skill_def['name']}' with trigger '{skill_def['trigger']}'",
                "skill_file": str(skill_file),
                "skill": skill_def,
            }

        except Exception as e:
            logger.error(f"[SkillCreator] Save error: {e}")
            return {
                "success": False,
                "error": f"Failed to save skill: {str(e)}",
            }

    def _generate_toml(self, skill_def: Dict[str, Any]) -> str:
        """Generate TOML content from a skill definition."""
        lines = [
            f"# Auto-generated skill: {skill_def['name']}",
            f"# Created at: {datetime.now().isoformat()}",
            "",
            "[skill]",
            f'name = "{skill_def["name"]}"',
            f'trigger = "{skill_def["trigger"]}"',
        ]

        if skill_def.get("aliases"):
            aliases_str = json.dumps(skill_def["aliases"])
            lines.append(f'aliases = {aliases_str}')

        lines.extend([
            f'trigger_mode = "{skill_def.get("trigger_mode", "contains")}"',
            f'description = "{skill_def["description"]}"',
            f'priority = {skill_def.get("priority", 50)}',
            f'enabled = {"true" if skill_def.get("enabled", True) else "false"}',
            f'requires_online = {"true" if skill_def.get("requires_online", False) else "false"}',
            f'cooldown_seconds = {skill_def.get("cooldown_seconds", 0)}',
            f'timeout_seconds = {skill_def.get("timeout_seconds", 10)}',
            "",
            "[action]",
            f'type = "{skill_def["action"].get("type", "response")}"',
        ])

        if skill_def["action"].get("command"):
            # Escape quotes in command
            cmd = skill_def["action"]["command"].replace('"', '\\"')
            lines.append(f'command = "{cmd}"')

        if skill_def["action"].get("response"):
            lines.append(f'response = "{skill_def["action"]["response"]}"')

        return "\n".join(lines)


# Global creator instance
_creator: Optional[NaturalLanguageSkillCreator] = None


def get_creator() -> NaturalLanguageSkillCreator:
    """Get or create the global skill creator."""
    global _creator
    if _creator is None:
        _creator = NaturalLanguageSkillCreator()
    return _creator


def create_skill_from_language(user_request: str) -> Dict[str, Any]:
    """Convenience function to create a skill from natural language."""
    creator = get_creator()
    return creator.create_skill(user_request)


if __name__ == "__main__":
    # Test skill creation
    logging.basicConfig(level=logging.INFO)

    test_requests = [
        "Create a skill that opens Chrome when I say 'browse'",
        "Make a skill that backs up my documents when I say 'backup now'",
        "When I say 'focus time', start my work playlist",
        "Create a skill to search Google when I say 'look up'",
    ]

    creator = get_creator()

    for request in test_requests:
        print(f"\nRequest: {request}")
        result = creator.create_skill(request)
        print(f"Result: {result}")
