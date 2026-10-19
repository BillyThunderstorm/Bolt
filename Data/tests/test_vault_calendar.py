"""Calendar notes, CT confirmation, and cancel that keeps the file."""

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
from modules import Vault_Store as vs

FROZEN = datetime(2026, 10, 19, 10, 0, tzinfo=ZoneInfo("America/Chicago"))


class CalendarTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "vault"
        self.root.mkdir()
        self.pending = Path(self._tmp.name) / "pending.json"
        self.filing = Path(self._tmp.name) / "filing.json"
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
            patch("modules.Vault_Calendar.now_ct", return_value=FROZEN),
            patch("modules.Vault_Capture.now_ct", return_value=FROZEN),
            patch("modules.Vault_Pending.now_ct", return_value=FROZEN),
        ]
        for item in self.clocks:
            item.start()

    def tearDown(self):
        for item in self.clocks:
            item.stop()
        self.env.stop()
        self._tmp.cleanup()

    def test_schedule_thursday_night_quotes_the_clock(self):
        preview = ir.try_handle_intent("schedule the K&F short Thursday 7pm")
        self.assertIn("Thu Oct 22, 7:00 PM to 8:00 PM CT", preview)
        self.assertFalse((self.root / "10 Bolt" / "Calendar").exists())
        ir.try_handle_intent("yes")
        path = self.root / "10 Bolt" / "Calendar" / "K&F short.md"
        raw = path.read_text(encoding="utf-8")
        self.assertIn('startTime: "19:00"', raw)
        self.assertIn('endTime: "20:00"', raw)
        self.assertIn("allDay: false", raw)
        note = vs.VaultStore(self.root).read_note("10 Bolt/Calendar/K&F short.md")
        self.assertEqual(note.frontmatter["date"], "2026-10-22")
        self.assertEqual(note.frontmatter["type"], "event")
        self.assertNotEqual(path.name, "Bolt Calendar.md")
        events = vs.VaultStore(self.root).list_events()
        self.assertEqual([item.title for item in events], ["K&F short"])

    def test_all_day_and_tonight(self):
        ir.try_handle_intent("schedule dentist Friday")
        ir.try_handle_intent("yes")
        note = vs.VaultStore(self.root).read_note("10 Bolt/Calendar/Dentist.md")
        self.assertEqual(note.frontmatter["date"], "2026-10-23")
        self.assertTrue(note.frontmatter["allDay"])
        self.assertNotIn("startTime", note.frontmatter)
        preview = ir.try_handle_intent("schedule stream tonight")
        self.assertIn("Mon Oct 19, 7:00 PM to 8:00 PM CT", preview)

    def test_move_keeps_the_clock_and_reads_a_drag(self):
        ir.try_handle_intent("schedule the K&F short Thursday 7pm")
        ir.try_handle_intent("yes")
        path = self.root / "10 Bolt" / "Calendar" / "K&F short.md"
        path.write_text(path.read_text(encoding="utf-8").replace("2026-10-22", "2026-10-21"), encoding="utf-8")
        preview = ir.try_handle_intent("move the K&F short to Friday")
        self.assertIn("Wed Oct 21, 7:00 PM CT", preview)
        self.assertIn("Fri Oct 23, 7:00 PM to 8:00 PM CT", preview)
        self.assertEqual(
            vs.VaultStore(self.root).read_note("10 Bolt/Calendar/K&F short.md").frontmatter["date"],
            "2026-10-21",
        )
        ir.try_handle_intent("yes")
        note = vs.VaultStore(self.root).read_note("10 Bolt/Calendar/K&F short.md")
        self.assertEqual(note.frontmatter["date"], "2026-10-23")
        self.assertEqual(note.frontmatter["startTime"], "19:00")
        self.assertEqual(note.frontmatter["endTime"], "20:00")

    def test_cancel_hides_the_event_and_undo_restores_it(self):
        ir.try_handle_intent("schedule the K&F short Thursday 7pm")
        ir.try_handle_intent("yes")
        preview = ir.try_handle_intent("cancel the K&F short")
        self.assertIn("note stays", preview.lower())
        ir.try_handle_intent("yes")
        path = self.root / "10 Bolt" / "Calendar" / "K&F short.md"
        self.assertTrue(path.is_file())
        note = vs.VaultStore(self.root).read_note("10 Bolt/Calendar/K&F short.md")
        self.assertTrue(note.frontmatter["cancelled"])
        self.assertEqual(note.frontmatter["cancelledDate"], "2026-10-22")
        self.assertNotIn("date", note.frontmatter)
        self.assertEqual(vs.VaultStore(self.root).list_events(), [])
        ir.try_handle_intent("undo that")
        note = vs.VaultStore(self.root).read_note("10 Bolt/Calendar/K&F short.md")
        self.assertEqual(note.frontmatter["date"], "2026-10-22")
        self.assertEqual(len(vs.VaultStore(self.root).list_events()), 1)

    def test_task_due_move_and_ambiguous_choice(self):
        ir.try_handle_intent("add task film the K&F short by Friday")
        ir.try_handle_intent("yes")
        preview = ir.try_handle_intent("move film the K&F short to next Friday")
        self.assertIn("Fri Oct 30 CT", preview)
        self.assertNotIn("calendar", preview.lower())
        ir.try_handle_intent("yes")
        task = vs.VaultStore(self.root).read_note("10 Bolt/Tasks/Film the K&F short.md")
        self.assertEqual(task.frontmatter["due"], "2026-10-30")
        self.assertFalse((self.root / "10 Bolt" / "Calendar").exists() and any((self.root / "10 Bolt" / "Calendar").glob("*.md")))

        ir.try_handle_intent("schedule the K&F short Thursday 7pm")
        ir.try_handle_intent("yes")
        asked = ir.try_handle_intent("move K&F to Friday")
        self.assertIn("Which one", asked)
        self.assertIn("event", asked)
        self.assertIn("task", asked)
        ir.try_handle_intent("2")
        ir.try_handle_intent("yes")
        task = vs.VaultStore(self.root).read_note("10 Bolt/Tasks/Film the K&F short.md")
        event = vs.VaultStore(self.root).read_note("10 Bolt/Calendar/K&F short.md")
        self.assertEqual(task.frontmatter["due"], "2026-10-23")
        self.assertEqual(event.frontmatter["date"], "2026-10-22")

    def test_lane_move_stays_on_the_board_and_missing_vault_is_not_created(self):
        ir.try_handle_intent("add task film the short by Friday")
        ir.try_handle_intent("yes")
        preview = ir.try_handle_intent("move it to Doing")
        self.assertIn("Doing", preview)
        ir.try_handle_intent("yes")
        note = vs.VaultStore(self.root).read_note("10 Bolt/Tasks/Film the short.md")
        self.assertEqual(note.frontmatter["status"], "doing")
        self.assertFalse(any((self.root / "10 Bolt" / "Calendar").glob("*.md")))

        missing = Path(self._tmp.name) / "absent"
        os.environ["BOLT_VAULT_PATH"] = str(missing)
        reply = ir.try_handle_intent("schedule dentist Thursday 7pm")
        self.assertIn("can't see the vault", reply.lower())
        self.assertFalse(missing.exists())
        self.assertFalse(Path("/Users/carter/Documents/Obsidian/Bolt Vault").exists())
