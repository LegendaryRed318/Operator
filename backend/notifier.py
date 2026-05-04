#!/usr/bin/env python3
"""
notifier.py - Sends Windows toast notifications and Telegram alerts for errors.
"""

import json
import threading
import requests
from pathlib import Path
from datetime import datetime

# Config paths
DASHBOARD_URL = "http://localhost:8080"


def send_windows_alert(project_name, error_summary, timestamp):
    """Show a Windows desktop toast notification using plyer."""
    def _show_toast():
        try:
            from plyer import notification
            notification.notify(
                title=f"Operator — {project_name}",
                message=error_summary[:100] if error_summary else "Error detected",
                app_name="Operator",
                timeout=8
            )
            print("[NOTIFIER] Windows toast sent successfully")
        except Exception as e:
            print(f"[NOTIFIER] Windows toast failed: {e}")
    
    # Run in thread so it doesn't block the watcher
    thread = threading.Thread(target=_show_toast, daemon=True)
    thread.start()


def send_telegram_alert(project_name, error_summary, timestamp, dashboard_url=DASHBOARD_URL):
    """Send a Telegram alert for a new error."""
    import os
    from dotenv import load_dotenv
    import logging
    
    logger = logging.getLogger(__name__)
    load_dotenv(Path(__file__).parent / ".env")
    
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN not set - Telegram notifications disabled")
        return
    
    if not chat_id:
        logger.warning("TELEGRAM_CHAT_ID not set - Telegram notifications disabled")
        return
    
    # Build message
    error_preview = error_summary[:200] if error_summary else "No details available"
    message = (
        f"🚨 *Operator Alert*\n\n"
        f"*Project:* {project_name}\n"
        f"*Time:* {timestamp}\n"
        f"*Error:* `{error_preview}`\n\n"
        f"[Open Dashboard]({dashboard_url})"
    )
    
    # Send to Telegram
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print(f"[NOTIFIER] Telegram alert sent to {chat_id}")
        else:
            print(f"[NOTIFIER] Telegram API error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[NOTIFIER] Failed to send Telegram alert: {e}")


def notify_new_error(project_name, error_summary, timestamp):
    """Send both Windows and Telegram notifications for a new error."""
    # Windows toast first (instant, no internet needed)
    try:
        send_windows_alert(project_name, error_summary, timestamp)
    except Exception as e:
        print(f"[NOTIFIER] Windows alert error: {e}")
    
    # Telegram second (only fires if configured)
    try:
        send_telegram_alert(project_name, error_summary, timestamp)
    except Exception as e:
        print(f"[NOTIFIER] Telegram alert error: {e}")
