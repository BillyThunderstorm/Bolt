"""Write intents: conversation is a front-end for bolt week / mission update."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_repo_root / "Core"))

from modules import Command_Center as cc
from modules import Intent_Router as ir
from modules import Week_Card as wc


class WriteIntentTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.week_file = self.root / "week_card.json"
        self.missions = self.root / "missions"
        self.missions.mkdir()
        self.research = self.root / "research_log.jsonl"
        self.research.write_text("", encoding="utf-8")
        self.memory_notes = []

        def _remember(fact, section="Recent Notes"):
            self.memory_notes.append(fact)
            return True

        self.patches = [
            patch.object(wc, "WEEK_FILE", self.week_file),
            patch.object(wc, "RESEARCH_LOG", self.research),
            patch.object(wc, "_remember", lambda *_a, **_k: None),
            patch.object(cc, "MISSIONS_DIR", self.missions),
            patch.object(ir, "_save_memory_note", _remember),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self._tmp.cleanup()

    def test_ready_keeps_topic_and_clears_pause(self):
        wc.set_week("tech", note="PAUSE. stepping away.")
        reply = ir.try_handle_intent("I'm ready to continue")
        self.assertIsNotNone(reply)
        self.assertIn("tech", reply.lower())
        self.assertIn("unpaused", reply.lower())
        data = wc.load()
        self.assertEqual(data["this_week"]["topic"], "tech")
        self.assertEqual(data["this_week"]["note"], "ready to continue")
        self.assertFalse(wc.is_paused(data))

    def test_ready_without_topic_asks(self):
        reply = ir.try_handle_intent("I'm back")
        self.assertIn("which week topic", reply.lower())
        self.assertEqual((wc.load()["this_week"].get("topic") or ""), "")

    def test_week_set_from_plain_language(self):
        reply = ir.try_handle_intent("this week is tech")
        self.assertIn("tech", reply.lower())
        self.assertEqual(wc.load()["this_week"]["topic"], "tech")
        ir.try_handle_intent("let's do gaming this week")
        self.assertEqual(wc.load()["this_week"]["topic"], "gaming")

    def test_whats_this_week_is_status_not_a_write(self):
        wc.set_week("tech")
        with patch.object(ir, "_write_week_set") as mocked:
            reply = ir.try_handle_intent("what's this week")
            mocked.assert_not_called()
        self.assertIn("tech", reply.lower())

    def test_this_shipped_writes_week_done(self):
        wc.set_week("tech")
        reply = ir.try_handle_intent("this shipped: posted the earbuds hook")
        self.assertIn("earbuds", reply.lower())
        self.assertIn("posted the earbuds hook", wc.load()["this_week"]["done"])

    def test_i_posted_writes_week_done(self):
        wc.set_week("tech")
        ir.try_handle_intent("I posted the tech clip")
        self.assertIn("the tech clip", wc.load()["this_week"]["done"])

    def test_mission_checkin_updates_latest(self):
        path = cc.start_mission("fund a mic", hours="", budget="", use_nexus=False)
        reply = ir.try_handle_intent("hours: 6, budget 40")
        self.assertIn("saved", reply.lower())
        self.assertIn("6", reply)
        body = path.read_text(encoding="utf-8")
        self.assertIn("| Time available | 6 |", body)
        self.assertIn("| Max budget | 40 |", body)

    def test_checkin_without_mission_does_not_invent_one(self):
        reply = ir.try_handle_intent("I have 6 hours")
        self.assertIn("no mission file", reply.lower())
        self.assertEqual(list(self.missions.glob("*.md")), [])

    def test_remember_saves_note(self):
        reply = ir.try_handle_intent("remember: filming after Randy's lunch")
        self.assertIn("saved", reply.lower())
        self.assertTrue(any("Randy" in n for n in self.memory_notes))

    def test_comment_block_applies_writes_and_keeps_leftover(self):
        wc.set_week("tech")
        applied = ir.apply_reply_block(
            "I'm ready to continue\n"
            "this shipped: posted the earbuds hook\n"
            "the lighting still looks off\n"
        )
        self.assertEqual(len(applied["replies"]), 2)
        self.assertEqual(applied["leftover"], ["the lighting still looks off"])
        self.assertIn("posted the earbuds hook", wc.load()["this_week"]["done"])

    def test_ready_to_post_does_not_unpause(self):
        wc.set_week("tech", note="PAUSE. stepping away.")
        reply = ir.try_handle_intent("ready to post")
        self.assertTrue(wc.is_paused())
        self.assertTrue(
            (wc.load()["this_week"].get("note") or "").upper().startswith("PAUSE")
        )
        self.assertNotIn("unpaused", (reply or "").lower())

    def test_chat_falls_through(self):
        self.assertIsNone(ir.try_handle_intent("Just chatting about games"))


if __name__ == "__main__":
    unittest.main()
