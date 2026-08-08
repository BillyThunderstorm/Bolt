#!/usr/bin/env python3
"""
scripts/sync_youtube_stats.py — Pull YouTube views/likes into Bolt's learning loop
==================================================================================
Fetches your channel uploads (and Shorts) via YouTube Data API v3 and
writes/updates rows in Data/performance_outcomes.jsonl.

Usage:
  python3 scripts/sync_youtube_stats.py              # live sync
  python3 scripts/sync_youtube_stats.py --dry-run
  python3 scripts/sync_youtube_stats.py --shorts-only --min-age-hours 24
  python3 scripts/sync_youtube_stats.py --json

Setup (one-time):
  1. Google Cloud → enable YouTube Data API v3 → OAuth Desktop client
  2. python3 scripts/get_youtube_token.py
  3. Optional cron (daily 10:15am):
       15 10 * * * cd /path/to/Bolt && .venv/bin/python3 scripts/sync_youtube_stats.py \\
         --min-age-hours 24 >> logs/youtube_stats_sync.log 2>&1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from _paths import REPO_ROOT  # noqa: E402

_CORE = REPO_ROOT / "Core"
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync YouTube post stats into Bolt performance_outcomes.jsonl"
    )
    parser.add_argument("--limit", type=int, default=50, help="Max videos (default 50)")
    parser.add_argument(
        "--min-age-hours",
        type=float,
        default=0.0,
        help="Skip videos younger than N hours",
    )
    parser.add_argument(
        "--shorts-only",
        action="store_true",
        help="Only keep videos ≤60s (typical Shorts)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and match only; do not write files",
    )
    parser.add_argument(
        "--no-learning",
        action="store_true",
        help="Write outcomes but skip Clip_Ranker / decision engine",
    )
    parser.add_argument(
        "--game",
        default=None,
        help="Default game when a video cannot be matched",
    )
    parser.add_argument("--json", action="store_true", help="Print full result as JSON")
    args = parser.parse_args()

    from modules.Performance_Sync import print_sync_report, sync_youtube_stats

    result = sync_youtube_stats(
        limit=args.limit,
        min_age_hours=args.min_age_hours,
        dry_run=args.dry_run,
        default_game=args.game,
        feed_learning=not args.no_learning,
        shorts_only=args.shorts_only,
    )

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print_sync_report(result)
        if not result.get("ok"):
            print(
                "  Tip: create a Google OAuth client and run:\n"
                "    python3 scripts/get_youtube_token.py\n"
            )

    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
