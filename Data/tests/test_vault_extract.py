"""Conversation to tasks and pages. The model is mocked. Temp vault and history."""

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
from modules import Vault_Pending as vp
from modules import Vault_Store as vs

FROZEN = datetime(2026, 10, 19, 10, 0, tzinfo=ZoneInfo("America/Chicago"))

MODEL_TASKS = {
    "tasks": [
        {"title": "film the K&F short", "due": "Friday", "area": "Product Testing"},
        {"title": "write the hook", "due": "", "area": ""},
        {"title": "call Randy", "due": "Thursday", "area": "Personal"},
    ],
    "page": None,
}


class ExtractTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "vault"
        self.root.mkdir()
        self.pending = Path(self._tmp.name) / "pending.json"
        self.filing = Path(self._tmp.name) / "filing.json"
        self.history = Path(self._tmp.name) / "history.json"
        self.history.write_text(
            json.dumps(
                [
                    {"role": "user", "content": "I need to film the K&F short by Friday."},
                    {"role": "assistant", "content": "Thursday also has a hook to write, and call Randy."},
                    {"role": "user", "content": "turn this into tasks"},
                ]
            ),
            encoding="utf-8",
        )
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
        self.clock = patch("modules.Vault_Extract.now_ct", return_value=FROZEN)
        self.clock.start()
        self.calls = []

        def fake_ask(prompt, **kwargs):
            self.calls.append((prompt, kwargs))
            return json.dumps(MODEL_TASKS)

        self.ask = patch("modules.LLM_Handler.ask_llm", side_effect=fake_ask)
        self.ask.start()

    def tearDown(self):
        self.ask.stop()
        self.clock.stop()
        self.env.stop()
        self._tmp.cleanup()

    def test_preview_lists_tasks_and_does_not_write(self):
        reply = ir.try_handle_intent("turn this into tasks")
        self.assertIn("I found 3", reply)
        self.assertIn("Film the K&F short", reply)
        self.assertIn("30 Product Testing", reply)
        self.assertIn("Fri Oct 23 CT", reply)
        self.assertIn("Write the hook", reply)
        self.assertIn("00 Inbox", reply)
        self.assertIn("Call Randy", reply)
        self.assertIn("50 Personal", reply)
        self.assertIn("only 1 and 3", reply)
        self.assertFalse(list((self.root / "10 Bolt" / "Tasks").glob("*.md")))
        self.assertEqual(len(self.calls), 1)
        prompt, kwargs = self.calls[0]
        self.assertIn("film the K&F short", prompt)
        self.assertNotIn("turn this into tasks", prompt)
        self.assertEqual(kwargs.get("task_type"), "planning")
        self.assertEqual(kwargs.get("complexity"), "high")
        self.assertGreaterEqual(kwargs.get("max_tokens"), 900)

    def test_only_some_numbers_and_one_undo(self):
        ir.try_handle_intent("turn this into tasks")
        saved = ir.try_handle_intent("only 1 and 3")
        self.assertIn("Saved 2", saved)
        tasks = self.root / "10 Bolt" / "Tasks"
        names = sorted(path.name for path in tasks.glob("*.md"))
        self.assertEqual(names, ["Call Randy.md", "Film the K&F short.md"])
        film = vs.VaultStore(self.root).read_note("10 Bolt/Tasks/Film the K&F short.md")
        self.assertEqual(film.frontmatter["due"], "2026-10-23")
        self.assertEqual(film.frontmatter["area"], "30 Product Testing")
        self.assertEqual(film.frontmatter["source"], "chat")
        stack = json.loads((self.root / ".bolt" / "undo.json").read_text(encoding="utf-8"))
        self.assertEqual(len(stack), 1)
        self.assertEqual(stack[0]["summary"], "add notes from chat")

        reply = ir.try_handle_intent("undo that")
        self.assertIn("Undid", reply)
        self.assertFalse((tasks / "Film the K&F short.md").exists())
        self.assertFalse((tasks / "Call Randy.md").exists())
        parked = list((self.root / ".bolt" / "undone").rglob("*.md"))
        self.assertGreaterEqual(len(parked), 2)

    def test_yes_saves_all_and_no_or_none_saves_nothing(self):
        ir.try_handle_intent("turn this into tasks")
        ir.try_handle_intent("no")
        self.assertFalse(any((self.root / "10 Bolt" / "Tasks").glob("*.md")))
        self.assertFalse(self.pending.exists())

        ir.try_handle_intent("turn this into tasks")
        ir.try_handle_intent("none")
        self.assertFalse(any((self.root / "10 Bolt" / "Tasks").glob("*.md")))

        ir.try_handle_intent("turn this into tasks")
        saved = ir.try_handle_intent("yes")
        self.assertIn("Saved 3", saved)
        self.assertEqual(len(list((self.root / "10 Bolt" / "Tasks").glob("*.md"))), 3)

    def test_page_from_this_lands_in_the_area_folder(self):
        def page_ask(prompt, **kwargs):
            self.calls.append((prompt, kwargs))
            return json.dumps(
                {
                    "tasks": [{"title": "ignore me", "due": "", "area": ""}],
                    "page": {
                        "title": "K&F shoot plan",
                        "area": "30 Product Testing",
                        "body": "Open with the unboxing.",
                    },
                }
            )

        self.ask.stop()
        self.ask = patch("modules.LLM_Handler.ask_llm", side_effect=page_ask)
        self.ask.start()
        reply = ir.try_handle_intent("make a page from this")
        self.assertIn("page in 30 Product Testing", reply)
        self.assertNotIn("Ignore me", reply)
        ir.try_handle_intent("yes")
        page = self.root / "30 Product Testing" / "K&F shoot plan.md"
        self.assertTrue(page.is_file())
        self.assertIn("Open with the unboxing.", page.read_text(encoding="utf-8"))
        self.assertFalse(any((self.root / "10 Bolt" / "Tasks").glob("*.md")))

    def test_bad_json_and_offline_model_write_nothing(self):
        self.ask.stop()
        self.ask = patch("modules.LLM_Handler.ask_llm", return_value="sure, here are some ideas")
        self.ask.start()
        reply = ir.try_handle_intent("turn this into tasks")
        self.assertIn("didn't save", reply.lower())
        self.assertFalse(self.pending.exists())

        self.ask.stop()
        self.ask = patch("modules.LLM_Handler.ask_llm", return_value="LLM unavailable: ollama down")
        self.ask.start()
        reply = ir.try_handle_intent("turn our chat into tasks")
        self.assertIn("couldn't reach a model", reply.lower())
        self.assertFalse(any((self.root / "10 Bolt" / "Tasks").glob("*.md")))

    def test_empty_history_and_quick_capture_skips_the_model(self):
        self.history.write_text("[]", encoding="utf-8")
        reply = ir.try_handle_intent("turn this into tasks")
        self.assertIn("don't have a recent conversation", reply.lower())
        self.assertEqual(self.calls, [])

        self.history.write_text(
            json.dumps([{"role": "user", "content": "turn this into tasks"}]),
            encoding="utf-8",
        )
        reply = ir.try_handle_intent("turn this into tasks")
        self.assertIn("don't have a recent conversation", reply.lower())

        captured = ir.try_handle_intent("add task film the short by Friday")
        self.assertIn("I'll add a task", captured)
        self.assertEqual(self.calls, [])

    def test_fenced_json_and_out_of_range(self):
        self.ask.stop()
        self.ask = patch(
            "modules.LLM_Handler.ask_llm",
            return_value="```json\n" + json.dumps(MODEL_TASKS) + "\n```",
        )
        self.ask.start()
        reply = ir.try_handle_intent("please turn the conversation into tasks")
        self.assertIn("I found 3", reply)
        snag = ir.try_handle_intent("only 9")
        self.assertIn("numbered 3", snag.lower())
        self.assertTrue(self.pending.exists())
