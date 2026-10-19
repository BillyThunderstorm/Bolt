"""Partner chat: prompt, routing, and context. LLM calls are mocked."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_repo_root / "Core"))

from modules import Chat_Partner as cp
from modules import Intent_Router as ir


def _vault_with_notes(root: Path) -> None:
    career = root / "40 Career & Creator Plan"
    career.mkdir(parents=True)
    (career / "Current priorities and next steps.md").write_text(
        "---\ntitle: Current priorities and next steps\n---\n"
        "# Current priorities and next steps\n\nShip one flagship a week.\n",
        encoding="utf-8",
    )
    testing = root / "30 Product Testing"
    testing.mkdir()
    (testing / "K&F neck holder assessment.md").write_text(
        "---\ntitle: K&F neck holder assessment\narea: 30 Product Testing\n---\n"
        "# K&F neck holder assessment\n\nThe chest strap is what keeps the shot stable.\n",
        encoding="utf-8",
    )


class ClearCommandTests(unittest.TestCase):
    def test_a_thought_that_mentions_this_week_is_conversation(self):
        reply = ir.try_handle_intent(
            "I keep thinking about this week and whether the queue is even "
            "the right place for the K&F short"
        )
        self.assertIsNone(reply)

    def test_clear_commands_still_match(self):
        self.assertIs(ir._match_action(ir._normalize("what's this week")), ir._action_week)
        self.assertIs(ir._match_action(ir._normalize("show me the posting queue")), ir._action_queue)
        self.assertIs(ir._match_action("whats next"), ir._action_next)
        self.assertIs(ir._match_action("good morning bolt"), ir._action_morning)

    def test_how_are_things_looking_still_matches(self):
        self.assertIs(ir._match_action(ir._normalize("how are things looking")), ir._action_status)


class PartnerComposeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.summary = self.root / "summary.json"
        self.vault = self.root / "vault"
        self.vault.mkdir()
        _vault_with_notes(self.vault)
        self._env = patch.dict(
            os.environ,
            {
                "BOLT_CHAT_SUMMARY_PATH": str(self.summary),
                "BOLT_CHAT_THINK": "1",
                "BOLT_CHAT_THINK_PAID": "on",
                "BOLT_VAULT_PATH": str(self.vault),
                "BOLT_CHAT_HISTORY_TURNS": "12",
            },
        )
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    def _history(self, n_pairs: int = 8):
        turns = []
        for i in range(n_pairs):
            turns.append({"role": "user", "content": f"earlier thought {i} about filming"})
            turns.append({"role": "assistant", "content": f"earlier reply {i}"})
        return turns

    def test_think_step_is_private_and_context_is_in_the_prompt(self):
        calls = []

        def fake(prompt, **kwargs):
            calls.append((prompt, kwargs))
            system = kwargs.get("system") or ""
            if "scratchpad" in system:
                return "He means the K&F shoot is a timing problem. Offer to capture a task."
            return (
                "You're stuck on the timing, not the idea. "
                "Thursday runs into Randy's shift, so I'd film earlier and use the K&F assessment. "
                "Want me to add that as a task?"
            )

        os.environ["BOLT_CHAT_SUMMARY_EVERY"] = "100"
        with patch.object(cp, "week_context", return_value="WEEK CARD TEST TOPIC widgets"):
            with patch.object(cp, "memory_context", return_value="Retrieved memory for this question:\n- honest reviews"):
                reply = cp.compose_reply(
                    "the K&F short keeps slipping",
                    history=self._history(),
                    text_mode=True,
                    ask=fake,
                )

        self.assertIn("timing", reply.lower())
        self.assertNotIn("scratchpad", reply.lower())
        self.assertNotIn("PRIVATE PLAN", reply)
        self.assertEqual(len(calls), 2)
        plan_prompt, plan_kwargs = calls[0]
        self.assertIn("scratchpad", plan_kwargs["system"])
        self.assertEqual(plan_kwargs["task_type"], "planning")
        self.assertEqual(plan_kwargs["complexity"], "high")
        self.assertIn("K&F short", plan_prompt)
        _reply_prompt, reply_kwargs = calls[1]
        system = reply_kwargs["system"]
        self.assertIn("WEEK CARD TEST TOPIC widgets", system)
        self.assertIn("honest reviews", system)
        self.assertIn("chest strap", system)
        self.assertIn("Ship one flagship", system)
        self.assertIn("timing problem", system)
        self.assertIn("TEXT MODE", system)
        self.assertIn("Mickey-Hades", system)
        self.assertGreater(len(reply_kwargs["history"]), 6)
        self.assertNotIn("gpt-4o", system)

    def test_think_off_is_one_call_and_paid_off_stays_on_chat(self):
        os.environ["BOLT_CHAT_THINK"] = "0"
        calls = []

        def fake(prompt, **kwargs):
            calls.append(kwargs)
            return "A plain reply with **one idea**."

        with patch.object(cp, "week_context", return_value="WEEK"):
            with patch.object(cp, "memory_context", return_value=""):
                reply = cp.compose_reply("hello", history=[], text_mode=True, ask=fake)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["task_type"], "chat")
        self.assertIn("**one idea**", reply)

        os.environ["BOLT_CHAT_THINK"] = "1"
        os.environ["BOLT_CHAT_THINK_PAID"] = "off"
        calls.clear()

        def fake_paid(prompt, **kwargs):
            calls.append(kwargs)
            if "scratchpad" in (kwargs.get("system") or ""):
                return "plan"
            return "reply"

        with patch.object(cp, "week_context", return_value="WEEK"):
            with patch.object(cp, "memory_context", return_value=""):
                cp.compose_reply("hello", history=[], text_mode=False, ask=fake_paid)
        self.assertEqual(calls[0]["task_type"], "chat")
        self.assertEqual(calls[0]["complexity"], "medium")

    def test_voice_strips_markdown_and_text_keeps_it(self):
        os.environ["BOLT_CHAT_THINK"] = "0"
        long_reply = "Idea. " + ("word " * 200) + " **keep** this."

        def fake(prompt, **kwargs):
            return long_reply

        with patch.object(cp, "week_context", return_value=""):
            with patch.object(cp, "memory_context", return_value=""):
                voice = cp.compose_reply("hello", text_mode=False, ask=fake)
                text = cp.compose_reply("hello", text_mode=True, ask=fake)
        self.assertNotIn("**", voice)
        self.assertLessEqual(len(voice), 420)
        self.assertIn("**keep**", text)
        self.assertGreater(len(text), 420)

    def test_running_summary_is_injected_and_refreshed(self):
        os.environ["BOLT_CHAT_THINK"] = "0"
        os.environ["BOLT_CHAT_SUMMARY_EVERY"] = "2"
        cp.save_summary(self.summary, "He is finishing the K&F review.", 0)
        calls = []

        def fake(prompt, **kwargs):
            calls.append((prompt, kwargs.get("system") or ""))
            if "running summary" in prompt.lower():
                return "He decided to film the K&F short on Friday."
            return "Friday still fits."

        history = [
            {"role": "user", "content": "maybe thursday"},
            {"role": "assistant", "content": "thursday is tight"},
            {"role": "user", "content": "friday instead"},
        ]
        with patch.object(cp, "week_context", return_value=""):
            with patch.object(cp, "memory_context", return_value=""):
                cp.compose_reply("what about friday", history=history, text_mode=True, ask=fake)
        systems = [system for _prompt, system in calls]
        self.assertTrue(any("film the K&F short on Friday" in system for system in systems))
        saved = cp.load_summary(self.summary)
        self.assertIn("Friday", saved["summary"])

    def test_offline_model_does_not_dump_the_error(self):
        os.environ["BOLT_CHAT_THINK"] = "0"

        def fake(prompt, **kwargs):
            return "LLM unavailable: ollama down"

        with patch.object(cp, "week_context", return_value=""):
            with patch.object(cp, "memory_context", return_value=""):
                reply = cp.compose_reply("hello", text_mode=True, ask=fake)
        self.assertIn("offline", reply.lower())
        self.assertNotIn("ollama", reply.lower())


if __name__ == "__main__":
    unittest.main()
