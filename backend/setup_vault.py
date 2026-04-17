#!/usr/bin/env python3
"""setup_vault.py - Create and initialize the JARVIS Obsidian vault."""

import os
from pathlib import Path


def setup_vault():
    """Create the vault structure and starter knowledge base."""
    vault = Path("E:/JarvisVault")
    
    # Create folder structure
    folders = [
        "raw_sources",
        "wiki/ai-responses",
        "wiki/errors",
        "wiki/projects",
        "conversations",
        "errors",
        "skills"
    ]
    
    for folder in folders:
        (vault / folder).mkdir(parents=True, exist_ok=True)
        print(f"[Vault] Created: {vault / folder}")

    # Write starter knowledge base
    kb = vault / "JARVIS_Knowledge_Base.md"
    kb_content = """# JARVIS Knowledge Base
Version: 1.0 — April 2026
User: RED (Olami)

## Hardware
- C: Windows SSD 118GB (95% full — needs cleanup)
- D: Micro SSD 29GB (core daemon, SQLite, logs)
- E: WD_BLACK HDD 1.72TB (models, vault, skills, archives)
- RAM: 8GB
- CPU: 8-Core AMD

## Active Projects
- Brainify: React study app (Lovable + Supabase + Gemini)
- Brainify-AI: AI backend (has config module error)
- Brainify-Motions: Framer Motion animations (fixing)
- Operator: This system — JARVIS guardian (Phases 1-4 complete)
- NEPA CBT: Nigerian school exam platform (Supabase)
- SquirexOptimizer: Desktop optimizer app (Tauri + Rust)

## Operator System Ports
- Dashboard: http://localhost:8081
- API: http://localhost:5050
- WebSocket: ws://localhost:8765

## JARVIS Rules
- Address user as sir or boss
- Swearing allowed
- No markdown in voice responses
- British dry wit at all times
- Auto-sleep after 3 hours of inactivity
"""
    
    kb.write_text(kb_content, encoding='utf-8')
    print(f"[Vault] Created: {kb}")
    
    # Create skills README
    skills_readme = vault / "skills" / "README.md"
    skills_readme.write_text(
        "JARVIS Skills — OpenJarvis .toml format. Store all skill files here to save SSD space.",
        encoding='utf-8'
    )
    print(f"[Vault] Created: {skills_readme}")
    
    print(f"\n[Vault] Setup complete at {vault}")
    return vault


if __name__ == "__main__":
    setup_vault()
