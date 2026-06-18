#!/usr/bin/env python3
"""
scripts/update_game_from_obs.py — Wire up OBS scene changes to update config.json

This script:
1. Loads the scene-to-game mapping from configs/scene_game_mapping.json
2. Starts the Stream_Monitor with a callback that updates config.json
3. Runs in the background while you stream

Usage:
    python3 scripts/update_game_from_obs.py

Or add to your launch.py so it starts automatically with Bolt.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

CONFIG_FILE = ROOT / "config.json"
MAPPING_FILE = ROOT / "configs" / "scene_game_mapping.json"


def update_config_game(new_game: str):
    """Update the game field in config.json."""
    if not CONFIG_FILE.exists():
        print(f"Config file not found: {CONFIG_FILE}")
        return

    try:
        with open(CONFIG_FILE) as f:
            config = json.load(f)

        current_game = config.get("game", "")
        if current_game == new_game:
            print(f"Game already set to '{new_game}' — no change needed")
            return

        config["game"] = new_game

        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
            f.write("\n")

        print(f"✓ Updated config.json: game = '{new_game}' (was '{current_game}')")

    except Exception as e:
        print(f"✗ Failed to update config: {e}")


def main():
    """Start OBS monitor with game-change callback."""
    from modules.Stream_Monitor import StreamMonitor

    print("Starting OBS game tracker...")
    print(f"  Mapping file: {MAPPING_FILE}")
    print(f"  Config file: {CONFIG_FILE}")
    print()
    print("Switch scenes in OBS to test. Bolt will update config.json automatically.")
    print("Press Ctrl+C to stop.\n")

    monitor = StreamMonitor(
        host="localhost",
        port=4455,
        on_game_changed=update_config_game,
    )

    try:
        monitor.start()
        # Keep running
        while True:
            import time

            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping OBS game tracker...")
        monitor.stop()


if __name__ == "__main__":
    main()
