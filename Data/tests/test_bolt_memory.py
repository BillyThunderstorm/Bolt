"""Targeted tests for READY `bolt memory` (Bolt_Memory recall/remember).

Temp files + mocked LLM only — never touches the real Data/MEMORY.md and never
calls a real provider.
"""

import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[2]
for _p in [_repo_root / "Core"]:
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from modules import Bolt_Memory as bm
from modules import LLM_Handler as lh


class _TempMemory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "Core").mkdir()
        (root / "Core" / "config.json").write_text(json.dumps({"game": "Test Game"}))
        data = root / "Data"
        for d in ("people", "projects", "context", "content", "memory"):
            (data / d).mkdir(parents=True)
        (data / "MEMORY.md").write_text(
            "# Bolt Memory\n\n## Identity\nBolt is William's assistant.\n\n"
            "## Recent Notes\n- [2026-01-01] old note\n",
            encoding="utf-8",
        )
        (data / "glossary.md").write_text("PDP = product drop", encoding="utf-8")
        (data / "content" / "big.md").write_text("x" * 50000, encoding="utf-8")
        self.mem = data / "MEMORY.md"
        self.patches = [
            patch.object(bm, "MEMORY_ROOT", data),
            patch.object(bm, "MEMORY_FILE", self.mem),
            patch.object(bm, "GLOSSARY", data / "glossary.md"),
            patch.object(bm, "PEOPLE_DIR", data / "people"),
            patch.object(bm, "PROJECTS_DIR", data / "projects"),
            patch.object(bm, "CONTEXT_DIR", data / "context"),
            patch.object(bm, "CONTENT_DIR", data / "content"),
            patch.object(bm, "MEMORY_DIR", data / "memory"),
            patch.object(bm, "CONFIG_FILE", root / "Core" / "config.json"),
            patch.object(bm, "refresh_memory_index", None),
            patch.object(bm, "notify", lambda *a, **k: None),
            patch.object(bm, "_search_context", lambda q, limit=6: "### hit\nmatched note"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()


class RememberTests(_TempMemory):
    def test_adds_under_exact_section_newest_first(self):
        self.assertTrue(bm.remember("new fact"))
        lines = self.mem.read_text().splitlines()
        i = lines.index("## Recent Notes")
        self.assertTrue(lines[i + 1].endswith("] new fact"))
        self.assertEqual(lines[i + 2], "- [2026-01-01] old note")

    def test_same_day_duplicate_not_added(self):
        bm.remember("dup fact")
        r = bm.try_remember("dup fact")
        self.assertTrue(r["ok"])
        self.assertTrue(r["duplicate"])
        self.assertEqual(self.mem.read_text().count("dup fact"), 1)

    def test_subheader_does_not_match_section(self):
        self.mem.write_text("# M\n\n### Recent Notes Archive\n- a\n", encoding="utf-8")
        bm.remember("fresh", section="Recent Notes")
        text = self.mem.read_text()
        self.assertIn("### Recent Notes Archive\n- a\n", text)
        self.assertRegex(text, r"\n## Recent Notes\n- \[\d{4}-\d{2}-\d{2}\] fresh\n$")

    def test_keeps_same_inode(self):
        ino = self.mem.stat().st_ino
        bm.remember("inode check")
        self.assertEqual(self.mem.stat().st_ino, ino)
        self.assertEqual(list(self.mem.parent.glob(".MEMORY.*.tmp")), [])

    def test_empty_fact_soft_fails(self):
        r = bm.try_remember("   ")
        self.assertFalse(r["ok"])
        self.assertTrue(r["error"].startswith("Bolt memory unavailable:"))


class PromptTests(_TempMemory):
    def test_live_state_has_game(self):
        self.assertIn("Test Game", bm._live_state())

    def test_local_budget_trims(self):
        built = bm.build_recall_prompt("q", budget_chars=6000)
        self.assertLessEqual(built["chars"], 6100)
        self.assertIn("Core Memory (MEMORY.md)", built["included"])
        self.assertIn("LIVE STATE", built["system"])
        self.assertIn("matched note", built["system"])

    def test_cloud_budget_keeps_all(self):
        built = bm.build_recall_prompt("q", budget_chars=60000)
        self.assertIn("Content Memory", built["included"])
        self.assertEqual(built["dropped"], [])


class RecallTests(_TempMemory):
    def test_falls_back_when_first_provider_fails(self):
        calls = []

        def fake_ask(prompt, *, system=None, provider=None, fallback=True, **kw):
            calls.append((provider, fallback, len(system)))
            if provider == "xai":
                print("LLM Handler error (xai): boom")
                return "LLM unavailable: xai/grok: boom"
            return "local answer"

        with patch.object(bm, "recall_providers", lambda p=None: ["xai", "ollama"]), \
                patch.object(lh, "ask_llm", fake_ask):
            buf = io.StringIO()
            with redirect_stdout(buf):
                res = bm.recall_detailed("what game?")
        self.assertTrue(res["ok"])
        self.assertEqual(res["provider"], "ollama")
        self.assertEqual(res["answer"], "local answer")
        self.assertEqual(buf.getvalue(), "")  # provider noise captured, not printed
        self.assertTrue(all(fb is False for _, fb, _ in calls))
        self.assertGreater(calls[0][2], calls[1][2])  # cloud prompt bigger than local
        self.assertEqual(res["attempts"][0]["provider"], "xai")

    def test_all_fail_soft(self):
        with patch.object(bm, "recall_providers", lambda p=None: ["openai"]), \
                patch.object(lh, "ask_llm", lambda *a, **k: "LLM unavailable: openai: 429"):
            res = bm.try_recall("q")
            plain = bm.recall("q")
        self.assertTrue(plain.startswith("Recall failed:"))
        self.assertFalse(res["ok"])
        self.assertTrue(res["error"].startswith("Bolt memory unavailable:"))
        self.assertIn("429", res["error"])

    def test_cli_flags_before_question(self):
        seen = {}

        def fake_try(q, **kw):
            seen.update(q=q, **kw)
            return {"ok": True, "answer": "A", "provider": "ollama", "model": "m",
                    "prompt_chars": 1, "relevant_hits": True}

        with patch.object(bm, "try_recall", fake_try):
            buf = io.StringIO()
            with redirect_stdout(buf):
                bm.main(["recall", "--provider", "ollama", "what", "game"])
        self.assertEqual(seen["q"], "what game")
        self.assertEqual(seen["provider"], "ollama")
        self.assertIn("via ollama/m", buf.getvalue())


class HandlerFallbackFlagTests(unittest.TestCase):
    def test_fallback_false_only_named_provider(self):
        tried = []

        class _C:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kw):
                        raise RuntimeError("nope")

        with patch.object(lh, "_resolve_providers", lambda *a, **k: ["xai", "ollama"]), \
                patch.object(lh, "_get_client", lambda p: tried.append(p) or _C()):
            with redirect_stdout(io.StringIO()):
                out = lh.ask_llm("hi", provider="ollama", fallback=False)
        self.assertEqual(tried, ["ollama"])
        self.assertTrue(out.startswith("LLM unavailable:"))


if __name__ == "__main__":
    unittest.main()
