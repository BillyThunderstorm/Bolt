"""Tests for `bolt watch` (Core/modules/Folder_Watch.py) — temp files only.

The clip pipeline is replaced by a fake processor, so nothing touches real
recordings, clips, queues or Google Docs.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

_repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_repo_root / "Core"))
sys.path.insert(0, str(_repo_root / "scripts"))

from modules import Folder_Watch as fw  # noqa: E402
from modules import Watcher as watcher  # noqa: E402


class FolderWatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.folder = root / "Recordings"
        self.folder.mkdir()
        self.log = root / "processed_recordings.json"
        self.patches = [
            patch.object(watcher, "PROCESSED_LOG", self.log),
            patch.object(watcher, "RECORDINGS_FOLDER", str(self.folder)),
            patch.object(fw, "_PROCESSED", self.log),
            patch.object(fw, "_ffmpeg_path", lambda: "/usr/bin/true"),
        ]
        for p in self.patches:
            p.start()
        self.seen: list[str] = []

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def _touch(self, name: str, age: float = 0.0) -> Path:
        path = self.folder / name
        path.write_bytes(b"x" * 32)
        if age:
            t = time.time() - age
            os.utime(path, (t, t))
        return path

    def _proc(self, path: str):
        self.seen.append(Path(path).name)
        return "ok"

    def _logged(self) -> set:
        return set(json.loads(self.log.read_text())) if self.log.exists() else set()

    def test_once_processes_pending_oldest_first_and_marks(self):
        self._touch("new.mp4", age=10)
        self._touch("old.mkv", age=1000)
        res = fw.try_run(once=True, processor=self._proc, stable_wait=0)
        self.assertTrue(res["ok"], res)
        self.assertEqual(self.seen, ["old.mkv", "new.mp4"])
        self.assertEqual(self._logged(), {"old.mkv", "new.mp4"})

    def test_second_run_skips_already_processed(self):
        self._touch("a.mp4")
        fw.try_run(once=True, processor=self._proc, stable_wait=0)
        self.seen.clear()
        res = fw.try_run(once=True, processor=self._proc, stable_wait=0)
        self.assertEqual(self.seen, [])
        self.assertEqual(res["processed"], [])

    def test_uppercase_mov_is_picked_up(self):
        self._touch("IMG_0001.MOV")
        pending = watcher.list_pending_recordings(self.folder)
        self.assertEqual([p.name for p in pending], ["IMG_0001.MOV"])

    def test_hidden_and_appledouble_ignored(self):
        self._touch("._clip.mp4")
        self._touch(".hidden.mp4")
        self._touch("notes.txt")
        self.assertEqual(watcher.list_pending_recordings(self.folder), [])

    def test_dry_run_changes_nothing(self):
        self._touch("a.mp4")
        res = fw.try_run(once=True, dry_run=True, processor=self._proc)
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["pending"]), 1)
        self.assertEqual(self.seen, [])
        self.assertFalse(self.log.exists())

    def test_failed_recording_reported_and_marked(self):
        self._touch("bad.mp4")

        def boom(_):
            raise RuntimeError("ffmpeg exploded")

        res = fw.try_run(once=True, processor=boom, stable_wait=0)
        self.assertFalse(res["ok"])
        self.assertTrue(res["error"].startswith("Watch unavailable:"))
        self.assertIn("bad.mp4", self._logged())

    def test_file_still_being_written_is_skipped(self):
        self._touch("growing.mp4")
        with patch.object(fw, "_is_stable", lambda p, w: False):
            res = fw.try_run(once=True, processor=self._proc, stable_wait=0)
        self.assertEqual(self.seen, [])
        self.assertEqual(len(res["skipped_writing"]), 1)
        self.assertNotIn("growing.mp4", self._logged())

    def test_max_limits_count(self):
        for i in range(3):
            self._touch(f"r{i}.mp4", age=100 - i)
        fw.try_run(once=True, processor=self._proc, stable_wait=0, max_items=2)
        self.assertEqual(len(self.seen), 2)

    def test_missing_ffmpeg_soft_fails(self):
        self._touch("a.mp4")
        with patch.object(fw, "_ffmpeg_path", lambda: None):
            res = fw.try_run(once=True)
            st = fw.status()
        self.assertTrue(res["error"].startswith("Watch unavailable:"))
        self.assertIn("ffmpeg", res["error"])
        self.assertFalse(st["ready"])

    def test_status_ready_counts(self):
        self._touch("a.mp4")
        self._touch("b.MOV")
        st = fw.status()
        self.assertTrue(st["ready"])
        self.assertEqual(st["readiness"], "READY")
        self.assertEqual(st["video_count"], 2)
        self.assertEqual(st["pending_count"], 2)

    def test_save_processed_merges_disk(self):
        self.log.write_text(json.dumps(["elsewhere.mp4"]))
        watcher._save_processed({"mine.mp4"})
        self.assertEqual(self._logged(), {"elsewhere.mp4", "mine.mp4"})
        self.assertFalse(self.log.with_name(self.log.name + ".tmp").exists())


if __name__ == "__main__":
    unittest.main()
