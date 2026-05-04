#!/usr/bin/env python3
"""
tool_executor.py - Parse and execute tool calls from JARVIS LLM responses.

This module parses LLM responses for JSON tool calls at the start of responses,
executes the corresponding tool functions, and returns clean text for TTS.

Example flow:
1. User: "Open Chrome"
2. LLM response: '{"tool":"open_app","args":{"name":"chrome"}} Opening Chrome now, sir.'
3. Tool executor parses JSON, executes open_app("chrome")
4. Returns: ('{"status":"opened","app":"chrome"}', 'Opening Chrome now, sir.')
"""

import json
import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

import psutil

from paths import VAULT_PATH

logger = logging.getLogger(__name__)

# Windows app registry with common paths
APP_REGISTRY = {
    "chrome": r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    "brave": r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    "browser": r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    "google chrome": "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "firefox": "C:/Program Files/Mozilla Firefox/firefox.exe",
    "vscode": "code",
    "visual studio code": "code",
    "code": "code",
    "discord": "discord",
    "spotify": "spotify",
    "terminal": "cmd",
    "cmd": "cmd",
    "command prompt": "cmd",
    "explorer": "explorer",
    "file explorer": "explorer",
    "notepad": "notepad",
    "calculator": "calc",
    "calc": "calc",
    "settings": "ms-settings:",
    "edge": "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "microsoft edge": "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
}


def fuzzy_match_app(name: str) -> Optional[str]:
    """Fuzzy match app name against registry keys."""
    name_lower = name.lower().strip()
    
    # Direct match
    if name_lower in APP_REGISTRY:
        return APP_REGISTRY[name_lower]
    
    # Partial match
    for key, path in APP_REGISTRY.items():
        if name_lower in key or key in name_lower:
            return path
    
    return None


def open_app(name: str) -> Dict[str, Any]:
    """Open an application by name."""
    try:
        app_path = fuzzy_match_app(name)
        
        if app_path:
            if app_path.startswith("ms-"):
                # UWP app (like Settings)
                subprocess.Popen(f"start {app_path}", shell=True)
            else:
                subprocess.Popen(app_path, shell=True)
            logger.info(f"[Tool] Opened app: {name} ({app_path})")
            return {"status": "opened", "app": name, "path": app_path}
        else:
            # Try generic start command
            subprocess.Popen(f"start {name}", shell=True)
            logger.info(f"[Tool] Attempted to open: {name}")
            return {"status": "attempted", "app": name}
            
    except Exception as e:
        logger.error(f"[Tool] Failed to open app {name}: {e}")
        return {"status": "error", "error": str(e), "app": name}


def take_note(text: str) -> Dict[str, Any]:
    """Append a note to today's vault notes file."""
    try:
        notes_dir = Path(VAULT_PATH) / "notes"
        notes_dir.mkdir(parents=True, exist_ok=True)
        
        today = datetime.now().strftime("%Y-%m-%d")
        note_file = notes_dir / f"{today}.md"
        
        time_str = datetime.now().strftime("%H:%M")
        entry = f"\n## {time_str}\n{text}\n\n"
        
        with open(note_file, "a", encoding="utf-8") as f:
            f.write(entry)
        
        logger.info(f"[Tool] Note saved to {note_file}")
        return {"status": "noted", "file": str(note_file), "text": text}
        
    except Exception as e:
        logger.error(f"[Tool] Failed to save note: {e}")
        return {"status": "error", "error": str(e)}


def add_task(title: str, priority: str = "medium") -> Dict[str, Any]:
    """Add a task to the tasks file."""
    try:
        tasks_file = Path(VAULT_PATH) / "tasks.md"
        tasks_file.parent.mkdir(parents=True, exist_ok=True)
        
        entry = f"- [ ] {title} [{priority.upper()}]\n"
        
        with open(tasks_file, "a", encoding="utf-8") as f:
            f.write(entry)
        
        logger.info(f"[Tool] Task added: {title} [{priority}]")
        return {"status": "added", "title": title, "priority": priority}
        
    except Exception as e:
        logger.error(f"[Tool] Failed to add task: {e}")
        return {"status": "error", "error": str(e)}


def run_fix(project: str) -> Dict[str, Any]:
    """Trigger the error fix pipeline for a project."""
    # This returns a signal for ws_server to handle
    logger.info(f"[Tool] Fix requested for project: {project}")
    return {
        "status": "triggered",
        "project": project,
        "action": "trigger_fix",
        "signal": {"type": "trigger_fix", "project": project}
    }


def gaming_mode(active: bool) -> Dict[str, Any]:
    """Toggle gaming mode - reduces priority of background apps."""
    try:
        background_apps = [
            "Discord.exe", "Teams.exe", "OneDrive.exe", 
            "Spotify.exe", "chrome.exe"
        ]
        
        results = []
        
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] in background_apps:
                    p = psutil.Process(proc.info['pid'])
                    
                    if active:
                        p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
                        results.append(f"{proc.info['name']}: lowered priority")
                    else:
                        p.nice(psutil.NORMAL_PRIORITY_CLASS)
                        results.append(f"{proc.info['name']}: normal priority")
                        
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        status = "enabled" if active else "disabled"
        logger.info(f"[Tool] Gaming mode {status}: {len(results)} apps adjusted")
        
        return {
            "status": status,
            "adjusted_apps": results,
            "signal": {"type": "gaming_mode", "active": active}
        }
        
    except Exception as e:
        logger.error(f"[Tool] Gaming mode error: {e}")
        return {"status": "error", "error": str(e)}


def end_of_day() -> Dict[str, Any]:
    """Create end of day log with session summary."""
    try:
        logs_dir = Path(VAULT_PATH) / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = logs_dir / f"{today}.md"
        
        # Count today's notes
        notes_dir = Path(VAULT_PATH) / "notes"
        notes_count = 0
        if notes_dir.exists():
            today_notes = notes_dir / f"{today}.md"
            if today_notes.exists():
                content = today_notes.read_text(encoding="utf-8")
                notes_count = content.count("## ")
        
        # Count tasks
        tasks_file = Path(VAULT_PATH) / "tasks.md"
        tasks_count = 0
        if tasks_file.exists():
            tasks_content = tasks_file.read_text(encoding="utf-8")
            tasks_count = tasks_content.count("- [ ]")
        
        summary = f"""# End of Day Summary - {today}

## Session Stats
- Notes taken today: {notes_count}
- Pending tasks: {tasks_count}
- Logged at: {datetime.now().strftime("%H:%M")}

"""
        
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(summary)
        
        logger.info(f"[Tool] End of day log created: {log_file}")
        
        return {
            "status": "logged",
            "file": str(log_file),
            "notes_count": notes_count,
            "tasks_count": tasks_count,
            "summary": summary
        }
        
    except Exception as e:
        logger.error(f"[Tool] End of day error: {e}")
        return {"status": "error", "error": str(e)}


def good_morning() -> Dict[str, Any]:
    """Generate morning briefing with tasks and notes."""
    try:
        # Get incomplete tasks
        tasks_file = Path(VAULT_PATH) / "tasks.md"
        incomplete_tasks = []
        if tasks_file.exists():
            content = tasks_file.read_text(encoding="utf-8")
            for line in content.split('\n'):
                if line.startswith('- [ ]'):
                    task_text = line.replace('- [ ]', '').strip()
                    incomplete_tasks.append(task_text)
        
        # Get yesterday's notes if any
        from datetime import timedelta
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        notes_file = Path(VAULT_PATH) / "notes" / f"{yesterday}.md"
        
        yesterday_notes = []
        if notes_file.exists():
            content = notes_file.read_text(encoding="utf-8")
            for line in content.split('\n'):
                if line.startswith('## '):
                    note = line.replace('## ', '').strip()
                    yesterday_notes.append(note)
        
        briefing = {
            "status": "briefed",
            "incomplete_tasks": incomplete_tasks[:5],  # Top 5
            "yesterday_notes": yesterday_notes[:3],
            "task_count": len(incomplete_tasks)
        }
        
        logger.info(f"[Tool] Morning briefing: {len(incomplete_tasks)} tasks, {len(yesterday_notes)} notes")
        return briefing
        
    except Exception as e:
        logger.error(f"[Tool] Good morning error: {e}")
        return {"status": "error", "error": str(e)}


def search_vault(query: str, n_results: int = 3) -> Dict[str, Any]:
    """Search vault for relevant content using ChromaDB."""
    try:
        # Lazy import to avoid circular dependencies
        try:
            from vault_rag import get_vault_rag
            vault_rag = get_vault_rag()
            
            if vault_rag is None:
                # Fallback: simple grep search
                return _grep_vault(query)
            
            results = vault_rag.search(query, n_results=n_results)
            
            if results:
                logger.info(f"[Tool] Vault search for '{query}': {len(results)} results")
                return {
                    "status": "found",
                    "query": query,
                    "results": results,
                    "count": len(results)
                }
            else:
                return {
                    "status": "no_results",
                    "query": query,
                    "results": [],
                    "count": 0
                }
                
        except ImportError:
            # Fallback to grep
            return _grep_vault(query)
            
    except Exception as e:
        logger.error(f"[Tool] Vault search error: {e}")
        return {"status": "error", "error": str(e), "query": query}


def _grep_vault(query: str) -> Dict[str, Any]:
    """Fallback grep search of vault files."""
    try:
        notes_dir = Path(VAULT_PATH) / "notes"
        results = []
        
        if notes_dir.exists():
            for md_file in notes_dir.rglob("*.md"):
                content = md_file.read_text(encoding="utf-8")
                if query.lower() in content.lower():
                    # Find the line with the match
                    for line in content.split('\n'):
                        if query.lower() in line.lower():
                            results.append(f"{md_file.name}: {line.strip()}")
                            break
                
                if len(results) >= 3:
                    break
        
        return {
            "status": "found" if results else "no_results",
            "query": query,
            "results": results,
            "count": len(results),
            "method": "grep_fallback"
        }
        
    except Exception as e:
        return {"status": "error", "error": str(e)}


# Tool registry
TOOLS: Dict[str, Callable] = {
    "open_app": open_app,
    "take_note": take_note,
    "add_task": add_task,
    "run_fix": run_fix,
    "gaming_mode": gaming_mode,
    "end_of_day": end_of_day,
    "good_morning": good_morning,
    "search_vault": search_vault,
}


def parse_tool_call(text: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Parse a tool call from the start of an LLM response.
    
    Returns:
        Tuple of (tool_call_dict or None, clean_text_without_json)
    """
    # Look for JSON object at start of response
    # Pattern: {"tool":"name","args":{...}} followed by text
    json_pattern = r'^\s*(\{[^}]+\})\s*'
    
    match = re.match(json_pattern, text)
    if not match:
        return None, text
    
    json_str = match.group(1)
    
    try:
        tool_call = json.loads(json_str)
        
        # Validate tool call structure
        if "tool" not in tool_call:
            return None, text
        
        # Remove the JSON from the text
        clean_text = text[match.end():].strip()
        
        return tool_call, clean_text
        
    except json.JSONDecodeError:
        # Not valid JSON, return original
        return None, text


def execute_tool(tool_call: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a tool call and return the result.
    """
    tool_name = tool_call.get("tool")
    args = tool_call.get("args", {})
    
    if tool_name not in TOOLS:
        logger.warning(f"[Tool] Unknown tool: {tool_name}")
        return {"status": "error", "error": f"Unknown tool: {tool_name}"}
    
    try:
        result = TOOLS[tool_name](**args)
        logger.info(f"[Tool] Executed {tool_name} with args {args}: {result.get('status', 'ok')}")
        return result
    except Exception as e:
        logger.error(f"[Tool] Error executing {tool_name}: {e}")
        return {"status": "error", "error": str(e), "tool": tool_name}


def parse_and_execute(response_text: str) -> Tuple[Optional[Dict[str, Any]], str, Optional[Dict[str, Any]]]:
    """
    Parse and execute tool call from LLM response.
    
    Returns:
        Tuple of (tool_result or None, clean_text_for_tts, signal_for_ws or None)
        - tool_result: The result dict from the tool execution
        - clean_text: The response text with JSON removed
        - signal: Any WebSocket signal to send (for gaming_mode, run_fix, etc.)
    """
    tool_call, clean_text = parse_tool_call(response_text)
    
    if tool_call is None:
        return None, clean_text, None
    
    # Execute the tool
    result = execute_tool(tool_call)
    
    # Extract any signals from the result
    signal = result.pop("signal", None)
    
    return result, clean_text, signal


def get_tool_schema() -> str:
    """Get the tool schema for the system prompt."""
    return """
You have access to tools. When you need to use one, output ONLY a JSON object on a single line at the START of your response, then continue with your spoken reply. Format: {"tool":"tool_name","args":{key:value}}

Available tools:
- open_app: {"tool":"open_app","args":{"name":"chrome"}} - Opens an application. Common names: chrome, firefox, vscode, discord, spotify, terminal, explorer, notepad, calculator, edge.
- take_note: {"tool":"take_note","args":{"text":"note content"}} - Saves a note to the vault with timestamp.
- add_task: {"tool":"add_task","args":{"title":"task name","priority":"high"}} - Adds a task. Priority can be: low, medium, high.
- run_fix: {"tool":"run_fix","args":{"project":"project_name"}} - Triggers error fixing for a project.
- gaming_mode: {"tool":"gaming_mode","args":{"active":true}} - Toggles gaming mode (adjusts process priorities).
- end_of_day: {"tool":"end_of_day","args":{}} - Creates end of day summary log.
- good_morning: {"tool":"good_morning","args":{}} - Generates morning briefing (tasks + notes).

Only emit tool JSON when the user clearly wants an action. For questions or conversation, respond in plain text only."""
