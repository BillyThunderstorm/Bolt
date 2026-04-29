"""
Post_Queue.py — Background peak-hour checker
=============================================
This module runs a simple loop that checks whether it's peak posting time
and fires a Discord + terminal alert when it is.

It does NOT post anything automatically. That's intentional.
You post manually on TikTok; this module just makes sure you never
miss a peak window when you have clips ready.

Peak windows (default, changeable in config.json):
  7–9 AM  |  12–2 PM  |  7–10 PM  (your POSTING_TIMEZONE in .env)

How it works:
  - Wakes up every CHECK_INTERVAL_MINUTES to check the time
  - If it's a new peak window AND you have unposted clips, sends an alert
  - Tracks which windows it's already alerted for (so you don't get spammed)
  - Resets tracking each day so you get alerts again tomorrow
"""

import os
import time
from datetime import datetime, date

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from modules.Peak_Hour_Notifier import (
        alert_peak_window,
        queue_summary,
        PEAK_WINDOWS,
        POSTING_TIMEZONE,
        _is_peak_now,
    )
except ImportError:
    # Fallback so the file is importable even if Peak_Hour_Notifier isn't present
    def alert_peak_window():
        print("[PostQueue] Peak_Hour_Notifier not found — no alerts sent")
    def queue_summary():
        return {"ready": 0, "posted": 0, "total": 0}
    PEAK_WINDOWS      = [(7, 9), (12, 14), (19, 22)]
    POSTING_TIMEZONE  = os.getenv("POSTING_TIMEZONE", "America/New_York")
    def _is_peak_now():
        return False, "unknown"


# How often to wake up and check (in minutes).
# Smaller = more responsive; larger = uses less CPU.
CHECK_INTERVAL_MINUTES = int(os.getenv("PEAK_CHECK_INTERVAL_MINUTES", "15"))


# ── Public convenience functions (used by bot.py) ─────────────────────────────

def add_to_queue(
    clip_path: str,
    title: str,
    hashtags: list = None,
    score: float = 50,
    tier: str = "queue",
):
    """
    Add a finished clip to the ready-to-post list.

    This is the main entry point called by bot.py after each clip is processed.
    It delegates to Peak_Hour_Notifier.queue_clip() which handles storage,
    timing, and immediate peak-window alerts.

    Parameters
    ----------
    tier : str
        "queue" (default), "mid", or "discard". Only "queue" triggers
        peak-hour Discord alerts. "discard" should be filtered upstream
        in bot.py and never reach this function.
    """
    from modules.Peak_Hour_Notifier import queue_clip
    return queue_clip(clip_path, title, hashtags=hashtags, score=score, tier=tier)


def get_summary() -> dict:
    """Return current queue counts (ready / posted / total)."""
    return queue_summary()


# ── Background loop ────────────────────────────────────────────────────────────

def run_peak_checker():
    """
    Long-running loop that checks peak windows on a timer.

    Designed to run in a background thread while Bolt processes recordings.
    Keeps track of which windows have already been alerted today so Billy
    doesn't get the same notification five times in a row.

    Usage (from bot.py or launch.py):
        import threading
        from modules.Post_Queue import run_peak_checker
        t = threading.Thread(target=run_peak_checker, daemon=True)
        t.start()
    """
    tz             = ZoneInfo(POSTING_TIMEZONE)
    alerted_today  = set()   # set of (date, start_hour) tuples already notified
    last_check_day = None

    print(f"[PostQueue] Peak-hour checker started. "
          f"Checking every {CHECK_INTERVAL_MINUTES} min ({POSTING_TIMEZONE})")

    while True:
        try:
            now  = datetime.now(tz)
            today = now.date()

            # Reset alerts each new day
            if today != last_check_day:
                alerted_today.clear()
                last_check_day = today

            is_peak, window_info = _is_peak_now()

            if is_peak:
                # Find which peak window we're in
                current_window = None
                for start_h, end_h in PEAK_WINDOWS:
                    if start_h <= now.hour < end_h:
                        current_window = (today, start_h)
                        break

                # Only alert once per window per day
                if current_window and current_window not in alerted_today:
                    summary = queue_summary()
                    if summary["ready"] > 0:
                        alerted_today.add(current_window)
                        alert_peak_window()
                    # If ready == 0, don't add to alerted_today —
                    # in case clips come in during the window

        except Exception as exc:
            print(f"[PostQueue] Checker error: {exc}")

        time.sleep(CHECK_INTERVAL_MINUTES * 60)


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    """
    Run the peak-hour checker directly for testing.
    Press Ctrl+C to stop.

    Usage:
        python -m modules.Post_Queue
    """
    import sys

    if "--summary" in sys.argv:
        s = get_summary()
        print(f"\n  📋  Queue: {s['ready']} ready  |  {s['posted']} posted  |  {s['total']} total\n")
        sys.exit(0)

    tz          = ZoneInfo(POSTING_TIMEZONE)
    is_peak, info = _is_peak_now()
    print(f"\n  🕐  {datetime.now(tz).strftime('%I:%M %p')} {POSTING_TIMEZONE}")
    print(f"  {'🔥 Peak time' if is_peak else '💤 Off-peak'}  —  {info}")
    s = get_summary()
    print(f"  📋  {s['ready']} clip(s) ready to post\n")

    print("Starting peak-hour checker (Ctrl+C to stop)…\n")
    try:
        run_peak_checker()
    except KeyboardInterrupt:
        print("\n[PostQueue] Stopped.")
