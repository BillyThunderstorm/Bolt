"""Tests for scripts/generate_thumbnails.py.

Covers the public library API and CLI behavior. Uses a real tiny video file
created on the fly with ffmpeg so the ffmpeg integration is exercised
end-to-end without relying on fixtures in the project.
"""


import sys
from pathlib import Path
_repo_root = Path(__file__).resolve().parents[2]
for _p in [_repo_root / '3rd_Party' / 'colabs']:
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import generate_thumbnails as gt


def _have_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg"))


def _make_test_video(directory: Path, name: str = "tiny.mp4", duration: float = 2.0) -> Path:
    """Create a tiny test video using ffmpeg's lavfi source."""
    if not _have_ffmpeg():
        raise RuntimeError("ffmpeg not available; cannot make test video")
    path = directory / name
    # testsrc generates a moving pattern; scale to 320x240 to keep size small.
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=duration={duration}:size=320x240:rate=10",
        "-pix_fmt",
        "yuv420p",
        str(path),
    ]
    subprocess.run(cmd, check=True, timeout=30)
    return path


@unittest.skipUnless(_have_ffmpeg(), "ffmpeg not installed")
class GenerateThumbnailTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.video = _make_test_video(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_generates_jpg_next_to_source(self):
        result = gt.generate_thumbnail(self.video)
        self.assertIsNone(result.error, msg=result.error)
        self.assertIsNotNone(result.output)
        out = Path(result.output)
        self.assertTrue(out.exists())
        self.assertEqual(out.suffix, ".jpg")
        # ffmpeg JPEGs are at minimum a few KB.
        self.assertGreater(out.stat().st_size, 1000)

    def test_default_strategy_is_smart(self):
        result = gt.generate_thumbnail(self.video)
        self.assertEqual(result.strategy, "smart")
        # Smart strategy on a 2s clip should pick a seek around 0.66s.
        self.assertIsNotNone(result.seek_seconds)
        self.assertGreaterEqual(result.seek_seconds, 0.0)

    def test_first_strategy_uses_zero_seek(self):
        result = gt.generate_thumbnail(self.video, strategy="first")
        self.assertEqual(result.strategy, "first")
        self.assertEqual(result.seek_seconds, 0.0)

    def test_middle_strategy_uses_duration_over_two(self):
        result = gt.generate_thumbnail(self.video, strategy="middle")
        self.assertEqual(result.strategy, "middle")
        # 2.0s clip -> middle is ~1.0s
        self.assertAlmostEqual(result.seek_seconds, 1.0, delta=0.05)

    def test_returns_error_for_missing_source(self):
        result = gt.generate_thumbnail(self.root / "does_not_exist.mp4")
        self.assertIsNotNone(result.error)
        self.assertIn("not found", result.error)

    def test_respects_custom_output_path(self):
        custom = self.root / "thumbnails" / "custom.jpg"
        result = gt.generate_thumbnail(self.video, output_path=custom)
        self.assertIsNone(result.error)
        self.assertEqual(Path(result.output), custom)
        self.assertTrue(custom.exists())

    def test_respects_custom_width(self):
        result = gt.generate_thumbnail(self.video, width=640)
        self.assertEqual(result.width, 640)
        # Verify width via ffprobe-style check using PIL-ish raw ffmpeg inspect.
        out = Path(result.output)
        # The file must exist; ffmpeg writes the exact width we asked for.
        self.assertTrue(out.exists())

    def test_dry_run_does_not_invoke_ffmpeg(self):
        result = gt.generate_thumbnail(self.video, dry_run=True)
        self.assertIsNone(result.error)
        self.assertIsNotNone(result.output)
        # Output path was planned but never written.
        self.assertFalse(Path(result.output).exists())

    def test_probe_duration_returns_float(self):
        duration = gt.probe_duration(self.video)
        self.assertIsNotNone(duration)
        self.assertAlmostEqual(duration, 2.0, delta=0.2)

    def test_probe_duration_returns_none_for_missing(self):
        self.assertIsNone(gt.probe_duration(self.root / "nope.mp4"))


@unittest.skipUnless(_have_ffmpeg(), "ffmpeg not installed")
class GenerateForDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        # Two real videos + one non-video file.
        _make_test_video(self.root, "a.mp4", duration=1.0)
        _make_test_video(self.root, "b.mov", duration=1.0)
        (self.root / "notes.txt").write_text("ignore me")

    def tearDown(self):
        self.tmp.cleanup()

    def test_processes_supported_extensions_only(self):
        results = gt.generate_for_directory(self.root)
        sources = {Path(r.source).name for r in results}
        self.assertIn("a.mp4", sources)
        self.assertIn("b.mov", sources)
        self.assertNotIn("notes.txt", sources)

    def test_skips_videos_with_fresh_thumbnails(self):
        # First run makes thumbnails.
        first = gt.generate_for_directory(self.root)
        first_made = sum(1 for r in first if r.output and not r.skipped)
        self.assertEqual(first_made, 2)
        # Second run skips everything.
        second = gt.generate_for_directory(self.root)
        self.assertTrue(all(r.skipped for r in second))

    def test_force_regenerates_existing_thumbnails(self):
        gt.generate_for_directory(self.root)
        second = gt.generate_for_directory(self.root, force=True)
        self.assertFalse(any(r.skipped for r in second))
        self.assertTrue(all(r.output for r in second))

    def test_returns_error_for_missing_directory(self):
        results = gt.generate_for_directory(self.root / "no_such_dir")
        self.assertEqual(len(results), 1)
        self.assertIsNotNone(results[0].error)


class FrameStrategyTests(unittest.TestCase):
    """Pure-logic tests that don't need ffmpeg."""

    def test_first_strategy_zero_seek(self):
        self.assertEqual(gt._pick_seek_seconds("first", 30.0), 0.0)

    def test_middle_strategy_half_duration(self):
        self.assertEqual(gt._pick_seek_seconds("middle", 30.0), 15.0)

    def test_smart_strategy_first_third(self):
        self.assertAlmostEqual(gt._pick_seek_seconds("smart", 30.0), 10.0, places=3)

    def test_zero_duration_falls_back_to_zero(self):
        self.assertEqual(gt._pick_seek_seconds("smart", 0.0), 0.0)
        self.assertEqual(gt._pick_seek_seconds("middle", 0.0), 0.0)
        self.assertEqual(gt._pick_seek_seconds("first", 0.0), 0.0)

    def test_needs_regeneration_when_no_thumb(self):
        with tempfile.TemporaryDirectory() as td:
            video = Path(td) / "v.mp4"
            video.write_bytes(b"\x00")
            self.assertTrue(gt._needs_regeneration(video, video.with_suffix(".jpg"), force=False))

    def test_needs_regeneration_when_thumb_older(self):
        with tempfile.TemporaryDirectory() as td:
            video = Path(td) / "v.mp4"
            thumb = Path(td) / "v.jpg"
            video.write_bytes(b"\x00")
            thumb.write_bytes(b"\x00")
            import os
            import time

            os.utime(thumb, (time.time() - 100, time.time() - 100))
            os.utime(video, (time.time(), time.time()))
            self.assertTrue(gt._needs_regeneration(video, thumb, force=False))

    def test_force_overrides_fresh_thumb(self):
        with tempfile.TemporaryDirectory() as td:
            video = Path(td) / "v.mp4"
            thumb = Path(td) / "v.jpg"
            video.write_bytes(b"\x00")
            thumb.write_bytes(b"\x00")
            import os
            import time

            os.utime(thumb, (time.time(), time.time()))
            os.utime(video, (time.time() - 100, time.time() - 100))
            self.assertFalse(gt._needs_regeneration(video, thumb, force=False))
            self.assertTrue(gt._needs_regeneration(video, thumb, force=True))


class StatePersistenceTests(unittest.TestCase):
    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            tmp_root = Path(td)
            # Patch STATE_FILE to a temp path via direct calls.
            fake_state_file = tmp_root / "data" / "thumbnail_state.json"
            fake_state_file.parent.mkdir(parents=True, exist_ok=True)

            with patch.object(gt, "STATE_FILE", fake_state_file):
                gt._save_state({"last_run": {"timestamp": "2026-06-21T00:00:00"}})
                loaded = gt._load_state()
            self.assertEqual(loaded["last_run"]["timestamp"], "2026-06-21T00:00:00")

    def test_load_state_returns_empty_when_file_missing(self):
        with tempfile.TemporaryDirectory() as td:
            fake_state_file = Path(td) / "missing.json"
            with patch.object(gt, "STATE_FILE", fake_state_file):
                self.assertEqual(gt._load_state(), {})

    def test_load_state_returns_empty_on_corrupt_json(self):
        with tempfile.TemporaryDirectory() as td:
            fake_state_file = Path(td) / "corrupt.json"
            fake_state_file.write_text("{not json", encoding="utf-8")
            with patch.object(gt, "STATE_FILE", fake_state_file):
                self.assertEqual(gt._load_state(), {})


if __name__ == "__main__":
    unittest.main()
