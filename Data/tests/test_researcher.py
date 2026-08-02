"""Tests for the Researcher role module.

Covers:
- Profile loading
- Hard-constraint extraction
- C7 gate (Trump/MAGA/insulting content filter)
- C6 soft flag heuristic
- Candidate gating end-to-end
- Research log append-only behavior
- Summary builder shape
- Research questions generation

The Researcher role exists because Billy's bottleneck (per Q2 of the
interview) is "no roadmap, no example to follow." These tests confirm the
module behaves as designed.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Path shim — Researcher.py lives in Core/modules/, tests live in Data/tests/
_repo_root = Path(__file__).resolve().parents[2]
for _p in [_repo_root / "Core"]:
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

from modules import Researcher as rs  # noqa: E402


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

SAMPLE_PROFILE = {
    "_meta": {"schema_version": 1},
    "vision": {
        "career_goal": "Honest product reviewer. Brand sponsorships + event hosting.",
        "named_aspirations": [
            "chosen by gaming companies to test newest releases",
            "hosting/presenting at game awards and events like Dream Con",
            "creating with Marvel",
        ],
    },
    "lane_mix": {
        "target": {
            "gaming_anime_entertainment": 25,
            "tech_gadgets_ai": 25,
            "general_product_testing": 25,
            "skincare_personal_advice": 25,
        },
    },
    "hard_constraints": [
        {"id": "C1", "text": "no gimmick content"},
        {"id": "C2", "text": "direction over execution"},
        {"id": "C5", "text": "every recommendation cross-checked against user interests"},
        {"id": "C6", "text": "authenticity outranks profitability"},
        {"id": "C7", "text": "no Trump/MAGA/insulting"},
    ],
}


def _tmp_dir_patcher(monkeypatch_target_attr: str, tmp_path: Path):
    """Patch a path constant in the Researcher module to point at a tmp dir."""
    def _patcher():
        return patch.object(rs, monkeypatch_target_attr, tmp_path / "research_log.jsonl")
    return _patcher


# ──────────────────────────────────────────────────────────────────────────────
# Profile loading
# ──────────────────────────────────────────────────────────────────────────────

class ProfileLoadingTests(unittest.TestCase):
    def test_load_profile_returns_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            profile_file = tmp_path / "user_profile.json"
            profile_file.write_text(json.dumps(SAMPLE_PROFILE))
            with patch.object(rs, "USER_PROFILE", profile_file):
                profile = rs.load_profile()
                self.assertEqual(profile["vision"]["career_goal"], SAMPLE_PROFILE["vision"]["career_goal"])

    def test_load_profile_returns_empty_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does_not_exist.json"
            with patch.object(rs, "USER_PROFILE", missing):
                profile = rs.load_profile()
                self.assertEqual(profile, {})

    def test_load_profile_returns_empty_on_malformed_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text("{not valid json")
            with patch.object(rs, "USER_PROFILE", bad):
                profile = rs.load_profile()
                self.assertEqual(profile, {})

    def test_get_career_goal(self):
        self.assertEqual(
            rs.get_career_goal(SAMPLE_PROFILE),
            SAMPLE_PROFILE["vision"]["career_goal"],
        )

    def test_get_career_goal_returns_empty_for_missing_profile(self):
        self.assertEqual(rs.get_career_goal({}), "")

    def test_get_named_aspirations(self):
        aspirations = rs.get_named_aspirations(SAMPLE_PROFILE)
        self.assertEqual(len(aspirations), 3)
        self.assertIn("creating with Marvel", aspirations)

    def test_get_hard_constraints(self):
        constraints = rs.get_hard_constraints(SAMPLE_PROFILE)
        self.assertEqual(len(constraints), 5)
        c7 = next(c for c in constraints if c["id"] == "C7")
        self.assertIn("Trump", c7["text"])


# ──────────────────────────────────────────────────────────────────────────────
# C7 gate (no Trump/MAGA/insulting content)
# ──────────────────────────────────────────────────────────────────────────────

class C7GateTests(unittest.TestCase):
    def test_c7_passes_for_clean_text(self):
        result = rs.check_c7("honest product reviewer focused on gaming")
        self.assertTrue(result["passes"])
        self.assertEqual(result["matches"], [])

    def test_c7_blocks_trump(self):
        result = rs.check_c7("big fan of Trump and his policies")
        self.assertFalse(result["passes"])
        self.assertGreater(len(result["matches"]), 0)

    def test_c7_blocks_maga(self):
        result = rs.check_c7("MAGA supporter reviewing tech")
        self.assertFalse(result["passes"])

    def test_c7_blocks_case_insensitive(self):
        result = rs.check_c7("TRUMP endorsed this product")
        self.assertFalse(result["passes"])

    def test_c7_handles_empty_string(self):
        result = rs.check_c7("")
        self.assertTrue(result["passes"])


# ──────────────────────────────────────────────────────────────────────────────
# C6 soft flag (heuristic, not blocking)
# ──────────────────────────────────────────────────────────────────────────────

class C6FlagTests(unittest.TestCase):
    def test_c6_clean_text(self):
        result = rs.check_c6_flags("honest take, mentioned pros and cons")
        self.assertFalse(result["flagged"])

    def test_c6_flags_shills(self):
        result = rs.check_c6_flags("this creator shills everything they get sent")
        self.assertTrue(result["flagged"])
        self.assertIn("shills", result["matches"])

    def test_c6_flags_dropshipped(self):
        result = rs.check_c6_flags("dropshipped product review")
        self.assertTrue(result["flagged"])

    def test_c6_handles_empty_string(self):
        result = rs.check_c6_flags("")
        self.assertFalse(result["flagged"])


# ──────────────────────────────────────────────────────────────────────────────
# Candidate gating end-to-end
# ──────────────────────────────────────────────────────────────────────────────

class CandidateGatingTests(unittest.TestCase):
    def _candidate(self, **kwargs):
        base = {
            "name": "Test Creator",
            "platform": "YouTube",
            "summary": "Honest product reviewer, gaming background",
            "why_match": "Does adjacent work",
            "public_signal": "long-form honest reviews, no gimmicks",
        }
        base.update(kwargs)
        return base

    def test_clean_candidate_cleared(self):
        candidate = self._candidate()
        gated = rs.gate_candidate(candidate, SAMPLE_PROFILE)
        self.assertEqual(gated["gate"]["verdict"], "cleared")
        self.assertTrue(gated["gate"]["c7_passes"])
        self.assertFalse(gated["gate"]["c6_flagged"])
        self.assertTrue(gated["gate"]["c5_user_decision_required"])

    def test_c7_blocked_candidate(self):
        candidate = self._candidate(
            public_signal="big Trump supporter reviewing tech"
        )
        gated = rs.gate_candidate(candidate, SAMPLE_PROFILE)
        self.assertEqual(gated["gate"]["verdict"], "blocked_c7")
        self.assertFalse(gated["gate"]["c7_passes"])

    def test_c6_flagged_candidate(self):
        candidate = self._candidate(
            public_signal="creator shills everything they review"
        )
        gated = rs.gate_candidate(candidate, SAMPLE_PROFILE)
        self.assertEqual(gated["gate"]["verdict"], "flagged_c6")
        self.assertTrue(gated["gate"]["c6_flagged"])

    def test_user_test_always_required(self):
        """C5 user test must always be surfaced, even on cleared candidates."""
        candidate = self._candidate()
        gated = rs.gate_candidate(candidate, SAMPLE_PROFILE)
        self.assertTrue(gated["gate"]["c5_user_decision_required"])
        self.assertIn("Would Billy want to be known for this", gated["gate"]["user_test"])
        self.assertIn("believe in / stand behind / trust it", gated["gate"]["user_test"])

    def test_candidate_gate_does_not_mutate_input_missing_fields(self):
        """Candidates with no public_signal shouldn't crash the gate."""
        candidate = {"name": "Bare bones", "summary": "minimal info"}
        gated = rs.gate_candidate(candidate, SAMPLE_PROFILE)
        self.assertEqual(gated["gate"]["verdict"], "cleared")


# ──────────────────────────────────────────────────────────────────────────────
# Research log (append-only, file-level)
# ──────────────────────────────────────────────────────────────────────────────

class ResearchLogTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self._log_patcher = patch.object(
            rs, "RESEARCH_LOG", self.tmp_path / "research_log.jsonl"
        )
        self._log_patcher.start()

    def tearDown(self):
        self._log_patcher.stop()
        self._tmp.cleanup()

    def test_log_finding_creates_file(self):
        rs.log_finding({"name": "Test", "summary": "test"}, finding_type="general")
        self.assertTrue((self.tmp_path / "research_log.jsonl").exists())

    def test_log_finding_appends_timestamp(self):
        rs.log_finding({"x": 1}, finding_type="general")
        entries = rs.read_log()
        self.assertEqual(len(entries), 1)
        self.assertIn("timestamp", entries[0])
        self.assertIn("finding_type", entries[0])

    def test_log_finding_with_profile_runs_gate(self):
        candidate = {
            "name": "Test",
            "summary": "clean",
            "public_signal": "honest reviews",
        }
        rs.log_finding(candidate, finding_type="candidate_creator", profile=SAMPLE_PROFILE)
        entries = rs.read_log()
        self.assertEqual(entries[0]["gate"]["verdict"], "cleared")

    def test_log_finding_general_does_not_run_gate(self):
        """General findings don't get gated — only candidate_creator does."""
        rs.log_finding({"note": "thinking about X"}, finding_type="general")
        entries = rs.read_log()
        self.assertNotIn("gate", entries[0])

    def test_log_is_append_only(self):
        for i in range(3):
            rs.log_finding({"n": i}, finding_type="general")
        entries = rs.read_log()
        self.assertEqual(len(entries), 3)
        self.assertEqual([e["n"] for e in entries], [0, 1, 2])

    def test_read_log_skips_malformed_lines(self):
        log = self.tmp_path / "research_log.jsonl"
        log.write_text(
            json.dumps({"good": 1}) + "\n" +
            "this is not json\n" +
            json.dumps({"good": 2}) + "\n"
        )
        entries = rs.read_log()
        self.assertEqual(len(entries), 2)
        self.assertEqual([e["good"] for e in entries], [1, 2])


# ──────────────────────────────────────────────────────────────────────────────
# Research questions
# ──────────────────────────────────────────────────────────────────────────────

class ResearchQuestionsTests(unittest.TestCase):
    def test_questions_returns_list(self):
        questions = rs.get_research_questions(SAMPLE_PROFILE)
        self.assertIsInstance(questions, list)
        self.assertGreater(len(questions), 0)

    def test_questions_have_required_fields(self):
        questions = rs.get_research_questions(SAMPLE_PROFILE)
        for q in questions:
            self.assertIn("id", q)
            self.assertIn("question", q)
            self.assertIn("why", q)
            self.assertIn("status", q)

    def test_through_line_question_present(self):
        questions = rs.get_research_questions(SAMPLE_PROFILE)
        ids = [q["id"] for q in questions]
        self.assertIn("through_line", ids)

    def test_creator_examples_question_present(self):
        questions = rs.get_research_questions(SAMPLE_PROFILE)
        ids = [q["id"] for q in questions]
        self.assertIn("creator_examples", ids)

    def test_aspirations_question_includes_named_aspirations(self):
        questions = rs.get_research_questions(SAMPLE_PROFILE)
        asp_q = next(q for q in questions if q["id"] == "aspirations_research")
        self.assertIn("Marvel", asp_q["question"])
        self.assertIn("Dream Con", asp_q["question"])


# ──────────────────────────────────────────────────────────────────────────────
# Summary builder
# ──────────────────────────────────────────────────────────────────────────────

class SummaryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self._log_patcher = patch.object(
            rs, "RESEARCH_LOG", self.tmp_path / "research_log.jsonl"
        )
        self._profile_patcher = patch.object(
            rs, "USER_PROFILE", self.tmp_path / "user_profile.json"
        )
        self._log_patcher.start()
        self._profile_patcher.start()
        (self.tmp_path / "user_profile.json").write_text(json.dumps(SAMPLE_PROFILE))

    def tearDown(self):
        self._log_patcher.stop()
        self._profile_patcher.stop()
        self._tmp.cleanup()

    def test_summary_returns_required_fields(self):
        s = rs.summary()
        self.assertIn("user_career_goal", s)
        self.assertIn("named_aspirations", s)
        self.assertIn("open_questions", s)
        self.assertIn("next_action", s)

    def test_summary_handles_empty_log(self):
        s = rs.summary()
        self.assertEqual(s["candidates_total"], 0)
        self.assertEqual(s["candidates_cleared"], 0)

    def test_summary_counts_candidates_by_verdict(self):
        # Log: 2 cleared, 1 blocked, 1 flagged
        rs.log_finding(
            {"name": "C1", "summary": "clean", "public_signal": "good"},
            finding_type="candidate_creator", profile=SAMPLE_PROFILE,
        )
        rs.log_finding(
            {"name": "C2", "summary": "clean", "public_signal": "good"},
            finding_type="candidate_creator", profile=SAMPLE_PROFILE,
        )
        rs.log_finding(
            {"name": "C3", "summary": "trump fan", "public_signal": "trump fan"},
            finding_type="candidate_creator", profile=SAMPLE_PROFILE,
        )
        rs.log_finding(
            {"name": "C4", "summary": "shills", "public_signal": "shills everything"},
            finding_type="candidate_creator", profile=SAMPLE_PROFILE,
        )
        rs.log_finding(
            {"name": "Note", "text": "thinking about X"},
            finding_type="general",
        )

        s = rs.summary()
        self.assertEqual(s["candidates_total"], 4)
        self.assertEqual(s["candidates_cleared"], 2)
        self.assertEqual(s["candidates_blocked_c7"], 1)
        self.assertEqual(s["candidates_flagged_c6"], 1)

    def test_next_action_mentions_user_test_when_pending(self):
        rs.log_finding(
            {"name": "Pending Creator", "summary": "clean", "public_signal": "good"},
            finding_type="candidate_creator", profile=SAMPLE_PROFILE,
        )
        s = rs.summary()
        self.assertIn("C5", s["next_action"])
        self.assertIn("Bolt cannot answer", s["next_action"])
        self.assertEqual(s["candidates_pending_c5"], 1)

    def test_next_action_when_empty_log_suggests_add(self):
        s = rs.summary()
        self.assertIn("No candidates", s["next_action"])

    def test_summary_no_profile_does_not_crash(self):
        # Patch USER_PROFILE to missing
        with patch.object(rs, "USER_PROFILE", self.tmp_path / "missing.json"):
            s = rs.summary()
            self.assertIsInstance(s, dict)



# ──────────────────────────────────────────────────────────────────────────────
# C5 decisions + add helpers
# ──────────────────────────────────────────────────────────────────────────────

class C5AndAddTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self._log_patcher = patch.object(
            rs, "RESEARCH_LOG", self.tmp_path / "research_log.jsonl"
        )
        self._profile_patcher = patch.object(
            rs, "USER_PROFILE", self.tmp_path / "user_profile.json"
        )
        self._log_patcher.start()
        self._profile_patcher.start()
        (self.tmp_path / "user_profile.json").write_text(json.dumps(SAMPLE_PROFILE))

    def tearDown(self):
        self._log_patcher.stop()
        self._profile_patcher.stop()
        self._tmp.cleanup()

    def test_add_candidate_gates_and_logs(self):
        entry = rs.add_candidate(
            "Clean Creator",
            platform="YouTube",
            summary="Honest reviews",
            why_match="Voice-first",
            public_signal="honest product takes",
        )
        self.assertEqual(entry["gate"]["verdict"], "cleared")
        self.assertEqual(rs.pending_c5_count(), 1)

    def test_c5_keep_updates_candidate_and_appends_audit(self):
        rs.add_candidate(
            "Keep Me",
            platform="YouTube",
            summary="good",
            public_signal="good",
        )
        result = rs.set_c5_verdict("Keep Me", "keep", why="Sounds like me")
        self.assertEqual(result["verdict"], "fits")
        self.assertEqual(rs.pending_c5_count(), 0)
        entries = rs._read_all_entries()
        candidates = [e for e in entries if e.get("finding_type") == "candidate_creator"]
        self.assertEqual(candidates[0]["c5_verdict"], "fits")
        self.assertEqual(candidates[0]["c5_user_words"], "Sounds like me")
        audits = [e for e in entries if e.get("finding_type") == "c5_decision"]
        self.assertEqual(len(audits), 1)
        s = rs.summary()
        self.assertEqual(s["candidates_kept"], 1)
        self.assertEqual(s["candidates_pending_c5"], 0)

    def test_c5_drop_alias(self):
        rs.add_candidate("Drop Me", summary="x", public_signal="clean")
        rs.set_c5_verdict("Drop Me", "drop")
        s = rs.summary()
        self.assertEqual(s["candidates_dropped"], 1)
        self.assertEqual(s["candidates_pending_c5"], 0)

    def test_c5_substring_match(self):
        rs.add_candidate("Susan Yara (Mixed Makeup)", summary="x", public_signal="clean")
        result = rs.set_c5_verdict("Susan Yara", "keep")
        self.assertEqual(result["matches"], 1)

    def test_c5_ambiguous_raises(self):
        rs.add_candidate("Alex One", summary="x", public_signal="clean")
        rs.add_candidate("Alex Two", summary="x", public_signal="clean")
        with self.assertRaises(ValueError):
            rs.set_c5_verdict("Alex", "keep")

    def test_c5_unknown_verdict_raises(self):
        rs.add_candidate("Zed", summary="x", public_signal="clean")
        with self.assertRaises(ValueError):
            rs.set_c5_verdict("Zed", "banana")

    def test_list_pending_only(self):
        rs.add_candidate("A", summary="x", public_signal="clean")
        rs.add_candidate("B", summary="x", public_signal="clean")
        rs.set_c5_verdict("A", "keep")
        pending = rs.list_candidates(pending_c5_only=True)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["name"], "B")

    def test_add_note_general(self):
        entry = rs.add_note("Through-line idea", finding_type="pattern_note", title="Thread")
        self.assertEqual(entry["finding_type"], "pattern_note")
        self.assertIn("Through-line", entry["text"])

    def test_cli_c5_and_add_roundtrip(self):
        code = rs.main([
            "add", "CLI Creator",
            "--platform", "YouTube",
            "--summary", "honest takes",
            "--why", "fits voice",
            "--signal", "honest product reviews",
        ])
        self.assertEqual(code, 0)
        code = rs.main(["c5", "keep", "CLI Creator", "--why", "yes"])
        self.assertEqual(code, 0)
        self.assertEqual(rs.pending_c5_count(), 0)



if __name__ == "__main__":
    unittest.main()