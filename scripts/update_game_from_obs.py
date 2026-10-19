#!/usr/bin/env python3
"""
scripts/update_game_from_obs.py — Wire up OBS scene changes to update config.json

This script:
1. Loads the scene-to-game mapping from Data/configs/scene_game_mapping.json
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

# Post-reorg path bootstrap. Adds the script's own dir to sys.path so
# `from _paths import …` works in both direct invocation and `from
# scripts import X` (test) contexts. The helper itself adds Core/ and
# 3rd_Party/llm/ to sys.path so `from modules import Y` resolves, and
# chdirs to the repo root for any CWD-relative paths the script uses.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from _paths import (  # noqa: E402
    REPO_ROOT,
    DATA_DIR,
    CLIPS_DIR,
    LOGS_DIR,
    CONFIG_FILE,
    CONFIG_DIR,
)

# Backward-compatible aliases for code that uses `ROOT` / `PROJECT_ROOT`.
# Do NOT overwrite ROOT / CONFIG_FILE after _paths — post-reorg layout.
PROJECT_ROOT = REPO_ROOT
ROOT = REPO_ROOT

# Scene→game mapping lives under Data/configs/ (not repo-root configs/).
MAPPING_FILE = CONFIG_DIR / "scene_game_mapping.json"

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


def update_config_game(new_game: str, source: str = "obs_scene"):
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
            _stamp_game(new_game, source, current_game)
            return

        config["game"] = new_game

        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
            f.write("\n")

        print(f"✓ Updated config.json: game = '{new_game}' (was '{current_game}')")
        _stamp_game(new_game, source, current_game)

    except Exception as e:
        print(f"✗ Failed to update config: {e}")


def _stamp_game(game: str, source: str, previous: str) -> None:
    """Record freshness in Data/configs/game_state.json (Game_Refresh). Soft."""
    try:
        from modules.Game_Refresh import record_change

        record_change(game, source, previous=previous)
    except Exception as exc:  # never break the tracker
        logger.warning("game_state stamp failed: %s", exc)


def _refresh_game(trigger: str) -> None:
    """Stream start / tracker start: re-resolve the game (Twitch → pin → keep)."""
    try:
        from modules.Game_Refresh import refresh

        r = refresh(source=trigger)
        print(f"[game refresh:{trigger}] game = {r.get('game')!r} via {r.get('resolved_via')}")
        if r.get("warning"):
            print(f"  WARNING: {r['warning']}")
    except Exception as exc:
        logger.warning("game refresh (%s) failed: %s", trigger, exc)


def _on_scene_changed(mapped_value: str):
    """Stream_Monitor callback — resolves the sentinel then updates config."""
    game = _resolve_game(mapped_value)
    if game:
        if mapped_value == TWITCH_LIVE_SENTINEL:
            source = "twitch"
        else:
            # A pinned Live Scene value is not proof of what is being played.
            try:
                mapping = json.loads(MAPPING_FILE.read_text())
                live = mapping.get("live_scene") or "Live Scene"
                pinned = (mapping.get("scenes") or {}).get(live)
            except Exception:
                pinned = None
            source = "obs_mapping_pin" if mapped_value == pinned else "obs_scene"
        update_config_game(game, source=source)


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

    # Refresh once now so a stale value never survives a tracker start.
    _refresh_game("tracker_start")

    monitor = StreamMonitor(
        host="localhost",
        port=4455,
        on_game_changed=_on_scene_changed,
        on_stream_start=lambda: _refresh_game("stream_start"),
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


# Docs / launch.py import this name
start_game_tracker = main


if __name__ == "__main__":
    main()
