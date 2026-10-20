"""Tests for the real-data weekly report in scripts/weekly_analysis.py.

All file I/O goes to a temp REPO_ROOT; Bolt_Alerts / Nexus are mocked, so
nothing is texted, emailed, or sent to an LLM.
"""

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

_repo_root = Path(__file__).resolve().parents[2]
for _p in [_repo_root / "Core", _repo_root]:
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from scripts import weekly_analysis as wa  # noqa: E402


def _iso(days_ago: float, utc: bool = False) -> str:
    if utc:
        return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (datetime.now() - timedelta(days=days_ago)).isoformat()


class _TempRepo(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "Data").mkdir()
        (self.root / "media" / "clips").mkdir(parents=True)
        (self.root / "media" / "vertical_clips").mkdir(parents=True)
        self._p = patch.object(wa, "REPO_ROOT", self.root)
        self._p.start()

    def tearDown(self):
        self._p.stop()
        self._tmp.cleanup()

    def write_outcomes(self, rows):
        with (self.root / "Data" / "performance_outcomes.jsonl").open("w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
            f.write("not json\n")

    def write_queue(self, clips):
        (self.root / "Data" / "ready_to_post.json").write_text(json.dumps({"clips": clips}))


class OutcomeLoadingTests(_TempRepo):
    def test_window_handles_naive_and_utc_and_skips_old_or_bad(self):
        self.write_outcomes([
            {"timestamp": _iso(1), "views": 10, "platform": "YouTube"},
            {"timestamp": _iso(2, utc=True), "views": 20, "platform": "TikTok"},
            {"timestamp": _iso(40, utc=True), "views": 999},  # old, aware stamp
            {"timestamp": _iso(30), "views": 999},             # old, naive
            {"timestamp": "garbage", "views": 999},
            {"views": 999},
        ])
        rows = wa.load_outcomes(days=7)
        self.assertEqual(sorted(r["views"] for r in rows), [10, 20])
        prev = wa.load_previous_outcomes(days=7)
        self.assertEqual(prev, [])
        self.assertEqual(wa.last_outcome()["views"], 10)

    def test_previous_window(self):
        self.write_outcomes([{"timestamp": _iso(10), "views": 5}])
        self.assertEqual(len(wa.load_previous_outcomes(days=7)), 1)
        self.assertEqual(wa.load_outcomes(days=7), [])


class QueueTests(_TempRepo):
    def test_reads_clips_key_with_status_and_recent_counts(self):
        self.write_queue([
            {"status": "held", "queued_at": _iso(1)},
            {"status": "held", "queued_at": _iso(20)},
            {"status": "posted", "queued_at": _iso(3), "posted_at": _iso(2)},
            {"status": "scrapped"},
        ])
        q = wa.load_queue_stats(days=7)
        self.assertEqual(q["total"], 4)
        self.assertEqual(q["by_status"], {"held": 2, "posted": 1, "scrapped": 1})
        self.assertEqual(q["queued_recent"], 2)
        self.assertEqual(q["posted_recent"], 1)

    def test_missing_queue_is_empty(self):
        self.assertEqual(wa.load_queue_stats()["total"], 0)


class ReportTests(_TempRepo):
    OUTS = [
        {"timestamp": _iso(1), "views": 1200, "likes": 9, "platform": "YouTube", "game": "Hades 2", "title": "Big dodge"},
        {"timestamp": _iso(2), "views": 300, "likes": 1, "platform": "TikTok", "game": "Marvel Rivals", "title": "Oops"},
    ]

    def test_summary_has_views_platforms_top_clip_and_delta(self):
        extra = {"days": 7, "previous": [{"views": 750}], "media": {"clips": 3, "verticals": 1, "plans": 2}}
        q = {"total": 2, "items": [], "by_status": {"held": 2}, "queued_recent": 1, "posted_recent": 0}
        report = wa.generate_insights(self.OUTS, q, [], extra)
        self.assertIn("Clips logged this week: 2", report)
        self.assertIn("Views logged: 1,500", report)
        self.assertIn("+100% vs the week before: 750", report)
        self.assertIn("YouTube 1,200 views / 1 clip(s)", report)
        self.assertIn("Big dodge — 1,200 views (YouTube, Hades 2)", report)
        self.assertIn("Queue by status: held 2", report)
        self.assertIn("Made this week: 3 new clip(s), 1 vertical(s), 2 multi-platform plan(s)", report)
        self.assertIn('Lean into what worked: "Big dodge"', report)
        self.assertIn("2 clip(s) are held", report)
        self.assertNotIn("Start logging performance", report)

    def test_no_outcomes_names_last_logged_date(self):
        extra = {"days": 7, "last_outcome": {"timestamp": "2026-08-27T19:09:56", "platform": "YouTube"}}
        report = wa.generate_insights([], {"total": 0, "items": []}, [], extra)
        self.assertIn("Last logged: Aug 27, 2026 (YouTube)", report)
        self.assertIn("Start logging performance", report)

    def test_constraint_hit_shows_rule_not_id(self):
        prof = self.root / "Data" / "memory"
        prof.mkdir(parents=True)
        (prof / "user_profile.json").write_text(json.dumps({"hard_constraints": [{"id": "C1", "text": "Be honest about hype"}]}))
        with patch.dict("sys.modules", {"modules.Memory_Index": MagicMock(retrieve_memory=lambda **k: [])}):
            hits = wa._retrieve_weekly_memory()
        self.assertEqual(hits[0]["title"], "Reminder: Be honest about hype")


class MainFlowTests(_TempRepo):
    def test_main_saves_and_sends_full_report(self):
        self.write_outcomes(ReportTests.OUTS)
        self.write_queue([{"status": "held", "queued_at": _iso(1)}])
        with (
            patch.object(wa, "_retrieve_weekly_memory", return_value=[]),
            patch.object(wa, "send_sms", return_value=True) as sms,
            patch.object(wa, "send_email", return_value=True) as email,
            patch.object(wa, "_nexus_block") as nexus,
        ):
            wa.main(send=True, days=7, use_ai=False)
        nexus.assert_not_called()
        saved = list((self.root / "Data" / "weekly_reports").glob("weekly_*.md"))
        self.assertEqual(len(saved), 1)
        body = saved[0].read_text()
        self.assertIn("Views logged: 1,500", body)
        self.assertIn("*Generated by Bolt*", body)
        sms_text = sms.call_args[0][0]
        self.assertIn("2 clip(s) logged, 1,500 views", sms_text)
        self.assertIn("queue 1 (1 held)", sms_text)
        self.assertIn(saved[0].name, sms_text)
        self.assertEqual(email.call_args[0][0].strip(), body.strip())
        self.assertIn("Bolt weekly", email.call_args[1]["subject"])

    def test_no_save_writes_nothing(self):
        with patch.object(wa, "_retrieve_weekly_memory", return_value=[]):
            wa.main(days=7, use_ai=False, save=False)
        self.assertFalse((self.root / "Data" / "weekly_reports").exists())

    def test_nexus_gets_real_numbers_and_soft_fails(self):
        self.write_outcomes(ReportTests.OUTS)
        fake = MagicMock()
        fake.return_value.consult.return_value = {"advice": "", "error": "LLM unavailable: test"}
        with (
            patch.object(wa, "_retrieve_weekly_memory", return_value=[]),
            patch("modules.Nexus_Creator.NexusCreator", fake),
        ):
            wa.main(days=7, use_ai=True)
        ctx = fake.return_value.consult.call_args[1]["context"]
        self.assertIn("Views logged: 1,500", ctx)
        body = next((self.root / "Data" / "weekly_reports").glob("weekly_*.md")).read_text()
        self.assertIn("AI recommendations unavailable: LLM unavailable: test", body)


class WrapperQueueTests(unittest.TestCase):
    def test_module_queue_total_reads_clips(self):
        from modules import Weekly_Analysis as W

        with tempfile.TemporaryDirectory() as d:
            q = Path(d) / "ready_to_post.json"
            q.write_text(json.dumps({"clips": [{}, {}, {}]}))
            with patch.object(W, "_QUEUE", q):
                self.assertEqual(W._queue_total(), 3)


if __name__ == "__main__":
    unittest.main()
