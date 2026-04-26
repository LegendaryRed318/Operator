#!/usr/bin/env python3
"""
skills_engine.py - Dynamic skill loading and execution system for JARVIS
Loads TOML skill definitions and executes them based on fuzzy trigger matching.
"""

import os
import re
import json
import logging
import difflib
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime

logger = logging.getLogger(__name__)

# Skill registry: name -> skill definition
_skills_registry: Dict[str, Dict] = {}

# Vault path from environment
VAULT_PATH = Path(os.getenv("VAULT_PATH", "E:/JarvisVault"))


def load_skill_from_toml(toml_path: Path) -> Optional[Dict]:
    """Parse a TOML skill file and return skill definition."""
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    
    try:
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        
        skill_def = data.get("skill", {})
        actions = data.get("actions", {})
        triggers = data.get("triggers", {})
        response = data.get("response", {})
        
        return {
            "name": skill_def.get("name", toml_path.stem),
            "triggers": triggers.get("phrases", []),
            "action_type": list(actions.keys())[0] if actions else "unknown",
            "action_params": actions,
            "response_template": response.get("success", "Done, sir."),
            "source": str(toml_path)
        }
    except Exception as e:
        logger.error(f"[Skills] Failed to load {toml_path}: {e}")
        return None


def load_all_skills(skills_dir: Path = None) -> int:
    """Load all TOML skills from the skills directory."""
    global _skills_registry
    
    if skills_dir is None:
        skills_dir = Path(__file__).parent.parent / "skills"
    
    loaded = 0
    if skills_dir.exists():
        for toml_file in skills_dir.glob("*.toml"):
            skill = load_skill_from_toml(toml_file)
            if skill:
                _skills_registry[skill["name"]] = skill
                loaded += 1
                logger.info(f"[Skills] Loaded: {skill['name']} ({len(skill['triggers'])} triggers)")
    
    logger.info(f"[Skills] Total loaded: {loaded} skills")
    return loaded


def fuzzy_match(text: str, triggers: List[str], threshold: float = 0.72) -> tuple[bool, float, Optional[str]]:
    """
    Fuzzy match text against a list of trigger phrases.
    Returns (matched, score, best_match).
    """
    text_lower = text.lower().strip()
    
    for trigger in triggers:
        trigger_lower = trigger.lower().strip()
        
        # Exact match first
        if trigger_lower in text_lower:
            return True, 1.0, trigger
        
        # Sequence matcher for fuzzy similarity
        similarity = difflib.SequenceMatcher(None, text_lower, trigger_lower).ratio()
        if similarity >= threshold:
            return True, similarity, trigger
    
    return False, 0.0, None


def extract_app_name(text: str, trigger_phrases: List[str]) -> Optional[str]:
    """Extract application name from open command text."""
    text_lower = text.lower()
    
    # Common open patterns
    patterns = [
        r"open\s+(\w+)",
        r"launch\s+(\w+)",
        r"start\s+(\w+)",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            return match.group(1)
    
    # Try removing trigger words and see what's left
    for trigger in trigger_phrases:
        if trigger.lower() in text_lower:
            remainder = text_lower.replace(trigger.lower(), "").strip()
            # Clean up common filler words
            remainder = re.sub(r"^(please|the|my|your)\s+", "", remainder)
            if remainder:
                return remainder.split()[0] if remainder.split() else None
    
    return None


def execute_skill(skill_name: str, text: str, context: Dict = None) -> Dict[str, Any]:
    """Execute a skill with the given text and context."""
    skill = _skills_registry.get(skill_name)
    if not skill:
        return {"success": False, "error": f"Skill '{skill_name}' not found"}
    
    action_type = skill["action_type"]
    params = skill["action_params"].get(action_type, {})
    
    try:
        if action_type == "vault_summary":
            return _action_vault_summary(skill, text, context)
        elif action_type == "vault_log":
            return _action_vault_log(skill, text, context)
        elif action_type == "voice_capture_then_write":
            return _action_voice_capture(skill, text, context)
        elif action_type == "open_application":
            app_name = extract_app_name(text, skill["triggers"])
            return _action_open_app(skill, app_name, context)
        else:
            return {"success": False, "error": f"Unknown action type: {action_type}"}
    except Exception as e:
        logger.error(f"[Skills] Execution error for {skill_name}: {e}")
        return {"success": False, "error": str(e)}


def _action_vault_summary(skill: Dict, text: str, context: Dict) -> Dict:
    """Generate a vault summary for good morning briefing."""
    vault_path = Path(skill["action_params"].get("vault_summary", {}).get("vault_path", VAULT_PATH))
    
    # Count files in vault
    file_count = 0
    recent_files = []
    if vault_path.exists():
        for item in vault_path.rglob("*"):
            if item.is_file():
                file_count += 1
                stat = item.stat()
                recent_files.append((item, stat.st_mtime))
        
        # Sort by modification time and take top 5
        recent_files.sort(key=lambda x: x[1], reverse=True)
        recent_files = recent_files[:5]
    
    response = skill["response_template"]
    if file_count > 0:
        response += f" Your vault contains {file_count} files."
        if recent_files:
            response += " Recent activity includes: " + ", ".join(
                [f.name for f, _ in recent_files[:3]]
            ) + "."
    
    return {
        "success": True,
        "response": response,
        "skill": skill["name"]
    }


def _action_vault_log(skill: Dict, text: str, context: Dict) -> Dict:
    """Log end of day summary to vault."""
    vault_path = Path(skill["action_params"].get("vault_log", {}).get("vault_path", VAULT_PATH))
    log_dir = vault_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = log_dir / f"{today}.md"
    
    timestamp = datetime.now().strftime("%H:%M")
    entry = f"\n## {timestamp} — End of Day\nSession ended.\n"
    
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(entry)
    
    return {
        "success": True,
        "response": skill["response_template"],
        "skill": skill["name"]
    }


def _action_voice_capture(skill: Dict, text: str, context: Dict) -> Dict:
    """Placeholder for voice capture and note taking."""
    # The actual capture happens via separate flow
    return {
        "success": True,
        "response": skill["response_template"],
        "skill": skill["name"],
        "awaiting_capture": True
    }


def _action_open_app(skill: Dict, app_name: Optional[str], context: Dict) -> Dict:
    """Open an application by name."""
    if not app_name:
        return {
            "success": False,
            "response": "I didn't catch which application to open, sir.",
            "skill": skill["name"]
        }
    
    # Map common app names to executables
    app_map = {
        "chrome": "chrome",
        "browser": "chrome",
        "firefox": "firefox",
        "code": "code",
        "vscode": "code",
        "spotify": "spotify",
        "discord": "discord",
        "terminal": "wt",
        "cmd": "cmd",
        "explorer": "explorer",
        "notepad": "notepad",
        "calculator": "calc",
    }
    
    app_lower = app_name.lower()
    executable = app_map.get(app_lower, app_name)
    
    try:
        import subprocess
        subprocess.Popen([executable], creationflags=subprocess.CREATE_NO_WINDOW)
        response = skill["response_template"].replace("{app_name}", app_name.title())
        return {
            "success": True,
            "response": response,
            "skill": skill["name"]
        }
    except Exception as e:
        return {
            "success": False,
            "response": f"I couldn't open {app_name}, sir. Error: {e}",
            "skill": skill["name"]
        }


def match_skill(text: str, threshold: float = 0.72) -> Optional[Dict]:
    """
    Match incoming text against all skill triggers.
    Returns the best matching skill or None.
    """
    best_match = None
    best_score = 0.0
    
    for skill_name, skill in _skills_registry.items():
        matched, score, trigger = fuzzy_match(text, skill["triggers"], threshold)
        if matched and score > best_score:
            best_score = score
            best_match = {
                "skill": skill_name,
                "trigger": trigger,
                "score": score,
                "definition": skill
            }
    
    return best_match


def get_all_skills() -> Dict[str, Dict]:
    """Return all loaded skills."""
    return _skills_registry.copy()


# Initialize on module load
load_all_skills()
