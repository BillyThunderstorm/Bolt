#!/usr/bin/env python3
"""
scripts/start_obs_game_tracker.py — start the OBS game tracker in the background

Runs ``scripts/update_game_from_obs.py`` (watch mode) as its own process,
appending to logs/obs_game_tracker.log. Its PID goes in
logs/obs_game_tracker.pid. Only one copy runs at a time.

Stop it with:  bolt obs-game stop
"""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from _paths import REPO_ROOT, DATA_DIR, CLIPS_DIR, LOGS_DIR, CONFIG_FILE  # noqa: E402

PROJECT_ROOT = REPO_ROOT
ROOT = REPO_ROOT
PID_FILE = LOGS_DIR / "obs_game_tracker.pid"
LOG_FILE = LOGS_DIR / "obs_game_tracker.log"


def running_pid():
    """PID of a live tracker, else None (stale PID files are removed)."""
    try:
        pid = int(PID_FILE.read_text().strip())
    except Exception:
        return None
    try:
        os.kill(pid, 0)
        return pid
    except OSError:
        try:
            PID_FILE.unlink()
        except Exception:
            pass
        return None


def main():
    tracker_script = ROOT / "scripts" / "update_game_from_obs.py"
    if not tracker_script.exists():
        print(f"Game tracker unavailable: missing {tracker_script}")
        return 0
    pid = running_pid()
    if pid:
        print(f"OBS game tracker already running (PID {pid}). Stop it with: bolt obs-game stop")
        return 0
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as log:
        log.write(f"\n=== start {datetime.now():%Y-%m-%d %H:%M:%S} ===\n")
        log.flush()
        proc = subprocess.Popen(
            [sys.executable, "-u", str(tracker_script)],
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
            cwd=str(ROOT),
            start_new_session=True,
        )
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    print(f"✓ OBS game tracker started in the background (PID {proc.pid})")
    print(f"  Log:  {LOG_FILE}")
    print("  Stop: bolt obs-game stop")
    return 0


if __name__ == "__main__":
    sys.exit(main())
