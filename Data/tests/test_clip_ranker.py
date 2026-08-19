"""Tests for the learned clip-ranking model.

The original Clip_Ranker had no test coverage at all. This file
covers both the original scoring formula and the new ML step
(learned_boost with recency-weighted views + like_rate).
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_repo_root = Path(__file__).resolve().parents[2]
for _p in [_repo_root / 'Core']:
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

from modules import Clip_Ranker as cr  # noqa: E402


class _FakeClip:
    """Minimal stand-in for GeneratedClip with the attributes
    rank_clips/_score_clip actually touch."""

    def __init__(self, highlight_score=80.0, trigger="highlight", output_file="/tmp/fake.mp4"):
        class _Hl:
            pass
        self.highlight = _Hl()
        self.highlight.score = highlight_score
        self.highlight.trigger = trigger
        self.output_file = output_file
        self.success = True


class ClipRankerTests(unittest.TestCase):
    # ── Original formula ──────────────────────────────────────────────────
    def test_score_clip_breakdown_includes_learned(self):
        # The breakdown string should expose all four components.
        clip = _FakeClip(highlight_score=80.0, trigger="multi_kill")
        history = {"multi_kill": {"total_clips": 1, "avg_views": 100}}
        score, breakdown = cr._score_clip(clip, history)
        self.assertIn("audio=", breakdown)
        self.assertIn("trigger=", breakdown)
        self.assertIn("history=", breakdown)
        self.assertIn("learned=", breakdown)
        # With only 1 sample, learned should be 0
        self.assertLessEqual(score, 100.0)
        self.assertGreaterEqual(score, 0.0)

    def test_score_clip_zero_audio_zero_history(self):
        # 0 highlight score, no history, just trigger bonus.
        clip = _FakeClip(highlight_score=0.0, trigger="ace")
        score, breakdown = cr._score_clip(clip, {})
        # audio=0 + trigger(ace=35) + 0 + 0 = 35
        self.assertEqual(score, 35.0)
        self.assertIn("trigger=35 (ace)", breakdown)

    def test_score_clip_caps_at_100(self):
        # Stacking every signal should still top out at 100.
        clip = _FakeClip(highlight_score=100.0, trigger="ace")
        # Lots of recent high-quality data
        from modules.Clip_Ranker import _now_iso
        obs = [
            {"at": _now_iso(), "views": 100_000, "likes": 15_000}
            for _ in range(20)
        ]
        history = {"ace": {"observations": obs, "total_clips": 20}}
        score, _ = cr._score_clip(clip, history)
        self.assertEqual(score, 100.0)

    # ── learned_boost ────────────────────────────────────────────────────
    def test_learned_boost_zero_for_too_few_samples(self):
        # 1-2 samples → no signal, no boost
        for n in (0, 1, 2):
            history = {
                "multi_kill": {
                    "observations": [
                        {"at": cr._now_iso(), "views": 50_000, "likes": 5000}
                        for _ in range(n)
                    ]
                }
            }
            self.assertEqual(
                cr.learned_boost("multi_kill", history), 0.0,
                f"should be 0 with {n} samples",
            )

    def test_learned_boost_caps_at_max(self):
        # Saturate both signals
        obs = [
            {"at": cr._now_iso(), "views": 200_000, "likes": 30_000}
            for _ in range(50)
        ]
        # learned_boost takes the per-trigger dict (game_history[trigger]),
        # not the per-game dict.
        history = {"observations": obs}
        boost = cr.learned_boost("multi_kill", history)
        self.assertLessEqual(boost, cr.LEARNED_MAX_BOOST)
        self.assertEqual(boost, cr.LEARNED_MAX_BOOST)

    def test_learned_boost_prefers_high_like_rate(self):
        # Two triggers with similar views but very different like rates.
        # The one with the higher like rate should get a bigger boost.
        obs_high_like = [
            {"at": cr._now_iso(), "views": 5000, "likes": 750}  # 15% like rate
            for _ in range(10)
        ]
        obs_low_like = [
            {"at": cr._now_iso(), "views": 5000, "likes": 50}  # 1% like rate
            for _ in range(10)
        ]
        b_high = cr.learned_boost("good", {"observations": obs_high_like})
        b_low = cr.learned_boost("meh", {"observations": obs_low_like})
        self.assertGreater(b_high, b_low,
                            f"high-like {b_high} should beat low-like {b_low}")

    def test_learned_boost_recency_decay(self):
        # Old data should count for less than recent data per-observation.
        # We construct two scenarios:
        #   - many ancient entries with low views (1k each)
        #   - a few recent entries with very high views (50k each)
        # Without recency weighting, the ancient entries would dominate
        # by sheer count. With recency decay (14-day half-life, 200
        # days old), the ancient entries' contribution should be
        # nearly zero, so the recent high-views signal should win.
        from datetime import datetime, timezone, timedelta
        very_old_ts = (datetime.now(timezone.utc) - timedelta(days=200)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        recent_ts = cr._now_iso()
        # 50 old observations at 1k views, 3 recent at 50k views
        old_obs = [
            {"at": very_old_ts, "views": 1_000, "likes": 50}
            for _ in range(50)
        ]
        recent_obs = [
            {"at": recent_ts, "views": 50_000, "likes": 5_000}  # 10% like rate
            for _ in range(3)
        ]
        b_old = cr.learned_boost("trig", {"observations": old_obs})
        b_recent = cr.learned_boost("trig", {"observations": recent_obs})
        # Both should be > 0 (>= 3 samples)
        self.assertGreater(b_old, 0)
        self.assertGreater(b_recent, 0)
        # Recent should beat old: the recent has higher views AND
        # the old has decayed to nearly nothing.
        self.assertGreater(b_recent, b_old,
                            f"recent {b_recent} should beat old {b_old}")

    def test_learned_boost_back_compat_with_legacy_format(self):
        # When there's no `observations` array, fall back to the legacy
        # total_clips / avg_views / total_likes fields.
        legacy = {
            "total_clips": 10,
            "total_views": 100_000,
            "total_likes": 8000,
            "avg_views": 10_000,
        }
        boost = cr.learned_boost("multi_kill", legacy)
        self.assertGreater(boost, 0)
        self.assertLessEqual(boost, cr.LEARNED_MAX_BOOST)

    def test_learned_boost_handles_empty_history(self):
        # Defensive: don't crash on weird input.
        for h in ({}, None, "", [], {"observations": []}):
            self.assertEqual(cr.learned_boost("trig", h or {}), 0.0)

    # ── update_historical_performance ────────────────────────────────────
    def test_update_records_observations_and_aggregates(self):
        # Mock the file so we don't touch the real history.
        with tempfile.TemporaryDirectory() as tmp:
            fake_path = Path(tmp) / "clip_history.json"
            with patch.object(cr, "HISTORY_FILE", fake_path):
                cr.update_historical_performance("Marvel Rivals", "ace", views=1000, likes=50)
                cr.update_historical_performance("Marvel Rivals", "ace", views=2000, likes=120)
                data = json.loads(fake_path.read_text())
                entry = data["Marvel Rivals"]["ace"]
                # Legacy aggregates still updated
                self.assertEqual(entry["total_clips"], 2)
                self.assertEqual(entry["total_views"], 3000)
                self.assertEqual(entry["total_likes"], 170)
                self.assertEqual(entry["avg_views"], 1500)
                # New: per-observation records
                self.assertEqual(len(entry["observations"]), 2)
                self.assertEqual(entry["observations"][0]["views"], 1000)
                self.assertEqual(entry["observations"][1]["likes"], 120)

    def test_update_caps_observations_at_200(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_path = Path(tmp) / "clip_history.json"
            with patch.object(cr, "HISTORY_FILE", fake_path):
                for i in range(250):
                    cr.update_historical_performance("G", "kill", views=10 + i, likes=1)
                data = json.loads(fake_path.read_text())
                self.assertEqual(len(data["G"]["kill"]["observations"]), 200)
                # The most recent 200 should be kept; the first 50 dropped.
                self.assertEqual(data["G"]["kill"]["observations"][0]["views"], 60)
                self.assertEqual(data["G"]["kill"]["observations"][-1]["views"], 259)

    # ── inspect_learned_model + learning_loop_status ─────────────────────
    def test_inspect_returns_per_trigger_breakdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_path = Path(tmp) / "clip_history.json"
            with patch.object(cr, "HISTORY_FILE", fake_path):
                # Seed two games with different trigger mixes.
                for _ in range(5):
                    cr.update_historical_performance("Marvel Rivals", "multi_kill", 2000, 100)
                for _ in range(3):
                    cr.update_historical_performance("Marvel Rivals", "kill", 500, 20)
                cr.update_historical_performance("Other", "kill", 100, 5)
                model = cr.inspect_learned_model()
                self.assertIn("Marvel Rivals", model["games"])
                self.assertIn("Other", model["games"])
                mr = model["games"]["Marvel Rivals"]
                triggers = {t["trigger"]: t for t in mr["triggers"]}
                self.assertIn("multi_kill", triggers)
                self.assertIn("kill", triggers)
                # multi_kill has 5 samples, kill has 3, both above min
                self.assertEqual(triggers["multi_kill"]["samples"], 5)
                self.assertEqual(triggers["kill"]["samples"], 3)
                # multi_kill should have a higher boost than kill
                self.assertGreater(
                    triggers["multi_kill"]["learned_boost"],
                    triggers["kill"]["learned_boost"],
                )
                # Filter by game
                only_mr = cr.inspect_learned_model(game="Marvel Rivals")
                self.assertIn("Marvel Rivals", only_mr["games"])
                self.assertNotIn("Other", only_mr["games"])

    def test_learning_loop_status_top_boost(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_path = Path(tmp) / "clip_history.json"
            with patch.object(cr, "HISTORY_FILE", fake_path):
                # Trigger A: high views, high like rate -> big boost
                for _ in range(10):
                    cr.update_historical_performance("G", "ace", 5000, 750)
                # Trigger B: meh -> smaller boost
                for _ in range(10):
                    cr.update_historical_performance("G", "kill", 1000, 20)
                ll = cr.learning_loop_status()
                self.assertEqual(ll["total_outcomes"], 20)
                self.assertGreater(ll["pairs_with_signal"], 0)
                self.assertIsNotNone(ll["top_boost"])
                self.assertEqual(ll["top_boost"]["trigger"], "ace")
                self.assertEqual(ll["top_boost"]["game"], "G")
                self.assertGreater(ll["top_boost"]["boost"], 0)

    def test_learning_loop_status_empty_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_path = Path(tmp) / "clip_history.json"
            fake_path.write_text("{}")
            with patch.object(cr, "HISTORY_FILE", fake_path):
                ll = cr.learning_loop_status()
                self.assertEqual(ll["total_outcomes"], 0)
                self.assertIsNone(ll["last_observation_at"])
                self.assertIsNone(ll["top_boost"])

    # ── rank_clips end-to-end ────────────────────────────────────────────
    def test_rank_clips_sorts_descending(self):
        clips = [
            _FakeClip(highlight_score=80.0, trigger="highlight", output_file="/tmp/a.mp4"),
            _FakeClip(highlight_score=95.0, trigger="ace", output_file="/tmp/b.mp4"),
            _FakeClip(highlight_score=60.0, trigger="kill", output_file="/tmp/c.mp4"),
        ]
        history = {
            "kill": {"observations": [
                {"at": cr._now_iso(), "views": 2000, "likes": 100}
                for _ in range(5)
            ]},
        }
        ranked = cr.rank_clips(clips, game="TestGame", min_score=0)
        scores = [c.score for c in ranked]
        self.assertEqual(scores, sorted(scores, reverse=True))
        # Each clip should have a tier
        for c in ranked:
            self.assertIn(c.tier, {cr.TIER_DISCARD, cr.TIER_MID, cr.TIER_QUEUE})

    def test_parse_clip_filename_audio_spike(self):
        parsed = cr.parse_clip_filename(
            "2026-08-09_01-13-33_clip01_audio_spike_84.mp4"
        )
        self.assertEqual(parsed["trigger"], "audio_spike")
        self.assertEqual(parsed["timestamp"], 84.0)
        self.assertEqual(parsed["index"], 1)
        self.assertEqual(parsed["stem"], "2026-08-09_01-13-33")

    def test_parse_clip_filename_unknown(self):
        self.assertEqual(cr.parse_clip_filename("random_export.mp4"), {})

    def test_history_alias_audio_spike_uses_highlight_row(self):
        history = {"highlight": {"avg_views": 10_000}}
        boost = cr._history_boost("audio_spike", history)
        self.assertGreater(boost, 0)

    def test_load_logged_highlight_scores_pairs_saved_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "Bolt_2026-08-09.log"
            log.write_text(
                '{"msg": "  Clip 1/12 — audio_spike @ 84.0s (score 100)"}\n'
                '{"msg": "  ✓ Saved: 2026-08-09_01-13-33_clip01_audio_spike_84.mp4"}\n'
                '{"msg": "  Clip 2/12 — audio_spike @ 416.0s (score 42)"}\n'
                '{"msg": "  \\u2713 Saved: 2026-08-08_08-55-07_clip01_audio_spike_416.mp4"}\n',
                encoding="utf-8",
            )
            scores = cr.load_logged_highlight_scores(Path(tmp), refresh=True)
            self.assertEqual(
                scores["2026-08-09_01-13-33_clip01_audio_spike_84.mp4"], 100.0
            )
            self.assertEqual(
                scores["2026-08-08_08-55-07_clip01_audio_spike_416.mp4"], 42.0
            )
        cr._LOG_SCORE_CACHE = None

    def test_clip_from_path_prefers_sidecar_over_fake_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            clip_path = Path(tmp) / "2026-08-09_01-13-33_clip01_audio_spike_84.mp4"
            clip_path.write_bytes(b"not-a-real-video")
            cr.write_clip_sidecar(
                clip_path, trigger="audio_spike", highlight_score=87.0
            )
            clip = cr.clip_from_path(
                clip_path, analyze_audio=False, logged_scores={}
            )
            self.assertEqual(clip.highlight.score, 87.0)
            self.assertEqual(clip.highlight.trigger, "audio_spike")
            self.assertEqual(clip.score_source, "sidecar")

    def test_clip_from_path_uses_log_then_zero_not_fifty(self):
        with tempfile.TemporaryDirectory() as tmp:
            clip_path = Path(tmp) / "session_clip02_kill_12.mp4"
            clip_path.write_bytes(b"not-a-real-video")
            clip = cr.clip_from_path(
                clip_path,
                analyze_audio=False,
                logged_scores={"session_clip02_kill_12.mp4": 71.0},
            )
            self.assertEqual(clip.highlight.score, 71.0)
            self.assertEqual(clip.highlight.trigger, "kill")
            self.assertEqual(clip.score_source, "log")

            orphan = Path(tmp) / "unknown_export.mp4"
            orphan.write_bytes(b"x")
            empty = cr.clip_from_path(
                orphan, analyze_audio=False, logged_scores={}
            )
            self.assertEqual(empty.highlight.score, 0.0)
            self.assertNotEqual(empty.highlight.score, 50.0)
            self.assertEqual(empty.score_source, "none")


if __name__ == "__main__":
    unittest.main()
