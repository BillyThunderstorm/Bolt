"""Kanban board stays aligned with task notes. Temp vault, no model."""

from __future__ import annotations

import json
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


class BoardTests(unittest.TestCase):
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

    def test_new_task_lands_on_the_inbox_lane(self):
        ir.try_handle_intent("add task film the K&F short by Friday")
        self.assertFalse((self.root / "10 Bolt" / "Tasks" / "Film the K&F short.md").exists())
        saved = ir.try_handle_intent("yes")
        self.assertIn("Saved", saved)
        board = (self.root / "10 Bolt" / "Bolt Board.md").read_text(encoding="utf-8")
        self.assertIn("kanban-plugin: board", board)
        self.assertIn("**Complete**", board)
        self.assertIn("- [ ] [[Film the K&F short]]", board.split("## This Week")[0])
        spoken = ir.try_handle_intent("what's on my board?")
        self.assertIn("Inbox: Film the K&F short", spoken)
        self.assertIn("Doing: nothing", spoken)

    def test_drag_wins_and_a_second_read_is_quiet(self):
        ir.try_handle_intent("add task film the K&F short by Friday")
        ir.try_handle_intent("yes")
        path = self.root / "10 Bolt" / "Bolt Board.md"
        text = path.read_text(encoding="utf-8")
        text = text.replace("- [ ] [[Film the K&F short]]\n", "")
        text = text.replace("## Doing\n\n", "## Doing\n\n- [ ] [[Film the K&F short]]\n")
        path.write_text(text, encoding="utf-8")
        before = len(json.loads((self.root / ".bolt" / "undo.json").read_text(encoding="utf-8")))
        spoken = ir.try_handle_intent("what's on my board?")
        self.assertIn("Doing: Film the K&F short", spoken)
        note = vs.VaultStore(self.root).read_note("10 Bolt/Tasks/Film the K&F short.md")
        self.assertEqual(note.frontmatter["status"], "doing")
        log = (self.root / "10 Bolt" / "Bolt Activity Log.md").read_text(encoding="utf-8")
        self.assertIn("inbox -> doing", log)
        after = len(json.loads((self.root / ".bolt" / "undo.json").read_text(encoding="utf-8")))
        self.assertEqual(after, before + 1)
        ir.try_handle_intent("what's on my board?")
        quiet = len(json.loads((self.root / ".bolt" / "undo.json").read_text(encoding="utf-8")))
        self.assertEqual(quiet, after)

    def test_move_previews_and_undoes(self):
        ir.try_handle_intent("add task film the K&F short by Friday")
        ir.try_handle_intent("yes")
        preview = ir.try_handle_intent("move it to Doing")
        self.assertIn("I'll move Film the K&F short to Doing", preview)
        self.assertEqual(
            vs.VaultStore(self.root).read_note("10 Bolt/Tasks/Film the K&F short.md").frontmatter["status"],
            "inbox",
        )
        ir.try_handle_intent("yes")
        note = vs.VaultStore(self.root).read_note("10 Bolt/Tasks/Film the K&F short.md")
        self.assertEqual(note.frontmatter["status"], "doing")
        board = (self.root / "10 Bolt" / "Bolt Board.md").read_text(encoding="utf-8")
        self.assertIn("- [ ] [[Film the K&F short]]", board.split("## Doing")[1].split("## Done")[0])
        ir.try_handle_intent("undo that")
        note = vs.VaultStore(self.root).read_note("10 Bolt/Tasks/Film the K&F short.md")
        self.assertEqual(note.frontmatter["status"], "inbox")

    def test_ambiguous_move_asks_which(self):
        ir.try_handle_intent("add task film the K&F short by Friday")
        ir.try_handle_intent("yes")
        ir.try_handle_intent("add task film the K&F write-up by Friday")
        ir.try_handle_intent("yes")
        asked = ir.try_handle_intent("move K&F to this week")
        self.assertIn("Which one", asked)
        self.assertIn("Film the K&F short", asked)
        self.assertIn("Film the K&F write-up", asked)
        preview = ir.try_handle_intent("2")
        self.assertIn("Film the K&F write-up", preview)
        self.assertIn("This Week", preview)
        ir.try_handle_intent("yes")
        short = vs.VaultStore(self.root).read_note("10 Bolt/Tasks/Film the K&F short.md")
        writeup = vs.VaultStore(self.root).read_note("10 Bolt/Tasks/Film the K&F write-up.md")
        self.assertEqual(short.frontmatter["status"], "inbox")
        self.assertEqual(writeup.frontmatter["status"], "this-week")

    def test_custom_card_settings_and_a_non_board_stay(self):
        store = vs.VaultStore(self.root)
        store.ensure_scaffold()
        path = self.root / "10 Bolt" / "Bolt Board.md"
        text = path.read_text(encoding="utf-8")
        text = text.replace("## Inbox\n\n", "## Inbox\n\n- [ ] [[Not a task]]\n")
        text = text.replace('"show-checkboxes":true', '"show-checkboxes":true,"lane-width":272')
        path.write_text(text, encoding="utf-8")
        store.add_note("Film the short", kind="task", area="00 Inbox")
        board = path.read_text(encoding="utf-8")
        self.assertIn("[[Not a task]]", board)
        self.assertIn("[[Film the short]]", board)
        self.assertIn('"lane-width":272', board)
        self.assertIn("**Complete**", board)
        path.write_text("# Just notes\n\nHello\n", encoding="utf-8")
        store.add_note("Another short", kind="task", area="00 Inbox")
        self.assertEqual(path.read_text(encoding="utf-8"), "# Just notes\n\nHello\n")

    def test_friday_is_not_a_lane(self):
        ir.try_handle_intent("add task film the short by Friday")
        ir.try_handle_intent("yes")
        reply = ir.try_handle_intent("move film the short to Friday")
        self.assertIn("due", reply.lower())
        note = vs.VaultStore(self.root).read_note("10 Bolt/Tasks/Film the short.md")
        self.assertEqual(note.frontmatter["status"], "inbox")
        self.assertEqual(note.frontmatter["due"], "2026-10-23")
