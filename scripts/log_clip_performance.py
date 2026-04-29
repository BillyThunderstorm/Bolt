#!/usr/bin/env python3
"""
scripts/log_clip_performance.py — Close the learning loop
=========================================================
Tells Bolt how a posted clip actually performed on TikTok so future clips
with the same trigger type get a ranking boost (or penalty) accordingly.

Why this matters:
  Clip_Ranker._history_boost() already exists and reads from clip_history.json.
  But until you log real performance, that file stays empty and the boost is 0.
  This script is the bridge between "Billy posted a clip" and "Bolt learned
  what works."

Usage:
  Interactive (recommended for first time):
      python3 scripts/log_clip_performance.py

  Direct flags (faster once you know what you're doing):
      python3 scripts/log_clip_performance.py --trigger kill --views 12500 --likes 2100
      python3 scripts/log_clip_performance.py --trigger ace --views 540
      python3 scripts/log_clip_performance.py --list   # show what's currently logged

What gets recorded:
  clip_history.json (in repo root) gets updated like:
  {
    "Marvel Rivals": {
      "kill":       {"total_clips": 4, "total_views": 38400, "total_likes": 6200, "avg_views": 9600},
      "multi_kill": {"total_clips": 2, "total_views": 21000, "total_likes": 3100, "avg_views": 10500}
    }
  }

  Clip_Ranker uses avg_views to give a 0-15 point boost on future clips.
  10k+ avg views → max boost. 1k avg views → ~1.5 point boost.

Tips:
  - Wait at least 24 hours after posting before logging — early numbers lie
  - Only log clips that have stabilized (likes ratio matters more than raw views)
  - If a clip flops badly (under 200 views), still log it — Bolt needs the
    negative signal to avoid that trigger type drifting up the rankings
"""

import argparse
import json
import sys
from pathlib import Path

# Make sure we can import from the project regardless of cwd
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def _load_config_game() -> str:
    """Read the current game from config.json, default to 'Gaming'."""
    cfg = ROOT / "config.json"
    if cfg.exists():
        try:
            return json.load(open(cfg)).get("game", "Gaming")
        except Exception:
            pass
    return "Gaming"


def _load_history() -> dict:
    f = ROOT / "clip_history.json"
    if f.exists():
        try:
            return json.load(open(f))
        except Exception:
            return {}
    return {}


def show_current(game: str):
    """Print what's currently in clip_history.json for the current game."""
    history = _load_history()
    game_data = history.get(game, {})
    if not game_data:
        print(f"\n  No history yet for '{game}'. Log your first clip!\n")
        return

    print(f"\n  Performance history for: {game}")
    print(f"  {'-' * 60}")
    print(f"  {'Trigger':<14} {'Clips':>6} {'Total Views':>12} "
          f"{'Avg Views':>10} {'Boost':>7}")
    print(f"  {'-' * 60}")
    for trigger, data in sorted(game_data.items(),
                                 key=lambda kv: kv[1].get("avg_views", 0),
                                 reverse=True):
        clips = data.get("total_clips", 0)
        views = data.get("total_views", 0)
        avg   = data.get("avg_views", 0)
        boost = min(15.0, (avg / 10_000) * 15.0)
        print(f"  {trigger:<14} {clips:>6} {views:>12,} "
              f"{avg:>10,} {boost:>6.1f}p")
    print()


def interactive(game: str):
    """Walk Billy through logging a clip step-by-step."""
    print(f"\n  Logging clip performance for: {game}")
    print(f"  (Press Ctrl+C any time to cancel)\n")

    print("  Trigger types: kill, multi_kill, ace, donation, raid, sub,")
    print("                 resub, bits, chat_hype, highlight, manual\n")

    trigger = input("  Trigger type: ").strip().lower()
    if not trigger:
        print("  No trigger entered — aborted.")
        return

    try:
        views = int(input("  Views (after 24h+): ").strip().replace(",", ""))
    except ValueError:
        print("  Invalid number — aborted.")
        return

    likes_raw = input("  Likes (optional, press enter to skip): ").strip()
    likes = 0
    if likes_raw:
        try:
            likes = int(likes_raw.replace(",", ""))
        except ValueError:
            print("  Invalid likes — using 0.")
            likes = 0

    _commit(game, trigger, views, likes)


def _commit(game: str, trigger: str, views: int, likes: int):
    """Call the existing Clip_Ranker function — the source of truth."""
    try:
        from modules.Clip_Ranker import update_historical_performance
    except ImportError as exc:
        print(f"  Could not import Clip_Ranker: {exc}")
        print(f"  Make sure you're running from the Bolt project root.")
        sys.exit(1)

    update_historical_performance(game, trigger, views, likes)
    print(f"\n  ✓ Logged: {trigger} → {views:,} views, {likes:,} likes for {game}")
    print(f"  Future {trigger} clips will get a boosted ranking score.\n")


def main():
    p = argparse.ArgumentParser(
        description="Log a posted clip's TikTok performance so Bolt learns what works.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--trigger", help="Clip trigger type (kill, ace, donation, etc.)")
    p.add_argument("--views", type=int, help="View count after 24h+")
    p.add_argument("--likes", type=int, default=0, help="Like count (optional)")
    p.add_argument("--game", default=None, help="Override game name (defaults to config.json)")
    p.add_argument("--list", action="store_true", help="Show current performance history and exit")

    args = p.parse_args()
    game = args.game or _load_config_game()

    if args.list:
        show_current(game)
        return

    if args.trigger and args.views is not None:
        _commit(game, args.trigger.lower(), args.views, args.likes)
        return

    # No flags — drop into interactive mode
    try:
        interactive(game)
    except KeyboardInterrupt:
        print("\n  Aborted.")


if __name__ == "__main__":
    main()
