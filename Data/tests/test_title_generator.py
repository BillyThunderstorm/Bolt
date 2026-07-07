

import sys
from pathlib import Path
_repo_root = Path(__file__).resolve().parents[2]
for _p in [_repo_root / 'Core']:
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modules import Title_Generator as titles


class TitleGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.cache_path = Path(self.tempdir.name) / "title_cache.json"

    def tearDown(self):
        self.tempdir.cleanup()

    def test_templates_are_default_when_ai_disabled(self):
        generated, hashtags = titles.generate_titles(
            trigger="kill",
            game="Marvel Rivals",
            context={"config": {"quality_tiers": {"use_ai_titles": False}}},
        )

        self.assertEqual(len(generated), 3)
        self.assertIn("#MarvelRivals", hashtags)

    def test_on_screen_stats_prepend_to_template_titles(self):
        # Tier 2.1 wiring: when Video_Intelligence surfaces stats, they
        # are prepended to each title so the result is a data-driven
        # title like "15 KILL STREAK — Billy..." instead of just the
        # template alone.
        generated, hashtags = titles.generate_titles(
            trigger="kill",
            game="Marvel Rivals",
            context={
                "config": {"quality_tiers": {"use_ai_titles": False}},
                "on_screen_stats": ["15 KILL STREAK", "Score 27 - 19"],
            },
        )
        self.assertEqual(len(generated), 3)
        for t in generated:
            self.assertTrue(
                t.startswith("15 KILL STREAK — "),
                f"expected title to start with stat, got: {t!r}",
            )

    def test_no_on_screen_stats_keeps_template_intact(self):
        # When there's no OCR signal, titles should NOT have a leading
        # dash artifact.
        generated, _ = titles.generate_titles(
            trigger="kill",
            game="Marvel Rivals",
            context={"config": {"quality_tiers": {"use_ai_titles": False}}},
        )
        for t in generated:
            self.assertFalse(
                t.startswith(" — "),
                f"title should not have empty prefix, got: {t!r}",
            )

    def test_ai_titles_are_cached_when_enabled(self):
        response = json.dumps(
            {
                "titles": ["Billy just erased the lobby.", "That fight got personal."],
                "hashtags": ["MarvelRivals", "#Gaming"],
            }
        )

        with (
            patch.object(titles, "TITLE_CACHE", self.cache_path),
            # Force OpenAI path so the ask_llm mock is actually reached.
            # Without this, the live GEMINI_API_KEY in .env makes the
            # real Gemini call fire first and the mock is bypassed.
            patch.object(titles, "USE_GEMINI", False),
            patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=False),
            patch("modules.LLM_Handler.ask_llm", return_value=response) as ask_llm,
        ):
            generated, hashtags = titles.generate_titles(
                trigger="multi_kill",
                game="Marvel Rivals",
                score=88,
                context={
                    "creator_brain": "Billy likes dry humor and honest gaming reactions.",
                    "config": {"quality_tiers": {"use_ai_titles": True}},
                },
            )
            generated_again, _ = titles.generate_titles(
                trigger="multi_kill",
                game="Marvel Rivals",
                score=88,
                context={
                    "creator_brain": "Billy likes dry humor and honest gaming reactions.",
                    "config": {"quality_tiers": {"use_ai_titles": True}},
                },
            )

        self.assertEqual(generated[0], "Billy just erased the lobby.")
        self.assertIn("#MarvelRivals", hashtags)
        self.assertEqual(generated_again, generated)
        ask_llm.assert_called_once()

    def test_ai_failure_falls_back_to_templates(self):
        with (
            patch.object(titles, "TITLE_CACHE", self.cache_path),
            patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=False),
            patch("modules.LLM_Handler.ask_llm", return_value="not json"),
        ):
            generated, hashtags = titles.generate_titles(
                trigger="ace",
                game="Marvel Rivals",
                context={"config": {"quality_tiers": {"use_ai_titles": True}}},
            )

        self.assertEqual(len(generated), 3)
        self.assertIn("#MarvelRivals", hashtags)


if __name__ == "__main__":
    unittest.main()
