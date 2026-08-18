#!/usr/bin/env python3
"""
scripts/sync_tiktok_stats.py — Pull TikTok views/likes into Bolt's learning loop
================================================================================
Fetches your public TikTok videos via the Open API (scope: video.list) and
writes/updates rows in Data/performance_outcomes.jsonl.

Usage:
  python3 scripts/sync_tiktok_stats.py              # live sync
  python3 scripts/sync_tiktok_stats.py --dry-run    # fetch + match only
  python3 scripts/sync_tiktok_stats.py --limit 20 --min-age-hours 24
  python3 scripts/sync_tiktok_stats.py --json       # machine-readable summary

Setup (one-time):
  1. TikTok Developer app with Login Kit + video.list scope approved
  2. python3 scripts/get_tiktok_token.py --scopes \\
       "user.info.basic,video.list,video.publish,video.upload"
  3. Cron (daily, e.g. 10am):
       0 10 * * * cd /path/to/Bolt && .venv/bin/python3 scripts/sync_tiktok_stats.py \\
         --min-age-hours 24 >> logs/tiktok_stats_sync.log 2>&1
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

# Ensure Core/modules is importable
_CORE = REPO_ROOT / "Core"
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync TikTok post stats into Bolt performance_outcomes.jsonl"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max videos to fetch (default 50)",
    )
    parser.add_argument(
        "--min-age-hours",
        type=float,
        default=0.0,
        help="Skip videos younger than N hours (e.g. 24 for mature metrics)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and match only; do not write files or feed learning",
    )
    parser.add_argument(
        "--no-learning",
        action="store_true",
        help="Write outcomes but skip Clip_Ranker / decision-engine updates",
    )
    parser.add_argument(
        "--game",
        default=None,
        help="Default game name when a video cannot be matched (else config.json)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full result as JSON instead of a table",
    )
    args = parser.parse_args()

    from modules.TikTok_Auth import TIKTOK_API_PAUSE_MESSAGE, tiktok_api_enabled
    from modules.Performance_Sync import print_sync_report, sync_tiktok_stats

    if not tiktok_api_enabled():
        if args.json:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "paused": True,
                        "skipped": True,
                        "platform": "TikTok",
                        "error": TIKTOK_API_PAUSE_MESSAGE,
                    },
                    indent=2,
                )
            )
        else:
            print(f"\n  {TIKTOK_API_PAUSE_MESSAGE}\n")
        return 0

    result = sync_tiktok_stats(
        limit=args.limit,
        min_age_hours=args.min_age_hours,
        dry_run=args.dry_run,
        default_game=args.game,
        feed_learning=not args.no_learning,
    )

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print_sync_report(result)
        if not result.get("ok"):
            print(
                "  Tip: re-authorize with video.list scope:\n"
                '    python3 scripts/get_tiktok_token.py --scopes '
                '"user.info.basic,video.list,video.publish,video.upload"\n'
            )

    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
