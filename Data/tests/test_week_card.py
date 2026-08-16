import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_repo_root / "Core"))

from modules import Week_Card as wc


class WeekCardTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.week_file = self.root / "week_card.json"
        self.research = self.root / "research_log.jsonl"
        self.research.write_text(
            json.dumps(
                {
                    "name": "Hyram (Skincare by Hyram)",
                    "c5_verdict": "no",
                    "finding_type": "candidate_creator",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.patches = [
            patch.object(wc, "WEEK_FILE", self.week_file),
            patch.object(wc, "RESEARCH_LOG", self.research),
            patch.object(wc, "_remember", lambda *_a, **_k: None),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tempdir.cleanup()

    def test_set_and_done_and_rotate(self):
        wc.set_week("skincare first-use", note="already filmed AM")
        wc.mark_done("filmed AM routine")
        data = wc.load()
        self.assertEqual(data["this_week"]["topic"], "skincare first-use")
        self.assertIn("filmed AM routine", data["this_week"]["done"])
        wc.rotate()
        data = wc.load()
        self.assertEqual(data["this_week"]["topic"], "")
        self.assertEqual(data["last_week"]["topic"], "skincare first-use")

    def test_blocked_includes_c5_drops_and_bans(self):
        wc.ban("start a new career plan", why="already have one")
        blocked = wc.blocked_suggestions()
        self.assertTrue(any("Hyram" in b for b in blocked))
        self.assertTrue(any("career plan" in b for b in blocked))
        self.assertEqual(wc.is_blocked("Hyram-style education"), "Hyram (Skincare by Hyram)")

    def test_prompt_refuses_to_invent_a_lane(self):
        text = wc.format_prompt()
        self.assertIn("Do not restart the career", text)
        self.assertIn("pick one", text.lower())
        wc.set_week("Hades 2 fails")
        text = wc.format_prompt()
        self.assertIn("This week is: Hades 2 fails", text)
        self.assertIn("Hyram", text)
