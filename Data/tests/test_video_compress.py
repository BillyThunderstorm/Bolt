"""Targeted tests for bolt compress (Video_Compress).

Temp dirs and tiny ffmpeg-generated clips only — never touches media/clips,
Data/compress_ledger.json, logs/, Google Docs or other Data/ files.

Covers:
1. A big clip is re-encoded, swapped in under the same name with the same
   mtime, original moved to originals_backup/, ledger written, no temp left.
2. A second run skips it (no re-encode loop), even after backups are cleaned.
3. A clip that doesn't shrink enough is kept and not retried every run.
4. A corrupt clip fails safely (original untouched) and stops after 3 tries.
5. Files younger than 5 minutes are left alone.
6. No working ffmpeg and no working HandBrake → soft-fail message.
7. clean-backups deletes only old backups; dry-run deletes nothing.
"""

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

_repo_root = Path(__file__).resolve().parents[2]
_core = str(_repo_root / "Core")
if _core not in sys.path:
    sys.path.insert(0, _core)

from modules import Video_Compress as vc  # noqa: E402
from modules.FFmpeg_Bin import working_ffmpeg  # noqa: E402

FF = working_ffmpeg()
OLD = time.time() - 3600


def _make_clip(path: Path, *, seconds: int = 3, crf: int = 0, size: str = "640x360") -> None:
    subprocess.run(
        [FF, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30:duration={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-c:v", "libx264", "-crf", str(crf), "-preset", "ultrafast",
         "-c:a", "aac", "-shortest", str(path)],
        check=True, capture_output=True,
    )
    os.utime(path, (OLD, OLD))


@unittest.skipUnless(FF, "needs a working ffmpeg")
class VideoCompressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.clips = root / "clips"
        self.clips.mkdir()
        self.env = patch.dict(os.environ, {
            "BOLT_COMPRESS_CLIPS_DIR": str(self.clips),
            "BOLT_COMPRESS_LEDGER": str(root / "ledger.json"),
            "BOLT_COMPRESS_LOG": str(root / "compress.log"),
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_compress_swaps_in_place_and_does_not_loop(self):
        clip = self.clips / "big clip's #1.mp4"
        _make_clip(clip, crf=0)
        before = clip.stat().st_size
        res = vc.compress_clips(echo=False)
        self.assertTrue(res["ok"], res)
        self.assertEqual(len(res["compressed"]), 1, res)
        self.assertLess(clip.stat().st_size, before)
        self.assertAlmostEqual(clip.stat().st_mtime, OLD, delta=2)
        self.assertTrue((self.clips / "originals_backup" / clip.name).is_file())
        self.assertFalse((self.clips / ".compress_tmp").exists())
        info = vc._probe(clip)
        self.assertTrue(info["has_video"] and info["has_audio"])
        self.assertAlmostEqual(info["duration"], 3.0, delta=0.75)
        # second run: nothing to do
        self.assertEqual(vc.compress_clips(echo=False)["candidates"], [])
        # still nothing after backups are cleaned (ledger remembers)
        vc.clean_backups(older_than_days=0)
        self.assertEqual(vc.compress_clips(echo=False)["candidates"], [])

    def test_small_clip_kept_and_not_retried(self):
        clip = self.clips / "small.mp4"
        _make_clip(clip, crf=40)
        before = clip.read_bytes()
        res = vc.compress_clips(echo=False, min_savings=95)
        self.assertEqual(len(res["kept"]), 1, res)
        self.assertEqual(clip.read_bytes(), before)
        self.assertFalse((self.clips / "originals_backup" / clip.name).exists())
        self.assertEqual(vc.compress_clips(echo=False)["candidates"], [])

    def test_corrupt_clip_fails_safely_and_gives_up(self):
        clip = self.clips / "broken.mp4"
        clip.write_bytes(b"not a video" * 100)
        os.utime(clip, (OLD, OLD))
        for _ in range(vc.MAX_FAILS):
            res = vc.compress_clips(echo=False)
            self.assertEqual(len(res["failed"]), 1, res)
        self.assertEqual(clip.read_bytes(), b"not a video" * 100)
        self.assertEqual(vc.compress_clips(echo=False)["candidates"], [])

    def test_fresh_clip_left_alone(self):
        clip = self.clips / "fresh.mp4"
        _make_clip(clip)
        now = time.time()
        os.utime(clip, (now, now))
        res = vc.compress_clips(echo=False)
        self.assertEqual(res["candidates"], [])
        self.assertIn("5 min", res["skipped"][0]["reason"])

    def test_no_encoder_soft_fails(self):
        _make_clip(self.clips / "a.mp4")
        with patch.object(vc, "_ffmpeg", return_value=None), \
             patch.object(vc, "_handbrake_state",
                          return_value={"path": "/x/HandBrakeCLI", "works": False,
                                        "problem": "won't start"}):
            res = vc.compress_clips(echo=False)
            st = vc.status()
        self.assertFalse(res["ok"])
        self.assertTrue(res["error"].startswith(vc._SOFT))
        self.assertFalse(st["ready"])
        self.assertIn("ffmpeg-full", st["error"])

    def test_clean_backups_only_old(self):
        backup = self.clips / "originals_backup"
        backup.mkdir()
        (backup / "new.mp4").write_bytes(b"x" * 10)
        res = vc.clean_backups(older_than_days=7, dry_run=True)
        self.assertEqual(res["removed"], [])
        self.assertEqual(res["kept"], 1)
        res = vc.clean_backups(older_than_days=0, dry_run=True)
        self.assertEqual(res["removed"], ["new.mp4"])
        self.assertTrue((backup / "new.mp4").exists())
        vc.clean_backups(older_than_days=0)
        self.assertFalse((backup / "new.mp4").exists())


if __name__ == "__main__":
    unittest.main()
