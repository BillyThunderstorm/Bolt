import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import log_clip_performance as lcp


class LogClipPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "data").mkdir()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_record_learning_outcome_writes_jsonl_and_learns(self):
        outcome_file = self.root / "data" / "performance_outcomes.jsonl"

        with patch.object(lcp, "PERFORMANCE_OUTCOMES_FILE", outcome_file), \
             patch("modules.Think_Learn_Decide.ThinkLearnDecideEngine") as engine_cls, \
             patch("modules.Memory_Index.refresh_memory_index") as refresh:
            engine = engine_cls.return_value
            outcome = lcp._record_learning_outcome(
                game="Marvel Rivals",
                trigger="multi_kill",
                views=1200,
                likes=80,
                clip_path="clip.mp4",
                platform="TikTok",
                note="good hook",
            )

        self.assertTrue(outcome["success"])
        self.assertTrue(outcome_file.exists())
        saved = json.loads(outcome_file.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(saved["trigger"], "multi_kill")
        engine.learn_from_outcome.assert_called_once()
        refresh.assert_called_once()

    def test_success_threshold_accepts_strong_like_rate(self):
        self.assertTrue(lcp._is_success(100, 8))
        self.assertFalse(lcp._is_success(100, 1))


if __name__ == "__main__":
    unittest.main()
