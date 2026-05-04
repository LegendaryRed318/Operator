#!/usr/bin/env python3
"""
memory.py - Obsidian vault integration for Jarvis second-brain memory.
Vault location: Loaded from OPERATOR_VAULT_PATH env var, defaults to repo-local vault.
"""

import logging
import json
import re
import shutil
from datetime import datetime
from paths import VAULT_PATH

logger = logging.getLogger(__name__)

VAULT_ROOT = VAULT_PATH
FOLDERS = {
    "raw_sources": VAULT_ROOT / "raw_sources",
    "wiki": VAULT_ROOT / "wiki",
    "conversations": VAULT_ROOT / "conversations",
    "errors": VAULT_ROOT / "errors",
}
PROFILE_JSON_PATH = FOLDERS["raw_sources"] / "jarvis_brain_profile.json"
PROFILE_MD_PATH = FOLDERS["wiki"] / "user-profile" / "RED_Profile.md"
BACKUPS_PATH = FOLDERS["raw_sources"] / "backups"


DEFAULT_BRAIN_PROFILE = {
    "identity": {
        "preferred_name": "RED",
        "full_name": "Olamide Arowolo",
        "pronouns": "he/him",
        "age_years": 14,
        "birthdate": "October 25",
        "origin": "Nigeria",
        "current_location": "United Kingdom",
        "school": "St Illtyds High School",
        "best_friends": ["Tyler", "Daniel"],
    },
    "preferences": {
        "tone": {
            "likes_humor": True,
            "direct_feedback": True,
            "can_be_blunt": True,
            "allow_profanity_general": True,
            "allow_slurs": False,
        },
        "budget": {
            "prefers_free_tools": True,
        },
    },
    "goals": {
        "primary": [
            "Become a billionaire",
            "Become an entrepreneur",
            "Build Jarvis into a major invention",
            "Lose weight",
        ],
        "money_mindset": "Strongly focused on making money and business growth.",
    },
    "interests": {
        "coding": True,
        "gaming": ["Minecraft"],
        "sports": ["football", "rugby", "tennis", "basketball", "swimming"],
    },
    "assistant_rules": {
        "ask_clarifying_questions_on_personal_challenges": True,
        "use_he_him_pronouns": True,
        "financial_advisor_mode": "guidance_only_no_direct_fund_control",
        "location_tracking": "disabled",
        "device_surveillance": "disabled",
    },
    "contacts": {
        "emails": [
            "Olamidepeniel@gmail.com",
            "LegendaryRed318@gmail.com",
            "shadowwyred@gmail.com",
        ]
    },
    "projects": [
        "NexusPlay.io",
        "GameGalaxy Hub",
        "Brainify AI",
        "BloodLust Minecraft Plugin",
    ],
    "updated_at": None,
}


def ensure_vault() -> bool:
    """Create vault folder structure if missing. Returns True if vault is accessible."""
    try:
        for folder in FOLDERS.values():
            folder.mkdir(parents=True, exist_ok=True)
        PROFILE_MD_PATH.parent.mkdir(parents=True, exist_ok=True)
        BACKUPS_PATH.mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.warning(f"[Memory] Vault not accessible at {VAULT_ROOT}: {e}")
        return False


def get_vault_health() -> dict:
    """Return vault connectivity/writability diagnostics."""
    exists = VAULT_ROOT.exists()
    writable = False
    test_file = FOLDERS["raw_sources"] / ".vault_write_test.tmp"
    latency_ms = None
    started = datetime.now()
    try:
        if exists:
            FOLDERS["raw_sources"].mkdir(parents=True, exist_ok=True)
            test_file.write_text("ok", encoding="utf-8")
            _ = test_file.read_text(encoding="utf-8")
            test_file.unlink(missing_ok=True)
            writable = True
    except Exception:
        writable = False
    elapsed = datetime.now() - started
    latency_ms = int(elapsed.total_seconds() * 1000)

    free_bytes = None
    total_bytes = None
    try:
        usage = shutil.disk_usage(str(VAULT_ROOT))
        free_bytes = int(usage.free)
        total_bytes = int(usage.total)
    except Exception:
        pass

    return {
        "path": str(VAULT_ROOT),
        "connected": bool(exists),
        "writable": bool(writable),
        "read_write_latency_ms": latency_ms,
        "free_bytes": free_bytes,
        "total_bytes": total_bytes,
        "checked_at": datetime.now().isoformat(),
    }


def _validate_brain_profile(profile: dict) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if not isinstance(profile, dict):
        return False, ["Profile must be a JSON object"]
    identity = profile.get("identity", {})
    if identity and not isinstance(identity, dict):
        issues.append("identity must be an object")
    if isinstance(identity, dict):
        age = identity.get("age_years")
        if age is not None and (not isinstance(age, int) or age < 0 or age > 120):
            issues.append("identity.age_years must be an integer between 0 and 120")
    contacts = profile.get("contacts", {})
    if isinstance(contacts, dict):
        emails = contacts.get("emails", [])
        if emails is not None:
            if not isinstance(emails, list):
                issues.append("contacts.emails must be a list")
            else:
                for em in emails:
                    if not isinstance(em, str) or "@" not in em:
                        issues.append(f"Invalid email entry: {em}")
    return len(issues) == 0, issues


def _write_profile_markdown(profile: dict) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    content = (
        "# RED Profile (Jarvis Brain)\n\n"
        f"_Last updated: {now}_\n\n"
        "## Identity\n"
        f"- Preferred name: {profile.get('identity', {}).get('preferred_name', 'RED')}\n"
        f"- Full name: {profile.get('identity', {}).get('full_name', '')}\n"
        f"- Pronouns: {profile.get('identity', {}).get('pronouns', '')}\n"
        f"- Age: {profile.get('identity', {}).get('age_years', '')}\n"
        f"- Birthdate: {profile.get('identity', {}).get('birthdate', '')}\n"
        f"- School: {profile.get('identity', {}).get('school', '')}\n\n"
        "## Goals\n"
    )
    goals = profile.get("goals", {}).get("primary", [])
    for g in goals:
        content += f"- {g}\n"
    content += (
        "\n## Preferences\n"
        "- Prefer free tools and alternatives\n"
        "- Likes direct, clear responses with humor\n"
        "- Keep safety guardrails active\n\n"
        "## Notes\n"
        "- Edit via API: GET/PUT/PATCH /brain/profile\n"
        "- Add notes via POST /brain/profile/note\n"
    )
    PROFILE_MD_PATH.write_text(content, encoding="utf-8")


def _deep_merge(base: dict, patch: dict) -> dict:
    merged = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def get_brain_profile() -> dict:
    """Read Jarvis brain profile; initialize default if missing."""
    if not ensure_vault():
        return {}
    try:
        if not PROFILE_JSON_PATH.exists():
            profile = dict(DEFAULT_BRAIN_PROFILE)
            profile["updated_at"] = datetime.now().isoformat()
            PROFILE_JSON_PATH.write_text(json.dumps(profile, indent=2), encoding="utf-8")
            _write_profile_markdown(profile)
            return profile
        raw = PROFILE_JSON_PATH.read_text(encoding="utf-8")
        return json.loads(raw)
    except Exception as e:
        logger.error(f"[Memory] Failed to read brain profile: {e}")
        return {}


def set_brain_profile(profile: dict, mode: str = "replace") -> dict:
    """
    Persist Jarvis brain profile.
    mode='replace' writes full profile, mode='merge' deep-merges with existing.
    """
    if not ensure_vault():
        return {}
    try:
        existing = get_brain_profile() or {}
        if mode == "merge":
            updated = _deep_merge(existing, profile or {})
        else:
            updated = profile or {}
        valid, issues = _validate_brain_profile(updated)
        if not valid:
            logger.warning(f"[Memory] Brain profile validation failed: {issues}")
            return {"_validation_error": issues}
        updated["updated_at"] = datetime.now().isoformat()
        PROFILE_JSON_PATH.write_text(json.dumps(updated, indent=2), encoding="utf-8")
        _write_profile_markdown(updated)
        return updated
    except Exception as e:
        logger.error(f"[Memory] Failed to save brain profile: {e}")
        return {}


def append_brain_profile_note(note: str) -> bool:
    """Append freeform user note into profile journal."""
    if not ensure_vault():
        return False
    
    if not note or not note.strip():
        return False
    try:
        journal = FOLDERS["raw_sources"] / "brain_profile_notes.md"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(journal, "a", encoding="utf-8") as f:
            f.write(f"\n## {ts}\n- {note.strip()}\n")
        return True
    except Exception as e:
        logger.error(f"[Memory] Failed to append brain note: {e}")
        return False


def import_brain_profile_export(raw_text: str) -> dict:
    """
    Parse freeform memory export text and merge extracted fields into brain profile.
    Returns updated profile and extraction metadata.
    """
    if not raw_text or not raw_text.strip():
        return {"error": "empty_input"}
    existing = get_brain_profile() or {}
    patch: dict = {"imported_memories": {"raw_export_excerpt": raw_text[:2000]}}
    identity: dict = {}

    name_match = re.search(r"full name is ([A-Za-z ]+)", raw_text, flags=re.I)
    if name_match:
        identity["full_name"] = name_match.group(1).strip()
    pref_match = re.search(r"called ([A-Za-z0-9_-]+)", raw_text, flags=re.I)
    if pref_match:
        identity["preferred_name"] = pref_match.group(1).strip()
    age_match = re.search(r"(\d{1,2}) years old", raw_text, flags=re.I)
    if age_match:
        try:
            identity["age_years"] = int(age_match.group(1))
        except ValueError:
            pass
    bday_match = re.search(r"turn \d+ on ([A-Za-z]+ \d{1,2})", raw_text, flags=re.I)
    if bday_match:
        identity["birthdate"] = bday_match.group(1).strip()

    emails = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", raw_text)
    if emails:
        patch["contacts"] = {"emails": sorted(set(emails))}

    if identity:
        patch["identity"] = identity
    if "free alternatives" in raw_text.lower() or "free tools" in raw_text.lower():
        patch.setdefault("preferences", {})
        patch["preferences"]["budget"] = {"prefers_free_tools": True}
    if "clarifying questions" in raw_text.lower():
        patch.setdefault("assistant_rules", {})
        patch["assistant_rules"]["ask_clarifying_questions_on_personal_challenges"] = True

    merged = _deep_merge(existing, patch)
    result = set_brain_profile(merged, mode="replace")
    if "_validation_error" in result:
        return {"error": "validation_failed", "issues": result["_validation_error"]}
    return {"status": "ok", "profile": result, "extracted_emails": len(emails)}


def create_vault_backup() -> dict:
    """Create timestamped backup of key memory/skills artifacts."""
    if not ensure_vault():
        return {"ok": False, "error": "vault_unavailable"}
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BACKUPS_PATH / ts
    backup_dir.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    targets = [
        PROFILE_JSON_PATH,
        PROFILE_MD_PATH,
        FOLDERS["conversations"],
        VAULT_ROOT / "skills",
    ]
    for target in targets:
        try:
            if target.is_file():
                dest = backup_dir / target.name
                shutil.copy2(target, dest)
                copied.append(str(dest))
            elif target.is_dir():
                dest = backup_dir / target.name
                shutil.copytree(target, dest, dirs_exist_ok=True)
                copied.append(str(dest))
        except Exception as e:
            logger.warning(f"[Memory] Backup skip {target}: {e}")
    return {"ok": True, "backup_dir": str(backup_dir), "items_copied": copied}


def search_vault(query: str) -> list:
    """
    Search vault using ChromaDB semantic RAG search. 
    Falls back to naive keyword search if Chroma isn't initialized yet.
    """
    if not ensure_vault():
        return []

    try:
        from rag_memory import semantic_search
        results = semantic_search(query)
        if results:
            return results
    except Exception as e:
        logger.warning(f"[Memory] RAG search failed ({e}), falling back to keyword search.")

    # Fallback naïve keyword search
    results = []
    raw_words = [w.lower() for w in query.split() if len(w) > 2]
    
    query_words = set(raw_words)
    if not query_words:
        return []

    try:
        for md_file in VAULT_ROOT.rglob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8", errors="ignore")
                for line in content.split("\n"):
                    line_stripped = line.strip()
                    if not line_stripped:
                        continue
                    line_lower = line_stripped.lower()
                    matches = sum(1 for w in query_words if w in line_lower)
                    if matches > 0:
                        results.append({
                            "file": str(md_file.relative_to(VAULT_ROOT)).replace("\\", "/"),
                            "excerpt": line_stripped[:200],
                            "relevance_score": matches,
                        })
            except Exception:
                pass
    except Exception as e:
        logger.error(f"[Memory] Search failed: {e}")

    results.sort(key=lambda x: x["relevance_score"], reverse=True)
    return results[:5]


def save_to_wiki(title: str, content: str, category: str) -> bool:
    """Save a knowledge note to E:\\JarvisVault\\wiki\\{category}\\{title}.md"""
    if not ensure_vault():
        return False

    try:
        category_dir = FOLDERS["wiki"] / category
        category_dir.mkdir(parents=True, exist_ok=True)

        safe_title = "".join(
            c if c.isalnum() or c in " -_" else "_" for c in title
        ).strip()[:80]
        if not safe_title:
            safe_title = f"note_{datetime.now().strftime('%H%M%S')}"
        file_path = category_dir / f"{safe_title}.md"

        now = datetime.now()
        frontmatter = (
            f"---\ntitle: {title}\ndate: {now.strftime('%Y-%m-%d')}\n"
            f"category: {category}\nsource: jarvis-response\n---\n\n"
        )
        file_path.write_text(frontmatter + content, encoding="utf-8")
        logger.info(f"[Memory] Saved wiki note: {file_path}")
        return True
    except Exception as e:
        logger.error(f"[Memory] Failed to save wiki entry: {e}")
        return False


def save_conversation(user_text: str, jarvis_response: str) -> bool:
    """Append a conversation turn to E:\\JarvisVault\\conversations\\YYYY-MM-DD.md"""
    if not ensure_vault():
        return False

    try:
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M")

        conv_file = FOLDERS["conversations"] / f"{date_str}.md"

        if not conv_file.exists():
            conv_file.write_text(f"# Conversations — {date_str}\n", encoding="utf-8")

        entry = (
            f"\n## {time_str}\n"
            f"**RED:** {user_text}\n"
            f"**JARVIS:** {jarvis_response}\n"
        )
        with open(conv_file, "a", encoding="utf-8") as f:
            f.write(entry)
        return True
    except Exception as e:
        logger.error(f"[Memory] Failed to save conversation: {e}")
        return False


def get_context_for_query(query: str) -> str:
    """
    Search vault and return a formatted context string for prepending to AI prompts.
    Returns empty string if nothing found.
    """
    results = search_vault(query)
    if not results:
        return ""

    parts = [f"[{r['file']}] {r['excerpt']}" for r in results[:3]]
    return "From your vault:\n" + "\n".join(parts)


def get_recent_files(n: int = 10) -> list:
    """Return metadata for the last n modified .md files in the vault."""
    if not ensure_vault():
        return []

    try:
        files = sorted(
            VAULT_ROOT.rglob("*.md"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        return [
            {
                "file": str(f.relative_to(VAULT_ROOT)).replace("\\", "/"),
                "modified": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            }
            for f in files[:n]
        ]
    except Exception as e:
        logger.error(f"[Memory] Failed to list recent files: {e}")
        return []


def save_voice_note(transcript: str, tags: list = None) -> bool:
    r"""
    Save a voice note (quick memo) to E:\JarvisVault\raw_sources\voice_notes\YYYY-MM-DD_HHMMSS.md
    
    Args:
        transcript: The transcribed voice text
        tags: Optional list of tags to include in frontmatter
    
    Returns:
        True if saved successfully, False otherwise
    """
    if not ensure_vault():
        return False
    
    if not transcript or not transcript.strip():
        logger.warning("[Memory] Empty voice note, skipping save")
        return False
    
    try:
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")
        filename = f"{date_str}_{time_str.replace(':', '')}.md"
        
        notes_dir = FOLDERS["raw_sources"] / "voice_notes"
        notes_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = notes_dir / filename
        
        # Build frontmatter
        tags_str = ""
        if tags:
            tags_str = f"tags: {tags}\n"
        
        frontmatter = f"""---
date: {date_str}
time: {time_str}
type: voice_note
source: speech-to-text
{tags_str}---

# Voice Note — {time_str}

{transcript}
"""
        file_path.write_text(frontmatter, encoding="utf-8")
        logger.info(f"[Memory] Saved voice note: {file_path.name}")
        return True
    except Exception as e:
        logger.error(f"[Memory] Failed to save voice note: {e}")
        return False
