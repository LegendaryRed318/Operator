#!/usr/bin/env python3
"""
skill_scheduler.py - Cron-based scheduler for skills.
Run skills automatically on schedules (e.g., morning briefing at 8am).
"""

import json
import threading
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional, Dict, List

from paths import LOGS_PATH

logger = logging.getLogger(__name__)

SCHEDULES_FILE = LOGS_PATH / "skill_schedules.json"


class SkillScheduler:
    """Schedule skills to run on cron-like intervals."""

    def __init__(self, skill_executor_callback: Optional[Callable] = None):
        self.schedules: Dict[str, dict] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._skill_executor = skill_executor_callback
        self._load_schedules()

    def _load_schedules(self):
        """Load schedules from disk."""
        if SCHEDULES_FILE.exists():
            try:
                with open(SCHEDULES_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.schedules = data.get("schedules", {})
            except Exception as e:
                logger.error(f"[Scheduler] Failed to load schedules: {e}")
                self.schedules = {}

    def _save_schedules(self):
        """Save schedules to disk."""
        try:
            LOGS_PATH.mkdir(parents=True, exist_ok=True)
            with open(SCHEDULES_FILE, "w", encoding="utf-8") as f:
                json.dump({"schedules": self.schedules}, f, indent=2)
        except Exception as e:
            logger.error(f"[Scheduler] Failed to save schedules: {e}")

    def add_schedule(
        self,
        schedule_id: str,
        skill_name: str,
        cron_expression: str,
        enabled: bool = True,
        params: Optional[dict] = None,
        description: str = "",
    ) -> bool:
        """
        Add a scheduled skill.

        Cron expression format: "minute hour day_of_month month day_of_week"
        Examples:
            "0 8 * * *" - Every day at 8:00 AM
            "*/30 * * * *" - Every 30 minutes
            "0 9 * * 1-5" - Weekdays at 9:00 AM
            "0 18 * * *" - Every day at 6:00 PM
        """
        with self._lock:
            self.schedules[schedule_id] = {
                "skill_name": skill_name,
                "cron": cron_expression,
                "enabled": enabled,
                "params": params or {},
                "description": description,
                "created_at": datetime.now().isoformat(),
                "last_run": None,
                "next_run": self._calculate_next_run(cron_expression),
                "run_count": 0,
            }
            self._save_schedules()
            return True

    def remove_schedule(self, schedule_id: str) -> bool:
        """Remove a schedule."""
        with self._lock:
            if schedule_id in self.schedules:
                del self.schedules[schedule_id]
                self._save_schedules()
                return True
            return False

    def enable_schedule(self, schedule_id: str, enabled: bool = True) -> bool:
        """Enable or disable a schedule."""
        with self._lock:
            if schedule_id in self.schedules:
                self.schedules[schedule_id]["enabled"] = enabled
                self._save_schedules()
                return True
            return False

    def get_schedule(self, schedule_id: str) -> Optional[dict]:
        """Get a schedule by ID."""
        return self.schedules.get(schedule_id)

    def list_schedules(self) -> List[dict]:
        """List all schedules."""
        return [
            {**{"id": sid}, **data}
            for sid, data in self.schedules.items()
        ]

    def start(self):
        """Start the scheduler background thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("[Scheduler] Started")

    def stop(self):
        """Stop the scheduler."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("[Scheduler] Stopped")

    def _run_loop(self):
        """Main scheduler loop - check every 10 seconds."""
        while self._running:
            try:
                self._check_and_run_schedules()
            except Exception as e:
                logger.error(f"[Scheduler] Loop error: {e}")
            time.sleep(10)

    def _check_and_run_schedules(self):
        """Check if any schedules should run and execute them."""
        now = datetime.now()
        to_run = []

        with self._lock:
            for schedule_id, schedule in self.schedules.items():
                if not schedule.get("enabled", True):
                    continue

                next_run_str = schedule.get("next_run")
                if not next_run_str:
                    continue

                try:
                    next_run = datetime.fromisoformat(next_run_str)
                    if now >= next_run:
                        to_run.append(schedule_id)
                        # Calculate next run time
                        self.schedules[schedule_id]["next_run"] = self._calculate_next_run(
                            schedule["cron"]
                        )
                except Exception as e:
                    logger.error(f"[Scheduler] Parse error for {schedule_id}: {e}")

        # Run scheduled skills
        for schedule_id in to_run:
            self._run_scheduled_skill(schedule_id)

    def _run_scheduled_skill(self, schedule_id: str):
        """Execute a scheduled skill."""
        schedule = self.schedules.get(schedule_id)
        if not schedule:
            return

        skill_name = schedule.get("skill_name")
        params = schedule.get("params", {})

        logger.info(f"[Scheduler] Running scheduled skill: {skill_name} ({schedule_id})")

        try:
            if self._skill_executor:
                result = self._skill_executor(skill_name, params)
                logger.info(f"[Scheduler] Result: {result}")
            else:
                # Fallback: try direct dispatch
                from skills import dispatch_skill_command
                result = dispatch_skill_command(
                    skill_name=skill_name,
                    command_text=params.get("text", ""),
                    params=params,
                    source="scheduler"
                )
                logger.info(f"[Scheduler] Result: {result}")

            # Update run stats
            with self._lock:
                self.schedules[schedule_id]["last_run"] = datetime.now().isoformat()
                self.schedules[schedule_id]["run_count"] = (
                    self.schedules[schedule_id].get("run_count", 0) + 1
                )
                self._save_schedules()

        except Exception as e:
            logger.error(f"[Scheduler] Execution error for {schedule_id}: {e}")

    def _parse_cron(self, cron_expr: str) -> dict:
        """Parse a cron expression into components."""
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: {cron_expr}")

        return {
            "minute": parts[0],
            "hour": parts[1],
            "day": parts[2],
            "month": parts[3],
            "dow": parts[4],  # day of week
        }

    def _matches_cron(self, dt: datetime, cron_expr: str) -> bool:
        """Check if a datetime matches a cron expression."""
        try:
            c = self._parse_cron(cron_expr)

            # Minute check
            if c["minute"] != "*":
                if "/" in c["minute"]:
                    base, step = c["minute"].split("/")
                    step = int(step)
                    if dt.minute % step != 0:
                        return False
                elif "," in c["minute"]:
                    if dt.minute not in [int(x) for x in c["minute"].split(",")]:
                        return False
                elif "-" in c["minute"]:
                    start, end = c["minute"].split("-")
                    if not (int(start) <= dt.minute <= int(end)):
                        return False
                else:
                    if dt.minute != int(c["minute"]):
                        return False

            # Hour check
            if c["hour"] != "*":
                if "/" in c["hour"]:
                    _, step = c["hour"].split("/")
                    if dt.hour % int(step) != 0:
                        return False
                elif "," in c["hour"]:
                    if dt.hour not in [int(x) for x in c["hour"].split(",")]:
                        return False
                elif "-" in c["hour"]:
                    start, end = c["hour"].split("-")
                    if not (int(start) <= dt.hour <= int(end)):
                        return False
                else:
                    if dt.hour != int(c["hour"]):
                        return False

            # Day of month check
            if c["day"] != "*":
                if dt.day != int(c["day"]):
                    return False

            # Month check
            if c["month"] != "*":
                if dt.month != int(c["month"]):
                    return False

            # Day of week check
            if c["dow"] != "*":
                if "-" in c["dow"]:
                    start, end = c["dow"].split("-")
                    if not (int(start) <= dt.weekday() <= int(end)):
                        return False
                else:
                    if dt.weekday() != int(c["dow"]):
                        return False

            return True

        except Exception:
            return False

    def _calculate_next_run(self, cron_expr: str) -> str:
        """Calculate the next run time for a cron expression."""
        now = datetime.now()
        # Check next 24 hours
        for minute_offset in range(1, 24 * 60):
            candidate = now.replace(
                second=0,
                microsecond=0
            )
            candidate = candidate + __import__('datetime').timedelta(minutes=minute_offset)

            if self._matches_cron(candidate, cron_expr):
                return candidate.isoformat()

        # Fallback: 1 hour from now
        return (now + __import__('datetime').timedelta(hours=1)).isoformat()


# Global scheduler instance
_scheduler: Optional[SkillScheduler] = None


def get_scheduler(skill_executor_callback: Optional[Callable] = None) -> SkillScheduler:
    """Get or create the global scheduler."""
    global _scheduler
    if _scheduler is None:
        _scheduler = SkillScheduler(skill_executor_callback)
    return _scheduler


def schedule_skill(
    schedule_id: str,
    skill_name: str,
    cron_expression: str,
    description: str = "",
    params: Optional[dict] = None,
) -> bool:
    """Convenience function to schedule a skill."""
    scheduler = get_scheduler()
    return scheduler.add_schedule(
        schedule_id, skill_name, cron_expression,
        params=params, description=description
    )


# Predefined schedule templates
PREDEFINED_SCHEDULES = {
    "morning_briefing": {
        "cron": "0 8 * * *",
        "description": "Daily morning briefing at 8 AM",
        "skill": "morning_routine",
    },
    "evening_summary": {
        "cron": "0 18 * * *",
        "description": "Evening system summary at 6 PM",
        "skill": "system_health",
    },
    "hourly_check": {
        "cron": "0 * * * *",
        "description": "Hourly status check",
        "skill": "system_status",
    },
    "workday_start": {
        "cron": "0 9 * * 1-5",
        "description": "Workday start routine (weekdays at 9 AM)",
        "skill": "morning_routine",
    },
    "backup_friday": {
        "cron": "0 17 * * 5",
        "description": "Weekly backup on Friday at 5 PM",
        "skill": "backup_now",
    },
}


def setup_predefined_schedules():
    """Set up common predefined schedules."""
    scheduler = get_scheduler()
    for schedule_id, config in PREDEFINED_SCHEDULES.items():
        if not scheduler.get_schedule(schedule_id):
            scheduler.add_schedule(
                schedule_id,
                config["skill"],
                config["cron"],
                description=config["description"],
            )
    logger.info("[Scheduler] Predefined schedules configured")


if __name__ == "__main__":
    # Test scheduler
    logging.basicConfig(level=logging.INFO)

    print("Testing skill scheduler...")

    scheduler = get_scheduler()

    # Add test schedule
    scheduler.add_schedule(
        "test_schedule",
        "system_status",
        "*/2 * * * *",  # Every 2 minutes
        description="Test schedule",
    )

    print(f"Schedules: {scheduler.list_schedules()}")
    print(f"Next run: {scheduler.get_schedule('test_schedule')['next_run']}")

    # Start scheduler (will run in background)
    scheduler.start()

    print("Scheduler running... Press Ctrl+C to stop")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        scheduler.stop()
        print("Scheduler stopped")
