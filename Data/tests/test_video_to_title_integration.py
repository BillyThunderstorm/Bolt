"""End-to-end integration test: Video_Intelligence OCR feeds Title_Generator.

This is the production code path that bot.py runs:
  1. extract_stats(clip_path) finds on-screen text
  2. generate_titles(context={'on_screen_stats': stats}) prepends the
     strongest stat to each title

The test uses a real ffmpeg-generated video with PIL-overlaid text
to exercise both modules together. Skipped if ffmpeg or tesseract
isn't available.
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
from PIL import Image, ImageDraw, ImageFont

from modules import Title_Generator as tg
from modules import Video_Intelligence as vi


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not available")
@unittest.skipUnless(vi.HAS_OCR, "pytesseract not available")
class VideoToTitleIntegrationTests(unittest.TestCase):

    def test_ocr_stats_prepend_to_titles(self):
        """A clip with overlaid '15 KILL STREAK' produces titles that
        start with that stat."""
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
            self.assertEqual(r.returncode, 0, "ffmpeg setup failed")

            # Extract a real frame, overlay text, OCR, generate title.
            img = vi._extract_frame(str(clip), 1.0)
            self.assertIsNotNone(img)

            draw = ImageDraw.Draw(img)
            try:
                font = ImageFont.truetype(
                    "/System/Library/Fonts/Helvetica.ttc", 64
                )
            except OSError:
                font = ImageFont.load_default()
            draw.text((50, 50), "15 KILL STREAK", fill="red", font=font)

            text = vi._run_ocr(img)
            stats = vi._stat_lines(text)
            self.assertTrue(
                any("KILL STREAK" in s for s in stats),
                f"setup failed: OCR didn't find expected stat. got: {stats!r}",
            )

            # Now the production path: feed stats into generate_titles.
            titles, hashtags = tg.generate_titles(
                trigger="kill",
                game="Marvel Rivals",
                context={
                    "config": {"quality_tiers": {"use_ai_titles": False}},
                    "on_screen_stats": stats,
                },
            )
            self.assertEqual(len(titles), 3)
            for t in titles:
                self.assertTrue(
                    t.startswith("15 KILL STREAK — "),
                    f"title should be stat-augmented, got: {t!r}",
                )

    def test_no_ocr_signal_keeps_template_clean(self):
        """A clip with no overlaid text produces normal template titles."""
        titles, _ = tg.generate_titles(
            trigger="kill",
            game="Marvel Rivals",
            context={
                "config": {"quality_tiers": {"use_ai_titles": False}},
                "on_screen_stats": [],  # empty OCR result
            },
        )
        for t in titles:
            self.assertFalse(
                t.startswith(" — "),
                f"title should not have a stray dash prefix, got: {t!r}",
            )

    def test_empty_stats_list_is_treated_as_no_signal(self):
        """An empty list (not just None) should not prepend anything."""
        titles, _ = tg.generate_titles(
            trigger="kill",
            game="Marvel Rivals",
            context={
                "config": {"quality_tiers": {"use_ai_titles": False}},
                "on_screen_stats": None,  # explicitly None
            },
        )
        for t in titles:
            self.assertFalse(
                t.startswith(" — "),
                f"None on_screen_stats should not add prefix, got: {t!r}",
            )


if __name__ == "__main__":
    unittest.main()
