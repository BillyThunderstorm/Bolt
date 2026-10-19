"""Targeted tests for scripts/reprocess_clips.py (temp dirs only — never real Data/)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for p in (str(REPO / "Core"), str(REPO / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import reprocess_clips as rc  # noqa: E402
from modules.FFmpeg_Bin import ffmpeg_bin  # noqa: E402

SETTINGS = {"style": "crop", "hashtags": ["gaming"]}


def _make_clip(path: Path, w: int = 640, h: int = 360, secs: float = 1.5) -> None:
    subprocess.run(
        [ffmpeg_bin(), "-v", "error", "-y",
         "-f", "lavfi", "-i", f"testsrc=size={w}x{h}:rate=30",
         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
         "-t", str(secs), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)],
        check=True, capture_output=True, timeout=60,
    )


class ReprocessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.clips = root / "clips"
        self.vert = root / "vertical"
        self.queue = root / "queue.json"
        self.clips.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, **kw):
        kw.setdefault("settings", SETTINGS)
        kw.setdefault("tag", False)
        return rc.run(clips_dir=self.clips, vertical_dir=self.vert, queue_file=self.queue, **kw)

    def test_no_clips_soft(self):
        s = self._run()
        self.assertTrue(s["error"].startswith("no mp4 clips"))
        self.assertFalse(self.queue.exists())

    def test_dry_run_writes_nothing(self):
        (self.clips / "a_clip01_audio_spike_5.mp4").write_bytes(b"x")
        s = self._run(dry_run=True)
        self.assertEqual([r["action"] for r in s["plan"]], ["build"])
        self.assertFalse(self.vert.exists())
        self.assertFalse(self.queue.exists())

    def test_real_convert_and_merge_keeps_other_items(self):
        _make_clip(self.clips / "Game's 100%_clip01_audio_spike_9.mp4")
        other = {"queue_id": "keep-me", "platforms": [{"clip_path": "/x/other.mp4"}]}
        self.queue.write_text(json.dumps({"items": [other]}))
        s = self._run()
        self.assertEqual(s["failed"], [])
        self.assertEqual(len(s["processed"]), 1)
        out = self.vert / "Game's 100%_clip01_audio_spike_9_tiktok.mp4"
        ok, why = rc.is_good_vertical(out)
        self.assertTrue(ok, why)
        items = json.loads(self.queue.read_text())["items"]
        self.assertEqual(items[0], other)
        self.assertEqual(len(items), 2)
        self.assertEqual({p["platform"] for p in items[1]["platforms"]},
                         {"tiktok", "youtube_shorts", "instagram_reels", "kick"})
        self.assertTrue(all(p["status"] == "manual_upload_ready" for p in items[1]["platforms"]))
        self.assertTrue((self.queue.parent / "queue.json.bak").exists())
        # Second run: reuse, no duplicate, schedule untouched.
        before = self.queue.read_text()
        s2 = self._run()
        self.assertEqual(s2["reused"], [out.name])
        self.assertEqual(self.queue.read_text(), before)

    def test_formatter_returning_source_is_failure(self):
        _make_clip(self.clips / "c_clip01.mp4")
        s = self._run(formatter=lambda src, output_dir=None, style=None: src)
        self.assertEqual(len(s["failed"]), 1)
        self.assertIn("original horizontal", s["failed"][0]["reason"])
        self.assertEqual(s["queued"], [])
        self.assertFalse(self.queue.exists())

    def test_landscape_output_rejected(self):
        _make_clip(self.clips / "d_clip01.mp4")

        def fake(src, output_dir=None, style=None):
            out = Path(output_dir) / "d_clip01_tiktok.mp4"
            _make_clip(out, 640, 360)
            return str(out)

        s = self._run(formatter=fake)
        self.assertEqual(len(s["failed"]), 1)
        self.assertIn("not vertical", s["failed"][0]["reason"])

    def test_already_queued_by_pipeline_not_duplicated(self):
        _make_clip(self.clips / "e_clip01.mp4")
        self.vert.mkdir()
        _make_clip(self.vert / "e_clip01_tiktok.mp4", 360, 640)
        pipe = {"queue_id": "abc", "platforms": [{"clip_path": str(self.vert / "e_clip01_tiktok.mp4")}]}
        self.queue.write_text(json.dumps({"items": [pipe]}))
        s = self._run()
        self.assertEqual(s["already_queued"], ["e_clip01.mp4"])
        self.assertEqual(json.loads(self.queue.read_text())["items"], [pipe])

    def test_bad_queue_json_left_untouched(self):
        _make_clip(self.clips / "f_clip01.mp4")
        self.queue.write_text("{not json")
        s = self._run()
        self.assertIn("not valid JSON", s["error"])
        self.assertEqual(self.queue.read_text(), "{not json")

    def test_name_filter_and_limit(self):
        for n in ("g_clip01.mp4", "h_clip02.mp4", "h_clip03.mp4"):
            (self.clips / n).write_bytes(b"x")
        s = self._run(dry_run=True, only=["h_"])
        self.assertEqual(len(s["plan"]), 2)
        s = self._run(dry_run=True, limit=1)
        self.assertEqual(len(s["plan"]), 1)

    def test_title_from_sidecar(self):
        clip = self.clips / "123_clip04_audio_spike_7.mp4"
        clip.write_bytes(b"x")
        clip.with_suffix(".json").write_text(json.dumps({"game": "Wolverine"}))
        self.assertEqual(rc.clip_title(clip), "Wolverine highlight (clip 04)")


if __name__ == "__main__":
    unittest.main()
