"""Targeted tests for Memory_Search (bolt memsearch). Temp files only."""

import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[2]
for _p in [_repo_root / "Core"]:
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

from modules import Memory_Index as mi
from modules import Memory_Search as ms


class MemorySearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.mem_dir = root / "memory"
        self.mem_dir.mkdir()
        self.unified = root / "unified_memory.jsonl"
        self.processed = root / "processed_recordings.json"
        self.index = root / "memory_index.json"
        (self.mem_dir / "games.md").write_text(
            "# Games\n\n## Wolverine\nWolverine stream clips held for review this week.",
            encoding="utf-8",
        )
        self.unified.write_text(
            json.dumps(
                {
                    "timestamp": "2026-10-01T19:00:00",
                    "source": "nexus",
                    "action": "hold_for_review",
                    "reason": "Wolverine recording does not match the skincare week",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        # Many short filename entries: these used to win on hash collisions.
        self.processed.write_text(
            json.dumps([f"/rec/2026-07-{d:02d}_11-53-13.mov" for d in range(1, 29)]),
            encoding="utf-8",
        )
        self.patches = [
            patch.object(mi, "MEMORY_DIR", self.mem_dir),
            patch.object(mi, "UNIFIED_MEMORY_FILE", self.unified),
            patch.object(mi, "PROCESSED_RECORDINGS_FILE", self.processed),
            patch.object(mi, "SEEN_CLIPS_FILE", root / "seen.json"),
            patch.object(mi, "DECISION_AUDIT_FILE", root / "audit.log"),
            patch.object(mi, "PERFORMANCE_OUTCOMES_FILE", root / "perf.jsonl"),
            patch.object(ms, "_INDEX", self.index),
            patch.object(ms, "_REPO", root),
            patch.object(ms, "_SOURCE_FILES", [self.unified, self.processed]),
            patch.object(ms, "_SOURCE_DIRS", [self.mem_dir]),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def test_run_builds_missing_index_and_finds_word_matches_only(self):
        self.assertFalse(self.index.exists())
        out = ms.try_run("Wolverine", limit=5)
        self.assertTrue(out["ok"], out)
        self.assertTrue(out["refreshed"])
        self.assertTrue(self.index.exists())
        self.assertGreaterEqual(out["hit_count"], 2)
        for h in out["hits"]:
            self.assertIn("wolverine", h["matched_terms"])
        self.assertIn("matched: wolverine", out["context"])

    def test_unrelated_query_returns_no_noise(self):
        out = ms.try_run("God of War", limit=5)
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["hit_count"], 0)
        self.assertGreater(out["unmatched_dropped"], 0)
        self.assertIn("no memory entries", out.get("hint", ""))

    def test_more_matched_words_rank_first(self):
        out = ms.try_run("wolverine skincare", limit=5)
        self.assertTrue(out["hits"])
        self.assertEqual(
            sorted(out["hits"][0]["matched_terms"]), ["skincare", "wolverine"]
        )

    def test_stale_index_rebuilds_and_fresh_index_does_not(self):
        ms.try_run("Wolverine")
        fresh = ms.try_run("Wolverine")
        self.assertFalse(fresh["refreshed"])
        future = time.time() + 120
        os.utime(self.unified, (future, future))
        stale = ms.try_run("Wolverine")
        self.assertTrue(stale["refreshed"])
        self.assertIn("unified_memory.jsonl", stale["refresh_reason"])
        os.utime(self.unified, (future + 120, future + 120))
        skipped = ms.try_run("Wolverine", auto_refresh=False)
        self.assertFalse(skipped["refreshed"])

    def test_status_ready_and_empty_query_soft_fails(self):
        st = ms.status()
        self.assertEqual(st["readiness"], "READY")
        self.assertTrue(st["ready"])
        self.assertTrue(st["index_stale"])  # not built yet
        out = ms.try_run("   ")
        self.assertFalse(out["ok"])
        self.assertTrue(out["error"].startswith("Memory search unavailable:"))


if __name__ == "__main__":
    unittest.main()
