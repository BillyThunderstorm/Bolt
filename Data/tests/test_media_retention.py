"""Targeted tests for Core/modules/Media_Retention.py and the cleanup scripts.

Temp dirs only — never touches media/, Data/ queue files, logs/ or the real
Trash (BOLT_RETENTION_TRASH_DIR points the "trash" at a temp folder).
"""

import ast
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

_repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_repo / "Core"))
sys.path.insert(0, str(_repo / "scripts"))

from modules import Media_Retention as mr  # noqa: E402

OLD = time.time() - 40 * 86400
SRC = "2889961274"
CLIP = f"{SRC}_clip02_audio_spike_182"


def _touch(path: Path, ts: float = OLD, data: bytes = b"x" * 2048) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.utime(path, (ts, ts))
    return path


class RetentionBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.clips = self.root / "clips"
        self.vert = self.root / "vertical_clips"
        self.rec = self.root / "Recordings"
        for d in (self.clips, self.vert, self.rec):
            d.mkdir()
        self.trash = self.root / "Trash"
        self.log = self.root / "media_retention.log"
        self.rtp = self.root / "ready_to_post.json"
        self.mpq = self.root / "multi_platform_queue.json"
        self.hashdb = self.root / "media_hash_db.json"
        self.backups = self.root / "backups"
        self.write_queues([], [])
        self.env = patch.dict(os.environ, {
            "BOLT_RETENTION_QUEUES": os.pathsep.join([str(self.rtp), str(self.mpq)]),
            "BOLT_RETENTION_HASH_DB": str(self.hashdb),
            "BOLT_RETENTION_LOG": str(self.log),
            "BOLT_RETENTION_TRASH_DIR": str(self.trash),
            "BOLT_RETENTION_BACKUP_DIR": str(self.backups),
        })
        self.env.start()
        mr._HASH_CACHE.clear()

    def tearDown(self):
        self.env.stop()
        mr._HASH_CACHE.clear()
        self.tmp.cleanup()

    def write_queues(self, clips, items):
        self.rtp.write_text(json.dumps({"clips": clips, "consecutive_ignored_reviews": 0}))
        self.mpq.write_text(json.dumps({"items": items}))

    def ready_entry(self, path, status="ready", qid="671f95cd"):
        return {"id": qid, "clip_path": str(path), "status": status,
                "title": f"Highlight from the stream: {Path(path).name}",
                "platform_plan": [{"platform": "youtube_shorts", "status": "manual_upload_ready",
                                   "clip_path": str(path)}]}

    def quiet(self, *_a, **_k):
        pass


class ProtectionTests(RetentionBase):
    def test_queued_clip_vertical_thumb_and_source_are_kept(self):
        vertical = _touch(self.vert / f"{CLIP}_tiktok.mp4")
        horiz = _touch(self.clips / f"{CLIP}.mp4")
        thumb = _touch(self.clips / f"{CLIP}.jpg")
        source = _touch(self.rec / f"{SRC}.mp4")
        other = _touch(self.clips / "2026-09-02_23-25-40_clip01_audio_spike_1.mp4")
        self.write_queues([self.ready_entry(vertical)], [])

        res = mr.run_age([self.clips, self.vert], 14, "Clips", echo=self.quiet)
        mr.run_age([self.rec], 30, "Recordings", echo=self.quiet)

        for f in (vertical, horiz, thumb, source):
            self.assertTrue(f.exists(), f"{f.name} should be protected")
        self.assertFalse(other.exists())
        self.assertTrue((self.trash / other.name).exists(), "goes to Trash, not deleted")
        self.assertEqual(res["trashed"], 1)
        self.assertGreaterEqual(res["protected"], 3)
        log = self.log.read_text()
        self.assertIn("KEPT_PROTECTED", log)
        self.assertRegex(log, r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d C[DS]T\tTRASHED\t.*clip01_audio_spike_1\.mp4\tolder than 14d")

    def test_posted_scrapped_and_fully_done_items_do_not_protect(self):
        posted = _touch(self.clips / "a_clip01_audio_spike_1.mp4")
        scrapped = _touch(self.clips / "b_clip01_audio_spike_1.mp4")
        mp_done = _touch(self.clips / "c_clip01_audio_spike_1.mp4")
        mp_live = _touch(self.clips / "d_clip01_audio_spike_1.mp4")
        self.write_queues(
            [self.ready_entry(posted, "posted", "1"), self.ready_entry(scrapped, "scrapped", "2")],
            [{"queue_id": "x", "original_clip_path": str(mp_done),
              "platforms": [{"status": "posted", "clip_path": str(mp_done)}]},
             {"queue_id": "y", "original_clip_path": str(mp_live),
              "platforms": [{"status": "posted"}, {"status": "manual_upload_ready",
                                                   "clip_path": str(mp_live)}]}],
        )
        mr.run_age([self.clips], 14, "Clips", echo=self.quiet)
        self.assertFalse(posted.exists())
        self.assertFalse(scrapped.exists())
        self.assertFalse(mp_done.exists())
        self.assertTrue(mp_live.exists())

    def test_size_limit_skips_queued_oldest_and_trashes_next(self):
        queued = _touch(self.clips / f"{CLIP}.mp4", OLD - 86400, b"q" * 600_000)
        older = _touch(self.clips / "z_clip01_audio_spike_9.mp4", OLD, b"o" * 600_000)
        newer = _touch(self.clips / "z_clip02_audio_spike_9.mp4", time.time(), b"n" * 600_000)
        self.write_queues([self.ready_entry(queued)], [])
        mr.run_size(self.clips, 0.0012, "Clips", echo=self.quiet)  # ~1.29MB limit
        self.assertTrue(queued.exists())
        self.assertFalse(older.exists())
        self.assertTrue(newer.exists())


class AgeTests(RetentionBase):
    def test_sidecar_created_at_beats_carried_over_mtime(self):
        clip = _touch(self.clips / "e_clip01_audio_spike_5.mp4")
        (self.clips / "e_clip01_audio_spike_5.json").write_text(
            json.dumps({"created_at": mr.now_ct().isoformat()}))
        ts, src = mr.created_time(clip)
        self.assertEqual(src, "sidecar")
        mr.run_age([self.clips], 14, "Clips", echo=self.quiet)
        self.assertTrue(clip.exists())

    def test_hash_db_first_seen_used(self):
        clip = _touch(self.clips / "f_clip01_audio_spike_5.mp4")
        self.hashdb.write_text(json.dumps({"files": {str(clip): {"first_seen": "2099-01-01T00:00:00Z"}}}))
        _, src = mr.created_time(clip)
        self.assertEqual(src, "hash_db.first_seen")
        mr.run_age([self.clips], 14, "Clips", echo=self.quiet)
        self.assertTrue(clip.exists())

    def test_fallback_is_later_of_mtime_and_birthtime(self):
        clip = _touch(self.clips / "g.mp4")
        ts, src = mr.created_time(clip)
        st = clip.stat()
        self.assertAlmostEqual(ts, max(st.st_mtime, getattr(st, "st_birthtime", 0)), delta=1)
        self.assertIn(src, ("mtime", "birthtime"))

    def test_dry_run_moves_nothing_and_never_unlinks(self):
        clip = _touch(self.clips / "h.mp4")
        with patch.object(Path, "unlink", side_effect=AssertionError("unlink used")), \
             patch("os.remove", side_effect=AssertionError("os.remove used")):
            mr.run_age([self.clips], 14, "Clips", dry_run=True, echo=self.quiet)
            self.assertTrue(clip.exists())
            self.assertIn("WOULD_TRASH", self.log.read_text())
            mr.run_age([self.clips], 14, "Clips", echo=self.quiet)
        self.assertFalse(clip.exists())
        self.assertTrue((self.trash / "h.mp4").exists())


class PruneTests(RetentionBase):
    def test_marks_missing_entries_and_backs_up(self):
        alive = _touch(self.vert / "alive_clip01_x_tiktok.mp4")
        gone = self.vert / "gone_clip01_x_tiktok.mp4"
        self.write_queues(
            [self.ready_entry(alive, "ready", "a"), self.ready_entry(gone, "held", "b"),
             self.ready_entry(gone, "posted", "c")],
            [{"queue_id": "m", "original_clip_path": str(gone),
              "platforms": [{"status": "manual_upload_ready", "clip_path": str(gone)},
                            {"status": "posted", "clip_path": str(gone)}]}],
        )
        dry = mr.prune_queues(dry_run=True, echo=self.quiet)
        self.assertEqual(dry["files"]["ready_to_post.json"]["marked_missing_file"], 1)
        self.assertEqual(json.loads(self.rtp.read_text())["clips"][1]["status"], "held")
        self.assertFalse(self.backups.exists())

        rep = mr.prune_queues(echo=self.quiet)
        self.assertEqual(rep["files"]["ready_to_post.json"]["marked_missing_file"], 1)
        self.assertEqual(rep["files"]["multi_platform_queue.json"]["marked_missing_file"], 1)
        self.assertEqual(len(rep["backups"]), 2)
        for b in rep["backups"]:
            self.assertTrue(Path(b).is_file())
        clips = json.loads(self.rtp.read_text())["clips"]
        self.assertEqual(clips[0]["status"], "ready")
        self.assertEqual(clips[1]["status"], "missing_file")
        self.assertEqual(clips[1]["missing_file_prev_status"], "held")
        self.assertEqual(clips[1]["platform_plan"][0]["status"], "missing_file")
        self.assertEqual(clips[2]["status"], "posted")
        item = json.loads(self.mpq.read_text())["items"][0]
        self.assertEqual(item["status"], "missing_file")
        self.assertEqual([p["status"] for p in item["platforms"]], ["missing_file", "posted"])
        # second run: nothing new, no new backups
        again = mr.prune_queues(echo=self.quiet)
        self.assertEqual(again["backups"], [])


class WiringTests(RetentionBase):
    def _env(self):
        e = dict(os.environ)
        e.update({"CLIPS_DIR": str(self.clips), "VERTICAL_CLIPS_DIR": str(self.vert),
                  "RECORDINGS_DIR": str(self.rec), "OUTPUT_DIR": str(self.root / "output"),
                  "MEDIA_DIR": str(self.root), "LOG_DIR": str(self.root / "logs"),
                  "RETENTION_PY": sys.executable})
        return e

    def test_storage_optimization_dry_run_uses_helper(self):
        queued = _touch(self.vert / f"{CLIP}_tiktok.mp4")
        old = _touch(self.clips / "old_clip01_audio_spike_3.mp4")
        self.write_queues([self.ready_entry(queued)], [])
        out = subprocess.run(
            ["bash", str(_repo / "scripts" / "storage_optimization.sh"), "--dry-run",
             "--skip-dedup", "--skip-compress"],
            env=self._env(), capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Would trash", out.stdout)
        self.assertIn("Kept (in post queue)", out.stdout)
        self.assertTrue(queued.exists() and old.exists())

    def test_media_rotation_dry_run_uses_helper(self):
        _touch(self.clips / "big_clip01_a_1.mp4", OLD, b"b" * 1_500_000)
        out = subprocess.run(
            ["bash", str(_repo / "scripts" / "media_rotation.sh"), "--dry-run", "--clips-gb", "0.001"],
            env=self._env(), capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Would trash", out.stdout)
        self.assertTrue((self.clips / "big_clip01_a_1.mp4").exists())

    def test_scripts_have_no_rm_of_media(self):
        for name in ("storage_optimization.sh", "media_rotation.sh"):
            text = (_repo / "scripts" / name).read_text()
            for line in text.splitlines():
                s = line.strip()
                if s.startswith("rm ") or s.startswith("rm -f"):
                    self.assertTrue("temp" in s or "output_file" in s, f"{name}: {s}")

    def test_launch_cleanup_no_longer_deletes(self):
        tree = ast.parse((_repo / "Core" / "launch.py").read_text())
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "_cleanup_old_clips")
        called = {getattr(n.func, "attr", getattr(n.func, "id", ""))
                  for n in ast.walk(fn) if isinstance(n, ast.Call)}
        for bad in ("unlink", "remove", "rmtree", "send2trash", "trash"):
            self.assertNotIn(bad, called)
        self.assertIn("nightly", ast.unparse(fn))

    def test_ytdlp_commands_request_fresh_mtime(self):
        import twitch_vod_downloader as tvd
        cmd = tvd.ytdlp_sample_cmd("/x/yt-dlp", "1", self.root / "o.mp4", 0, 5, None)
        self.assertIn("--no-mtime", cmd)
        self.assertIn('"--no-mtime"', (_repo / "scripts" / "auto_clip_twitch.py").read_text())


if __name__ == "__main__":
    unittest.main()
