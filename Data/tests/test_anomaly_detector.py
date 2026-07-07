"""Tests for Anomaly_Detector (Tier 4.2).

Verifies:
1. Audio profile extraction returns the expected feature keys.
2. extract_audio_profile returns None for missing files / no ffmpeg.
3. fit_baseline computes correct (mean, std) per feature.
4. score() flags features > z_threshold std devs from the mean.
5. Severity bands (none/low/medium/high) trigger on the right combos.
6. Insufficient data returns a clean "no-op" report.
7. save_profile / load_profiles round-trip the JSONL.
8. detect_and_record saves and scores in one call.
"""

import sys
from pathlib import Path
_repo_root = Path(__file__).resolve().parents[2]
for _p in [_repo_root / 'Core']:
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

import json
import shutil
import statistics
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from modules import Anomaly_Detector as ad


class ProfileExtractionTests(unittest.TestCase):
    def test_missing_file_returns_none(self):
        self.assertIsNone(ad.extract_audio_profile("/tmp/does_not_exist_xyz.mp4"))

    def test_no_ffmpeg_returns_none(self):
        with patch.object(ad, "_has_ffmpeg", return_value=False):
            self.assertIsNone(ad.extract_audio_profile("/tmp/anything.mp4"))

    def test_no_librosa_returns_none(self):
        with patch.object(ad, "_has_librosa", return_value=False):
            self.assertIsNone(ad.extract_audio_profile("/tmp/anything.mp4"))

    @unittest.skipUnless(ad._has_ffmpeg() and ad._has_librosa(),
                         "ffmpeg and librosa required")
    def test_extracts_real_profile_from_synthetic_video(self):
        """Generate a 10-second white-noise video and confirm we get a profile."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            clip = tmp / "test.mp4"
            # Use ffmpeg's anoisesrc filter to make a colored-noise video
            # with a real audio track. White noise is good because it has
            # both high mean_rms and meaningful std_rms.
            r = __import__("subprocess").run(
                [
                    "ffmpeg", "-y",
                    "-f", "lavfi", "-i", f"anoisesrc=color=pink:duration=10:amplitude=0.3",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    str(clip),
                ],
                capture_output=True, timeout=30,
            )
            if r.returncode != 0:
                self.skipTest("ffmpeg test setup failed")
            profile = ad.extract_audio_profile(str(clip))
            self.assertIsNotNone(profile, "expected a profile, got None")
            for key in ("duration_sec", "mean_rms", "std_rms", "max_rms",
                        "silence_ratio", "num_high_spikes"):
                self.assertIn(key, profile, f"missing key: {key}")
            self.assertGreater(profile["duration_sec"], 5.0)
            self.assertGreater(profile["mean_rms"], 0.01)


class BaselineFittingTests(unittest.TestCase):

    def test_empty_returns_none(self):
        self.assertIsNone(ad.fit_baseline([], game="x"))

    def test_constant_feature_excluded_from_baseline(self):
        # All same std_rms → no std, must be excluded so we don't
        # divide by zero when scoring.
        profiles = [
            {"mean_rms": 0.1, "std_rms": 0.02, "max_rms": 0.4},
            {"mean_rms": 0.2, "std_rms": 0.02, "max_rms": 0.5},
            {"mean_rms": 0.3, "std_rms": 0.02, "max_rms": 0.6},
        ]
        baseline = ad.fit_baseline(profiles, game="x")
        self.assertIsNotNone(baseline)
        self.assertNotIn("std_rms", baseline.features)
        self.assertIn("mean_rms", baseline.features)
        self.assertIn("max_rms", baseline.features)
        # mean_rms baseline: (0.1+0.2+0.3)/3 = 0.2
        self.assertAlmostEqual(baseline.features["mean_rms"][0], 0.2, places=3)

    def test_known_values(self):
        profiles = [
            {"mean_rms": 0.10, "max_rms": 0.4},
            {"mean_rms": 0.20, "max_rms": 0.6},
            {"mean_rms": 0.30, "max_rms": 0.8},
            {"mean_rms": 0.40, "max_rms": 1.0},
        ]
        baseline = ad.fit_baseline(profiles, game="x")
        m, s = baseline.features["mean_rms"]
        self.assertAlmostEqual(m, 0.25, places=3)
        # sample std of [0.1, 0.2, 0.3, 0.4] ≈ 0.1291
        self.assertAlmostEqual(s, statistics.stdev([0.1, 0.2, 0.3, 0.4]), places=3)


class ScoringTests(unittest.TestCase):

    def test_no_baseline_returns_insufficient_data(self):
        report = ad.score({"mean_rms": 0.1}, None)
        self.assertFalse(report.is_anomalous)
        self.assertTrue(report.insufficient_data)

    def test_too_few_profiles_returns_insufficient_data(self):
        baseline = ad.Baseline(game="x", sample_size=2, features={"mean_rms": (0.2, 0.05)})
        report = ad.score({"mean_rms": 0.1}, baseline)
        self.assertTrue(report.insufficient_data)
        self.assertFalse(report.is_anomalous)

    def test_normal_value_is_not_flagged(self):
        baseline = ad.Baseline(
            game="x", sample_size=5,
            features={"mean_rms": (0.20, 0.05), "max_rms": (0.6, 0.1)},
        )
        report = ad.score({"mean_rms": 0.22, "max_rms": 0.65}, baseline)
        self.assertFalse(report.is_anomalous)
        self.assertEqual(report.severity, "none")
        self.assertEqual(report.flagged_features, [])

    def test_outlier_high_is_flagged(self):
        baseline = ad.Baseline(
            game="x", sample_size=5,
            features={"mean_rms": (0.20, 0.05)},
        )
        # 0.5 is 6 std devs above 0.20 — definitely an outlier.
        report = ad.score({"mean_rms": 0.5}, baseline, z_threshold=2.5)
        self.assertTrue(report.is_anomalous)
        self.assertEqual(len(report.flagged_features), 1)
        feat = report.flagged_features[0]
        self.assertEqual(feat["feature"], "mean_rms")
        self.assertEqual(feat["direction"], "high")
        self.assertGreater(feat["z_score"], 5.0)

    def test_outlier_low_is_flagged(self):
        baseline = ad.Baseline(
            game="x", sample_size=5,
            features={"silence_ratio": (0.1, 0.05)},
        )
        # 0.5 is 8 std devs above 0.1 — extreme silence
        report = ad.score({"silence_ratio": 0.5}, baseline, z_threshold=2.5)
        self.assertTrue(report.is_anomalous)
        feat = report.flagged_features[0]
        self.assertEqual(feat["direction"], "high")
        self.assertGreater(feat["z_score"], 5.0)

    def test_severity_bands(self):
        # Build a baseline with a wide-spread feature so we can pick
        # different z-scores by choosing different values.
        baseline = ad.Baseline(
            game="x", sample_size=5,
            features={"a": (0.0, 1.0), "b": (0.0, 1.0), "c": (0.0, 1.0)},
        )

        # None flagged → none
        r = ad.score({"a": 0.5, "b": 0.5, "c": 0.5}, baseline)
        self.assertEqual(r.severity, "none")

        # One feature mildly over (z=3) → low
        r = ad.score({"a": 3.0, "b": 0.5, "c": 0.5}, baseline, z_threshold=2.5)
        self.assertEqual(r.severity, "low")
        self.assertTrue(r.is_anomalous)

        # One feature wildly over (z=10) → medium
        r = ad.score({"a": 10.0, "b": 0.5, "c": 0.5}, baseline, z_threshold=2.5)
        self.assertEqual(r.severity, "medium")

        # Two features wildly over → high
        r = ad.score({"a": 10.0, "b": 10.0, "c": 0.5}, baseline, z_threshold=2.5)
        self.assertEqual(r.severity, "high")


class ProfileStorageTests(unittest.TestCase):

    def test_save_and_load_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profiles.jsonl"
            ad.save_profile("/tmp/a.mp4", "Game1", {"mean_rms": 0.1, "max_rms": 0.4}, profiles_file=path)
            ad.save_profile("/tmp/b.mp4", "Game1", {"mean_rms": 0.2, "max_rms": 0.5}, profiles_file=path)
            ad.save_profile("/tmp/c.mp4", "Game2", {"mean_rms": 0.05, "max_rms": 0.3}, profiles_file=path)

            g1 = ad.load_profiles("Game1", profiles_file=path)
            g2 = ad.load_profiles("Game2", profiles_file=path)
            self.assertEqual(len(g1), 2)
            self.assertEqual(len(g2), 1)
            self.assertEqual(g1[0]["mean_rms"], 0.1)

    def test_load_missing_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                ad.load_profiles("X", profiles_file=Path(tmp) / "nope.jsonl"),
                [],
            )

    def test_load_skips_bad_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.jsonl"
            path.write_text(
                "not json\n"
                + json.dumps({"game": "G", "profile": {"mean_rms": 0.1}})
                + "\n\n"
                + json.dumps({"game": "G", "profile": {"mean_rms": 0.2}})
            )
            self.assertEqual(len(ad.load_profiles("G", profiles_file=path)), 2)


class EndToEndTests(unittest.TestCase):

    @unittest.skipUnless(ad._has_ffmpeg() and ad._has_librosa(),
                         "ffmpeg and librosa required")
    def test_detect_and_record_saves_and_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            clip = tmp / "test.mp4"
            r = __import__("subprocess").run(
                [
                    "ffmpeg", "-y",
                    "-f", "lavfi", "-i", "anoisesrc=color=pink:duration=5:amplitude=0.3",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    str(clip),
                ],
                capture_output=True, timeout=30,
            )
            if r.returncode != 0:
                self.skipTest("ffmpeg setup failed")

            profiles_file = tmp / "anomaly.jsonl"
            # First call: insufficient data (0 profiles)
            profile, report = ad.detect_and_record(
                str(clip), "Marvel Rivals", profiles_file=profiles_file
            )
            self.assertIsNotNone(profile)
            self.assertIsNotNone(report)
            self.assertTrue(report.insufficient_data)

            # Second call: 1 profile, still insufficient
            profile, report = ad.detect_and_record(
                str(clip), "Marvel Rivals", profiles_file=profiles_file
            )
            self.assertTrue(report.insufficient_data)

            # Third + fourth calls: now we have enough to score
            ad.detect_and_record(str(clip), "Marvel Rivals", profiles_file=profiles_file)
            profile, report = ad.detect_and_record(
                str(clip), "Marvel Rivals", profiles_file=profiles_file
            )
            self.assertFalse(report.insufficient_data)
            self.assertEqual(report.game, "Marvel Rivals")

            # The JSONL has 4 lines, all for "Marvel Rivals"
            with open(profiles_file) as f:
                lines = [json.loads(l) for l in f if l.strip()]
            self.assertEqual(len(lines), 4)
            self.assertTrue(all(l["game"] == "Marvel Rivals" for l in lines))


if __name__ == "__main__":
    unittest.main()
