#!/usr/bin/env python3
"""
scripts/log_clip_performance.py — Log clip performance for Bolt's learning loop
=================================================================================
After you post a clip and it has been live for 24h+, log its performance.
Bolt uses this data to boost the ranking of trigger types that perform well.

Stores data in two places:
  - data/performance_outcomes.jsonl (append-only log for weekly analysis)
  - clip_history.json (per-game averages used by Clip_Ranker)

Usage:
  python3 scripts/log_clip_performance.py
    # interactive mode

  python3 scripts/log_clip_performance.py --trigger ace --views 15000 --likes 1200 --game "Marvel Rivals"
    # quick mode

  python3 scripts/log_clip_performance.py --list
    # view recent logged entries
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from modules.Clip_Ranker import update_historical_performance

DATA_DIR = ROOT / "data"
OUTCOMES_FILE = DATA_DIR / "performance_outcomes.jsonl"


def _load_config_game() -> str:
    config_path = ROOT / "config.json"
    if config_path.exists():
        try:
            with open(config_path) as f:
                return json.load(f).get("game", "Unknown")
        except Exception:
            pass
    return "Unknown"


def log_performance(game: str, trigger: str, views: int, likes: int) -> dict:
    """Append a performance outcome and update historical averages."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": datetime.now().isoformat(),
        "game": game,
        "trigger": trigger,
        "views": views,
        "likes": likes,
        "success": views >= 1000 or (likes / views * 100) >= 5 if views > 0 else False,
    }

    with open(OUTCOMES_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")

    update_historical_performance(game, trigger, views, likes)

    return entry


def list_recent(limit: int = 20):
    """Print recent performance entries."""
    if not OUTCOMES_FILE.exists():
        print("No performance data logged yet.")
        return

    entries = []
    with open(OUTCOMES_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except Exception:
                continue

    if not entries:
        print("No valid performance entries found.")
        return

    print(f"\nLast {limit} logged performances:\n")
    print(f"{'Date':12} {'Game':18} {'Trigger':12} {'Views':>10} {'Likes':>8} {'Success'}")
    print("-" * 70)
    for e in entries[-limit:]:
        date = e["timestamp"][:10]
        success = "✓" if e.get("success") else "○"
        print(
            f"{date:12} {e['game']:18} {e['trigger']:12} "
            f"{e['views']:>10,} {e['likes']:>8,} {success}"
        )
    print()


def main():
    parser = argparse.ArgumentParser(description="Log clip performance for Bolt")
    parser.add_argument("--game", "-g", help="Game name (defaults to config.json game)")
    parser.add_argument("--trigger", "-t", help="Trigger type, e.g. ace, kill, clutch")
    parser.add_argument("--views", "-v", type=int, help="View count after ~24h")
    parser.add_argument("--likes", "-l", type=int, default=0, help="Like count")
    parser.add_argument("--list", action="store_true", help="List recent entries")
    args = parser.parse_args()

    if args.list:
        list_recent()
        return

    game = args.game or _load_config_game()

    if args.trigger and args.views is not None:
        entry = log_performance(game, args.trigger, args.views, args.likes)
        print(
            f"\n✓ Logged: {entry['trigger']} in {entry['game']} — "
            f"{entry['views']:,} views, {entry['likes']:,} likes "
            f"({'success' if entry['success'] else 'no success'})\n"
        )
        return

    # Interactive mode
    print("\n=== Bolt Clip Performance Logger ===\n")
    print(f"Game (from config): {game}")
    change = input("Change game? [y/N]: ").strip().lower()
    if change == "y":
        game = input("Game name: ").strip() or game

    trigger = input("Trigger type (e.g. ace, kill, clutch, raid): ").strip().lower()
    while not trigger:
        trigger = input("Trigger type is required: ").strip().lower()

    views = int(input("View count: ").strip() or "0")
    likes = int(input("Like count: ").strip() or "0")

    entry = log_performance(game, trigger, views, likes)
    print(
        f"\n✓ Logged: {entry['trigger']} in {entry['game']} — "
        f"{entry['views']:,} views, {entry['likes']:,} likes "
        f"({'success' if entry['success'] else 'no success'})\n"
    )


if __name__ == "__main__":
    main()
