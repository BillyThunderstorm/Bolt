#!/usr/bin/env python3
"""Nexus provider routing — Ollama/Grok preferred; Gemini opt-in only."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_repo_root = Path(__file__).resolve().parents[2]
for _p in [_repo_root / "Core"]:
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

from modules.Nexus_Creator import NexusCreator


class NexusCreatorRoutingTests(unittest.TestCase):
    def test_high_strategy_stays_on_ollama_when_paid_disallowed(self):
        with patch.dict(
            os.environ,
            {
                "XAI_API_KEY": "xai-test",
                "GEMINI_API_KEY": "gem-test",
                "NEXUS_ALLOW_PAID": "false",
                "NEXUS_USE_GEMINI": "false",
                "NEXUS_PREFERRED": "ollama",
            },
            clear=False,
        ):
            nexus = NexusCreator()
            with patch.object(nexus, "_is_ollama_healthy", return_value=True):
                provider = nexus._pick_provider(
                    task_type="strategy",
                    complexity="high",
                    allow_paid=None,
                    force_provider=None,
                )
        self.assertEqual(provider, "ollama")

    def test_paid_opt_in_uses_grok_for_strategy(self):
        with patch.dict(
            os.environ,
            {
                "XAI_API_KEY": "xai-test",
                "GEMINI_API_KEY": "gem-test",
                "NEXUS_ALLOW_PAID": "false",
                "NEXUS_USE_GEMINI": "false",
            },
            clear=False,
        ):
            nexus = NexusCreator()
            provider = nexus._pick_provider(
                task_type="strategy",
                complexity="high",
                allow_paid=True,
                force_provider=None,
            )
        self.assertEqual(provider, "grok")

    def test_gemini_not_used_when_ollama_down_unless_enabled(self):
        with patch.dict(
            os.environ,
            {
                "XAI_API_KEY": "xai-test",
                "GEMINI_API_KEY": "gem-test",
                "NEXUS_ALLOW_PAID": "false",
                "NEXUS_USE_GEMINI": "false",
                "NEXUS_PREFERRED": "ollama",
            },
            clear=False,
        ):
            nexus = NexusCreator()
            with patch.object(nexus, "_is_ollama_healthy", return_value=False):
                provider = nexus._pick_provider(
                    task_type="strategy",
                    complexity="high",
                    allow_paid=False,
                    force_provider=None,
                )
        self.assertEqual(provider, "none")

    def test_gemini_last_resort_when_explicitly_enabled(self):
        with patch.dict(
            os.environ,
            {
                "XAI_API_KEY": "xai-test",
                "GEMINI_API_KEY": "gem-test",
                "NEXUS_ALLOW_PAID": "false",
                "NEXUS_USE_GEMINI": "true",
                "NEXUS_PREFERRED": "ollama",
            },
            clear=False,
        ):
            nexus = NexusCreator()
            with patch.object(nexus, "_is_ollama_healthy", return_value=False):
                provider = nexus._pick_provider(
                    task_type="strategy",
                    complexity="high",
                    allow_paid=False,
                    force_provider=None,
                )
        self.assertEqual(provider, "gemini")

    def test_consult_ollama_path_does_not_call_gemini(self):
        with patch.dict(
            os.environ,
            {
                "XAI_API_KEY": "xai-test",
                "GEMINI_API_KEY": "gem-test",
                "NEXUS_ALLOW_PAID": "false",
                "NEXUS_USE_GEMINI": "false",
            },
            clear=False,
        ):
            nexus = NexusCreator()
            mock_client = patch.object(nexus, "_get_client").start()
            mock_completion = mock_client.return_value.chat.completions.create
            mock_completion.return_value.choices = [
                type("C", (), {"message": type("M", (), {"content": "Local advice."})()})()
            ]
            with (
                patch.object(nexus, "_is_ollama_healthy", return_value=True),
                patch.object(
                    nexus, "_enrich_with_vector_memory", return_value="ctx"
                ),
                patch.object(nexus, "_ask_gemini") as gemini,
                patch.object(nexus, "_log_advice"),
            ):
                result = nexus.consult(
                    "test topic",
                    task_type="general",
                    complexity="medium",
                    allow_paid=False,
                )
            patch.stopall()

        self.assertEqual(result["provider"], "ollama")
        self.assertEqual(result["advice"], "Local advice.")
        gemini.assert_not_called()


if __name__ == "__main__":
    unittest.main()
