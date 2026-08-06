#!/usr/bin/env python3
"""
modules/Checkup_Writer.py — Writes live data to Bolt_Checkup.html
===================================================================
The checkup dashboard is a static HTML file — it can't pull data by itself.
This module bridges that gap: it reads Bolt's real runtime data and writes
a small JavaScript file that the HTML page loads on refresh.

Why a .js file instead of JSON?
  Browsers block fetch() requests to local files (file:// protocol) due to
  security restrictions. But <script src="..."> for local files works fine.
  So we write the data as a JS variable: window.Bolt_DATA = {...}
  The HTML reads window.Bolt_DATA and populates itself.

When does this run?
  - Called by launch.py at startup (so the page is fresh when you open it)
  - Called by bot.py after each pipeline run (so stats update as clips process)
  - Can also be run standalone: python -m modules.Checkup_Writer
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

# Post-reorg layout: this file lives at Core/modules/ → repo root is parents[2]
_REPO = Path(__file__).resolve().parents[2]
_CORE = _REPO / "Core"

# Prefer post-reorg paths; fall back to legacy names if someone still uses them.
DATA_DIR = _REPO / "Data"
if not DATA_DIR.exists():
    DATA_DIR = _REPO / "data"

CLIPS_DIR = _REPO / "media" / "clips"
if not CLIPS_DIR.exists():
    CLIPS_DIR = _REPO / "clips"

VERTICAL_DIR = _REPO / "media" / "vertical_clips"
if not VERTICAL_DIR.exists():
    VERTICAL_DIR = _REPO / "vertical_clips"

RANKINGS_FILE = DATA_DIR / "rankings.json"
QUEUE_FILE = DATA_DIR / "ready_to_post.json"
# Dashboard JS: keep under Data/ (and a legacy Core/data copy if present).
OUTPUT_FILE = DATA_DIR / "Bolt_data.js"


def _count_clips() -> int:
    """Count how many clips exist in the clips folder."""
    if not CLIPS_DIR.exists():
        return 0
    return len(list(CLIPS_DIR.glob("*.mp4"))) + len(list(CLIPS_DIR.glob("*.mkv")))


def _count_vertical_clips() -> int:
    """Count TikTok-formatted vertical clips."""
    if not VERTICAL_DIR.exists():
        return 0
    return len(list(VERTICAL_DIR.glob("*.mp4")))


def _load_rankings() -> list:
    """Load clip rankings from rankings.json."""
    if not RANKINGS_FILE.exists():
        return []
    try:
        with open(RANKINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return data.get("rankings", [])
    except Exception:
        return []


def _load_queue() -> list:
    """Load the post queue from ready_to_post.json."""
    if not QUEUE_FILE.exists():
        return []
    try:
        with open(QUEUE_FILE, encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return data.get("items", data.get("clips", data.get("queue", [])))
    except Exception:
        return []


def _check_env_keys() -> dict:
    """
    Check which API keys are present in .env.
    Returns a dict of key_name -> True/False.
    """
    try:
        from dotenv import load_dotenv

        load_dotenv(_REPO / ".env.local")
        load_dotenv(_REPO / ".env")
    except Exception:
        pass
    return {
        "twitch": bool(os.getenv("TWITCH_CLIENT_ID")),
        "obs": bool(os.getenv("OBS_PASSWORD")),
        "streamlabs": bool(os.getenv("STREAMLABS_SOCKET_TOKEN")),
        "discord": bool(os.getenv("DISCORD_WEBHOOK_URL")),
        "openai": bool(os.getenv("OPENAI_API_KEY")),
        "xai": bool(os.getenv("XAI_API_KEY")),
        "tiktok": bool(os.getenv("TIKTOK_ACCESS_TOKEN")),
        "bot_token": bool(os.getenv("TWITCH_BOT_TOKEN")),
    }


def _load_performance_totals() -> tuple[int, int, int]:
    """Return (clips_posted, total_views, total_likes) from performance log."""
    candidates = [
        DATA_DIR / "performance_outcomes.jsonl",
        DATA_DIR / "data" / "performance_outcomes.jsonl",
        _CORE / "data" / "performance_outcomes.jsonl",
    ]
    total_views = 0
    total_likes = 0
    clips_posted = 0
    for perf_file in candidates:
        if not perf_file.exists():
            continue
        try:
            with open(perf_file, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except Exception:
                        continue
                    total_views += int(data.get("views", 0) or 0)
                    total_likes += int(data.get("likes", 0) or 0)
                    clips_posted += 1
        except Exception:
            continue
        break  # use first file that exists
    return clips_posted, total_views, total_likes


def _count_processed_recordings() -> int:
    candidates = [
        DATA_DIR / "processed_recordings.json",
        _CORE / "data" / "processed_recordings.json",
    ]
    for processed_file in candidates:
        if not processed_file.exists():
            continue
        try:
            with open(processed_file, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return len(data)
            if isinstance(data, dict):
                return len(data.get("processed", data.get("files", [])))
        except Exception:
            continue
    return 0


def gather_stats() -> dict:
    """
    Read all real Bolt data and return a stats dict.
    This is what gets written into Bolt_data.js for the dashboard.
    """
    rankings = _load_rankings()
    queue = _load_queue()
    clips = _count_clips()
    vertical = _count_vertical_clips()
    keys = _check_env_keys()
    clips_posted, total_views, total_likes = _load_performance_totals()

    # Count highlights from rankings (each ranking entry = one detected highlight)
    highlight_count = len(rankings)

    # Count titles generated (clips that have a title in the queue)
    titles_generated = sum(
        1 for item in queue if str(item.get("title", "")).strip()
    )

    # Average clip score
    scores = [
        item.get("score", 0) for item in queue if item.get("score") is not None
    ]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0

    # Top clip
    top_clip = None
    if queue:
        sorted_q = sorted(queue, key=lambda x: x.get("score", 0) or 0, reverse=True)
        top = sorted_q[0]
        top_clip = {
            "title": top.get("title", "Untitled clip"),
            "score": top.get("score", 0),
            "path": Path(str(top.get("clip_path", "") or "")).name,
        }

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "clips_made": clips,
        "vertical_clips": vertical,
        "highlights": highlight_count,
        "titles_generated": titles_generated,
        "ready_to_post": len(queue),
        "avg_score": avg_score,
        "top_clip": top_clip,
        "api_keys": keys,
        "clips_posted": clips_posted,
        "total_views": total_views,
        "total_likes": total_likes,
        "recordings_processed": _count_processed_recordings(),
        "phase": {
            "current": 3,
            "p1_done": True,
            "p2_done": True,
            "p3_active": True,
            "p4_done": False,
        },
    }


def write_data_file(stats: dict | None = None) -> Path:
    """
    Write Bolt_data.js with current Bolt stats.
    The HTML dashboard loads this file to show live data.

    Returns the path to the written file.
    """
    if stats is None:
        stats = gather_stats()

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    js_content = f"""// Auto-generated by Bolt — do not edit manually.
// Updated: {stats["generated_at"]}
// Re-generated on every launch.py startup and after each pipeline run.
window.Bolt_DATA = {json.dumps(stats, indent=2)};
"""

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(js_content)

    return OUTPUT_FILE


def update_checkup():
    """
    Public entry point — gather stats and write the data file.
    Call this from launch.py and after each pipeline run.
    """
    stats = gather_stats()
    path = write_data_file(stats)

    clips = stats["clips_made"]
    queue = stats["ready_to_post"]
    avg = stats["avg_score"]

    print(f"  ✓  Checkup data updated → {path}")
    print(f"     Clips: {clips}  |  Ready to post: {queue}  |  Avg score: {avg}")
    return stats


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n  ⚡️  Bolt Checkup Writer")
    stats = update_checkup()
    print("\n  Full stats:")
    for k, v in stats.items():
        if k not in ("api_keys", "top_clip", "phase"):
            print(f"    {k:20} {v}")
    print("\n  API keys present:")
    for k, v in stats["api_keys"].items():
        mark = "✓" if v else "✗"
        print(f"    {mark}  {k}")
    if stats["top_clip"]:
        tc = stats["top_clip"]
        print(f"\n  Top clip: {tc['title']} (score: {tc['score']})")
    print(f"\n  Dashboard data written to: {OUTPUT_FILE}")
    print("  Open the checkup HTML in your browser to see it.\n")
