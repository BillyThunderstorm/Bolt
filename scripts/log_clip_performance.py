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
from datetime import datetime
from pathlib import Path

# Make sure we can import from the project regardless of cwd
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
PERFORMANCE_OUTCOMES_FILE = ROOT / "data" / "performance_outcomes.jsonl"


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

    clip_path = input("  Clip filename/path (optional): ").strip()
    note = input("  Note about why it worked/flopped (optional): ").strip()

    _commit(game, trigger, views, likes, clip_path=clip_path, note=note)


def _like_rate(views: int, likes: int) -> float:
    if views <= 0:
        return 0.0
    return round(likes / views, 4)


def _is_success(views: int, likes: int) -> bool:
    # Early creator-friendly threshold: do not require viral numbers before Bolt
    # learns a positive signal. A strong like rate can count even with modest views.
    return views >= 1000 or _like_rate(views, likes) >= 0.05


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload) + "\n")


def _record_learning_outcome(
    game: str,
    trigger: str,
    views: int,
    likes: int,
    clip_path: str = "",
    platform: str = "TikTok",
    note: str = "",
) -> dict:
    success = _is_success(views, likes)
    outcome = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "game": game,
        "trigger": trigger,
        "views": views,
        "likes": likes,
        "like_rate": _like_rate(views, likes),
        "success": success,
        "clip_path": clip_path,
        "platform": platform,
        "note": note,
    }
    _append_jsonl(PERFORMANCE_OUTCOMES_FILE, outcome)

    try:
        from modules.Think_Learn_Decide import ThinkLearnDecideEngine

        engine = ThinkLearnDecideEngine({"memory_auto_refresh": False})
        engine.learn_from_outcome("queue_clip", success=success, details=outcome)
    except Exception as exc:
        outcome["decision_learning_error"] = str(exc)

    try:
        from modules.Memory_Index import refresh_memory_index

        refresh_memory_index()
    except Exception as exc:
        outcome["index_refresh_error"] = str(exc)

    return outcome


def _commit(
    game: str,
    trigger: str,
    views: int,
    likes: int,
    clip_path: str = "",
    platform: str = "TikTok",
    note: str = "",
):
    """Call the existing Clip_Ranker function — the source of truth."""
    try:
        from modules.Clip_Ranker import update_historical_performance
    except ImportError as exc:
        print(f"  Could not import Clip_Ranker: {exc}")
        print(f"  Make sure you're running from the Bolt project root.")
        sys.exit(1)

    update_historical_performance(game, trigger, views, likes)
    outcome = _record_learning_outcome(
        game=game,
        trigger=trigger,
        views=views,
        likes=likes,
        clip_path=clip_path,
        platform=platform,
        note=note,
    )
    print(f"\n  ✓ Logged: {trigger} → {views:,} views, {likes:,} likes for {game}")
    print(f"  Future {trigger} clips will get a boosted ranking score.\n")
    print(
        f"  Bolt outcome memory: {'success' if outcome['success'] else 'underperformed'} "
        f"(like rate {outcome['like_rate']:.1%})"
    )
    print(f"  Saved outcome: {PERFORMANCE_OUTCOMES_FILE}\n")


def main():
    p = argparse.ArgumentParser(
        description="Log a posted clip's TikTok performance so Bolt learns what works.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--trigger", help="Clip trigger type (kill, ace, donation, etc.)")
    p.add_argument("--views", type=int, help="View count after 24h+")
    p.add_argument("--likes", type=int, default=0, help="Like count (optional)")
    p.add_argument("--clip", default="", help="Clip path or filename this performance belongs to")
    p.add_argument("--game", default=None, help="Override game name (defaults to config.json)")
    p.add_argument("--platform", default="TikTok", help="Platform posted to (default: TikTok)")
    p.add_argument("--note", default="", help="Optional note about why it worked/flopped")
    p.add_argument("--list", action="store_true", help="Show current performance history and exit")

    args = p.parse_args()
    game = args.game or _load_config_game()

    if args.list:
        show_current(game)
        return

    if args.trigger and args.views is not None:
        _commit(
            game,
            args.trigger.lower(),
            args.views,
            args.likes,
            clip_path=args.clip,
            platform=args.platform,
            note=args.note,
        )
        return

    # No flags — drop into interactive mode
    try:
        interactive(game)
    except KeyboardInterrupt:
        print("\n  Aborted.")


if __name__ == "__main__":
    main()
