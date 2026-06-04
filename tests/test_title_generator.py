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

    def test_ai_titles_are_cached_when_enabled(self):
        response = json.dumps({
            "titles": ["Billy just erased the lobby.", "That fight got personal."],
            "hashtags": ["MarvelRivals", "#Gaming"]
        })

        with patch.object(titles, "TITLE_CACHE", self.cache_path), \
             patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=False), \
             patch("modules.LLM_Handler.ask_llm", return_value=response) as ask_llm:
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
        with patch.object(titles, "TITLE_CACHE", self.cache_path), \
             patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=False), \
             patch("modules.LLM_Handler.ask_llm", return_value="not json"):
            generated, hashtags = titles.generate_titles(
                trigger="ace",
                game="Marvel Rivals",
                context={"config": {"quality_tiers": {"use_ai_titles": True}}},
            )

        self.assertEqual(len(generated), 3)
        self.assertIn("#MarvelRivals", hashtags)


if __name__ == "__main__":
    unittest.main()
