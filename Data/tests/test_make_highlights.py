"""Targeted tests for bolt make-highlights (Make_Highlights + engine).

Temp dirs and tiny ffmpeg-generated clips only — never touches media/clips,
media/output, Google Docs or Data/ files.

Covers:
1. Real stitch of mixed sources (720p60 with audio + portrait 25 fps with no
   audio track) whose names/dirs contain apostrophes and % → playable mp4
   with video + audio and the expected duration.
2. Zero clips → engine returns 1 with ``Highlights unavailable:`` (no stack).
3. No working ffmpeg → compile soft-fails; module status gives guidance.
4. Module ``run`` with an empty clips dir soft-fails before the engine.
5. A corrupt clip soft-fails instead of reporting a stale reel.
"""

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_repo_root = Path(__file__).resolve().parents[2]
for _p in [_repo_root / "Core", _repo_root / "scripts"]:
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

import make_twitch_highlights as engine  # noqa: E402
from modules import Make_Highlights as mh  # noqa: E402
from modules.FFmpeg_Bin import ffprobe_bin, working_ffmpeg  # noqa: E402

FF = working_ffmpeg()


def _probe(path: Path) -> tuple[float, set]:
    out = subprocess.run(
        [ffprobe_bin(), "-v", "error", "-show_entries",
         "stream=codec_type:format=duration", "-of", "default=nw=1", str(path)],
        capture_output=True, text=True, timeout=15,
    ).stdout
    dur = 0.0
    kinds = set()
    for line in out.splitlines():
        if line.startswith("duration="):
            dur = float(line.split("=", 1)[1])
        if line.startswith("codec_type="):
            kinds.add(line.split("=", 1)[1])
    return dur, kinds


def _quiet(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        rc = fn(*a, **kw)
    return rc, buf.getvalue()


@unittest.skipUnless(FF, "no working ffmpeg")
class TestEngineStitch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.clips = root / "billy's clips"
        self.out_dir = root / "it's 100% out"
        self.clips.mkdir()
        subprocess.run(
            [FF, "-v", "error", "-y", "-f", "lavfi", "-i",
             "testsrc=s=1280x720:r=60:d=2", "-f", "lavfi", "-i", "sine=d=2",
             "-c:v", "libx264", "-c:a", "aac", "-shortest",
             str(self.clips / "a_clip's 100%.mp4")],
            check=True, timeout=60,
        )
        subprocess.run(
            [FF, "-v", "error", "-y", "-f", "lavfi", "-i",
             "testsrc2=s=720x1280:r=25:d=2", "-c:v", "libx264", "-an",
             str(self.clips / "b_silent.mp4")],
            check=True, timeout=60,
        )
        self.p = [
            patch.object(engine, "CLIPS_DIR", self.clips),
            patch.object(engine, "OUTPUT_DIR", self.out_dir),
            patch.object(engine, "QUEUE_FILE", root / "none.json"),
            patch.object(engine, "PERFORMANCE_FILE", root / "none.jsonl"),
        ]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.tmp.cleanup()

    def test_mixed_sources_and_special_chars(self):
        out = self.out_dir / "reel's.mp4"
        rc, log = _quiet(engine.main, ["--count", "2", "--output", str(out)])
        self.assertEqual(rc, 0, log)
        self.assertTrue(out.is_file(), log)
        dur, kinds = _probe(out)
        self.assertGreater(dur, 6.0)  # 3 s title + 2 + 2
        self.assertLess(dur, 8.5)
        self.assertEqual(kinds, {"video", "audio"})
        # temp work dir cleaned up; only the reel remains
        self.assertEqual([p.name for p in self.out_dir.iterdir()], [out.name])
        # source clips untouched
        self.assertEqual(len(list(self.clips.glob("*.mp4"))), 2)

    def test_list_returns_zero(self):
        rc, log = _quiet(engine.main, ["--list"])
        self.assertEqual(rc, 0)
        self.assertIn("b_silent.mp4", log)

    def test_corrupt_clip_soft_fails(self):
        bad = self.clips / "zz_bad.mp4"
        bad.write_bytes(b"not a video" * 200)
        rc, log = _quiet(
            engine.compile_highlight_reel,
            [{"name": bad.name, "path": str(bad), "duration": 0.0}],
            self.out_dir / "x.mp4", "T", "S",
        )
        self.assertFalse(rc)
        self.assertIn(engine.SOFT, log)
        self.assertFalse((self.out_dir / "x.mp4").exists())


class TestSoftFail(unittest.TestCase):
    def test_zero_clips_engine(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(engine, "CLIPS_DIR", Path(d)):
                rc, log = _quiet(engine.main, ["--count", "2"])
        self.assertEqual(rc, 1)
        self.assertIn("Highlights unavailable: no clips", log)
        self.assertNotIn("Traceback", log)

    def test_bad_count(self):
        rc, log = _quiet(engine.main, ["--count", "0"])
        self.assertEqual(rc, 1)
        self.assertIn(engine.SOFT, log)

    def test_no_ffmpeg_compile(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(engine, "_ffmpeg", return_value=None):
                ok, log = _quiet(
                    engine.compile_highlight_reel,
                    [{"name": "a.mp4", "path": "/nope/a.mp4", "duration": 1}],
                    Path(d) / "r.mp4", "T", "S",
                )
        self.assertFalse(ok)
        self.assertIn("Highlights unavailable: no working ffmpeg", log)

    def test_no_ffmpeg_module_status(self):
        with patch.object(mh, "_ffmpeg_path", return_value=None):
            info = mh.status()
        self.assertFalse(info["ready"])
        self.assertIn("Highlights unavailable:", info["error"])
        self.assertIn("ffmpeg-full", info["error"])

    def test_module_run_zero_clips(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(mh, "_clips_dir", return_value=Path(d)), \
                    patch.object(mh, "_ffmpeg_path", return_value="/bin/ffmpeg"), \
                    patch.object(mh.subprocess, "call") as call:
                rc, log = _quiet(mh.try_run, count=2)
        self.assertEqual(rc, 0)
        call.assert_not_called()
        self.assertIn("Highlights unavailable: no mp4 clips", log)
        self.assertIn("bolt wrap", log)

    def test_module_status_ready_label(self):
        info = mh.status()
        self.assertEqual(info["readiness"], "READY")
        self.assertTrue(info["output_dir"].endswith("media/output"))


if __name__ == "__main__":
    unittest.main()
