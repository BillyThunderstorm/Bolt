#!/usr/bin/env python3
"""
scripts/generate_calendar.py — Generate ICS calendar feeds for Bolt
====================================================================
Writes RFC 5545 (iCalendar) files into data/calendar/ that Billy can
subscribe to from any calendar client (Apple Calendar, Google Calendar,
Fantastical, Outlook, Thunderbird).

Four feeds are produced:

  1. daily_briefing.ics    — recurring daily 5:00pm event with a preview
                              of the day's briefing. Description includes
                              the SMS summary line.
  2. weekly_insights.ics   — recurring Sunday 9:00am event with weekly
                              insights preview.
  3. peak_hours.ics        — recurring daily 7:00pm-9:00pm posting window
                              (Billy's peak audience hours per memory).
  4. scheduled_posts.ics   — one VEVENT per queued post in
                              data/multi_platform_queue.json, each with
                              platform-specific timing.

These are static local files. To subscribe, Billy can either:
  - Open the .ics file from Finder (Apple Calendar imports on open), or
  - Host the data/calendar/ directory on bolt.billythunderstorm.us and
    use the webcal:// or https:// subscribe URL in his client.

Usage:
  python3 scripts/generate_calendar.py
  python3 scripts/generate_calendar.py --dry-run
  python3 scripts/generate_calendar.py --output-dir /tmp/cal
  python3 scripts/generate_calendar.py --days 14   # only include events
                                                # within next N days

Library use:
  from scripts.generate_calendar import build_all_feeds
  paths = build_all_feeds(output_dir=Path("data/calendar"))
"""

import argparse
import json
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional
# Make _paths importable in BOTH direct invocation (script dir on
# sys.path) and `from scripts import X` (tests). The helper also adds
# Core/ and 3rd_Party/llm/ to sys.path so `from modules import Y` works
# without any per-script sys.path shim, and chdirs to the repo root so
# CWD-relative paths the rest of the script uses still resolve.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from _paths import (  # noqa: E402
    REPO_ROOT,
    DATA_DIR,
    CLIPS_DIR,
    VERTICAL_CLIPS_DIR,
    MEDIA_DIR,
    LOGS_DIR,
    DAILY_BRIEFINGS_DIR,
    CONFIG_FILE,
    BOT_FILE,
    BOLT_BRAIN_FILE,
    VOD_SAMPLES_DIR,
    RECORDINGS_DIR,
)

# Backward-compatible aliases for code that uses `ROOT` / `PROJECT_ROOT`.
PROJECT_ROOT = REPO_ROOT
ROOT = REPO_ROOT

REPO_ROOT  # keep linter quiet about unused import
DATA_DIR

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUTPUT_DIR = ROOT / "data" / "calendar"
QUEUE_FILE = ROOT / "data" / "multi_platform_queue.json"
CONFIG_FILE = ROOT / "config.json"

# --- Calendar constants ---------------------------------------------------

CALENDAR_NAME = "Bolt"
PRODID = "-//Bolt//Calendar Feeds//EN"
DAILY_BRIEFING_HOUR = 17  # 5pm local (evening wake window)
WEEKLY_INSIGHTS_DOW = 6   # Sunday (Mon=0 .. Sun=6)
WEEKLY_INSIGHTS_HOUR = 9  # 9am
PEAK_HOUR_START = 19      # 7pm
PEAK_HOUR_END = 21        # 9pm
DEFAULT_LOOKAHEAD_DAYS = 30
TIMEZONE = "America/Chicago"  # matches POSTING_TIMEZONE in Multi_Publisher


# --- Event model ----------------------------------------------------------


@dataclass
class CalendarEvent:
    summary: str
    start: datetime
    end: datetime
    description: str = ""
    location: str = ""
    uid: Optional[str] = None
    rrule: Optional[str] = None  # e.g. "FREQ=DAILY" or "FREQ=WEEKLY;BYDAY=SU"


def _format_ics_datetime(dt: datetime) -> str:
    """Format a datetime as a floating local ICS timestamp (no Z, no TZID).

    We use floating times so the events fire at the same wall-clock hour
    regardless of the subscriber's timezone, which matches how Billy
    thinks about his schedule.
    """
    return dt.strftime("%Y%m%dT%H%M%S")


def _escape_ics_text(text: str) -> str:
    """Escape per RFC 5545 section 3.3.11."""
    if not text:
        return ""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def render_vevent(event: CalendarEvent) -> str:
    """Render a single VEVENT block."""
    uid = event.uid or f"{uuid.uuid4()}@bolt"
    lines = ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{_format_ics_datetime(datetime.now())}"]
    lines.append(f"DTSTART:{_format_ics_datetime(event.start)}")
    lines.append(f"DTEND:{_format_ics_datetime(event.end)}")
    lines.append(f"SUMMARY:{_escape_ics_text(event.summary)}")
    if event.description:
        lines.append(f"DESCRIPTION:{_escape_ics_text(event.description)}")
    if event.location:
        lines.append(f"LOCATION:{_escape_ics_text(event.location)}")
    if event.rrule:
        lines.append(f"RRULE:{event.rrule}")
    lines.append("END:VEVENT")
    return "\r\n".join(lines)


def render_calendar(name: str, events: Iterable[CalendarEvent]) -> str:
    """Render a full VCALENDAR with the given events."""
    header = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        f"X-WR-CALNAME:{_escape_ics_text(name)}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    body = [render_vevent(e) for e in events]
    return "\r\n".join(header + body + ["END:VCALENDAR"]) + "\r\n"


# --- Feed builders --------------------------------------------------------


def build_daily_briefing_event(today: Optional[datetime] = None) -> CalendarEvent:
    """Recurring daily 5pm event with a placeholder briefing preview."""
    now = today or datetime.now()
    start = now.replace(hour=DAILY_BRIEFING_HOUR, minute=0, second=0, microsecond=0)
    # If today's 5pm already passed, advance to tomorrow so the first
    # occurrence is the next upcoming one.
    if start <= now:
        start = start + timedelta(days=1)
    return CalendarEvent(
        summary="Bolt daily briefing",
        start=start,
        end=start + timedelta(minutes=15),
        description=(
            "Auto-generated by scripts/daily_briefing.py. "
            "Open the briefing markdown or the SMS digest for action items."
        ),
        location="Local (scripts/daily_briefing.py --send)",
        uid="bolt-daily-briefing@bolt",
        rrule="FREQ=DAILY",
    )


def build_weekly_insights_event(today: Optional[datetime] = None) -> CalendarEvent:
    """Recurring Sunday 9am event with weekly insights preview."""
    now = today or datetime.now()
    days_ahead = (WEEKLY_INSIGHTS_DOW - now.weekday()) % 7
    sunday = now + timedelta(days=days_ahead)
    sunday = sunday.replace(hour=WEEKLY_INSIGHTS_HOUR, minute=0, second=0, microsecond=0)
    if sunday <= now:
        sunday = sunday + timedelta(days=7)
    return CalendarEvent(
        summary="Bolt weekly insights",
        start=sunday,
        end=sunday + timedelta(minutes=30),
        description=(
            "Auto-generated by scripts/weekly_analysis.py. "
            "Review last week's clip performance and next-week recommendations."
        ),
        location="Local (scripts/weekly_analysis.py --send)",
        uid="bolt-weekly-insights@bolt",
        rrule="FREQ=WEEKLY;BYDAY=SU",
    )


def build_peak_hours_event(today: Optional[datetime] = None) -> CalendarEvent:
    """Recurring daily 7-9pm peak audience window."""
    now = today or datetime.now()
    start = now.replace(hour=PEAK_HOUR_START, minute=0, second=0, microsecond=0)
    if start <= now:
        start = start + timedelta(days=1)
    return CalendarEvent(
        summary="Peak posting window (7-9pm)",
        start=start,
        end=start.replace(hour=PEAK_HOUR_END),
        description=(
            "Billy's peak audience hours per memory/content/live-streaming.md. "
            "Best time to post clips, run a stream, or send social announcements."
        ),
        uid="bolt-peak-hours@bolt",
        rrule="FREQ=DAILY",
    )


def _parse_iso(value: str) -> Optional[datetime]:
    """Parse an ISO 8601 timestamp; return None on failure."""
    if not value:
        return None
    try:
        # Python's fromisoformat handles most ISO 8601 variants including
        # the explicit -05:00 offsets in our queue file.
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    # Treat naive timestamps as floating local time (no conversion).
    if dt.tzinfo is not None:
        # Strip tzinfo so we render as floating local.
        dt = dt.replace(tzinfo=None)
    return dt


def build_scheduled_post_events(
    lookahead_days: int = DEFAULT_LOOKAHEAD_DAYS,
    today: Optional[datetime] = None,
) -> list[CalendarEvent]:
    """One VEVENT per queued post, filtered to the lookahead window."""
    now = today or datetime.now()
    cutoff = now + timedelta(days=lookahead_days)
    if not QUEUE_FILE.exists():
        return []

    try:
        with open(QUEUE_FILE, encoding="utf-8") as f:
            queue = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    events: list[CalendarEvent] = []
    items = queue.get("items", []) if isinstance(queue, dict) else queue
    for item in items:
        queue_id = item.get("queue_id") or item.get("id") or uuid.uuid4().hex[:8]
        for platform in item.get("platforms", []):
            scheduled_raw = platform.get("scheduled_for")
            scheduled = _parse_iso(scheduled_raw) if scheduled_raw else None
            if scheduled is None:
                continue
            if scheduled < now or scheduled > cutoff:
                continue
            label = platform.get("label") or platform.get("platform") or "post"
            caption = (platform.get("caption") or "").strip()
            first_line = caption.splitlines()[0] if caption else ""
            title = first_line[:80] or f"Clip {queue_id}"
            summary = f"Post to {label}: {title}"
            events.append(
                CalendarEvent(
                    summary=summary[:120],
                    start=scheduled,
                    end=scheduled + timedelta(minutes=10),
                    description=(
                        f"queue_id: {queue_id}\n"
                        f"platform: {label}\n"
                        f"clip: {platform.get('clip_path', 'unknown')}\n"
                        f"instructions: {platform.get('instructions', '')}"
                    ),
                    location=f"Bolt queue ({queue_id})",
                    uid=f"bolt-post-{queue_id}-{platform.get('platform', 'x')}-{int(scheduled.timestamp())}@bolt",
                )
            )
    events.sort(key=lambda e: e.start)
    return events


# --- Top-level entry points ----------------------------------------------


def build_all_feeds(
    output_dir: Optional[Path] = None,
    lookahead_days: int = DEFAULT_LOOKAHEAD_DAYS,
    dry_run: bool = False,
) -> dict[str, Optional[Path]]:
    """Render every feed and (unless dry_run) write it to disk.

    Returns a dict mapping feed name -> path written (or None if dry-run).
    """
    target_dir = Path(output_dir) if output_dir else OUTPUT_DIR

    feeds = {
        "daily_briefing": [build_daily_briefing_event()],
        "weekly_insights": [build_weekly_insights_event()],
        "peak_hours": [build_peak_hours_event()],
        "scheduled_posts": build_scheduled_post_events(lookahead_days=lookahead_days),
    }
    feed_names = {
        "daily_briefing": "Daily Briefing",
        "weekly_insights": "Weekly Insights",
        "peak_hours": "Peak Hours",
        "scheduled_posts": "Scheduled Posts",
    }

    written: dict[str, Optional[Path]] = {}
    for key, events in feeds.items():
        ics_text = render_calendar(feed_names[key], events)
        if dry_run:
            written[key] = None
            continue
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{key}.ics"
        path.write_text(ics_text, encoding="utf-8")
        written[key] = path
    return written


def summarize_results(written: dict[str, Optional[Path]], dry_run: bool) -> None:
    label = "Would write" if dry_run else "Wrote"
    for key, path in written.items():
        if dry_run or path is None:
            print(f"  plan   {key}.ics")
        else:
            print(f"  wrote  {path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate Bolt's ICS calendar feeds."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help=f"Directory to write .ics files (default: {OUTPUT_DIR})",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_LOOKAHEAD_DAYS,
        help=f"Include scheduled posts within N days (default: {DEFAULT_LOOKAHEAD_DAYS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan the work without writing files",
    )
    args = parser.parse_args()

    written = build_all_feeds(
        output_dir=args.output_dir,
        lookahead_days=args.days,
        dry_run=args.dry_run,
    )
    summarize_results(written, args.dry_run)
    if not args.dry_run:
        for key, path in written.items():
            if path:
                events = (
                    1 if key in ("daily_briefing", "weekly_insights", "peak_hours") else "varies"
                )
                print(f"  events {key}: {events}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
