#!/usr/bin/env python3
"""
memory.py - Obsidian vault integration for Jarvis second-brain memory.
Vault location: Loaded from OPERATOR_VAULT_PATH env var, defaults to E:/JarvisVault
"""

import logging
import os
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# Load from environment or use default
VAULT_ROOT = Path(os.getenv("OPERATOR_VAULT_PATH", "E:/JarvisVault"))
FOLDERS = {
    "raw_sources": VAULT_ROOT / "raw_sources",
    "wiki": VAULT_ROOT / "wiki",
    "conversations": VAULT_ROOT / "conversations",
    "errors": VAULT_ROOT / "errors",
}


def ensure_vault() -> bool:
    """Create vault folder structure if missing. Returns True if vault is accessible."""
    try:
        for folder in FOLDERS.values():
            folder.mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.warning(f"[Memory] Vault not accessible at {VAULT_ROOT}: {e}")
        return False


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
