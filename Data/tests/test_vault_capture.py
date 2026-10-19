"""Quick capture previews, then yes/no/edit. Temp vault and temp pending file."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

_repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_repo_root / "Core"))

from modules import Intent_Router as ir
from modules import Vault_Dates as vd
from modules import Vault_Pending as vp
from modules import Vault_Store as vs
from modules import Week_Card as wc

FROZEN = datetime(2026, 10, 19, 10, 0, tzinfo=ZoneInfo("America/Chicago"))


class DateParseTests(unittest.TestCase):
    def test_friday_thursday_and_next_friday(self):
        friday = vd.parse_when("by Friday", now=FROZEN)
        self.assertEqual(friday.iso_date, "2026-10-23")
        self.assertTrue(friday.all_day)
        self.assertEqual(vd.speak_when(friday), "Fri Oct 23 CT")

        thursday = vd.parse_when("Thursday 7pm", now=FROZEN)
        self.assertEqual(thursday.iso_date, "2026-10-22")
        self.assertEqual(thursday.hhmm, "19:00")
        self.assertIn("7:00 PM CT", vd.speak_when(thursday))

        nxt = vd.parse_when("next Friday", now=FROZEN)
        self.assertEqual(nxt.iso_date, "2026-10-30")

        tonight = vd.parse_when("tonight", now=FROZEN)
        self.assertEqual(tonight.hhmm, "19:00")
        self.assertEqual(tonight.iso_date, "2026-10-19")


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "vault"
        self.root.mkdir()
        self.pending = Path(self._tmp.name) / "pending.json"
        self.filing = Path(self._tmp.name) / "filing.json"
        self.week = Path(self._tmp.name) / "week_card.json"
        self.env = patch.dict(
            os.environ,
            {
                "BOLT_VAULT_PATH": str(self.root),
                "BOLT_PENDING_VAULT_PATH": str(self.pending),
                "BOLT_VAULT_FILING_PATH": str(self.filing),
                "BOLT_VAULT_FILING_AI": "off",
            },
        )
        self.env.start()
        self.clocks = [
            patch("modules.Vault_Capture.now_ct", return_value=FROZEN),
            patch("modules.Vault_Pending.now_ct", return_value=FROZEN),
        ]
        for item in self.clocks:
            item.start()
        self.notes = []
        self.memory = patch.object(ir, "_save_memory_note", lambda fact, **_k: self.notes.append(fact))
        self.memory.start()
        self.week_patch = patch.object(wc, "WEEK_FILE", self.week)
        self.week_patch.start()
        self.week_remember = patch.object(wc, "_remember", lambda *_a, **_k: None)
        self.week_remember.start()

    def tearDown(self):
        self.week_remember.stop()
        self.week_patch.stop()
        self.memory.stop()
        for item in self.clocks:
            item.stop()
        self.env.stop()
        self._tmp.cleanup()

    def test_preview_then_yes_writes_inbox_task(self):
        reply = ir.try_handle_intent("add task film the K&F short by Friday")
        self.assertIn("Film the K&F short", reply)
        self.assertIn("00 Inbox", reply)
        self.assertIn("Fri Oct 23 CT", reply)
        self.assertIn("yes", reply.lower())
        self.assertFalse((self.root / "10 Bolt" / "Tasks" / "Film the K&F short.md").exists())
        self.assertTrue(self.pending.is_file())

        saved = ir.try_handle_intent("yes")
        self.assertIn("Saved", saved)
        note = vs.VaultStore(self.root).read_note("10 Bolt/Tasks/Film the K&F short.md")
        self.assertEqual(note.frontmatter["due"], "2026-10-23")
        self.assertEqual(note.frontmatter["area"], "00 Inbox")
        self.assertEqual(note.frontmatter["source"], "chat")
        self.assertFalse(self.pending.exists())

    def test_no_writes_nothing(self):
        ir.try_handle_intent("add task film the K&F short by Friday")
        reply = ir.try_handle_intent("no")
        self.assertIn("won't", reply.lower())
        self.assertFalse((self.root / "10 Bolt" / "Tasks").exists() and any((self.root / "10 Bolt" / "Tasks").glob("*.md")))
        self.assertIsNone(ir.try_handle_intent("yes"))

    def test_edit_date_then_save(self):
        ir.try_handle_intent("add task film the K&F short by Friday")
        edited = ir.try_handle_intent("change it to Saturday")
        self.assertIn("Sat Oct 24 CT", edited)
        ir.try_handle_intent("yes")
        note = vs.VaultStore(self.root).read_note("10 Bolt/Tasks/Film the K&F short.md")
        self.assertEqual(note.frontmatter["due"], "2026-10-24")

    def test_note_files_by_keyword_and_remember_stays_memory(self):
        reply = ir.try_handle_intent("note: podcast idea about a gear episode")
        self.assertIn("20 Creator HQ & Content", reply)
        ir.try_handle_intent("yes")
        notes = list((self.root / "20 Creator HQ & Content").glob("*.md"))
        self.assertEqual(len(notes), 1)
        self.assertNotIn("10 Bolt/Tasks", notes[0].as_posix())

        remembered = ir.try_handle_intent("remember: filming after lunch")
        self.assertIn("saved", remembered.lower())
        self.assertTrue(any("lunch" in note for note in self.notes))
        tomorrow = ir.try_handle_intent("note for tomorrow: call Randy")
        self.assertIn("saved", tomorrow.lower())

    def test_review_keyword_picks_product_testing(self):
        reply = ir.try_handle_intent("add task review the capture card by Friday")
        self.assertIn("30 Product Testing", reply)

    def test_missing_vault_does_not_create_the_default_folder(self):
        missing = Path(self._tmp.name) / "absent"
        os.environ["BOLT_VAULT_PATH"] = str(missing)
        reply = ir.try_handle_intent("add task film the short by Friday")
        self.assertIn("can't see the vault", reply.lower())
        self.assertFalse(missing.exists())
        self.assertFalse(Path("/Users/carter/Documents/Obsidian/Bolt Vault").exists())

    def test_undo_that_parks_the_saved_task(self):
        ir.try_handle_intent("add task film the K&F short by Friday")
        ir.try_handle_intent("yes")
        path = self.root / "10 Bolt" / "Tasks" / "Film the K&F short.md"
        text = path.read_text(encoding="utf-8")
        reply = ir.try_handle_intent("undo that")
        self.assertIn("Undid", reply)
        self.assertFalse(path.exists())
        parked = list((self.root / ".bolt" / "undone").rglob("*.md"))
        self.assertTrue(any(item.read_text(encoding="utf-8") == text for item in parked))

    def test_pending_survives_reload_and_week_command_still_works(self):
        ir.try_handle_intent("add task film the K&F short by Friday")
        self.assertIsNotNone(vp.load_pending())
        week = ir.try_handle_intent("this week is tech")
        self.assertIn("tech", week.lower())
        self.assertEqual(wc.load()["this_week"]["topic"], "tech")
        self.assertIsNotNone(vp.load_pending())

    def test_yes_without_pending_is_not_a_command(self):
        self.assertIsNone(ir.try_handle_intent("yes"))
        self.assertIsNone(ir.try_handle_intent("Just chatting about games"))


if __name__ == "__main__":
    unittest.main()
