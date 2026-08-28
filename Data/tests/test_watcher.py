"""Tests for Core/modules/Watcher processed-log helpers."""

from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

_repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_repo_root / "Core"))

from modules import Watcher as watcher  # noqa: E402


class WatcherProcessedLogTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.folder = self.root / "Recordings"
        self.folder.mkdir()
        self.log = self.root / "processed_recordings.json"
        self.patches = [
            patch.object(watcher, "PROCESSED_LOG", self.log),
            patch.object(watcher, "RECORDINGS_FOLDER", str(self.folder)),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tempdir.cleanup()

    def _touch(self, name: str, age: float = 0.0) -> Path:
        path = self.folder / name
        path.write_bytes(b"x" * 16)
        if age:
            now = time.time()
            os_stat_time = now - age
            import os

            os.utime(path, (os_stat_time, os_stat_time))
        return path

    def test_pending_is_newest_unprocessed(self):
        old = self._touch("2026-08-01.mp4", age=1000)
        new = self._touch("2026-08-20.mp4", age=10)
        pending = watcher.list_pending_recordings(self.folder)
        self.assertEqual([p.name for p in pending], [new.name, old.name])

    def test_skips_processed_and_same_stem_sibling(self):
        self._touch("Replay_2026-08-09.mp4")
        self._touch("Replay_2026-08-09.mov")
        watcher.mark_processed("Replay_2026-08-09.mp4")
        pending = watcher.list_pending_recordings(self.folder)
        self.assertEqual(pending, [])
        self.assertTrue(watcher.is_processed("Replay_2026-08-09.mov"))

    def test_collapses_stem_to_preferred_mp4(self):
        self._touch("session.mov")
        mp4 = self._touch("session.mp4")
        pending = watcher.list_pending_recordings(self.folder)
        self.assertEqual([p.resolve() for p in pending], [mp4.resolve()])

    def test_mark_processed_is_idempotent(self):
        watcher.mark_processed("a.mp4")
        watcher.mark_processed("a.mp4")
        data = json.loads(self.log.read_text(encoding="utf-8"))
        self.assertEqual(data, ["a.mp4"])


if __name__ == "__main__":
    unittest.main()
