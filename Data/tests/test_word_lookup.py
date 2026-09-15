"""Local tests for Word_Lookup (no live dictionary/thesaurus HTTP)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_repo / "Core"))

from modules import Word_Lookup as wl


class SpellTests(unittest.TestCase):
    def test_known_word_is_ok(self):
        result = wl.spell("honest")
        self.assertTrue(result["ok"])
        self.assertEqual(result["word"], "honest")
        self.assertEqual(result["suggestions"], [])

    def test_typo_suggests_receive(self):
        result = wl.spell("recieve")
        self.assertFalse(result["ok"])
        self.assertIn("receive", result["suggestions"])

    def test_creator_extra_tiktok(self):
        result = wl.spell("tiktok")
        self.assertTrue(result["ok"], result)

    def test_empty_word_soft_fails(self):
        result = wl.spell("   ")
        self.assertFalse(result["ok"])
        self.assertTrue(str(result["error"]).startswith("Word lookup unavailable:"))


class CheckTextTests(unittest.TestCase):
    def test_flags_typo_in_sentence(self):
        result = wl.check_text("This recieve is fine")
        self.assertFalse(result["ok"])
        words = [m["word"] for m in result["misspellings"]]
        self.assertIn("recieve", words)

    def test_clean_sentence_ok(self):
        result = wl.check_text("This clip is honest")
        self.assertTrue(result["ok"])
        self.assertGreaterEqual(result["checked"], 4)


class StatusTests(unittest.TestCase):
    def test_ready_with_word_list(self):
        info = wl.status(probe=False)
        self.assertTrue(info["ready"])
        self.assertEqual(info["readiness"], "READY")
        self.assertGreater(info["word_count"], 1000)
        self.assertEqual(info["soft_fail_prefix"], "Word lookup unavailable:")


class DefineMockTests(unittest.TestCase):
    def test_define_uses_remote_payload(self):
        payload = [
            {
                "word": "honest",
                "phonetic": "/ˈɒnɪst/",
                "meanings": [
                    {
                        "partOfSpeech": "adjective",
                        "definitions": [
                            {
                                "definition": "Free of deceit.",
                                "example": "Be honest.",
                            }
                        ],
                        "synonyms": ["truthful"],
                        "antonyms": ["dishonest"],
                    }
                ],
            }
        ]
        with patch.object(wl, "_http_json", return_value=payload):
            result = wl.define("honest")
        self.assertTrue(result["found"])
        self.assertEqual(result["phonetic"], "/ˈɒnɪst/")
        self.assertIn("Free of deceit.", result["definitions"][0]["definition"])
        self.assertIn("truthful", result["synonyms"])

    def test_define_404_is_not_found(self):
        import urllib.error

        err = urllib.error.HTTPError(
            url="https://example.invalid",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )
        with patch.object(wl, "_http_json", side_effect=err):
            result = wl.define("xyzzyx")
        self.assertFalse(result["found"])
        self.assertEqual(result["error"], "")


class MainTests(unittest.TestCase):
    def test_help_exits_zero(self):
        self.assertEqual(wl.main(["--help"]), 0)

    def test_status_json(self):
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = wl.main(["status", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(buf.getvalue())
        self.assertTrue(payload.get("ready"))

    def test_spell_typo_prints_suggestion(self):
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = wl.main(["spell", "recieve"])
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("receive", out)


class ClosestInTests(unittest.TestCase):
    def test_command_typo_queue(self):
        hits = wl.closest_in("queu", ["queue", "week", "quest"], limit=3)
        self.assertTrue(hits)
        self.assertEqual(hits[0][0], "queue")
        self.assertEqual(hits[0][1], 1)

    def test_transpose_briefing(self):
        hits = wl.closest_in("breifing", ["briefing", "bring", "filter-backlog"])
        self.assertEqual(hits[0][0], "briefing")

    def test_hyphen_fold(self):
        hits = wl.closest_in("clipdedupe", ["clip-dedupe", "clip_dedupe", "queue"])
        self.assertEqual(hits[0][1], 0)
        self.assertIn(hits[0][0], {"clip-dedupe", "clip_dedupe"})


class RepairTokensTests(unittest.TestCase):
    def test_repairs_unknown_toward_vocab(self):
        text, changes = wl.repair_tokens(
            "show the queu",
            ["queue", "week", "briefing"],
        )
        self.assertEqual(text, "show the queue")
        self.assertEqual(changes, [("queu", "queue")])

    def test_does_not_rewrite_real_words(self):
        text, changes = wl.repair_tokens("this weak is fine", ["week", "queue"])
        self.assertEqual(text, "this weak is fine")
        self.assertEqual(changes, [])


class SpokenTests(unittest.TestCase):
    def test_spoken_spell_correct(self):
        line = wl.spoken_spell("honest")
        self.assertIn("spelled correctly", line.lower())

    def test_spoken_spell_typo(self):
        line = wl.spoken_spell("recieve")
        self.assertIn("receive", line.lower())


if __name__ == "__main__":
    unittest.main()
