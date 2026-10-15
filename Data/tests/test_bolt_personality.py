#!/usr/bin/env python3
"""Personality prompt is Bolt's system prompt, not a Gemini chat."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_repo = Path(__file__).resolve().parents[2]
for _p in (_repo / "scripts", _repo / "Core"):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

from load_bolt_personality import load_bolt_personality, personality_prompt
from modules.Bolt_Personality import status


class PersonalityPromptTests(unittest.TestCase):
    def test_live_prompt_is_the_persona_not_an_api_example(self):
        text = load_bolt_personality()
        self.assertIn("Mickey-Hades", text)
        self.assertNotIn("gpt-4o", text)
        self.assertNotIn("client.chat.completions", text)
        self.assertFalse(text.lower().startswith("revised"))

    def test_draft_junk_is_stripped(self):
        raw = (
            "Revised\n# SYSTEM PROMPT\nBe Bolt.\n\n"
            "Python code\n"
            "response = client.chat.completions.create()\n"
        )
        text = personality_prompt(raw)
        self.assertIn("Be Bolt.", text)
        self.assertNotIn("Python code", text)
        self.assertNotIn("completions", text)

    def test_status_is_ready_without_gemini(self):
        info = status()
        self.assertTrue(info["ready"])
        self.assertEqual(info["readiness"], "READY")
        self.assertTrue(info["engine_uses_llm_handler"])
        self.assertTrue(info["prompt_loaded"])
        self.assertNotIn("gemini_api_key_present", info)
        self.assertNotIn("google_genai_available", info)
        self.assertIn("not gemini", info["note"].lower())

    def test_voice_and_twitch_load_the_same_persona(self):
        from Bolt_Conversation import build_system_prompt
        from modules.Bolt_Chat import SessionMemory, _ask_llm

        voice = build_system_prompt()
        self.assertIn("Mickey-Hades", voice)
        self.assertNotIn("gpt-4o", voice)

        with patch("modules.Bolt_Chat.ask_llm", return_value="Oh wow!") as mocked:
            reply = _ask_llm("idea?", "Billy streams.", SessionMemory())
        self.assertEqual(reply, "Oh wow!")
        system = mocked.call_args.kwargs["system"]
        self.assertIn("Mickey-Hades", system)
        self.assertNotIn("gpt-4o", system)


if __name__ == "__main__":
    unittest.main()
