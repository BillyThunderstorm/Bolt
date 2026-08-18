"""Tests for Apple Reminders briefing delivery (no live Reminders.app)."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

_repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_repo / "Core"))

from modules import Apple_Reminders as ar


SAMPLE_BRIEFING = """# Bolt Daily Briefing

## Action Items For Today

1. Review last clip performance and log outcomes
2. C5 review: 1 candidate
3. Check for new recordings to process

---

## Quick Commands
"""


class ParseActionItemsTests(unittest.TestCase):
    def test_reads_numbered_items(self):
        items = ar.parse_action_items(SAMPLE_BRIEFING)
        self.assertEqual(
            items,
            [
                "Review last clip performance and log outcomes",
                "C5 review: 1 candidate",
                "Check for new recordings to process",
            ],
        )

    def test_empty_when_section_missing(self):
        self.assertEqual(ar.parse_action_items("# hi\n\nNo actions"), [])


class ReplaceTodayBriefingTests(unittest.TestCase):
    def test_writes_summary_and_actions(self):
        calls = {"jxa": 0}

        def fake_jxa(script, timeout=30):
            calls["jxa"] += 1
            class R:
                returncode = 0
                stdout = "1" if "completed" in script or "n;" in script else "ok"
                stderr = ""
            return R()

        with patch.object(ar, "_jxa", side_effect=fake_jxa):
            result = ar.replace_today_briefing(
                ["Review the queue", "Log last post"],
                briefing_path=_repo / "Docs" / "briefings" / "daily" / "latest_morning.md",
                summary="2 actions",
                due=datetime(2026, 8, 17, 17, 0),
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["actions_created"], 2)
        self.assertTrue(result["summary"])
        self.assertGreaterEqual(calls["jxa"], 3)

    def test_reports_failure_when_osascript_fails(self):
        class R:
            returncode = 1
            stdout = ""
            stderr = "not authorized"

        with patch.object(ar, "_jxa", return_value=R()):
            result = ar.replace_today_briefing(["x"])
        self.assertFalse(result["ok"])
        self.assertTrue(result["error"])


if __name__ == "__main__":
    unittest.main()
