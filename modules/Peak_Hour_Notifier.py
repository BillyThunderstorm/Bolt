#!/usr/bin/env python3
"""
modules/Peak_Hour_Notifier.py — Tell Billy when to post, not post for him
=========================================================================
TikTok's API is a nightmare. This module replaces auto-posting entirely.

Instead of uploading clips automatically, Bolt:
  1. Saves your ready-to-post clips to data/ready_to_post.json
  2. At peak hours, fires a Discord notification + terminal message telling
     you WHICH clips are ready and what to do with them
  3. Lets you mark clips as posted so the list stays clean

Peak windows (configurable in config.json):
  - 7:00 – 9:00 AM   (morning scroll)
  - 12:00 – 2:00 PM  (lunch break)
  - 7:00 – 10:00 PM  (prime time)

Why this is actually better than auto-posting:
  - You stay in control of what goes up
  - You can add context, trending sounds, or tweak the caption before posting
  - No API tokens to manage or rotate
  - TikTok's algorithm actually rewards manual posts with more reach
"""

import os
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

try:
    import requests
except ImportError:
    requests = None  # type: ignore

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from modules.notifier import notify
except ImportError:
    def notify(msg, level="info", reason=None):
        prefix = {"info": "ℹ", "success": "✓", "warning": "⚠", "error": "✗"}.get(level, "•")
        print(f"  {prefix}  {msg}")
        if reason:
            print(f"     → {reason}")


# ── Config ─────────────────────────────────────────────────────────────────────

POSTING_TIMEZONE = os.getenv("POSTING_TIMEZONE", "America/New_York")
DISCORD_WEBHOOK  = os.getenv("DISCORD_WEBHOOK_URL", "")
READY_FILE       = Path("data/ready_to_post.json")
CONFIG_FILE      = Path("config.json")

# Peak posting windows as (start_hour, end_hour) in 24h format
PEAK_WINDOWS = [
    (7,  9),   # 7:00 AM – 9:00 AM   morning scroll
    (12, 14),  # 12:00 PM – 2:00 PM  lunch break
    (19, 22),  # 7:00 PM – 10:00 PM  prime time
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_ready() -> dict:
    """Load the ready-to-post list from disk. Returns empty structure if missing."""
    READY_FILE.parent.mkdir(exist_ok=True)
    if READY_FILE.exists():
        try:
            with open(READY_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"clips": []}


def _save_ready(data: dict):
    """Persist the ready-to-post list to disk."""
    READY_FILE.parent.mkdir(exist_ok=True)
    with open(READY_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


def _load_config() -> dict:
    """Load local config for queue eligibility checks."""
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _score_floor() -> float:
    """Current minimum score required before a clip should wake Billy up."""
    config = _load_config()
    return float(config.get("min_post_score", config.get("min_clip_score", 0)))


def _clip_file_exists(clip: dict) -> bool:
    """Return True when the queued media file exists on this Mac."""
    clip_path = clip.get("clip_path", "")
    return bool(clip_path) and Path(clip_path).exists()


def _score_clears_floor(clip: dict) -> bool:
    """Return True when a queued clip clears the current posting score floor."""
    try:
        return float(clip.get("score", 0)) >= _score_floor()
    except Exception:
        return False


def _is_alertable_clip(clip: dict) -> bool:
    """
    Return True when a queue row is safe to include in peak-hour alerts.

    Old queue rows can survive config changes or iCloud sync without their media
    files. Keep those rows for history, but do not alert Billy to post clips that
    are missing locally or below the current score floor.
    """
    return (
        clip.get("status") == "ready"
        and clip.get("tier", "queue") == "queue"
        and _clip_file_exists(clip)
        and _score_clears_floor(clip)
    )


def _is_peak_now() -> tuple:
    """
    Check if the current time falls inside a peak window.
    Returns (is_peak: bool, window_label: str).

    Example return values:
      (True,  "7:00 AM – 9:00 AM")
      (False, "Next peak: 12:00 PM")
    """
    tz   = ZoneInfo(POSTING_TIMEZONE)
    now  = datetime.now(tz)
    hour = now.hour

    for start_h, end_h in PEAK_WINDOWS:
        if start_h <= hour < end_h:
            label = f"{_fmt_hour(start_h)} – {_fmt_hour(end_h)}"
            return True, label

    # Not peak — find next window
    next_window = _next_peak_window()
    return False, f"Next peak: {next_window}"


def _next_peak_window() -> str:
    """Return a human-readable string for the next upcoming peak window."""
    tz        = ZoneInfo(POSTING_TIMEZONE)
    now       = datetime.now(tz)
    hour      = now.hour

    # Check today's remaining windows
    for start_h, end_h in PEAK_WINDOWS:
        if start_h > hour:
            return _fmt_hour(start_h)

    # All today's windows passed — first window tomorrow
    start_h = PEAK_WINDOWS[0][0]
    tomorrow = (now + timedelta(days=1)).strftime("%a")
    return f"{_fmt_hour(start_h)} tomorrow ({tomorrow})"


def _fmt_hour(h: int) -> str:
    """Convert 24h integer to readable 12h string. E.g. 19 → '7:00 PM'"""
    period = "AM" if h < 12 else "PM"
    h12    = h % 12 or 12
    return f"{h12}:00 {period}"


def _send_discord(message: str):
    """
    Fire a Discord webhook notification.
    Does nothing silently if no webhook is configured or requests isn't installed.

    The webhook URL comes from DISCORD_WEBHOOK_URL in .env.
    """
    if not DISCORD_WEBHOOK or not requests:
        return
    try:
        requests.post(DISCORD_WEBHOOK, json={"content": message}, timeout=10)
    except Exception as exc:
        notify(f"Discord notify failed: {exc}", level="warning",
               reason="Check DISCORD_WEBHOOK_URL in .env. Clip still saved locally.")


# ── Public API ─────────────────────────────────────────────────────────────────

def queue_clip(
    clip_path: str,
    title: str,
    hashtags: list = None,
    score: float = 50,
    tier: str = "queue",
) -> dict:
    """
    Add a clip to the ready-to-post list.

    Called by bot.py after a clip has been processed and scored.
    The clip gets a unique ID so you can mark it posted later.

    Tier semantics (from Clip_Ranker):
      - "queue"  → counted in peak-hour alerts (pings you on Discord)
      - "mid"    → saved to disk, visible in --summary, but NEVER pings you
      - "discard"→ shouldn't reach this function; bot.py is supposed to skip
                   discard-tier clips before calling. We honor it defensively
                   anyway by tagging the item but still saving the row.

    Returns the item dict that was saved.
    """
    data = _load_ready()
    tz   = ZoneInfo(POSTING_TIMEZONE)
    now  = datetime.now(tz)

    is_peak, window_info = _is_peak_now()

    item = {
        "id":          str(uuid.uuid4())[:8],
        "clip_path":   str(clip_path),
        "title":       title,
        "hashtags":    hashtags or [],
        "score":       round(score, 1),
        "tier":        tier,
        "status":      "ready",
        "queued_at":   now.isoformat(),
        "posted_at":   None,
    }
    data["clips"].append(item)
    _save_ready(data)

    notify(
        f"Clip saved to post queue  [score {score:.0f}, tier {tier}]",
        level="success",
        reason=f"Title: '{title}'\n"
               f"     → File: {Path(clip_path).name}\n"
               f"     → {window_info}\n"
               f"     → Will trigger peak alert: {'YES' if tier == 'queue' else 'no (mid-tier)'}"
    )

    # Only QUEUE tier triggers an immediate peak-window alert.
    # Mid-tier clips just sit in the queue silently for manual review.
    if is_peak and tier == "queue":
        alert_peak_window()

    return item


def alert_peak_window():
    """
    Check if it's peak time and, if so, send Billy a Discord notification
    listing every unposted clip that's ready to go.

    This is called:
      - Automatically by queue_clip() when a clip arrives during peak hours
      - By Post_Queue's background checker (if running)
      - Any time you want to manually check: python -m modules.Peak_Hour_Notifier
    """
    data  = _load_ready()
    # Only QUEUE-tier clips wake Billy up. Mid-tier clips are visible in
    # --summary for manual review, but never trigger a Discord ping.
    # Backward compat: clips queued before tier existed have no 'tier' key
    # — treat those as 'queue' so old data still works.
    ready = [c for c in data["clips"] if _is_alertable_clip(c)]
    mid_count = sum(
        1 for c in data["clips"]
        if c["status"] == "ready" and c.get("tier") == "mid"
    )
    missing_count = sum(
        1 for c in data["clips"]
        if c.get("status") == "ready" and not _clip_file_exists(c)
    )
    low_score_count = sum(
        1 for c in data["clips"]
        if c.get("status") == "ready" and _clip_file_exists(c) and not _score_clears_floor(c)
    )

    if not ready:
        if missing_count or low_score_count:
            notify(
                "No alertable clips ready",
                level="info",
                reason=f"{missing_count} queued clip(s) are missing files on this Mac; "
                       f"{low_score_count} existing clip(s) are below the current score floor. "
                       "Queue history was left untouched."
            )
        elif mid_count:
            notify(
                f"No QUEUE-tier clips ready — but {mid_count} MID-tier clip(s) sitting on disk",
                level="info",
                reason="Mid-tier clips are decent but not great. They live in "
                       "data/ready_to_post.json with tier='mid'. Browse them manually "
                       "if you want, or lower quality_tiers.queue_at in config.json "
                       "to promote more clips into the auto-alert lane."
            )
        else:
            notify("No clips in post queue", level="info",
                   reason="Process a recording first, or drop an .mp4 into recordings/")
        return

    is_peak, window_info = _is_peak_now()

    if not is_peak:
        notify(
            f"Not peak hours yet  ({window_info})",
            level="info",
            reason=f"{len(ready)} clip(s) are ready and waiting. "
                   "Bolt will alert you when the window opens."
        )
        return

    # It IS peak time — build the notification
    lines = [
        f"⚡️ **Bolt ALERT — Peak Posting Window: {window_info}**",
        f"You have **{len(ready)} clip(s)** ready to post on TikTok:\n",
    ]
    for i, clip in enumerate(ready, 1):
        tags = " ".join(f"#{t.lstrip('#')}" for t in clip.get("hashtags", []))
        lines.append(
            f"**{i}. {clip['title']}**\n"
            f"   Score: {clip['score']}/100\n"
            f"   File: `{Path(clip['clip_path']).name}`\n"
            f"   Tags: {tags or '(none)'}\n"
        )
    lines.append(
        "✅ Post these manually on TikTok, then run:\n"
        "   `python -m modules.Peak_Hour_Notifier --mark-posted`\n"
        "   to clear them from the queue."
    )

    message = "\n".join(lines)

    # Terminal output
    print("\n" + "─" * 60)
    print(message.replace("**", "").replace("`", ""))
    print("─" * 60 + "\n")

    # Discord notification
    _send_discord(message)

    notify(
        f"Peak hour alert sent! {len(ready)} clip(s) are ready.",
        level="success",
        reason="Check Discord for the full list with titles and file names."
    )


def mark_posted(clip_id: str = None):
    """
    Mark one or all 'ready' clips as posted.

    clip_id=None  → marks ALL ready clips as posted (use after a posting session)
    clip_id='abc' → marks just that specific clip

    This keeps the queue clean so you don't get duplicate alerts.
    """
    data = _load_ready()
    tz   = ZoneInfo(POSTING_TIMEZONE)
    now  = datetime.now(tz)
    count = 0

    for clip in data["clips"]:
        if clip["status"] != "ready":
            continue
        if clip_id is None or clip["id"] == clip_id:
            clip["status"]    = "posted"
            clip["posted_at"] = now.isoformat()
            count += 1

    _save_ready(data)
    notify(
        f"Marked {count} clip(s) as posted ✓",
        level="success",
        reason="Queue updated. Run again after your next session to clear new clips."
    )
    return count


def reset_queue() -> Path:
    """
    Archive the current ready-to-post queue and start fresh.

    This only touches data/ready_to_post.json. It does not delete clips,
    vertical exports, captions, logs, or memory.
    """
    READY_FILE.parent.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = READY_FILE.with_name(f"ready_to_post.archive-{timestamp}.json")

    if READY_FILE.exists():
        archive_path.write_text(READY_FILE.read_text(encoding="utf-8"), encoding="utf-8")

    _save_ready({"clips": []})
    notify(
        "Post queue reset",
        level="success",
        reason=f"Archived old queue to {archive_path}. Clip files were not touched."
    )
    return archive_path


def queue_summary() -> dict:
    """Return counts for each status in the ready-to-post list."""
    data = _load_ready()
    clips = data["clips"]
    ready = [c for c in clips if c.get("status") == "ready"]
    return {
        "ready":  sum(1 for c in ready if _is_alertable_clip(c)),
        "ready_total": len(ready),
        "missing": sum(1 for c in ready if not _clip_file_exists(c)),
        "below_floor": sum(1 for c in ready if _clip_file_exists(c) and not _score_clears_floor(c)),
        "posted": sum(1 for c in clips if c.get("status") == "posted"),
        "total":  len(clips),
    }


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    args = sys.argv[1:]

    if "--mark-posted" in args:
        mark_posted()
    elif "--reset-queue" in args:
        reset_queue()
    elif "--summary" in args:
        s = queue_summary()
        print(
            f"\n  📋  Post Queue: {s['ready']} alertable  |  "
            f"{s['ready_total']} ready rows  |  {s['posted']} posted  |  {s['total']} total\n"
        )
        if s["missing"] or s["below_floor"]:
            print(f"      ignored: {s['missing']} missing file(s), {s['below_floor']} below score floor\n")
    else:
        # Default: check peak hours and alert if applicable
        is_peak, info = _is_peak_now()
        print(f"\n  🕐  Current time zone: {POSTING_TIMEZONE}")
        print(f"  {'🔥 PEAK TIME' if is_peak else '💤 Off-peak'}  —  {info}")
        s = queue_summary()
        print(f"  📋  Post Queue: {s['ready']} alertable / {s['ready_total']} ready row(s)\n")
        alert_peak_window()
