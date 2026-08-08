#!/usr/bin/env python3
"""
modules/Analytics_Tracker.py — Tier 2 (2.4) analytics summary
==============================================================
Reads Bolt's performance_outcomes.jsonl (one row per posted clip with
views/likes) and produces actionable summaries:

  - Per-trigger stats: avg views, avg likes, like rate, success rate
  - Per-game stats: same shape
  - Best posting times: hour-of-day buckets ranked by avg views
  - Overall summary: total posts, total views, top trigger, top game

This is the "continuous learning" piece of the Tier 2 spec — Bolt can
now see which trigger types and posting times actually perform, and
Clip_Ranker can later consume the output to boost winners.

Reads local JSONL written by:
  - scripts/log_clip_performance.py (manual entry)
  - scripts/sync_tiktok_stats.py / modules.Performance_Sync (TikTok API pull)

TikTok API pulls require a token with the video.list scope. YouTube analytics
are still a future add-on.

Usage:
    from modules.Analytics_Tracker import summarize, print_summary
    summary = summarize()          # returns a dict
    print_summary(summary)         # prints a human table

    python3 -m modules.Analytics_Tracker
    python3 -m modules.Analytics_Tracker --days 30 --top 5
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

# Repo root is two parents up from Core/modules/. Same convention as
# Memory_Index and other modules so this works whether you import it
# from Core/, the repo root, or a test.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Prefer the canonical Data/ path; fall back to legacy nested locations.
_OUTCOME_CANDIDATES = (
    PROJECT_ROOT / "Data" / "performance_outcomes.jsonl",
    PROJECT_ROOT / "Data" / "data" / "performance_outcomes.jsonl",
    PROJECT_ROOT / "data" / "performance_outcomes.jsonl",
)
PERFORMANCE_OUTCOMES_FILE = _OUTCOME_CANDIDATES[0]


def _resolve_outcomes_path(path: Optional[Path] = None) -> Path:
    if path is not None:
        return path
    for candidate in _OUTCOME_CANDIDATES:
        if candidate.exists():
            return candidate
    return PERFORMANCE_OUTCOMES_FILE


def _load_outcomes(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load all performance outcomes from the JSONL file. Skips blank/bad lines."""
    path = _resolve_outcomes_path(path)
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                # One bad row shouldn't kill the whole summary.
                continue
    return rows


def _within_days(rows: List[Dict[str, Any]], days: Optional[int]) -> List[Dict[str, Any]]:
    """Filter rows to only those within the last `days` days. None = no filter."""
    if days is None or not rows:
        return rows
    cutoff = datetime.now().timestamp() - (days * 86400)
    filtered: List[Dict[str, Any]] = []
    for r in rows:
        ts_str = r.get("timestamp")
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str).timestamp()
        except (ValueError, TypeError):
            continue
        if ts >= cutoff:
            filtered.append(r)
    return filtered


def _group_stats(rows: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    """Group rows by `key` (e.g. 'trigger', 'game', 'platform') and compute stats.

    Returns a list of dicts sorted by avg_views desc:
      { 'name': str, 'count': int, 'avg_views': float,
        'avg_likes': float, 'avg_like_rate': float, 'success_rate': float }
    """
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        name = r.get(key) or "unknown"
        buckets[name].append(r)

    out: List[Dict[str, Any]] = []
    for name, items in buckets.items():
        views = [r.get("views", 0) or 0 for r in items]
        likes = [r.get("likes", 0) or 0 for r in items]
        like_rates = [r.get("like_rate", 0.0) or 0.0 for r in items]
        successes = [1 if r.get("success") else 0 for r in items]
        out.append(
            {
                "name": name,
                "count": len(items),
                "avg_views": round(statistics.mean(views), 1) if views else 0,
                "avg_likes": round(statistics.mean(likes), 1) if likes else 0,
                "avg_like_rate": round(statistics.mean(like_rates), 2) if like_rates else 0,
                "success_rate": round(100 * sum(successes) / len(successes), 1) if successes else 0,
            }
        )
    out.sort(key=lambda r: r["avg_views"], reverse=True)
    return out


def _best_posting_times(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Bucket outcomes by hour-of-day and rank by avg views.

    "Hour-of-day" is local time from the timestamp field. Buckets with fewer
    than 2 samples are still reported (they show up at the bottom) but the
    caller may want to filter them.
    """
    buckets: Dict[int, List[int]] = defaultdict(list)
    for r in rows:
        ts_str = r.get("timestamp")
        if not ts_str:
            continue
        try:
            hour = datetime.fromisoformat(ts_str).hour
        except (ValueError, TypeError):
            continue
        buckets[hour].append(r.get("views", 0) or 0)

    out: List[Dict[str, Any]] = []
    for hour, views in sorted(buckets.items()):
        out.append(
            {
                "hour": hour,
                "count": len(views),
                "avg_views": round(statistics.mean(views), 1) if views else 0,
            }
        )
    out.sort(key=lambda r: r["avg_views"], reverse=True)
    return out


def summarize(
    path: Optional[Path] = None,
    days: Optional[int] = None,
) -> Dict[str, Any]:
    """Build the full analytics summary. Returns a dict ready for printing or JSON dump."""
    resolved = _resolve_outcomes_path(path)
    rows = _load_outcomes(resolved)
    rows = _within_days(rows, days)

    total_views = sum(r.get("views", 0) or 0 for r in rows)
    total_likes = sum(r.get("likes", 0) or 0 for r in rows)
    successes = sum(1 for r in rows if r.get("success"))

    return {
        "source_file": str(resolved),
        "row_count": len(rows),
        "total_views": total_views,
        "total_likes": total_likes,
        "success_count": successes,
        "success_rate": round(100 * successes / len(rows), 1) if rows else 0,
        "by_trigger": _group_stats(rows, "trigger"),
        "by_game": _group_stats(rows, "game"),
        "by_platform": _group_stats(rows, "platform"),
        "best_posting_hours": _best_posting_times(rows),
        "filter_days": days,
    }


def _row(label: str, value: Any, width: int = 28) -> str:
    return f"  {label:<{width}}{value}"


def print_summary(summary: Dict[str, Any], top: int = 5) -> None:
    """Pretty-print a summary to stdout. `top` limits per-group lists."""
    print("=" * 60)
    print(f"  BOLT PERFORMANCE SUMMARY")
    print("=" * 60)
    if summary.get("filter_days"):
        print(_row("Filter (last N days):", summary["filter_days"]))
    print(_row("Source file:", summary["source_file"]))
    print(_row("Posts analysed:", summary["row_count"]))
    if summary["row_count"] == 0:
        print("\n  No performance data yet. Log a clip with:")
        print("    python3 scripts/log_clip_performance.py --trigger ace --views 1200 --game 'Marvel Rivals'")
        return

    print(_row("Total views:", summary["total_views"]))
    print(_row("Total likes:", summary["total_likes"]))
    print(_row("Success count:", f"{summary['success_count']} ({summary['success_rate']}%)"))

    for group_key, title in [
        ("by_trigger", "TOP TRIGGERS (by avg views)"),
        ("by_game", "TOP GAMES (by avg views)"),
        ("by_platform", "TOP PLATFORMS (by avg views)"),
    ]:
        rows = summary[group_key]
        if not rows:
            continue
        print()
        print(f"  {title}")
        print("  " + "-" * 56)
        print(f"  {'name':<20} {'count':>5} {'avg_views':>10} {'like_rate':>10} {'success':>8}")
        for r in rows[:top]:
            print(
                f"  {str(r['name'])[:20]:<20} "
                f"{r['count']:>5} "
                f"{r['avg_views']:>10} "
                f"{r['avg_like_rate']:>9}% "
                f"{r['success_rate']:>7}%"
            )

    hours = summary["best_posting_hours"]
    if hours:
        print()
        print("  BEST POSTING HOURS (by avg views)")
        print("  " + "-" * 56)
        for h in hours[:top]:
            label = f"{h['hour']:02d}:00-{h['hour']:02d}:59"
            print(
                f"  {label}   posts={h['count']:>3}   "
                f"avg_views={h['avg_views']}"
            )
    print("=" * 60)


# ── CLI ────────────────────────────────────────────────────────────────────────


def _main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Summarize Bolt's clip performance outcomes."
    )
    parser.add_argument(
        "--file", type=Path, default=PERFORMANCE_OUTCOMES_FILE,
        help="Path to performance_outcomes.jsonl",
    )
    parser.add_argument(
        "--days", type=int, default=None,
        help="Only include rows from the last N days (default: all)",
    )
    parser.add_argument(
        "--top", type=int, default=5,
        help="How many rows per group to show (default: 5)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output JSON instead of a human table",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    summary = summarize(path=args.file, days=args.days)
    if args.json:
        json.dump(summary, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print_summary(summary, top=args.top)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
