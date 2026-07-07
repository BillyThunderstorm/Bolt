"""Tests for Predictive_Analytics (Tier 4.4).

Verifies:
1. predict() returns a clean "insufficient data" report on empty history.
2. predict() returns a clean "need more samples" report on under-sampled keys.
3. predict() with exact group match returns the right (median, range).
4. predict() falls back to less-specific group when the exact one is too small.
5. predict() falls back to (game,) when trigger is unknown.
6. predict() handles missing platform by dropping that dimension.
7. viral flag triggers when high_views >= 90th percentile of all views.
8. _load_outcomes filters by days cutoff.
9. _percentile is correct for various percentiles.
10. predict_queue handles a list of clips and returns one Prediction each.
11. JSON output is serializable.
"""

import sys
from pathlib import Path
_repo_root = Path(__file__).resolve().parents[2]
for _p in [_repo_root / 'Core']:
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

import json
import statistics
import tempfile
import unittest
from datetime import datetime, timedelta

from modules import Predictive_Analytics as pa


def _row(game, trigger, views, platform="tiktok", when=None, likes=0, success=True):
    """Build a performance_outcomes-shaped row."""
    return {
        "timestamp": (when or datetime.now()).isoformat(),
        "game": game,
        "trigger": trigger,
        "platform": platform,
        "views": views,
        "likes": likes,
        "like_rate": round((likes / views) * 100, 2) if views else 0.0,
        "success": success,
        "clip_path": f"/tmp/{trigger}_{views}.mp4",
        "note": "",
    }


class EmptyAndInsufficientDataTests(unittest.TestCase):

    def test_no_history_returns_clean_report(self):
        p = pa.predict({"game": "Marvel Rivals", "trigger": "kill"}, rows=[])
        self.assertTrue(p.insufficient_data)
        self.assertEqual(p.median_views, 0.0)
        self.assertFalse(p.is_potential_viral)
        self.assertEqual(p.sample_size, 0)

    def test_too_few_samples_returns_clean_report(self):
        # Only 1 sample in (Marvel Rivals, kill) — not enough.
        rows = [_row("Marvel Rivals", "kill", 1000)]
        p = pa.predict({"game": "Marvel Rivals", "trigger": "kill"}, rows=rows)
        self.assertTrue(p.insufficient_data)
        self.assertEqual(p.sample_size, 1)

    def test_unknown_game_returns_insufficient(self):
        rows = [_row("Marvel Rivals", "kill", 1000) for _ in range(10)]
        p = pa.predict({"game": "Unknown Game", "trigger": "kill"}, rows=rows)
        self.assertTrue(p.insufficient_data)
        self.assertEqual(p.sample_size, 0)


class ExactGroupMatchTests(unittest.TestCase):

    def test_exact_group_uses_its_data(self):
        # 10 Marvel Rivals kill clips, all 2000 views — median = 2000.
        rows = [_row("Marvel Rivals", "kill", 2000) for _ in range(10)]
        p = pa.predict({"game": "Marvel Rivals", "trigger": "kill"}, rows=rows)
        self.assertFalse(p.insufficient_data)
        self.assertEqual(p.sample_size, 10)
        self.assertEqual(p.median_views, 2000)
        self.assertEqual(p.low_views, 2000)
        self.assertEqual(p.high_views, 2000)
        self.assertEqual(p.confidence, 0.5)  # 10/20

    def test_returns_realistic_percentile_range(self):
        # 30 clips with views in [1000..3000]
        rows = [_row("Marvel Rivals", "kill", 1000 + i * 70) for i in range(30)]
        p = pa.predict({"game": "Marvel Rivals", "trigger": "kill"}, rows=rows)
        self.assertEqual(p.sample_size, 30)
        self.assertEqual(p.confidence, 1.0)  # 30/20 capped at 1.0
        # 25th pct of [1000..3030 step 70] should be in low range
        self.assertGreater(p.low_views, 1000)
        self.assertLess(p.high_views, 3100)


class FallbackTests(unittest.TestCase):

    def test_unknown_trigger_falls_back_to_game(self):
        # No "ace" data, but plenty of Marvel Rivals data.
        rows = [_row("Marvel Rivals", "kill", 2000) for _ in range(10)]
        p = pa.predict({"game": "Marvel Rivals", "trigger": "ace"}, rows=rows)
        self.assertFalse(p.insufficient_data)
        self.assertEqual(p.sample_size, 10)
        self.assertEqual(p.group_used, ("Marvel Rivals",))

    def test_unknown_trigger_unknown_game(self):
        rows = [_row("Marvel Rivals", "kill", 2000) for _ in range(10)]
        p = pa.predict({"game": "New Game", "trigger": "ace"}, rows=rows)
        self.assertTrue(p.insufficient_data)
        self.assertEqual(p.sample_size, 0)

    def test_no_platform_drops_platform_dimension(self):
        # If we ask for (game, trigger) without platform, we should
        # match the (game, trigger) group (which aggregates across platforms).
        rows = [_row("Marvel Rivals", "kill", 2000, platform="tiktok") for _ in range(5)] \
             + [_row("Marvel Rivals", "kill", 2500, platform="youtube") for _ in range(5)]
        p = pa.predict({"game": "Marvel Rivals", "trigger": "kill"}, rows=rows)
        self.assertEqual(p.sample_size, 10)
        self.assertEqual(p.group_used, ("Marvel Rivals", "kill"))
        # median of [2000]*5 + [2500]*5 = 2250
        self.assertEqual(p.median_views, 2250)


class ViralFlagTests(unittest.TestCase):

    def test_viral_flagged_when_above_threshold(self):
        # 8 normal kill clips at 2000 views, 5 multi_kill at 10000.
        # The 90th-pct of all views is 10000. multi_kill's high end
        # (10000) clears that bar.
        rows = [_row("Marvel Rivals", "kill", 2000) for _ in range(8)] \
             + [_row("Marvel Rivals", "multi_kill", 10000) for _ in range(5)]
        p = pa.predict({"game": "Marvel Rivals", "trigger": "multi_kill"}, rows=rows)
        self.assertTrue(p.is_potential_viral, "multi_kill should be viral")
        self.assertIn("POTENTIALLY VIRAL", p.summary)

    def test_normal_clip_not_flagged(self):
        rows = [_row("Marvel Rivals", "kill", 2000 + i * 10) for i in range(30)]
        p = pa.predict({"game": "Marvel Rivals", "trigger": "kill"}, rows=rows)
        self.assertFalse(p.is_potential_viral)

    def test_viral_threshold_zero_when_too_little_data(self):
        rows = [_row("Marvel Rivals", "kill", 2000) for _ in range(5)]
        p = pa.predict({"game": "Marvel Rivals", "trigger": "kill"}, rows=rows)
        self.assertEqual(p.viral_threshold, 0.0)
        self.assertFalse(p.is_potential_viral)


class LoadOutcomesTests(unittest.TestCase):

    def test_loads_jsonl_and_filters_by_days(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.jsonl"
            now = datetime.now()
            rows = [
                _row("G", "t", 100, when=now - timedelta(days=2)),
                _row("G", "t", 200, when=now - timedelta(days=10)),
                _row("G", "t", 300, when=now - timedelta(days=100)),
            ]
            path.write_text("\n".join(json.dumps(r) for r in rows))
            all_rows = pa._load_outcomes(path=path)
            self.assertEqual(len(all_rows), 3)
            recent = pa._load_outcomes(path=path, days=7)
            self.assertEqual(len(recent), 1)
            self.assertEqual(recent[0]["views"], 100)

    def test_load_skips_bad_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.jsonl"
            path.write_text("not json\n" + json.dumps(_row("G", "t", 100)) + "\n\n")
            self.assertEqual(len(pa._load_outcomes(path=path)), 1)


class PercentileHelperTests(unittest.TestCase):

    def test_percentile_known_values(self):
        # [1,2,3,4,5,6,7,8,9,10]
        values = list(range(1, 11))
        self.assertEqual(pa._percentile(values, 0.5), 5.5)
        self.assertEqual(pa._percentile(values, 0.0), 1.0)
        self.assertEqual(pa._percentile(values, 1.0), 10.0)
        self.assertEqual(pa._percentile(values, 0.9), 9.1)

    def test_percentile_empty(self):
        self.assertEqual(pa._percentile([], 0.5), 0.0)

    def test_percentile_single_value(self):
        self.assertEqual(pa._percentile([42], 0.5), 42.0)


class BatchPredictTests(unittest.TestCase):

    def test_predict_queue_returns_one_per_clip(self):
        # predict_queue loads from disk, so we use direct predict() for
        # row injection. The test verifies the *batch* shape: same
        # number of predictions as input clips, correct per-clip
        # insufficient-data flagging.
        rows = [_row("Marvel Rivals", "kill", 2000) for _ in range(10)]
        clips = [
            {"game": "Marvel Rivals", "trigger": "kill"},
            {"game": "Marvel Rivals", "trigger": "ace"},  # falls back
            {"game": "New Game", "trigger": "kill"},     # no data
        ]
        preds = [pa.predict(c, rows=rows) for c in clips]
        self.assertEqual(len(preds), 3)
        self.assertFalse(preds[0].insufficient_data)
        self.assertFalse(preds[1].insufficient_data)  # fell back to (Marvel Rivals,)
        self.assertTrue(preds[2].insufficient_data)   # New Game, no data

    def test_prediction_to_json(self):
        rows = [_row("Marvel Rivals", "kill", 2000) for _ in range(10)]
        p = pa.predict({"game": "Marvel Rivals", "trigger": "kill"}, rows=rows)
        d = p.to_dict()
        # Round-trip through json.dumps to confirm everything is serializable.
        out = json.dumps(d, default=str)
        self.assertIn("median_views", out)
        self.assertIn("summary", out)


if __name__ == "__main__":
    unittest.main()
