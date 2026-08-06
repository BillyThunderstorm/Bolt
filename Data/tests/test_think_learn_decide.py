

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
        (tld.MEMORY_DIR / "MEMORY.md").write_text(
            "# Notes\n- test fact", encoding="utf-8"
        )
        # Add a memory_content/ directory with a couple of .md files so
        # ingest_all_sources() finds at least 2 source paths (memory_hot
        # + memory_content) and the test_ingestion_writes_unified_memory
        # assertion `count >= 2` holds.
        content_dir = tld.MEMORY_DIR / "content"
        content_dir.mkdir(exist_ok=True)
        (content_dir / "creator-vision.md").write_text(
            "# Creator Vision\n- test content", encoding="utf-8"
        )
        (content_dir / "productivity.md").write_text(
            "# Productivity\n- test productivity", encoding="utf-8"
        )
        (tld.LOGS_DIR / "Bolt_2026-04-28.log").write_text(
            json.dumps({"level": "info", "msg": "started", "reason": "test"}) + "\n",
            encoding="utf-8",
        )

        self.engine = tld.ThinkLearnDecideEngine(
            {
                "decision_allowlist": ["queue_clip"],
                "decision_denylist": ["delete_clip"],
                # Unit tests must not call live Ollama/Grok.
                "nexus_enrich_decisions": False,
            }
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def test_ingestion_writes_unified_memory(self):
        count = self.engine.ingest_all_sources()
        self.assertGreaterEqual(count, 2)
        self.assertTrue(tld.UNIFIED_MEMORY_FILE.exists())

    def test_think_retrieves_relevant_memory_when_available(self):
        with (
            patch("modules.Think_Learn_Decide.refresh_memory_index") as refresh,
            patch(
                "modules.Think_Learn_Decide.retrieve_memory",
                return_value=[
                    {
                        "title": "Decision audit: think",
                        "source": "logs/decision_audit.log",
                        "kind": "decision_audit",
                        "score": 0.5,
                        "signal": "supportive",
                        "signal_reason": "supportive terms: queued",
                        "matched_terms": ["marvel", "rivals"],
                        "summary": "Past Marvel Rivals clip was queued for manual review.",
                    }
                ],
            ),
        ):
            thought = self.engine.think(
                {"recording": "clip.mp4", "game": "Marvel Rivals"}
            )

        refresh.assert_called_once()
        self.assertEqual(thought["retrieved_memory_count"], 1)
        self.assertIn("Marvel Rivals", thought["memory_query"])
        self.assertEqual(thought["retrieved_memory"][0]["kind"], "decision_audit")
        self.assertEqual(thought["memory_influence"]["net_direction"], "supportive")
        self.assertEqual(thought["memory_influence"]["supportive"], 1)

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

    def test_memory_context_adjusts_proposal_confidence(self):
        base = self.engine.propose_actions(
            [{"action": "queue_clip", "score": 70, "clip_path": "plain.mp4"}]
        )[0]
        boosted = self.engine.propose_actions(
            [
                {
                    "action": "queue_clip",
                    "score": 70,
                    "clip_path": "good.mp4",
                    "memory_context": [
                        {
                            "title": "Decision audit: think",
                            "score": 0.8,
                            "summary": "Similar clip was queued and approved for manual review.",
                        }
                    ],
                }
            ]
        )[0]
        reduced = self.engine.propose_actions(
            [
                {
                    "action": "queue_clip",
                    "score": 70,
                    "clip_path": "weak.mp4",
                    "memory_context": [
                        {
                            "title": "Decision audit: blocked",
                            "score": 0.8,
                            "summary": "Similar clip was rejected, skipped, and below score floor.",
                        }
                    ],
                }
            ]
        )[0]

        self.assertGreater(boosted.confidence, base.confidence)
        self.assertLess(reduced.confidence, base.confidence)
        self.assertIn("memory boosted confidence", boosted.reason)
        self.assertIn("memory reduced confidence", reduced.reason)

    def test_memory_influence_adjusts_proposal_confidence(self):
        base = self.engine.propose_actions(
            [{"action": "queue_clip", "score": 70, "clip_path": "plain.mp4"}]
        )[0]
        boosted = self.engine.propose_actions(
            [
                {
                    "action": "queue_clip",
                    "score": 70,
                    "clip_path": "good.mp4",
                    "memory_influence": {
                        "supportive": 2,
                        "cautionary": 0,
                        "mixed": 0,
                        "context": 1,
                        "net_direction": "supportive",
                        "confidence_delta": 0.04,
                        "strongest_match": {"title": "Strong product test"},
                    },
                }
            ]
        )[0]

        self.assertGreater(boosted.confidence, base.confidence)
        self.assertIn("memory boosted confidence", boosted.reason)
        self.assertIn("Strong product test", boosted.reason)

    def test_learning_updates_model(self):
        self.engine.learn_from_feedback(
            "queue_clip", accepted=False, feedback_text="bad fit"
        )
        self.engine.learn_from_outcome(
            "queue_clip", success=True, details={"clip_path": "x.mp4"}
        )
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

        with (
            patch(
                "modules.Think_Learn_Decide._format_for_tiktok",
                return_value="clipA_tiktok.mp4",
            ),
            patch("modules.Think_Learn_Decide._add_to_queue") as add_to_queue,
        ):
            applied = self.engine.apply_approved()

        self.assertEqual(applied, 1)
        add_to_queue.assert_called_once()


class ThinkAndProposeTests(unittest.TestCase):
    """The single-call bridge between think() and propose_actions().

    These tests prove the convenience method wires retrieved memory into
    ranking without forcing callers to thread memory_influence through
    every candidate by hand. They also verify back-compat: callers who
    already pass memory_influence on a candidate are not overwritten.
    """

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
        (tld.MEMORY_DIR / "MEMORY.md").write_text(
            "# Notes\n- test fact", encoding="utf-8"
        )

        self.engine = tld.ThinkLearnDecideEngine(
            {
                "decision_allowlist": ["queue_clip"],
                "decision_denylist": ["delete_clip"],
                # Unit tests must not call live Ollama/Grok.
                "nexus_enrich_decisions": False,
            }
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def test_supportive_memory_boosts_matching_proposal(self):
        """A supportive memory hit should raise the proposal's confidence."""
        with (
            patch("modules.Think_Learn_Decide.refresh_memory_index"),
            patch(
                "modules.Think_Learn_Decide.retrieve_memory",
                return_value=[
                    {
                        "title": "Past Marvel Rivals clip was queued",
                        "source": "logs/decision_audit.log",
                        "kind": "decision_audit",
                        "score": 0.8,
                        "signal": "supportive",
                        "matched_terms": ["marvel", "rivals"],
                        "summary": "Past Marvel Rivals clip was queued for manual review.",
                    }
                ],
            ),
        ):
            baseline = self.engine.propose_actions(
                [{"action": "queue_clip", "score": 70, "clip_path": "a.mp4"}]
            )[0]
            thought, proposals = self.engine.think_and_propose(
                {"game": "Marvel Rivals", "recording": "a.mp4"},
                [{"action": "queue_clip", "score": 70, "clip_path": "a.mp4"}],
            )

        self.assertEqual(thought["retrieved_memory_count"], 1)
        self.assertEqual(thought["memory_influence"]["net_direction"], "supportive")
        self.assertGreater(proposals[0].confidence, baseline.confidence)
        self.assertIn("memory boosted confidence", proposals[0].reason)

    def test_cautionary_memory_reduces_proposal_confidence(self):
        """A cautionary memory hit should lower the proposal's confidence."""
        with (
            patch("modules.Think_Learn_Decide.refresh_memory_index"),
            patch(
                "modules.Think_Learn_Decide.retrieve_memory",
                return_value=[
                    {
                        "title": "Past clip was rejected",
                        "source": "logs/decision_audit.log",
                        "kind": "decision_audit",
                        "score": 0.8,
                        "signal": "cautionary",
                        "matched_terms": ["rejected"],
                        "summary": "Similar clip was rejected and below score floor.",
                    }
                ],
            ),
        ):
            baseline = self.engine.propose_actions(
                [{"action": "queue_clip", "score": 70, "clip_path": "a.mp4"}]
            )[0]
            thought, proposals = self.engine.think_and_propose(
                {"game": "Test", "recording": "a.mp4"},
                [{"action": "queue_clip", "score": 70, "clip_path": "a.mp4"}],
            )

        self.assertEqual(thought["memory_influence"]["net_direction"], "cautionary")
        self.assertLess(proposals[0].confidence, baseline.confidence)
        self.assertIn("memory reduced confidence", proposals[0].reason)

    def test_no_memory_match_returns_proposals_unchanged(self):
        """With empty retrieval, think_and_propose matches plain propose_actions."""
        with (
            patch("modules.Think_Learn_Decide.refresh_memory_index"),
            patch(
                "modules.Think_Learn_Decide.retrieve_memory", return_value=[]
            ),
        ):
            thought, proposals = self.engine.think_and_propose(
                {"game": "Anything", "recording": "a.mp4"},
                [{"action": "queue_clip", "score": 70, "clip_path": "a.mp4"}],
            )

        self.assertEqual(thought["retrieved_memory_count"], 0)
        self.assertEqual(thought["memory_influence"]["net_direction"], "neutral")
        # Confidence should equal the plain-score baseline.
        plain = self.engine.propose_actions(
            [{"action": "queue_clip", "score": 70, "clip_path": "a.mp4"}]
        )[0]
        self.assertAlmostEqual(proposals[0].confidence, plain.confidence, places=6)

    def test_caller_provided_memory_influence_is_not_overwritten(self):
        """If the caller already attached memory_influence, keep it intact."""
        caller_influence = {
            "supportive": 5,
            "cautionary": 0,
            "mixed": 0,
            "context": 0,
            "net_direction": "supportive",
            "confidence_delta": 0.10,
            "strongest_match": {"title": "Caller-provided hit"},
        }
        with (
            patch("modules.Think_Learn_Decide.refresh_memory_index"),
            patch(
                "modules.Think_Learn_Decide.retrieve_memory",
                return_value=[
                    {
                        "title": "Different memory",
                        "source": "x",
                        "kind": "decision_audit",
                        "score": 0.5,
                        "signal": "cautionary",
                        "summary": "should be ignored",
                    }
                ],
            ),
        ):
            thought, proposals = self.engine.think_and_propose(
                {"game": "Test", "recording": "a.mp4"},
                [
                    {
                        "action": "queue_clip",
                        "score": 70,
                        "clip_path": "a.mp4",
                        "memory_influence": caller_influence,
                    }
                ],
            )

        # Reason should reference the caller's hit, not the retrieved one.
        self.assertIn("Caller-provided hit", proposals[0].reason)
        self.assertNotIn("should be ignored", proposals[0].reason)
        # And the retrieved memory is still surfaced in the thought for logging.
        self.assertEqual(thought["retrieved_memory_count"], 1)

    def test_think_and_propose_returns_ranked_proposals(self):
        """The returned proposals are still sorted by confidence descending."""
        with (
            patch("modules.Think_Learn_Decide.refresh_memory_index"),
            patch(
                "modules.Think_Learn_Decide.retrieve_memory",
                return_value=[
                    {
                        "title": "Helpful memory",
                        "source": "x",
                        "kind": "decision_audit",
                        "score": 0.7,
                        "signal": "supportive",
                        "summary": "boost the second candidate",
                    }
                ],
            ),
        ):
            _, proposals = self.engine.think_and_propose(
                {"game": "Test", "recording": "a.mp4"},
                [
                    {"action": "queue_clip", "score": 90, "clip_path": "a.mp4"},
                    {"action": "queue_clip", "score": 60, "clip_path": "b.mp4"},
                ],
            )

        # Proposals sorted by confidence descending.
        confidences = [p.confidence for p in proposals]
        self.assertEqual(confidences, sorted(confidences, reverse=True))

    def test_propose_actions_unchanged_for_back_compat(self):
        """Old callers that call propose_actions() directly still work."""
        # Regression guard: the existing memory_influence path still works.
        proposals = self.engine.propose_actions(
            [
                {"action": "queue_clip", "score": 70, "clip_path": "plain.mp4"},
                {
                    "action": "queue_clip",
                    "score": 70,
                    "clip_path": "boosted.mp4",
                    "memory_influence": {
                        "supportive": 3,
                        "cautionary": 0,
                        "mixed": 0,
                        "context": 0,
                        "net_direction": "supportive",
                        "confidence_delta": 0.06,
                        "strongest_match": {"title": "Manual memory"},
                    },
                },
            ]
        )
        # The boosted one wins because its reason includes the manual hit.
        boosted = next(p for p in proposals if "Manual memory" in p.reason)
        plain = next(p for p in proposals if "Manual memory" not in p.reason)
        self.assertGreater(boosted.confidence, plain.confidence)


if __name__ == "__main__":
    unittest.main()
