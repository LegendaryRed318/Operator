#!/usr/bin/env python3
"""
conversation_summarizer.py - Auto-generate daily conversation summaries.
Runs at midnight to summarize the day's conversations and save to wiki.
"""

import logging
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    from paths import VAULT_PATH, LOGS_PATH
except ImportError:
    from backend.paths import VAULT_PATH, LOGS_PATH

logger = logging.getLogger(__name__)

# Path for tracking last summary generation
LAST_SUMMARY_PATH = LOGS_PATH / "last_conversation_summary.txt"


def get_conversation_file(date_str: str) -> Optional[Path]:
    """Get the conversation file for a specific date."""
    conversations_dir = VAULT_PATH / "conversations"
    conv_file = conversations_dir / f"{date_str}.md"
    
    if conv_file.exists():
        return conv_file
    return None


def parse_conversation_file(file_path: Path) -> list[dict]:
    """Parse a conversation markdown file into structured data."""
    conversations = []
    
    try:
        content = file_path.read_text(encoding="utf-8")
        lines = content.split("\n")
        
        current_time = None
        current_speaker = None
        current_message = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check for time header (## HH:MM)
            if line.startswith("## ") and ":" in line:
                # Save previous message if exists
                if current_speaker and current_message:
                    conversations.append({
                        "time": current_time,
                        "speaker": current_speaker,
                        "message": " ".join(current_message)
                    })
                
                current_time = line.replace("## ", "").strip()
                current_speaker = None
                current_message = []
            
            # Check for speaker line (**RED:** or **JARVIS:**)
            elif line.startswith("**RED:**"):
                # Save previous message if exists
                if current_speaker and current_message:
                    conversations.append({
                        "time": current_time,
                        "speaker": current_speaker,
                        "message": " ".join(current_message)
                    })
                
                current_speaker = "RED"
                message_text = line.replace("**RED:**", "").strip()
                current_message = [message_text] if message_text else []
            
            elif line.startswith("**JARVIS:**"):
                # Save previous message if exists
                if current_speaker and current_message:
                    conversations.append({
                        "time": current_time,
                        "speaker": current_speaker,
                        "message": " ".join(current_message)
                    })
                
                current_speaker = "JARVIS"
                message_text = line.replace("**JARVIS:**", "").strip()
                current_message = [message_text] if message_text else []
            
            else:
                # Continuation of current message
                if current_speaker:
                    current_message.append(line)
        
        # Don't forget the last message
        if current_speaker and current_message:
            conversations.append({
                "time": current_time,
                "speaker": current_speaker,
                "message": " ".join(current_message)
            })
        
    except Exception as e:
        logger.error(f"[Summarizer] Error parsing conversation file: {e}")
    
    return conversations


def extract_topics(conversations: list[dict]) -> list[str]:
    """Extract main topics from conversations using keyword analysis."""
    topic_keywords = {
        "coding": ["code", "programming", "python", "javascript", "bug", "error", "debug", "function", "class", "import"],
        "system": ["system", "ram", "cpu", "disk", "memory", "performance", "slow", "crash"],
        "project": ["project", "build", "deploy", "git", "github", "commit", "branch", "merge"],
        "ai": ["jarvis", "ai", "model", "ollama", "gemini", "chatgpt", "llm", "training"],
        "schedule": ["schedule", "calendar", "meeting", "appointment", "reminder", "time", "today"],
        "files": ["file", "folder", "document", "save", "open", "edit", "delete"],
        "search": ["search", "find", "look up", "google", "web", "internet"],
        "hardware": ["laptop", "computer", "device", "server", "nas", "homelab"],
        "personal": ["name", "profile", "preferences", "settings", "configure"],
    }
    
    found_topics = set()
    
    for conv in conversations:
        message = conv.get("message", "").lower()
        
        for topic, keywords in topic_keywords.items():
            if any(keyword in message for keyword in keywords):
                found_topics.add(topic)
    
    return sorted(found_topics)


def generate_simple_summary(conversations: list[dict], date_str: str) -> str:
    """Generate a simple rule-based summary (fallback when Ollama unavailable)."""
    if not conversations:
        return ""
    
    topics = extract_topics(conversations)
    topics_str = ", ".join(topics) if topics else "general conversation"
    
    # Count exchanges
    red_messages = [c for c in conversations if c["speaker"] == "RED"]
    jarvis_messages = [c for c in conversations if c["speaker"] == "JARVIS"]
    
    # Extract key moments (first interaction, questions asked)
    questions_asked = [c for c in red_messages if "?" in c.get("message", "")]
    
    summary = f"""---
date: {date_str}
type: conversation_summary
topics: {topics_str}
generated_at: {datetime.now().isoformat()}
---

# Conversation Summary — {date_str}

## Overview
- **Total exchanges:** {len(red_messages)} messages from RED, {len(jarvis_messages)} responses from JARVIS
- **Topics discussed:** {topics_str}
- **Questions asked:** {len(questions_asked)}

## Key Moments
"""
    
    # Add first and last exchanges
    if conversations:
        first = conversations[0]
        last = conversations[-1]
        
        summary += f"\n**First interaction ({first.get('time', 'unknown')}):**\n"
        summary += f"- {first['speaker']}: {first['message'][:100]}{'...' if len(first['message']) > 100 else ''}\n"
        
        summary += f"\n**Last interaction ({last.get('time', 'unknown')}):**\n"
        summary += f"- {last['speaker']}: {last['message'][:100]}{'...' if len(last['message']) > 100 else ''}\n"
    
    # Add topics section
    if topics:
        summary += "\n## Topics\n"
        for topic in topics:
            summary += f"- {topic.capitalize()}\n"
    
    # Add sample questions
    if questions_asked:
        summary += "\n## Questions Asked\n"
        for i, q in enumerate(questions_asked[:3]):
            question_text = q["message"][:80] + "..." if len(q["message"]) > 80 else q["message"]
            summary += f"{i+1}. {question_text}\n"
    
    summary += f"\n*Full conversation log: [[conversations/{date_str}]]*\n"
    
    return summary


def generate_ai_summary(conversations: list[dict], date_str: str) -> Optional[str]:
    """Generate summary using Ollama AI (when available)."""
    try:
        from backend.decision_engine import DecisionEngine
        
        # Prepare conversation text
        conv_text = "\n".join([
            f"{c['time']} - {c['speaker']}: {c['message'][:200]}"
            for c in conversations[:20]  # First 20 exchanges
        ])
        
        engine = DecisionEngine()
        
        prompt = f"""Summarize the following conversation between RED (user) and JARVIS (AI assistant).
Focus on: main topics discussed, key questions asked, any decisions made, action items.
Keep it concise - 3-4 bullet points.

Conversation:
{conv_text}

Provide summary in this format:
- Topics: [list]
- Key Questions: [list]
- Action Items: [list or "None"]
- Notable: [any interesting moments]"""

        response = engine.chat(prompt)
        
        topics = extract_topics(conversations)
        topics_str = ", ".join(topics) if topics else "general conversation"
        
        summary = f"""---
date: {date_str}
type: conversation_summary
topics: {topics_str}
ai_generated: true
generated_at: {datetime.now().isoformat()}
---

# AI-Generated Conversation Summary — {date_str}

{response}

## Raw Stats
- **Total exchanges:** {len(conversations)}
- **Topics detected:** {topics_str}

*Full conversation log: [[conversations/{date_str}]]*"""
        
        return summary
        
    except Exception as e:
        logger.warning(f"[Summarizer] AI summary failed, using simple summary: {e}")
        return None


def generate_daily_summary(date_str: Optional[str] = None, force: bool = False) -> bool:
    """
    Generate a summary for a specific date (or yesterday if not specified).
    
    Args:
        date_str: Date in YYYY-MM-DD format. If None, uses yesterday.
        force: Regenerate even if summary already exists.
    
    Returns:
        True if summary was generated, False otherwise.
    """
    if date_str is None:
        # Default to yesterday
        yesterday = datetime.now() - timedelta(days=1)
        date_str = yesterday.strftime("%Y-%m-%d")
    
    # Check if already summarized today (unless force)
    if not force and LAST_SUMMARY_PATH.exists():
        last_date = LAST_SUMMARY_PATH.read_text().strip()
        if last_date == date_str:
            logger.info(f"[Summarizer] Already generated summary for {date_str}, skipping")
            return False
    
    # Get conversation file
    conv_file = get_conversation_file(date_str)
    if not conv_file:
        logger.info(f"[Summarizer] No conversations found for {date_str}")
        return False
    
    # Parse conversations
    conversations = parse_conversation_file(conv_file)
    
    if len(conversations) < 3:
        logger.info(f"[Summarizer] Not enough conversations to summarize for {date_str} (found {len(conversations)})")
        return False
    
    logger.info(f"[Summarizer] Generating summary for {date_str} ({len(conversations)} conversation turns)")
    
    # Try AI summary first, fallback to simple
    summary = generate_ai_summary(conversations, date_str)
    if not summary:
        summary = generate_simple_summary(conversations, date_str)
    
    # Save to wiki
    try:
        summaries_dir = VAULT_PATH / "wiki" / "conversation-summaries"
        summaries_dir.mkdir(parents=True, exist_ok=True)
        
        summary_file = summaries_dir / f"{date_str}-summary.md"
        summary_file.write_text(summary, encoding="utf-8")
        
        logger.info(f"[Summarizer] Saved summary to {summary_file}")
        
        # Also append to daily note if it exists
        daily_file = VAULT_PATH / "daily" / f"{date_str}.md"
        if daily_file.exists():
            daily_content = daily_file.read_text(encoding="utf-8")
            if "## Conversation Summary" not in daily_content:
                with open(daily_file, "a", encoding="utf-8") as f:
                    f.write(f"\n## Conversation Summary\n\nSee full summary: [[conversation-summaries/{date_str}-summary]]\n")
                logger.info(f"[Summarizer] Updated daily note with summary link")
        
        # Mark as summarized
        LAST_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
        LAST_SUMMARY_PATH.write_text(date_str, encoding="utf-8")
        
        return True
        
    except Exception as e:
        logger.error(f"[Summarizer] Failed to save summary: {e}")
        return False


def should_generate_summary() -> bool:
    """Check if summary should be generated (runs once per day at midnight)."""
    if not LAST_SUMMARY_PATH.exists():
        return True
    
    last_date = LAST_SUMMARY_PATH.read_text().strip()
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Generate if we haven't summarized today AND it's past midnight
    if last_date != today:
        # Check if there's conversation data for yesterday
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        conv_file = get_conversation_file(yesterday)
        return conv_file is not None
    
    return False


def run_scheduler_check():
    """Called periodically to check if summary needs generation."""
    if should_generate_summary():
        # Generate for yesterday
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        generate_daily_summary(yesterday)


if __name__ == "__main__":
    # Manual test
    print("Conversation Summarizer module loaded.")
    
    # Test with today's date if available
    today = datetime.now().strftime("%Y-%m-%d")
    result = generate_daily_summary(today, force=True)
    print(f"Summary generation result: {result}")
