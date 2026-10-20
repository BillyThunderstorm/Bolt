"""Tests for scripts/generate_calendar.py.

Covers the public feed-building API, ICS text rendering, and event
construction. We validate ICS by parsing the structure ourselves (no
external icalendar dep) so the test stays self-contained.
"""


import sys
from pathlib import Path
_repo_root = Path(__file__).resolve().parents[2]
for _p in [_repo_root / '3rd_Party' / 'colabs']:
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

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
    def test_event_is_at_briefing_hour_and_recurs_daily(self):
        hour = gc.DAILY_BRIEFING_HOUR
        today = datetime(2026, 6, 22, max(hour - 1, 0), 0)
        event = gc.build_daily_briefing_event(today=today)
        self.assertEqual(event.start.hour, gc.DAILY_BRIEFING_HOUR)
        self.assertEqual(event.start.minute, 0)
        self.assertEqual(event.rrule, "FREQ=DAILY")
        self.assertEqual(event.end - event.start, timedelta(minutes=15))

    def test_event_advances_to_tomorrow_if_briefing_hour_passed(self):
        hour = gc.DAILY_BRIEFING_HOUR
        today = datetime(2026, 6, 22, hour, 1)
        event = gc.build_daily_briefing_event(today=today)
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



# --- READY promotion (19 Oct 2026, Shells) --------------------------------


def _q(tmp: Path, items: list) -> Path:
    path = tmp / "queue.json"
    path.write_text(json.dumps({"items": items}), encoding="utf-8")
    return path


class QueueCorrectnessTests(unittest.TestCase):
    NOW = datetime(2026, 10, 19, 12, 0)

    def _events(self, items, **kw):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(gc, "QUEUE_FILE", _q(Path(td), items)):
                return gc.build_scheduled_post_events(lookahead_days=14, today=self.NOW, **kw)

    def test_offset_times_convert_to_chicago_local(self):
        # 08:20 at -04:00 (EDT) is 07:20 in Chicago (CDT) — used to be 08:20.
        ev = self._events([{"queue_id": "a", "platforms": [
            {"platform": "youtube_shorts", "label": "YouTube Shorts",
             "scheduled_for": "2026-10-20T08:20:00-04:00", "title": "T"}]}])
        self.assertEqual(ev[0].start, datetime(2026, 10, 20, 7, 20))
        ev = self._events([{"queue_id": "b", "platforms": [
            {"platform": "tiktok", "scheduled_for": "2026-10-20T00:00:00Z"}]}])
        self.assertEqual(ev[0].start, datetime(2026, 10, 19, 19, 0))

    def test_naive_times_stay_floating(self):
        ev = self._events([{"queue_id": "a", "platforms": [
            {"platform": "tiktok", "scheduled_for": "2026-10-20T19:00:00"}]}])
        self.assertEqual(ev[0].start, datetime(2026, 10, 20, 19, 0))

    def test_posted_and_rejected_are_skipped(self):
        ev = self._events([
            {"queue_id": "a", "platforms": [
                {"platform": "tiktok", "status": "posted", "scheduled_for": "2026-10-20T19:00:00"},
                {"platform": "kick", "status": "manual_upload_ready", "scheduled_for": "2026-10-20T19:10:00"}]},
            {"queue_id": "b", "status": "rejected", "platforms": [
                {"platform": "tiktok", "scheduled_for": "2026-10-20T19:00:00"}]},
        ])
        self.assertEqual([e.uid for e in ev], ["bolt-post-a-kick@bolt"])

    def test_same_clip_same_platform_merged_to_earliest(self):
        ev = self._events([
            {"queue_id": "late", "platforms": [
                {"platform": "tiktok", "clip_path": "/x/c.mp4", "scheduled_for": "2026-10-21T19:00:00"}]},
            {"queue_id": "early", "platforms": [
                {"platform": "tiktok", "clip_path": "/x/c.mp4", "scheduled_for": "2026-10-20T19:00:00"},
                {"platform": "kick", "clip_path": "/x/c.mp4", "scheduled_for": "2026-10-20T19:10:00"}]},
        ])
        self.assertEqual(len(ev), 2)
        tiktok = [e for e in ev if "tiktok" in e.uid][0]
        self.assertEqual(tiktok.start, datetime(2026, 10, 20, 19, 0))
        self.assertIn("also queued as: late", tiktok.description)

    def test_uid_stable_across_reschedule(self):
        a = self._events([{"queue_id": "q", "platforms": [
            {"platform": "tiktok", "scheduled_for": "2026-10-20T19:00:00"}]}])
        b = self._events([{"queue_id": "q", "platforms": [
            {"platform": "tiktok", "scheduled_for": "2026-10-22T08:00:00"}]}])
        self.assertEqual(a[0].uid, b[0].uid)

    def test_missing_clip_flagged_and_title_fallback(self):
        ev = self._events([{"queue_id": "q", "platforms": [
            {"platform": "youtube_shorts", "label": "YouTube Shorts", "title": "Big play",
             "clip_path": "/definitely/not/here.mp4", "scheduled_for": "2026-10-20T08:20:00"}]}])
        self.assertIn("Big play", ev[0].summary)
        self.assertIn("clip file missing", ev[0].summary)


class RfcFormatTests(unittest.TestCase):
    def test_dtstamp_is_utc(self):
        text = gc.render_vevent(gc.CalendarEvent("X", datetime(2026, 1, 1, 7), datetime(2026, 1, 1, 8)))
        self.assertRegex(text, r"DTSTAMP:\d{8}T\d{6}Z")

    def test_long_lines_folded_at_75_octets_utf8_safe(self):
        ev = gc.CalendarEvent("Post 🔥 " * 20, datetime(2026, 1, 1, 7), datetime(2026, 1, 1, 8),
                              description="word " * 60)
        text = gc.render_vevent(ev)
        for line in text.split("\r\n"):
            self.assertLessEqual(len(line.encode("utf-8")), 75)
        unfolded = text.replace("\r\n ", "")
        self.assertIn("SUMMARY:" + gc._escape_ics_text(("Post 🔥 " * 20)), unfolded)


class PeakWindowTests(unittest.TestCase):
    def test_windows_from_config(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "config.json"
            cfg.write_text(json.dumps({"peak_notifications": {"windows": [
                {"label": "Lunch", "start_hour": 12, "end_hour": 14},
                {"label": "Prime Time", "start_hour": 19, "end_hour": 22},
                {"label": "bad", "start_hour": 23, "end_hour": 2}]}}), encoding="utf-8")
            wins = gc.load_peak_windows(cfg)
        self.assertEqual(wins, [("Lunch", 12, 14), ("Prime Time", 19, 22)])
        ev = gc.build_peak_hours_events(today=datetime(2026, 10, 19, 13, 0), windows=wins)
        self.assertEqual(ev[0].start, datetime(2026, 10, 20, 12, 0))  # 12 passed → tomorrow
        self.assertEqual(ev[1].start, datetime(2026, 10, 19, 19, 0))
        self.assertEqual(ev[1].end, datetime(2026, 10, 19, 22, 0))
        self.assertTrue(all(e.rrule == "FREQ=DAILY" for e in ev))

    def test_missing_config_falls_back(self):
        self.assertEqual(gc.load_peak_windows(Path("/nope/config.json")), gc.DEFAULT_PEAK_WINDOWS)


class BriefingAttachmentTests(unittest.TestCase):
    def test_refresh_returns_scheduled_posts_path_only_when_events(self):
        sys.path.insert(0, str(_repo_root / "scripts"))
        import daily_briefing as db
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            full = t / "scheduled_posts.ics"
            full.write_text("BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
            other = t / "peak_hours.ics"
            other.write_text("BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
            with patch.object(gc, "build_all_feeds", return_value={"scheduled_posts": full, "peak_hours": other}):
                with patch.dict(sys.modules, {"scripts.generate_calendar": gc}):
                    self.assertEqual(db._refresh_calendar_feeds(), [full])
                    with patch.dict("os.environ", {"BOLT_BRIEFING_ICS": "0"}):
                        self.assertEqual(db._refresh_calendar_feeds(), [])
            full.write_text("BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n")
            with patch.object(gc, "build_all_feeds", return_value={"scheduled_posts": full}):
                with patch.dict(sys.modules, {"scripts.generate_calendar": gc}):
                    self.assertEqual(db._refresh_calendar_feeds(), [])


class AtomicWriteTests(unittest.TestCase):
    def test_no_tmp_left_behind(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(gc, "QUEUE_FILE", Path(td) / "none.json"):
                gc.build_all_feeds(output_dir=Path(td) / "cal")
            names = sorted(p.name for p in (Path(td) / "cal").iterdir())
        self.assertEqual(names, ["daily_briefing.ics", "peak_hours.ics", "scheduled_posts.ics", "weekly_insights.ics"])


if __name__ == "__main__":
    unittest.main()
