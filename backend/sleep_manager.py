#!/usr/bin/env python3
"""
sleep_manager.py - Idle / sleep watcher for Operator.
Monitors API activity (via heartbeat file) and tracks inactivity.
After IDLE_TIMEOUT_SECONDS of no requests it enters sleep mode and
writes SLEEP to logs/sleep.flag so other services can react.
Activity resets the timer and restores AWAKE state.
"""

import time
from datetime import datetime
from pathlib import Path

# ── paths ─────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent
_ROOT = _HERE.parent
LOGS_DIR = _ROOT / "logs"

SLEEP_FLAG_PATH  = LOGS_DIR / "sleep.flag"
HEARTBEAT_PATH   = LOGS_DIR / "heartbeat.flag"   # touched by server.py on every request

# ── config ────────────────────────────────────────────────────────────────────
IDLE_TIMEOUT_SECONDS = 3 * 60 * 60   # 3 hours
CHECK_INTERVAL       = 60             # poll every 60 s
LOG_IDLE_EVERY       = 30             # log idle status every N minutes

LOGS_DIR.mkdir(parents=True, exist_ok=True)


# ── helpers ───────────────────────────────────────────────────────────────────

def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [SleepMgr] {msg}", flush=True)


def set_flag(state: str) -> None:
    """Write AWAKE or SLEEP to the flag file."""
    try:
        SLEEP_FLAG_PATH.write_text(state)
    except Exception as exc:
        log(f"WARNING — could not write sleep flag: {exc}")


def last_activity_ts() -> float:
    """Return epoch of last known activity (heartbeat mtime or now if absent)."""
    try:
        if HEARTBEAT_PATH.exists():
            return HEARTBEAT_PATH.stat().st_mtime
    except Exception:
        pass
    # If heartbeat has never been written, treat startup as the last activity.
    return time.time()


# ── main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    log(f"Started — idle timeout: {IDLE_TIMEOUT_SECONDS // 3600}h")
    log(f"Heartbeat file : {HEARTBEAT_PATH}")
    log(f"Sleep flag     : {SLEEP_FLAG_PATH}")

    set_flag("AWAKE")
    is_sleeping      = False
    last_log_minute  = -1

    while True:
        try:
            idle_secs = time.time() - last_activity_ts()
            idle_min  = int(idle_secs / 60)

            if idle_secs >= IDLE_TIMEOUT_SECONDS:
                if not is_sleeping:
                    log(f"Idle for {idle_min}m — entering sleep mode")
                    set_flag("SLEEP")
                    is_sleeping = True
            else:
                if is_sleeping:
                    log("Activity detected — resuming from sleep")
                    set_flag("AWAKE")
                    is_sleeping = False

                # Periodic status log (every LOG_IDLE_EVERY minutes, de-duped)
                if idle_min > 0 and (idle_min % LOG_IDLE_EVERY == 0) and idle_min != last_log_minute:
                    last_log_minute = idle_min
                    remaining_min = int((IDLE_TIMEOUT_SECONDS - idle_secs) / 60)
                    log(f"Active — idle {idle_min}m, sleep in ~{remaining_min}m")

        except Exception as exc:
            log(f"ERROR — {exc}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
