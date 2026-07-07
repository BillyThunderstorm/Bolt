"""Tests for Video_Intelligence (Tier 2.1).

Verifies:
1. _stat_lines filters OCR text to game-stat-shaped lines only.
2. Common noise (chat, menu text) is filtered out.
3. extract_stats gracefully handles missing files.
4. extract_stats gracefully handles OCR-disabled state.
5. extract_stats_multi returns per-frame output.
6. End-to-end OCR on a tiny ffmpeg-generated test video with embedded
   text (skipped if ffmpeg or tesseract unavailable).
"""

import sys
from pathlib import Path
_repo_root = Path(__file__).resolve().parents[2]
for _p in [_repo_root / 'Core']:
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

import shutil
import subprocess
import tempfile
import unittest

from modules import Video_Intelligence as vi


class StatLineFilterTests(unittest.TestCase):
    """Test the pure-Python filter that doesn't need ffmpeg/OCR."""

    def test_empty_text_returns_empty(self):
        self.assertEqual(vi._stat_lines(""), [])
        self.assertEqual(vi._stat_lines("\n\n   \n"), [])

    def test_picks_kill_streak(self):
        text = "some menu text\n15 KILL STREAK!\nmore random text"
        out = vi._stat_lines(text)
        self.assertEqual(out, ["15 KILL STREAK!"])

    def test_picks_scoreboard(self):
        text = """Player joined the game
SCORE 27 - 19
Round 3"""
        out = vi._stat_lines(text)
        # Two stat lines, deduped.
        self.assertEqual(len(out), 2)
        self.assertIn("SCORE 27 - 19", out)
        self.assertIn("Round 3", out)

    def test_picks_team_counts(self):
        text = """Chat: lol nice
3v5
Player 1"""
        out = vi._stat_lines(text)
        self.assertIn("3v5", out)
        # "Player 1" and "Chat: lol nice" should NOT be in the output.
        self.assertNotIn("Player 1", out)
        self.assertNotIn("Chat: lol nice", out)

    def test_drops_pure_chat(self):
        text = """hey what's up
lol nice shot
brb
gg"""
        out = vi._stat_lines(text)
        self.assertEqual(out, [])

    def test_drops_pure_menu_text(self):
        text = """Settings
Audio
Video
Controls
Quit"""
        out = vi._stat_lines(text)
        self.assertEqual(out, [])

    def test_dedupes(self):
        text = "15 KILL STREAK\n15 KILL STREAK\n15 KILL STREAK"
        out = vi._stat_lines(text)
        self.assertEqual(out, ["15 KILL STREAK"])

    def test_collapses_internal_whitespace(self):
        text = "DOUBLE    KILL\nTRIPLE\tKILL"
        out = vi._stat_lines(text)
        self.assertEqual(out, ["DOUBLE KILL", "TRIPLE KILL"])

    def test_picks_clock_times(self):
        text = "match timer 12:34\nchat: hi"
        out = vi._stat_lines(text)
        self.assertIn("match timer 12:34", out)
        self.assertNotIn("chat: hi", out)


class ExtractStatsGracefulDegradationTests(unittest.TestCase):
    """extract_stats should not crash when things are missing."""

    def test_missing_file_returns_empty(self):
        # With OCR enabled (in this env) but a missing path, returns [].
        if not vi.HAS_OCR:
            self.skipTest("pytesseract not available")
        result = vi.extract_stats("/tmp/does_not_exist_xyz.mp4")
        self.assertEqual(result, [])

    def test_disabled_ocr_returns_empty(self):
        from unittest.mock import patch
        with patch.object(vi, "HAS_OCR", False):
            result = vi.extract_stats("/tmp/anything.mp4")
            self.assertEqual(result, [])

    def test_extract_stats_multi_also_graceful(self):
        from unittest.mock import patch
        with patch.object(vi, "HAS_OCR", False):
            hits, per_frame = vi.extract_stats_multi("/tmp/anything.mp4")
            self.assertEqual(hits, [])
            self.assertEqual(per_frame, [])


class BlackFrameDetectionTests(unittest.TestCase):
    def test_solid_white_is_not_black(self):
        from PIL import Image
        img = Image.new("RGB", (100, 100), color="white")
        self.assertFalse(vi._is_black_frame(img))

    def test_solid_black_is_black(self):
        from PIL import Image
        img = Image.new("RGB", (100, 100), color="black")
        self.assertTrue(vi._is_black_frame(img))


class EndToEndOCRTests(unittest.TestCase):
    """
    Generate a tiny mp4 with burned-in text using ffmpeg + drawtext, then
    run extract_stats on it. Skipped if ffmpeg isn't available.
    """

    @classmethod
    def setUpClass(cls):
        if shutil.which("ffmpeg") is None:
            raise unittest.SkipTest("ffmpeg not available")
        if not vi.HAS_OCR:
            raise unittest.SkipTest("pytesseract not available")

    def test_ocr_finds_text_overlaid_on_real_frame(self):
        """End-to-end: extract a real video frame, overlay text via PIL,
        OCR it, and confirm our filter picks the stat out.
        """
        from PIL import Image, ImageDraw, ImageFont
        # Generate a tiny white video so _extract_frame doesn't reject it as black.
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            clip = tmp / "test.mp4"
            r = subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-f", "lavfi", "-i", "color=c=white:s=1280x720:d=3",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    str(clip),
                ],
                capture_output=True, timeout=30,
            )
            if r.returncode != 0:
                self.skipTest(f"ffmpeg unavailable: {r.stderr.decode()[:120]}")
            self.assertTrue(clip.exists(), "test clip was not created")

            img = vi._extract_frame(str(clip), 1.0)
            self.assertIsNotNone(img, "frame extraction returned None")

            # Overlay text on the white frame using PIL.
            draw = ImageDraw.Draw(img)
            try:
                font = ImageFont.truetype(
                    "/System/Library/Fonts/Helvetica.ttc", 48
                )
            except OSError:
                font = ImageFont.load_default()
            draw.text((50, 50), "SCORE 27 - 19", fill="black", font=font)
            draw.text((50, 150), "15 KILL STREAK", fill="red", font=font)
            draw.text((50, 250), "Player joined the game", fill="gray", font=font)
            draw.text((50, 350), "lol nice shot", fill="gray", font=font)

            text = vi._run_ocr(img)
            stats = vi._stat_lines(text)
            self.assertTrue(
                any("KILL STREAK" in s for s in stats),
                f"expected KILL STREAK in hits, got: {stats} (raw OCR: {text!r})",
            )
            self.assertTrue(
                any("SCORE 27 - 19" in s for s in stats),
                f"expected score line in hits, got: {stats}",
            )
            # Noise should be filtered out.
            self.assertFalse(
                any("lol nice" in s for s in stats),
                f"chat should be filtered, got: {stats}",
            )


if __name__ == "__main__":
    import unittest.mock
    unittest.main()
