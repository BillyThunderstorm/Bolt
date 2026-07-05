"""Tests for scripts/generate_calendar.py.

Covers the public feed-building API, ICS text rendering, and event
construction. We validate ICS by parsing the structure ourselves (no
external icalendar dep) so the test stays self-contained.
"""

import json
import re
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from scripts import generate_calendar as gc


# --- ICS parsing helpers (tiny, no deps) --------------------------------


def _parse_vevents(ics_text: str) -> list[dict]:
    """Return a list of dicts with VEVENT fields keyed by uppercase name."""
    blocks = re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", ics_text, re.DOTALL)
    events = []
    for block in blocks:
        event: dict = {}
        for line in block.strip().splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            event[key.strip()] = value
        events.append(event)
    return events


# --- ICS rendering tests -------------------------------------------------


class RenderVEventTests(unittest.TestCase):
    def test_event_renders_required_fields(self):
        event = gc.CalendarEvent(
            summary="Test event",
            start=datetime(2026, 6, 22, 7, 0),
            end=datetime(2026, 6, 22, 7, 15),
            description="A test.",
            location="Local",
        )
        text = gc.render_vevent(event)
        self.assertIn("BEGIN:VEVENT", text)
        self.assertIn("END:VEVENT", text)
        self.assertIn("SUMMARY:Test event", text)
        self.assertIn("DTSTART:20260622T070000", text)
        self.assertIn("DTEND:20260622T071500", text)
        self.assertIn("DESCRIPTION:A test.", text)
        self.assertIn("LOCATION:Local", text)
        self.assertIn("UID:", text)

    def test_event_uses_provided_uid(self):
        event = gc.CalendarEvent(
            summary="X",
            start=datetime(2026, 6, 22, 7, 0),
            end=datetime(2026, 6, 22, 7, 15),
            uid="my-custom-uid@bolt",
        )
        text = gc.render_vevent(event)
        self.assertIn("UID:my-custom-uid@bolt", text)

    def test_event_escapes_ics_special_chars(self):
        event = gc.CalendarEvent(
            summary="With; comma, and newline",
            start=datetime(2026, 6, 22, 7, 0),
            end=datetime(2026, 6, 22, 7, 15),
            description="line1\nline2",
        )
        text = gc.render_vevent(event)
        self.assertIn(r"With\; comma\, and newline", text)
        self.assertIn(r"line1\nline2", text)

    def test_event_renders_rrule(self):
        event = gc.CalendarEvent(
            summary="Daily",
            start=datetime(2026, 6, 22, 7, 0),
            end=datetime(2026, 6, 22, 7, 15),
            rrule="FREQ=DAILY",
        )
        text = gc.render_vevent(event)
        self.assertIn("RRULE:FREQ=DAILY", text)


class RenderCalendarTests(unittest.TestCase):
    def test_calendar_wraps_events_with_header_and_footer(self):
        events = [
            gc.CalendarEvent(
                summary="E1",
                start=datetime(2026, 6, 22, 7, 0),
                end=datetime(2026, 6, 22, 7, 15),
            )
        ]
        text = gc.render_calendar("My Calendar", events)
        self.assertTrue(text.startswith("BEGIN:VCALENDAR"))
        self.assertTrue(text.rstrip().endswith("END:VCALENDAR"))
        self.assertIn("VERSION:2.0", text)
        self.assertIn("X-WR-CALNAME:My Calendar", text)
        self.assertIn("PRODID:-//Bolt//Calendar Feeds//EN", text)
        self.assertIn("SUMMARY:E1", text)

    def test_empty_calendar_still_valid_structure(self):
        text = gc.render_calendar("Empty", [])
        self.assertIn("BEGIN:VCALENDAR", text)
        self.assertIn("END:VCALENDAR", text)


# --- Event-builder tests -------------------------------------------------


class DailyBriefingEventTests(unittest.TestCase):
    def test_event_is_at_7am_and_recurs_daily(self):
        today = datetime(2026, 6, 22, 6, 0)  # 6am, so 7am is still ahead
        event = gc.build_daily_briefing_event(today=today)
        self.assertEqual(event.start.hour, gc.DAILY_BRIEFING_HOUR)
        self.assertEqual(event.start.minute, 0)
        self.assertEqual(event.rrule, "FREQ=DAILY")
        self.assertEqual(event.end - event.start, timedelta(minutes=15))

    def test_event_advances_to_tomorrow_if_7am_passed(self):
        today = datetime(2026, 6, 22, 8, 0)  # 8am, 7am already passed
        event = gc.build_daily_briefing_event(today=today)
        # The first occurrence should be tomorrow at 7am.
        expected_date = today.date() + timedelta(days=1)
        self.assertEqual(event.start.date(), expected_date)
        self.assertEqual(event.start.hour, gc.DAILY_BRIEFING_HOUR)


class WeeklyInsightsEventTests(unittest.TestCase):
    def test_event_is_on_sunday_at_9am(self):
        # 2026-06-22 is a Monday; next Sunday is 2026-06-28.
        today = datetime(2026, 6, 22, 6, 0)
        event = gc.build_weekly_insights_event(today=today)
        self.assertEqual(event.start.weekday(), 6)  # Sunday
        self.assertEqual(event.start.hour, gc.WEEKLY_INSIGHTS_HOUR)
        self.assertIn("BYDAY=SU", event.rrule)

    def test_event_advances_a_week_if_sunday_passed(self):
        # 2026-06-22 is Monday; build on Sunday afternoon and we should
        # get next Sunday.
        sunday_afternoon = datetime(2026, 6, 28, 12, 0)
        event = gc.build_weekly_insights_event(today=sunday_afternoon)
        expected_date = sunday_afternoon.date() + timedelta(days=7)
        self.assertEqual(event.start.date(), expected_date)


class PeakHoursEventTests(unittest.TestCase):
    def test_event_is_7pm_to_9pm_daily(self):
        today = datetime(2026, 6, 22, 6, 0)
        event = gc.build_peak_hours_event(today=today)
        self.assertEqual(event.start.hour, gc.PEAK_HOUR_START)
        self.assertEqual(event.end.hour, gc.PEAK_HOUR_END)
        self.assertEqual(event.rrule, "FREQ=DAILY")

    def test_event_advances_to_tomorrow_if_7pm_passed(self):
        today = datetime(2026, 6, 22, 22, 0)
        event = gc.build_peak_hours_event(today=today)
        expected_date = today.date() + timedelta(days=1)
        self.assertEqual(event.start.date(), expected_date)


class ScheduledPostEventsTests(unittest.TestCase):
    def _write_queue(self, tmp: Path, items: list) -> Path:
        path = tmp / "queue.json"
        path.write_text(json.dumps({"items": items}), encoding="utf-8")
        return path

    def test_no_queue_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(gc, "QUEUE_FILE", Path(td) / "missing.json"):
                events = gc.build_scheduled_post_events()
            self.assertEqual(events, [])

    def test_filters_to_lookahead_window(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            now = datetime(2026, 6, 22, 12, 0)
            soon = (now + timedelta(days=2)).isoformat()
            far = (now + timedelta(days=60)).isoformat()
            past = (now - timedelta(days=1)).isoformat()
            queue_path = self._write_queue(
                tmp,
                [
                    {
                        "queue_id": "a",
                        "platforms": [
                            {"platform": "tiktok", "label": "TikTok",
                             "scheduled_for": soon, "clip_path": "c.mp4",
                             "instructions": "post now"}
                        ],
                    },
                    {
                        "queue_id": "b",
                        "platforms": [
                            {"platform": "tiktok", "label": "TikTok",
                             "scheduled_for": far, "clip_path": "c.mp4",
                             "instructions": "too far"}
                        ],
                    },
                    {
                        "queue_id": "c",
                        "platforms": [
                            {"platform": "tiktok", "label": "TikTok",
                             "scheduled_for": past, "clip_path": "c.mp4",
                             "instructions": "too late"}
                        ],
                    },
                ],
            )
            with patch.object(gc, "QUEUE_FILE", queue_path):
                events = gc.build_scheduled_post_events(
                    lookahead_days=14, today=now
                )
            self.assertEqual(len(events), 1)
            self.assertIn("TikTok", events[0].summary)
            self.assertIn("a", events[0].description)

    def test_summarizes_first_caption_line(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            now = datetime(2026, 6, 22, 12, 0)
            soon = (now + timedelta(days=1)).isoformat()
            queue_path = self._write_queue(
                tmp,
                [
                    {
                        "queue_id": "q1",
                        "platforms": [
                            {
                                "platform": "youtube_shorts",
                                "label": "YouTube Shorts",
                                "scheduled_for": soon,
                                "clip_path": "clips/x.mp4",
                                "caption": "Billy just erased the lobby.\n\n#Gaming",
                                "instructions": "upload to Shorts",
                            }
                        ],
                    }
                ],
            )
            with patch.object(gc, "QUEUE_FILE", queue_path):
                events = gc.build_scheduled_post_events(
                    lookahead_days=14, today=now
                )
            self.assertEqual(len(events), 1)
            self.assertIn("YouTube Shorts", events[0].summary)
            self.assertIn("Billy just erased the lobby", events[0].summary)


# --- Top-level feed building tests ---------------------------------------


class BuildAllFeedsTests(unittest.TestCase):
    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as td:
            written = gc.build_all_feeds(
                output_dir=Path(td) / "cal", dry_run=True
            )
            self.assertEqual(set(written.keys()),
                             {"daily_briefing", "weekly_insights",
                              "peak_hours", "scheduled_posts"})
            self.assertFalse(any(Path(td, "cal").glob("*.ics")))

    def test_writes_all_four_feeds(self):
        # Build a queue with one future item so scheduled_posts.ics isn't empty.
        now = datetime.now()
        future_iso = (now + timedelta(days=2)).isoformat()
        queue_data = {
            "items": [{
                "queue_id": "tq",
                "platforms": [{
                    "platform": "tiktok",
                    "label": "TikTok",
                    "scheduled_for": future_iso,
                    "clip_path": "clip.mp4",
                    "caption": "Test caption",
                    "instructions": "upload",
                }],
            }],
        }
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "cal"
            tmp_queue = Path(td) / "queue.json"
            tmp_queue.write_text(json.dumps(queue_data), encoding="utf-8")
            with patch.object(gc, "QUEUE_FILE", tmp_queue):
                written = gc.build_all_feeds(output_dir=target, dry_run=False)
            self.assertTrue(all(p.exists() for p in written.values()))
            for path in written.values():
                self.assertGreater(path.stat().st_size, 0)
                content = path.read_text(encoding="utf-8")
                self.assertIn("BEGIN:VEVENT", content)
                self.assertTrue(content.rstrip().endswith("END:VCALENDAR"))

    def test_scheduled_posts_ics_parses_even_if_empty(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "cal"
            written = gc.build_all_feeds(output_dir=target, dry_run=False)
            content = (written["scheduled_posts"]).read_text(encoding="utf-8")
            # Always valid ICS structure (events list may be empty if no
            # queue items are within the lookahead window).
            self.assertTrue(content.startswith("BEGIN:VCALENDAR"))
            self.assertIn("END:VCALENDAR", content)
            events = _parse_vevents(content)
            for event in events:
                self.assertIn("UID", event)
                self.assertIn("DTSTART", event)
                self.assertIn("SUMMARY", event)

    def test_scheduled_posts_ics_includes_future_items(self):
        # Build a queue with one future item and verify it shows up.
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            now = datetime.now()
            future_iso = (now + timedelta(days=3)).isoformat()
            queue_file = tmp / "q.json"
            queue_file.write_text(json.dumps({
                "items": [{
                    "queue_id": "future1",
                    "platforms": [{
                        "platform": "tiktok",
                        "label": "TikTok",
                        "scheduled_for": future_iso,
                        "clip_path": "clip.mp4",
                        "caption": "Billy just erased the lobby.",
                        "instructions": "upload now",
                    }],
                }],
            }), encoding="utf-8")
            with patch.object(gc, "QUEUE_FILE", queue_file):
                events = gc.build_scheduled_post_events(lookahead_days=14)
            self.assertEqual(len(events), 1)
            self.assertIn("TikTok", events[0].summary)
            self.assertIn("Billy just erased the lobby", events[0].summary)


if __name__ == "__main__":
    unittest.main()
