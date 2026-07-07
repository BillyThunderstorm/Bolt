"""Tests for Clip_Deduplicator's highlight-series grouping (Tier 2 spec).

Verifies:
1. group_into_series() clusters clips by perceptual hash similarity.
2. keep_best_in_each_series() picks the highest-scoring clip per series.
3. Singleton clips (no near-duplicates) are passed through.
4. Series info correctly tags winners and dropped alternates.
5. Clips without output_file are silently dropped.
"""

import sys
from pathlib import Path
_repo_root = Path(__file__).resolve().parents[2]
for _p in [_repo_root / 'Core']:
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from modules import Clip_Deduplicator as cd


def make_clip(path: str, score: float = 50.0):
    """Lightweight stand-in for the real clip object."""
    return SimpleNamespace(output_file=path, score=score)


class HighlightSeriesTests(unittest.TestCase):
    def test_empty_input_returns_empty(self):
        dedup = cd.ClipDeduplicator(seen_file="/tmp/_series_empty.json")
        self.assertEqual(dedup.group_into_series([]), [])
        kept, info = dedup.keep_best_in_each_series([])
        self.assertEqual(kept, [])
        self.assertEqual(info, {})

    def test_clips_without_output_file_are_dropped(self):
        dedup = cd.ClipDeduplicator(seen_file="/tmp/_series_drop.json")
        clips = [
            SimpleNamespace(output_file="", score=80),  # no path -> dropped
            SimpleNamespace(output_file="good.mp4", score=70),
        ]
        series = dedup.group_into_series(clips)
        # Only the clip with a path is included.
        self.assertEqual(len(series), 1)
        self.assertEqual(len(series[0]), 1)

    def test_group_clusters_similar_clips_and_keeps_highest_score(self):
        """Mock pHashes so the test is deterministic and fast."""
        # Three clips: two look alike (hash 0xAAAA), one looks different (0xFFFF).
        clip_a = make_clip("/tmp/clip_a.mp4", score=80)
        clip_b = make_clip("/tmp/clip_b.mp4", score=95)  # highest in series
        clip_c = make_clip("/tmp/clip_c.mp4", score=60)

        # Simulate imagehash's __sub__ via a simple namespace.
        class FakeHash:
            def __init__(self, h): self.h = h
            def __sub__(self, other): return abs(self.h - other.h)

        h_similar_a = FakeHash(0xAAAA)
        h_similar_b = FakeHash(0xAAAB)  # 1 bit off -> within PHASH_THRESHOLD=8
        h_different = FakeHash(0x0000)  # far from AAAA

        with patch.object(cd, "HAS_PHASH", True), \
             patch.object(cd, "_compute_phash") as mock_hash:
            mock_hash.side_effect = [h_similar_a, h_similar_b, h_different]
            dedup = cd.ClipDeduplicator(seen_file="/tmp/_series_cluster.json")
            series = dedup.group_into_series([clip_a, clip_b, clip_c])

        # Expect 2 series: one with {a, b}, one with {c} (singleton).
        self.assertEqual(len(series), 2)
        sizes = sorted(len(g) for g in series)
        self.assertEqual(sizes, [1, 2])

        # The 2-clip series must contain a and b; c is alone.
        two_clip_series = next(g for g in series if len(g) == 2)
        paths_in_series = {c.output_file for c in two_clip_series}
        self.assertEqual(paths_in_series, {"/tmp/clip_a.mp4", "/tmp/clip_b.mp4"})

        # keep_best_in_each_series: b (score 95) should be the winner.
        with patch.object(cd, "HAS_PHASH", True), \
             patch.object(cd, "_compute_phash") as mock_hash:
            mock_hash.side_effect = [h_similar_a, h_similar_b, h_different]
            kept, info = dedup.keep_best_in_each_series([clip_a, clip_b, clip_c])

        kept_paths = {c.output_file for c in kept}
        # 2 series: one 2-clip series (winner=clip_b), one singleton (clip_c).
        # kept = {clip_b, clip_c} — 2 items, not 3.
        self.assertEqual(len(kept), 2)
        self.assertIn("/tmp/clip_b.mp4", kept_paths)
        self.assertIn("/tmp/clip_c.mp4", kept_paths)
        self.assertNotIn("/tmp/clip_a.mp4", kept_paths)

        # b is the series winner; a is dropped from the series.
        self.assertTrue(info["/tmp/clip_b.mp4"]["winner"])
        self.assertEqual(info["/tmp/clip_b.mp4"]["best_score"], 95)
        self.assertEqual(info["/tmp/clip_b.mp4"]["series_size"], 2)

        self.assertFalse(info["/tmp/clip_a.mp4"]["winner"])
        self.assertEqual(info["/tmp/clip_a.mp4"]["series_size"], 2)

        # c is a singleton -> winner=True, size=1.
        self.assertTrue(info["/tmp/clip_c.mp4"]["winner"])
        self.assertEqual(info["/tmp/clip_c.mp4"]["series_size"], 1)

    def test_transitive_grouping_via_union_find(self):
        """If A~B and B~C, A and C should end up in the same series."""
        # Build a chain of clips with hashes within PHASH_THRESHOLD of neighbors.
        clips = [make_clip(f"/tmp/chain_{i}.mp4", score=50 + i) for i in range(4)]

        class FakeHash:
            def __init__(self, h): self.h = h
            def __sub__(self, other): return abs(self.h - other.h)

        # Each consecutive pair differs by 1 bit; 0 vs 3 differs by 3 (still < 8).
        hashes = [FakeHash(0x1000 + i) for i in range(4)]

        with patch.object(cd, "HAS_PHASH", True), \
             patch.object(cd, "_compute_phash") as mock_hash:
            mock_hash.side_effect = hashes
            dedup = cd.ClipDeduplicator(seen_file="/tmp/_series_chain.json")
            series = dedup.group_into_series(clips)

        # All 4 should chain into one series via the union-find.
        self.assertEqual(len(series), 1)
        self.assertEqual(len(series[0]), 4)

    def test_no_phash_library_falls_back_to_singletons(self):
        """Without pHash available, every clip is its own series (no clustering)."""
        clips = [make_clip(f"/tmp/np_{i}.mp4", score=50) for i in range(3)]
        with patch.object(cd, "HAS_PHASH", False):
            dedup = cd.ClipDeduplicator(seen_file="/tmp/_series_nophash.json")
            series = dedup.group_into_series(clips)
        # Without pHash, no way to know they look alike -> 3 singletons.
        self.assertEqual(len(series), 3)
        for s in series:
            self.assertEqual(len(s), 1)


if __name__ == "__main__":
    unittest.main()
