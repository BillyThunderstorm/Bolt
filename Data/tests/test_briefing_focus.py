"""Briefing focus: one product, and a finished draft is not 'draft it again'."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_repo / "Core"))

from modules import Briefing_Focus as BF  # noqa: E402


def _item(**kwargs):
    base = {
        "id": "widget",
        "name": "Widget",
        "lane": "tech",
        "status": "testing",
        "notes_log": [],
    }
    base.update(kwargs)
    return base


class BriefingFocusStepsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="briefing_focus_"))
        self.catalog = self.tmp / "catalog.json"
        self.config = self.tmp / "config.json"
        self._write_catalog([])
        self._write_config({"enabled": True, "lane": "tech"})
        for p in (
            patch.object(BF, "CATALOG", self.catalog),
            patch.object(BF, "CONFIG", self.config),
        ):
            p.start()
            self.addCleanup(p.stop)

    def _write_catalog(self, items):
        self.catalog.write_text(json.dumps({"items": items}), encoding="utf-8")

    def _write_config(self, focus):
        self.config.write_text(json.dumps({"briefing_focus": focus}), encoding="utf-8")

    def test_journal_before_a_verdict(self):
        step = BF.next_step(_item(notes_log=[{"day": 1, "text": "ok"}]))
        self.assertIn("Day 2 journal note on Widget", step)

    def test_verdict_without_a_draft_asks_for_the_short(self):
        step = BF.next_step(_item(status="drafting", verdict="8/10"))
        self.assertIn("Draft the short for Widget", step)

    def test_unapproved_draft_is_a_review(self):
        step = BF.next_step(_item(
            status="drafting",
            verdict="8/10",
            last_draft={"format": "short"},
        ))
        self.assertIn("Review the draft for Widget", step)
        self.assertNotIn("Draft the short", step)

    def test_approved_draft_with_a_gap_is_a_post(self):
        step = BF.next_step(_item(
            name="K&F Concept Neck Phone Holder",
            status="drafting",
            verdict="8/10",
            last_draft={
                "approved_at": "2026-10-19T17:34:10",
                "needs": ["POV clip filmed from the holder (10-20s)"],
            },
        ))
        self.assertIn("Post K&F Concept Neck Phone Holder tonight", step)
        self.assertIn("POV clip", step)
        self.assertIn("bolt manage posted", step)
        self.assertNotIn("Draft the short", step)

    def test_focus_item_keeps_today_to_one_step(self):
        self._write_config({
            "enabled": True,
            "lane": "tech",
            "focus_item": "neck",
        })
        self._write_catalog([
            _item(id="cap", name="capture card", status="drafting", verdict="10/10",
                  last_draft={"format": "short"}),
            _item(id="neck", name="K&F", status="drafting", verdict="8/10",
                  last_draft={"approved_at": "2026-10-19T17:34:10"}),
        ])
        steps = BF.todays_steps()
        self.assertEqual(len(steps), 1)
        self.assertIn("Post the approved short for K&F", steps[0])

    def test_empty_lane_asks_for_one_product(self):
        steps = BF.todays_steps()
        self.assertEqual(len(steps), 1)
        self.assertIn("bolt manage add", steps[0])
