import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modules import Think_Learn_Decide as tld


class ThinkLearnDecideTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)

        tld.DATA_DIR = root / "data"
        tld.LOGS_DIR = root / "logs"
        tld.MEMORY_DIR = root / "memory"
        tld.UNIFIED_MEMORY_FILE = tld.DATA_DIR / "unified_memory.jsonl"
        tld.SOURCE_REGISTRY_FILE = tld.DATA_DIR / "source_registry.json"
        tld.DECISION_MODEL_FILE = tld.DATA_DIR / "decision_model.json"
        tld.AUDIT_LOG_FILE = tld.LOGS_DIR / "decision_audit.log"
        tld.PENDING_PROPOSALS_FILE = tld.DATA_DIR / "pending_proposals.json"

        tld.DATA_DIR.mkdir(parents=True, exist_ok=True)
        tld.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        tld.MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        (tld.MEMORY_DIR / "MEMORY.md").write_text("# Notes\n- test fact", encoding="utf-8")
        (tld.LOGS_DIR / "Bolt_2026-04-28.log").write_text(
            json.dumps({"level": "info", "msg": "started", "reason": "test"}) + "\n",
            encoding="utf-8",
        )

        self.engine = tld.ThinkLearnDecideEngine(
            {"decision_allowlist": ["queue_clip"], "decision_denylist": ["delete_clip"]}
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def test_ingestion_writes_unified_memory(self):
        count = self.engine.ingest_all_sources()
        self.assertGreaterEqual(count, 2)
        self.assertTrue(tld.UNIFIED_MEMORY_FILE.exists())

    def test_proposal_ranking_and_policy(self):
        proposals = self.engine.propose_actions(
            [
                {"action": "queue_clip", "score": 90, "clip_path": "a.mp4"},
                {"action": "delete_clip", "score": 95, "clip_path": "b.mp4"},
            ]
        )
        self.assertEqual(proposals[0].action, "delete_clip")
        self.assertFalse(self.engine.enforce_action_policy(proposals[0]))
        self.assertTrue(any(self.engine.enforce_action_policy(p) for p in proposals))

    def test_learning_updates_model(self):
        self.engine.learn_from_feedback("queue_clip", accepted=False, feedback_text="bad fit")
        self.engine.learn_from_outcome("queue_clip", success=True, details={"clip_path": "x.mp4"})
        model = json.loads(tld.DECISION_MODEL_FILE.read_text(encoding="utf-8"))
        self.assertIn("feedback_by_action", model)
        self.assertIn("outcomes_by_action", model)
        self.assertGreaterEqual(model["outcomes_by_action"]["queue_clip"]["total"], 1)

    def test_pending_batch_resolution(self):
        proposal = self.engine.propose_actions(
            [{"action": "queue_clip", "score": 80, "clip_path": "clip1.mp4"}]
        )[0]
        self.engine.enqueue_pending_proposal(proposal)
        pending = self.engine.pending_proposals()
        self.assertEqual(len(pending), 1)
        action_id = pending[0]["proposal"]["action_id"]
        resolved = self.engine.resolve_pending(action_id, approved=True, note="ok")
        self.assertTrue(resolved)
        updated = self.engine.pending_proposals()
        self.assertEqual(updated[0]["status"], "approved")

    def test_apply_approved_executes_queue_clip(self):
        proposal = self.engine.propose_actions(
            [
                {
                    "action": "queue_clip",
                    "score": 81,
                    "clip_path": "clipA.mp4",
                    "title": "My title",
                    "hashtags": ["gaming"],
                    "style": "letterbox",
                }
            ]
        )[0]
        self.engine.enqueue_pending_proposal(proposal)
        action_id = self.engine.pending_proposals()[0]["proposal"]["action_id"]
        self.engine.resolve_pending(action_id, approved=True, note="ship it")

        with patch("modules.Think_Learn_Decide._format_for_tiktok", return_value="clipA_tiktok.mp4"), \
             patch("modules.Think_Learn_Decide._add_to_queue") as add_to_queue:
            applied = self.engine.apply_approved()

        self.assertEqual(applied, 1)
        add_to_queue.assert_called_once()


if __name__ == "__main__":
    unittest.main()
