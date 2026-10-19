"""Timeline, due questions, morning briefing, and vault memory search."""

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

from modules import Content_Manager as cm
from modules import Intent_Router as ir
from modules import Memory_Index as mi
from modules import Vault_Store as vs
from modules import Week_Card as wc

FROZEN = datetime(2026, 10, 19, 10, 0, tzinfo=ZoneInfo("America/Chicago"))


class OverviewTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "vault"
        self.root.mkdir()
        self.pending = Path(self._tmp.name) / "pending.json"
        self.filing = Path(self._tmp.name) / "filing.json"
        self.week = Path(self._tmp.name) / "week_card.json"
        self.briefings = Path(self._tmp.name) / "briefings"
        self.briefings.mkdir()
        self.env = patch.dict(
            os.environ,
            {
                "BOLT_VAULT_PATH": str(self.root),
                "BOLT_PENDING_VAULT_PATH": str(self.pending),
                "BOLT_VAULT_FILING_PATH": str(self.filing),
                "BOLT_VAULT_FILING_AI": "off",
                "BOLT_NO_DRIVE_PUSH": "1",
                "BOLT_BRIEFING_FOCUS": "0",
            },
        )
        self.env.start()
        self.clocks = [
            patch("modules.Vault_Overview.now_ct", return_value=FROZEN),
            patch("modules.Vault_Capture.now_ct", return_value=FROZEN),
            patch("modules.Vault_Calendar.now_ct", return_value=FROZEN),
            patch("modules.Vault_Pending.now_ct", return_value=FROZEN),
        ]
        for item in self.clocks:
            item.start()
        self.week_file = patch.object(wc, "WEEK_FILE", self.week)
        self.week_file.start()
        self.week_remember = patch.object(wc, "_remember", lambda *_a, **_k: None)
        self.week_remember.start()
        self.brief_dir = patch.object(cm, "BRIEFINGS_DIR", self.briefings)
        self.brief_dir.start()
        self.drive = patch("modules.Google_Drive_Handbook.push_briefing_to_daily_log", lambda *_a, **_k: None)
        self.drive.start()

    def tearDown(self):
        self.drive.stop()
        self.brief_dir.stop()
        self.week_remember.stop()
        self.week_file.stop()
        for item in self.clocks:
            item.stop()
        self.env.stop()
        self._tmp.cleanup()

    def test_timeline_keeps_surrounding_text_and_undoes_with_the_task(self):
        store = vs.VaultStore(self.root)
        store.ensure_scaffold()
        path = self.root / "10 Bolt" / "Plan Timeline.md"
        text = path.read_text(encoding="utf-8")
        path.write_text("Keep this sentence.\n\n" + text, encoding="utf-8")
        store.add_note("Film the short", kind="task", area="00 Inbox", due="2026-10-23")
        updated = path.read_text(encoding="utf-8")
        self.assertTrue(updated.startswith("Keep this sentence."))
        self.assertIn("Film the short", updated.split("bolt:timeline:start")[1].split("bolt:timeline:end")[0])
        self.assertIn("Keep this sentence.", updated.split("bolt:timeline:start")[0])
        store.undo()
        restored = path.read_text(encoding="utf-8")
        self.assertIn("Keep this sentence.", restored)
        self.assertNotIn("Film the short", restored)

    def test_missing_markers_are_appended(self):
        store = vs.VaultStore(self.root)
        store.ensure_scaffold()
        path = self.root / "10 Bolt" / "Plan Timeline.md"
        path.write_text("Just a note.\n", encoding="utf-8")
        store.add_note("Call Randy", kind="task", area="50 Personal", due="2026-10-22")
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("Just a note."))
        self.assertIn("bolt:timeline:start", text)
        self.assertIn("bolt:timeline:end", text)
        self.assertIn("Call Randy", text)

    def test_due_question_is_not_the_week_card(self):
        ir.try_handle_intent("add task film the short by Friday")
        ir.try_handle_intent("yes")
        ir.try_handle_intent("schedule dentist Thursday 7pm")
        ir.try_handle_intent("yes")
        store = vs.VaultStore(self.root)
        store.add_note("Later", kind="task", area="00 Inbox", due="2026-10-30")
        week = ir.try_handle_intent("what's due this week")
        self.assertIn("Film the short", week)
        self.assertIn("Fri Oct 23 CT", week)
        self.assertIn("Dentist", week)
        self.assertIn("Thu Oct 22, 7:00 PM CT", week)
        self.assertNotIn("Later", week)
        self.assertFalse(self.week.exists())
        today = ir.try_handle_intent("what's due today")
        self.assertIn("Nothing is due today", today)
        card = ir.try_handle_intent("what's this week")
        self.assertIsNotNone(card)
        self.assertNotIn("Film the short", card)

    def test_briefing_adds_vault_due_only_when_present(self):
        missing = Path(self._tmp.name) / "absent"
        os.environ["BOLT_VAULT_PATH"] = str(missing)
        os.environ["BOLT_BRIEFING_FOCUS"] = "1"
        focused_without = cm.build_morning_briefing()["spoken"]
        os.environ["BOLT_BRIEFING_FOCUS"] = "0"
        full_without = cm.build_morning_briefing()["spoken"]
        self.assertNotIn("Due today", focused_without)
        self.assertNotIn("Due today", full_without)
        self.assertFalse(missing.exists())

        os.environ["BOLT_VAULT_PATH"] = str(self.root)
        vs.VaultStore(self.root).add_note("Film the short", kind="task", area="00 Inbox", due="2026-10-19")
        os.environ["BOLT_BRIEFING_FOCUS"] = "1"
        focused = cm.build_morning_briefing()["spoken"]
        os.environ["BOLT_BRIEFING_FOCUS"] = "0"
        full = cm.build_morning_briefing()
        self.assertTrue(focused.startswith(focused_without))
        self.assertIn("Due today: Film the short, task, Mon Oct 19 CT.", focused)
        self.assertTrue(full["spoken"].startswith(full_without))
        self.assertIn("Due today: Film the short, task, Mon Oct 19 CT.", full["spoken"])
        self.assertIn("Due today: Film the short, task, Mon Oct 19 CT.", full["spoken_voice"])

    def test_memory_search_includes_vault_notes_and_skips_archive(self):
        product = self.root / "30 Product Testing"
        product.mkdir()
        (product / "K&F Concept assessment.md").write_text(
            "# K&F Concept assessment\n\nzebragear check\n",
            encoding="utf-8",
        )
        archive = self.root / "90 Archive - Notion Templates"
        archive.mkdir()
        (archive / "Old.md").write_text("# Old\n\narchiveonly token\n", encoding="utf-8")
        hidden = self.root / ".bolt"
        hidden.mkdir()
        (hidden / "Secret.md").write_text("# Secret\n\nhiddenvault\n", encoding="utf-8")
        entries = [entry for entry in mi.build_memory_entries() if entry.kind == "vault_note"]
        blob = "\n".join(entry.text for entry in entries)
        self.assertIn("zebragear", blob)
        self.assertNotIn("archiveonly", blob)
        self.assertNotIn("hiddenvault", blob)

        os.environ["BOLT_VAULT_PATH"] = str(Path(self._tmp.name) / "absent")
        gone = [entry for entry in mi.build_memory_entries() if entry.kind == "vault_note"]
        self.assertEqual(gone, [])
