"""Filing learns corrections, matches note titles, and can ask a mocked model."""

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


class FilingTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "vault"
        self.root.mkdir()
        self.pending = Path(self._tmp.name) / "pending.json"
        self.filing = Path(self._tmp.name) / "filing.json"
        self.history = Path(self._tmp.name) / "history.json"
        self.env = patch.dict(
            os.environ,
            {
                "BOLT_VAULT_PATH": str(self.root),
                "BOLT_PENDING_VAULT_PATH": str(self.pending),
                "BOLT_VAULT_FILING_PATH": str(self.filing),
                "BOLT_VAULT_FILING_AI": "off",
                "BOLT_CHAT_HISTORY_PATH": str(self.history),
            },
        )
        self.env.start()
        self.clocks = [
            patch("modules.Vault_Capture.now_ct", return_value=FROZEN),
            patch("modules.Vault_Pending.now_ct", return_value=FROZEN),
            patch("modules.Vault_Filing.now_ct", return_value=FROZEN),
        ]
        for item in self.clocks:
            item.start()
        self.calls = []

        def fake_ask(prompt, **kwargs):
            self.calls.append((prompt, kwargs))
            return "Career & Creator Plan"

        self.ask = patch("modules.LLM_Handler.ask_llm", side_effect=fake_ask)
        self.ask.start()

    def tearDown(self):
        self.ask.stop()
        for item in self.clocks:
            item.stop()
        self.env.stop()
        self._tmp.cleanup()

    def _assessment(self):
        folder = self.root / "30 Product Testing"
        folder.mkdir(parents=True)
        (folder / "K&F Concept assessment.md").write_text(
            "# K&F Concept assessment\n\nA gear check.\n",
            encoding="utf-8",
        )

    def test_title_match_suggests_a_related_note(self):
        self._assessment()
        reply = ir.try_handle_intent("add task film the K&F short by Friday")
        self.assertIn("30 Product Testing", reply)
        self.assertIn("[[K&F Concept assessment]]", reply)
        self.assertFalse((self.root / "10 Bolt" / "Tasks" / "Film the K&F short.md").exists())
        ir.try_handle_intent("yes")
        note = vs.VaultStore(self.root).read_note("10 Bolt/Tasks/Film the K&F short.md")
        self.assertEqual(note.frontmatter["area"], "30 Product Testing")
        self.assertIn("[[K&F Concept assessment]]", note.body)
        self.assertEqual(self.calls, [])

    def test_correction_is_reused_and_task_stays_in_tasks(self):
        reply = ir.try_handle_intent("add task film the widget by Friday")
        self.assertIn("00 Inbox", reply)
        edited = ir.try_handle_intent("no, put that in Product Testing")
        self.assertIn("30 Product Testing", edited)
        self.assertIn("Film the widget", edited)
        ir.try_handle_intent("yes")
        note = vs.VaultStore(self.root).read_note("10 Bolt/Tasks/Film the widget.md")
        self.assertEqual(note.frontmatter["area"], "30 Product Testing")
        self.assertTrue(str(note.rel).startswith("10 Bolt/Tasks/"))

        again = ir.try_handle_intent("add task ship the widget")
        self.assertIn("30 Product Testing", again)
        self.assertEqual(self.calls, [])

    def test_saved_note_can_be_refiled_and_undone(self):
        ir.try_handle_intent("note: podcast idea about a gear episode")
        ir.try_handle_intent("yes")
        old = self.root / "20 Creator HQ & Content" / "Podcast idea about a gear episode.md"
        self.assertTrue(old.is_file())
        preview = ir.try_handle_intent("no, that's Personal")
        self.assertIn("50 Personal", preview)
        self.assertTrue(old.is_file())
        ir.try_handle_intent("yes")
        moved = self.root / "50 Personal" / "Podcast idea about a gear episode.md"
        self.assertTrue(moved.is_file())
        self.assertIn("50 Personal", moved.read_text(encoding="utf-8"))
        self.assertFalse(old.exists())
        parked = list((self.root / ".bolt" / "undone").rglob("*.md"))
        self.assertTrue(parked)
        ir.try_handle_intent("undo that")
        self.assertTrue(old.is_file())
        self.assertFalse(moved.exists())

    def test_two_areas_stay_inbox_and_dates_still_edit(self):
        for area, title in (
            ("40 Career & Creator Plan", "Launch plan"),
            ("50 Personal", "Launch dinner"),
        ):
            folder = self.root / area
            folder.mkdir(parents=True)
            (folder / f"{title}.md").write_text(f"# {title}\n", encoding="utf-8")
        reply = ir.try_handle_intent("add task plan the launch by Friday")
        self.assertIn("00 Inbox", reply)
        edited = ir.try_handle_intent("move it to Saturday")
        self.assertIn("Sat Oct 24 CT", edited)
        self.assertIn("00 Inbox", edited)

    def test_model_files_only_when_asked(self):
        reply = ir.try_handle_intent("add task something vague")
        self.assertIn("00 Inbox", reply)
        self.assertEqual(self.calls, [])
        os.environ["BOLT_VAULT_FILING_AI"] = "on"
        reply = ir.try_handle_intent("no")
        self.assertIn("won't", reply.lower())
        reply = ir.try_handle_intent("add task something vague")
        self.assertIn("40 Career & Creator Plan", reply)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][1].get("task_type"), "planning")

    def test_unknown_area_keeps_the_preview(self):
        ir.try_handle_intent("add task film the widget by Friday")
        reply = ir.try_handle_intent("no, put that in Narnia")
        self.assertIn("don't know an area", reply.lower())
        pending = json.loads(self.pending.read_text(encoding="utf-8"))
        self.assertEqual(pending["item"]["area"], "00 Inbox")

    def test_batch_correction_sets_every_item(self):
        self.history.write_text(
            json.dumps([{"role": "user", "content": "Film the widget and call Randy."}]),
            encoding="utf-8",
        )
        self.ask.stop()
        payload = {
            "tasks": [
                {"title": "film the widget", "due": "", "area": ""},
                {"title": "call Randy", "due": "", "area": ""},
            ],
            "page": None,
        }
        self.ask = patch("modules.LLM_Handler.ask_llm", return_value=json.dumps(payload))
        self.ask.start()
        ir.try_handle_intent("turn this into tasks")
        edited = ir.try_handle_intent("no, put those in Product Testing")
        self.assertIn("30 Product Testing", edited)
        ir.try_handle_intent("yes")
        store = vs.VaultStore(self.root)
        for name in ("Film the widget.md", "Call Randy.md"):
            note = store.read_note(f"10 Bolt/Tasks/{name}")
            self.assertEqual(note.frontmatter["area"], "30 Product Testing")
