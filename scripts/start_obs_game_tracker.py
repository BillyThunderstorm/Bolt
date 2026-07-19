#!/usr/bin/env python3
"""
scripts/start_obs_game_tracker.py — Start OBS game tracking in background

This is a wrapper that starts the OBS game tracker as a background process.
Use this if you want to run the tracker separately from launch.py.

Usage:
    python3 scripts/start_obs_game_tracker.py &

Or add to your shell profile to start automatically when you open a terminal.
"""

import subprocess
import sys
from pathlib import Path

# Post-reorg path bootstrap. Adds the script's own dir to sys.path so
# `from _paths import …` works in both direct invocation and `from
# scripts import X` (test) contexts. The helper itself adds Core/ and
# 3rd_Party/llm/ to sys.path so `from modules import Y` resolves, and
# chdirs to the repo root for any CWD-relative paths the script uses.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from _paths import REPO_ROOT, DATA_DIR, CLIPS_DIR, LOGS_DIR, CONFIG_FILE  # noqa: E402

# Backward-compatible aliases for code that uses `ROOT` / `PROJECT_ROOT`.
PROJECT_ROOT = REPO_ROOT
ROOT = REPO_ROOT

ROOT = Path(__file__).parent.parent


def main():
    """Start the OBS game tracker as a background process."""
    tracker_script = ROOT / "scripts" / "update_game_from_obs.py"

    if not tracker_script.exists():
        print(f"Error: Tracker script not found at {tracker_script}")
        sys.exit(1)

    print("Starting OBS game tracker in background...")
    print(f"  Script: {tracker_script}")
    print(f"  Log: {ROOT}/logs/obs_game_tracker.log")
    print()
    print("The tracker will:")
    print("  • Watch for OBS scene changes")
    print("  • Auto-update config.json with the current game")
    print("  • Run silently in the background")
    print()
    print("To stop: kill the process or restart OBS")
    print()

    # Start as background process
    log_file = ROOT / "logs" / "obs_game_tracker.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    with open(log_file, "w") as log:
        subprocess.Popen(
            [sys.executable, str(tracker_script)],
            stdout=log,
            stderr=log,
            cwd=str(ROOT),
        )

    print(f"✓ Game tracker started (PID in background)")
    print(f"  Logs: {log_file}")


if __name__ == "__main__":
    main()
