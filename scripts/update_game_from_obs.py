#!/usr/bin/env python3
"""
scripts/update_game_from_obs.py — Wire up OBS scene changes to update config.json

This script:
1. Loads the scene-to-game mapping from configs/scene_game_mapping.json
2. Starts the Stream_Monitor with a callback that updates config.json
3. Runs in the background while you stream

Special mapping value "__twitch__" means: fetch the current game from the
Twitch Helix API instead of using a hardcoded game name. This lets you
switch scenes in OBS and have Bolt automatically pick up whatever game
you set on your Twitch channel — no manual config editing needed.

Usage:
    python3 scripts/update_game_from_obs.py

Or add to your launch.py so it starts automatically with Bolt.
"""

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

CONFIG_FILE = ROOT / "config.json"
MAPPING_FILE = ROOT / "configs" / "scene_game_mapping.json"

logger = logging.getLogger("bolt.obs_game_tracker")

# Sentinel: when a scene maps to this value, fetch the game from Twitch
TWITCH_LIVE_SENTINEL = "__twitch__"


def _resolve_game(mapped_value: str) -> str:
    """Resolve a mapped scene value to an actual game name.

    If the value is the Twitch sentinel, fetch the current game from the
    Twitch Helix API. Otherwise return the value as-is.
    """
    if mapped_value == TWITCH_LIVE_SENTINEL:
        try:
            from modules.twitch_api import get_current_game

            game = get_current_game()
            if game and game != "Unknown":
                logger.info("Fetched live game from Twitch: %s", game)
                return game
            logger.warning("Twitch returned no game — keeping previous value")
            return ""
        except Exception as exc:
            logger.warning("Failed to fetch game from Twitch: %s", exc)
            return ""
    return mapped_value


def update_config_game(new_game: str):
    """Update the game field in config.json.

    `new_game` is the already-resolved game name (the Stream_Monitor
    callback resolves the sentinel before calling this).
    """
    if not new_game:
        return

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


def _on_scene_changed(mapped_value: str):
    """Stream_Monitor callback — resolves the sentinel then updates config."""
    game = _resolve_game(mapped_value)
    if game:
        update_config_game(game)


def main():
    """Start OBS monitor with game-change callback."""
    from modules.Stream_Monitor import StreamMonitor

    print("Starting OBS game tracker...")
    print(f"  Mapping file: {MAPPING_FILE}")
    print(f"  Config file: {CONFIG_FILE}")
    print()
    print("Switch scenes in OBS to test. Bolt will update config.json automatically.")
    print("  Live Scene -> fetches current game from Twitch automatically")
    print("  BRB / Starting Soon / Ending / Intermission -> 'Just Chatting'")
    print("Press Ctrl+C to stop.\n")

    monitor = StreamMonitor(
        host="localhost",
        port=4455,
        on_game_changed=_on_scene_changed,
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
