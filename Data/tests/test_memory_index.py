

import sys
from pathlib import Path
_repo_root = Path(__file__).resolve().parents[2]
for _p in [_repo_root / 'Core']:
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modules import Memory_Index as mi


class MemoryIndexTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "memory" / "projects").mkdir(parents=True)
        (self.root / "memory" / "content").mkdir(parents=True)
        (self.root / "data").mkdir()
        (self.root / "logs").mkdir()

        (self.root / "memory" / "MEMORY.md").write_text(
            "# Memory\n\n## Clips\nBilly liked honest Marvel Rivals clips with real commentary.",
            encoding="utf-8",
        )
        (self.root / "memory" / "projects" / "bolt.md").write_text(
            "# Bolt\n\n## Agent Direction\nStrengthen memory retrieval before model training.",
            encoding="utf-8",
        )
        (self.root / "memory" / "content" / "product-reviews.md").write_text(
            "# Product Reviews\n\nBilly wants honest product reviews with real-world testing notes.",
            encoding="utf-8",
        )
        (self.root / "data" / "unified_memory.jsonl").write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-18T10:00:00",
                    "source": "pipeline",
                    "intent": "recording_detected",
                    "action": "start_processing",
                    "result": "started",
                    "confidence": 1.0,
                    "reason": "Processing started for Replay_2026-05-18.mp4",
                    "feedback": None,
                    "metadata": {"recording_path": "recordings/Replay_2026-05-18.mp4"},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (self.root / "data" / "processed_recordings.json").write_text(
            json.dumps(["Replay_2026-05-18.mp4"]),
            encoding="utf-8",
        )
        (self.root / "seen_clips.json").write_text(
            json.dumps(["clip_marvel_rivals_good_moment.mp4"]),
            encoding="utf-8",
        )
        (self.root / "data" / "performance_outcomes.jsonl").write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-18T11:00:00",
                    "game": "Marvel Rivals",
                    "trigger": "multi_kill",
                    "views": 2200,
                    "likes": 180,
                    "success": True,
                    "clip_path": "clip_marvel_rivals_good_moment.mp4",
                    "platform": "TikTok",
                    "note": "Strong opening hook.",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        self.index_file = self.root / "data" / "memory_index.json"

    def tearDown(self):
        self.tempdir.cleanup()

    def test_refresh_indexes_markdown_decisions_and_clips(self):
        with (
            patch.object(mi, "MEMORY_DIR", self.root / "memory"),
            patch.object(mi, "DATA_DIR", self.root / "data"),
            patch.object(mi, "LOGS_DIR", self.root / "logs"),
            patch.object(
                mi, "UNIFIED_MEMORY_FILE", self.root / "data" / "unified_memory.jsonl"
            ),
            patch.object(
                mi,
                "PROCESSED_RECORDINGS_FILE",
                self.root / "data" / "processed_recordings.json",
            ),
            patch.object(mi, "SEEN_CLIPS_FILE", self.root / "seen_clips.json"),
            patch.object(
                mi, "DECISION_AUDIT_FILE", self.root / "logs" / "decision_audit.log"
            ),
            patch.object(
                mi,
                "PERFORMANCE_OUTCOMES_FILE",
                self.root / "data" / "performance_outcomes.jsonl",
            ),
        ):
            payload = mi.refresh_memory_index(
                project_root=self.root, out_file=self.index_file
            )

        kinds = {entry["kind"] for entry in payload["entries"]}
        self.assertIn("markdown", kinds)
        self.assertIn("decision_event", kinds)
        self.assertIn("clip", kinds)
        self.assertIn("recording", kinds)
        self.assertIn("performance_outcome", kinds)
        self.assertEqual(payload["version"], 2)
        self.assertEqual(payload["vector"]["type"], "hashed_term_frequency")
        self.assertTrue(all("vector" in entry for entry in payload["entries"]))
        self.assertTrue(
            all(
                len(entry["vector"]) == mi.VECTOR_DIMENSIONS
                for entry in payload["entries"]
            )
        )

    def test_retrieve_finds_relevant_memory(self):
        with (
            patch.object(mi, "MEMORY_DIR", self.root / "memory"),
            patch.object(mi, "DATA_DIR", self.root / "data"),
            patch.object(mi, "LOGS_DIR", self.root / "logs"),
            patch.object(
                mi, "UNIFIED_MEMORY_FILE", self.root / "data" / "unified_memory.jsonl"
            ),
            patch.object(
                mi,
                "PROCESSED_RECORDINGS_FILE",
                self.root / "data" / "processed_recordings.json",
            ),
            patch.object(mi, "SEEN_CLIPS_FILE", self.root / "seen_clips.json"),
            patch.object(
                mi, "DECISION_AUDIT_FILE", self.root / "logs" / "decision_audit.log"
            ),
            patch.object(
                mi,
                "PERFORMANCE_OUTCOMES_FILE",
                self.root / "data" / "performance_outcomes.jsonl",
            ),
        ):
            mi.refresh_memory_index(project_root=self.root, out_file=self.index_file)
            results = mi.retrieve_memory(
                "Marvel Rivals clip", index_file=self.index_file
            )

        self.assertTrue(results)
        self.assertIn("clip", {item["kind"] for item in results})
        self.assertNotIn("vector", results[0])
        self.assertIn("signal", results[0])
        self.assertIn("matched_terms", results[0])

    def test_vector_retrieval_finds_decision_language(self):
        with (
            patch.object(mi, "MEMORY_DIR", self.root / "memory"),
            patch.object(mi, "DATA_DIR", self.root / "data"),
            patch.object(mi, "LOGS_DIR", self.root / "logs"),
            patch.object(
                mi, "UNIFIED_MEMORY_FILE", self.root / "data" / "unified_memory.jsonl"
            ),
            patch.object(
                mi,
                "PROCESSED_RECORDINGS_FILE",
                self.root / "data" / "processed_recordings.json",
            ),
            patch.object(mi, "SEEN_CLIPS_FILE", self.root / "seen_clips.json"),
            patch.object(
                mi, "DECISION_AUDIT_FILE", self.root / "logs" / "decision_audit.log"
            ),
            patch.object(
                mi,
                "PERFORMANCE_OUTCOMES_FILE",
                self.root / "data" / "performance_outcomes.jsonl",
            ),
        ):
            mi.refresh_memory_index(project_root=self.root, out_file=self.index_file)
            results = mi.retrieve_memory(
                "training agent memory retrieval", index_file=self.index_file
            )

        self.assertTrue(results)
        top_text = " ".join(item["summary"] for item in results[:3])
        self.assertIn("memory retrieval", top_text)

    def test_retrieve_finds_performance_outcomes(self):
        with (
            patch.object(mi, "MEMORY_DIR", self.root / "memory"),
            patch.object(mi, "DATA_DIR", self.root / "data"),
            patch.object(mi, "LOGS_DIR", self.root / "logs"),
            patch.object(
                mi, "UNIFIED_MEMORY_FILE", self.root / "data" / "unified_memory.jsonl"
            ),
            patch.object(
                mi,
                "PROCESSED_RECORDINGS_FILE",
                self.root / "data" / "processed_recordings.json",
            ),
            patch.object(mi, "SEEN_CLIPS_FILE", self.root / "seen_clips.json"),
            patch.object(
                mi, "DECISION_AUDIT_FILE", self.root / "logs" / "decision_audit.log"
            ),
            patch.object(
                mi,
                "PERFORMANCE_OUTCOMES_FILE",
                self.root / "data" / "performance_outcomes.jsonl",
            ),
        ):
            mi.refresh_memory_index(project_root=self.root, out_file=self.index_file)
            results = mi.retrieve_memory(
                "multi kill TikTok performance", index_file=self.index_file
            )

        self.assertTrue(results)
        self.assertIn("performance_outcome", {item["kind"] for item in results})

    def test_retrieve_finds_content_memory(self):
        with (
            patch.object(mi, "MEMORY_DIR", self.root / "memory"),
            patch.object(mi, "DATA_DIR", self.root / "data"),
            patch.object(mi, "LOGS_DIR", self.root / "logs"),
            patch.object(
                mi, "UNIFIED_MEMORY_FILE", self.root / "data" / "unified_memory.jsonl"
            ),
            patch.object(
                mi,
                "PROCESSED_RECORDINGS_FILE",
                self.root / "data" / "processed_recordings.json",
            ),
            patch.object(mi, "SEEN_CLIPS_FILE", self.root / "seen_clips.json"),
            patch.object(
                mi, "DECISION_AUDIT_FILE", self.root / "logs" / "decision_audit.log"
            ),
            patch.object(
                mi,
                "PERFORMANCE_OUTCOMES_FILE",
                self.root / "data" / "performance_outcomes.jsonl",
            ),
        ):
            mi.refresh_memory_index(project_root=self.root, out_file=self.index_file)
            results = mi.retrieve_memory(
                "honest product review testing", index_file=self.index_file
            )

        self.assertTrue(results)
        self.assertTrue(
            any(
                item["source"] == "memory/content/product-reviews.md"
                for item in results
            )
        )

    def test_retrieve_classifies_supportive_and_cautionary_memory(self):
        (self.root / "memory" / "content" / "lessons.md").write_text(
            "# Lessons\n\n## Strong Clip\nSimilar clip was queued and successful.\n\n"
            "## Weak Clip\nSimilar clip was rejected and skipped below score floor.",
            encoding="utf-8",
        )

        with (
            patch.object(mi, "MEMORY_DIR", self.root / "memory"),
            patch.object(mi, "DATA_DIR", self.root / "data"),
            patch.object(mi, "LOGS_DIR", self.root / "logs"),
            patch.object(
                mi, "UNIFIED_MEMORY_FILE", self.root / "data" / "unified_memory.jsonl"
            ),
            patch.object(
                mi,
                "PROCESSED_RECORDINGS_FILE",
                self.root / "data" / "processed_recordings.json",
            ),
            patch.object(mi, "SEEN_CLIPS_FILE", self.root / "seen_clips.json"),
            patch.object(
                mi, "DECISION_AUDIT_FILE", self.root / "logs" / "decision_audit.log"
            ),
            patch.object(
                mi,
                "PERFORMANCE_OUTCOMES_FILE",
                self.root / "data" / "performance_outcomes.jsonl",
            ),
        ):
            mi.refresh_memory_index(project_root=self.root, out_file=self.index_file)
            supportive = mi.retrieve_memory(
                "queued successful clip", index_file=self.index_file, limit=3
            )
            cautionary = mi.retrieve_memory(
                "rejected skipped below clip", index_file=self.index_file, limit=3
            )

        self.assertEqual(supportive[0]["signal"], "supportive")
        self.assertEqual(cautionary[0]["signal"], "cautionary")
        self.assertIn("clip", supportive[0]["matched_terms"])


if __name__ == "__main__":
    unittest.main()
