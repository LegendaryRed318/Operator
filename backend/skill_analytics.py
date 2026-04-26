#!/usr/bin/env python3
"""
skill_analytics.py - Analytics and statistics for skill usage.
Tracks execution history, success rates, popular skills, and usage patterns.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from collections import defaultdict

from paths import LOGS_PATH

DB_PATH = LOGS_PATH / "skill_analytics.db"


def init_db():
    """Initialize the analytics database."""
    LOGS_PATH.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skill_executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id TEXT UNIQUE,
            skill_name TEXT NOT NULL,
            command_text TEXT,
            response TEXT,
            success INTEGER NOT NULL,
            duration_ms INTEGER,
            source TEXT,
            matched_by TEXT,
            hour INTEGER,
            day_of_week INTEGER,
            created_at REAL NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skill_stats (
            skill_name TEXT PRIMARY KEY,
            total_executions INTEGER DEFAULT 0,
            successful_executions INTEGER DEFAULT 0,
            failed_executions INTEGER DEFAULT 0,
            total_duration_ms INTEGER DEFAULT 0,
            last_used_at REAL,
            created_at REAL NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skill_triggers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_name TEXT NOT NULL,
            trigger_phrase TEXT NOT NULL,
            usage_count INTEGER DEFAULT 0,
            learned INTEGER DEFAULT 0,
            created_at REAL NOT NULL
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_skill_name ON skill_executions(skill_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON skill_executions(created_at)")

    conn.commit()
    conn.close()


def log_execution(
    trace_id: str,
    skill_name: str,
    command_text: str,
    response: str,
    success: bool,
    duration_ms: int,
    source: str,
    matched_by: str,
) -> None:
    """Log a skill execution for analytics."""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    now = datetime.now()
    created_at = now.timestamp()

    try:
        cursor.execute("""
            INSERT OR REPLACE INTO skill_executions
            (trace_id, skill_name, command_text, response, success, duration_ms, source, matched_by, hour, day_of_week, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trace_id, skill_name, command_text[:500], response[:1000],
            1 if success else 0, duration_ms, source, matched_by,
            now.hour, now.weekday(), created_at
        ))

        # Update aggregate stats
        cursor.execute("""
            INSERT INTO skill_stats (skill_name, total_executions, successful_executions, failed_executions, total_duration_ms, last_used_at, created_at)
            VALUES (?, 1, ?, ?, ?, ?, ?)
            ON CONFLICT(skill_name) DO UPDATE SET
                total_executions = total_executions + 1,
                successful_executions = successful_executions + ?,
                failed_executions = failed_executions + ?,
                total_duration_ms = total_duration_ms + ?,
                last_used_at = ?
        """, (
            skill_name,
            1 if success else 0,
            0 if success else 1,
            duration_ms,
            created_at,
            1 if success else 0,
            0 if success else 1,
            duration_ms,
            created_at
        ))

        conn.commit()
    except Exception as e:
        print(f"[Analytics] Log error: {e}")
    finally:
        conn.close()


def get_skill_stats(skill_name: Optional[str] = None) -> dict:
    """Get statistics for a skill or all skills."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if skill_name:
        cursor.execute("SELECT * FROM skill_stats WHERE skill_name = ?", (skill_name,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return dict(row)
        return {}
    else:
        cursor.execute("SELECT * FROM skill_stats ORDER BY total_executions DESC")
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]


def get_usage_trends(days: int = 7) -> dict:
    """Get usage trends over the last N days."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cutoff = (datetime.now() - timedelta(days=days)).timestamp()

    # Daily usage
    cursor.execute("""
        SELECT DATE(created_at, 'unixepoch', 'localtime') as date,
               COUNT(*) as executions,
               SUM(success) as successes,
               AVG(duration_ms) as avg_duration
        FROM skill_executions
        WHERE created_at >= ?
        GROUP BY DATE(created_at, 'unixepoch', 'localtime')
        ORDER BY date DESC
    """, (cutoff,))
    daily = [dict(row) for row in cursor.fetchall()]

    # Hourly heatmap (average by hour of day)
    cursor.execute("""
        SELECT hour, COUNT(*) as executions
        FROM skill_executions
        WHERE created_at >= ?
        GROUP BY hour
        ORDER BY hour
    """, (cutoff,))
    hourly = {row['hour']: row['executions'] for row in cursor.fetchall()}

    # Day of week distribution
    cursor.execute("""
        SELECT day_of_week, COUNT(*) as executions
        FROM skill_executions
        WHERE created_at >= ?
        GROUP BY day_of_week
        ORDER BY day_of_week
    """, (cutoff,))
    dow = {row['day_of_week']: row['executions'] for row in cursor.fetchall()}

    conn.close()

    return {
        "daily": daily,
        "hourly": hourly,
        "day_of_week": dow,
        "period_days": days,
    }


def get_top_skills(limit: int = 10, days: int = 7) -> list:
    """Get most used skills over the last N days."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cutoff = (datetime.now() - timedelta(days=days)).timestamp()

    cursor.execute("""
        SELECT skill_name,
               COUNT(*) as executions,
               SUM(success) as successes,
               CAST(SUM(success) AS FLOAT) / COUNT(*) * 100 as success_rate,
               AVG(duration_ms) as avg_duration
        FROM skill_executions
        WHERE created_at >= ?
        GROUP BY skill_name
        ORDER BY executions DESC
        LIMIT ?
    """, (cutoff, limit))

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def get_recent_executions(limit: int = 50) -> list:
    """Get most recent skill executions."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT skill_name, command_text, success, duration_ms, source, created_at
        FROM skill_executions
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,))

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def get_failure_analysis(days: int = 7) -> list:
    """Analyze skill failures over the last N days."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cutoff = (datetime.now() - timedelta(days=days)).timestamp()

    cursor.execute("""
        SELECT skill_name,
               COUNT(*) as failure_count,
               AVG(duration_ms) as avg_duration_before_failure,
               GROUP_CONCAT(DISTINCT source) as sources
        FROM skill_executions
        WHERE created_at >= ? AND success = 0
        GROUP BY skill_name
        ORDER BY failure_count DESC
    """, (cutoff,))

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def log_trigger_usage(skill_name: str, trigger_phrase: str, learned: bool = False) -> None:
    """Log trigger phrase usage for learning."""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO skill_triggers (skill_name, trigger_phrase, usage_count, learned, created_at)
        VALUES (?, ?, 1, ?, ?)
        ON CONFLICT(skill_name, trigger_phrase) DO UPDATE SET
            usage_count = usage_count + 1
    """, (skill_name, trigger_phrase, 1 if learned else 0, datetime.now().timestamp()))

    conn.commit()
    conn.close()


def get_learned_triggers(skill_name: Optional[str] = None) -> list:
    """Get learned trigger phrases."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if skill_name:
        cursor.execute("""
            SELECT * FROM skill_triggers
            WHERE skill_name = ? AND learned = 1
            ORDER BY usage_count DESC
        """, (skill_name,))
    else:
        cursor.execute("""
            SELECT * FROM skill_triggers
            WHERE learned = 1
            ORDER BY usage_count DESC
        """)

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def get_dashboard_data() -> dict:
    """Get complete dashboard data for the UI."""
    return {
        "summary": {
            "top_skills": get_top_skills(10, 7),
            "recent_executions": get_recent_executions(20),
            "failures": get_failure_analysis(7),
        },
        "trends": get_usage_trends(7),
        "stats": get_skill_stats(),
        "learned_triggers": get_learned_triggers(),
        "generated_at": datetime.now().isoformat(),
    }


# Initialize DB on import
init_db()


if __name__ == "__main__":
    # Test analytics
    import random

    print("Testing skill analytics...")

    # Log some test executions
    test_skills = ["morning_routine", "weather", "calendar", "system_status", "open_app"]
    for i in range(50):
        skill = random.choice(test_skills)
        log_execution(
            trace_id=f"test_{i}",
            skill_name=skill,
            command_text=f"Test command {i}",
            response="Test response",
            success=random.random() > 0.2,
            duration_ms=random.randint(100, 5000),
            source="voice",
            matched_by="trigger_match"
        )

    print("\nTop skills:")
    for s in get_top_skills(5):
        print(f"  {s['skill_name']}: {s['executions']} executions, {s['success_rate']:.1f}% success")

    print("\nDashboard summary:")
    data = get_dashboard_data()
    print(f"  Stats tracked: {len(data['stats'])} skills")
    print(f"  Learned triggers: {len(data['learned_triggers'])}")
