"""Unit / smoke tests for Clip_Factory caption burn-in."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "Core"
MODULES = CORE / "modules"
for p in (str(MODULES), str(CORE), str(REPO / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from Clip_Factory import (  # noqa: E402
    build_caption_drawtext_filter,
    format_for_tiktok,
    _escape_drawtext,
    _normalize_caption_text,
)


class TestCaptionFilterBuild(unittest.TestCase):
    def test_empty_segments(self):
        self.assertIsNone(build_caption_drawtext_filter(None))
        self.assertIsNone(build_caption_drawtext_filter([]))
        self.assertIsNone(
            build_caption_drawtext_filter([{"start": 0, "end": 1, "text": "  "}])
        )

    def test_builds_drawtext_with_enable(self):
        segs = [
            {"start": 0.0, "end": 1.5, "text": "Hello world"},
            {"start": 1.5, "end": 3.0, "text": "Clutch play"},
        ]
        vf = build_caption_drawtext_filter(segs, font_path="Arial")
        self.assertIsNotNone(vf)
        self.assertIn("drawtext=", vf)
        self.assertIn("Hello world", vf)
        self.assertIn("Clutch play", vf)
        self.assertIn("enable=", vf)
        self.assertIn("between(t", vf)

    def test_escape_and_normalize(self):
        self.assertEqual(_escape_drawtext("a:b"), "a\:b")
        self.assertEqual(_normalize_caption_text("  hi   there  "), "hi there")
        long = " ".join(f"w{i}" for i in range(20))
        out = _normalize_caption_text(long, max_words=12)
        self.assertTrue(out.endswith("…"))
        self.assertTrue(out.startswith("w0 "))
        self.assertIn("w11", out)
        self.assertNotIn("w12", out)


class TestFormatForTiktokBurnin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="bolt_burnin_")
        cls.src = os.path.join(cls.tmp, "src.mp4")
        # Tiny synthetic 2s 16:9 clip (color + silent audio)
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=blue:s=1280x720:d=2",
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-shortest",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            cls.src,
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=60)
        if r.returncode != 0:
            raise unittest.SkipTest(
                f"ffmpeg cannot create synthetic source: {(r.stderr or b'')[-200:]}"
            )

    def test_no_segments_still_vertical(self):
        out_dir = os.path.join(self.tmp, "out_none")
        os.makedirs(out_dir, exist_ok=True)
        out = format_for_tiktok(self.src, transcript_segments=None, output_dir=out_dir, preset="ultrafast")
        self.assertTrue(os.path.isfile(out), out)
        self.assertTrue(out.endswith("_tiktok.mp4"))

    def test_burnin_with_synthetic_segments(self):
        out_dir = os.path.join(self.tmp, "out_burn")
        os.makedirs(out_dir, exist_ok=True)
        segs = [
            {"start": 0.0, "end": 1.0, "text": "TEST CAPTION"},
            {"start": 1.0, "end": 2.0, "text": "SECOND LINE"},
        ]
        out = format_for_tiktok(
            self.src,
            transcript_segments=segs,
            output_dir=out_dir,
            preset="ultrafast",
        )
        self.assertTrue(os.path.isfile(out), out)
        # File should be non-trivial
        self.assertGreater(os.path.getsize(out), 1000)

    def test_degrade_on_empty_text_segments(self):
        out_dir = os.path.join(self.tmp, "out_empty")
        os.makedirs(out_dir, exist_ok=True)
        out = format_for_tiktok(
            self.src,
            transcript_segments=[{"start": 0, "end": 1, "text": ""}],
            output_dir=out_dir,
            preset="ultrafast",
        )
        self.assertTrue(os.path.isfile(out), out)


if __name__ == "__main__":
    unittest.main()
