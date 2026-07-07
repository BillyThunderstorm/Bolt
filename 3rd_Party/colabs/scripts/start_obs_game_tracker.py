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
