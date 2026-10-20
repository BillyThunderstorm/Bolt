"""Targeted tests for READY `bolt clip-dedupe` (Hash_Dedupe + scripts/clip_deduplicator.py).

Temp folders + temp hash cache only — never touches real media or Data/media_hash_db.json.
"""

import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[2]
for _p in [_repo_root / "Core"]:
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from modules import Hash_Dedupe as hd

eng = hd._engine()


class HashDedupeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.media = self.root / "media"
        self.media.mkdir()
        self.db = self.root / "media_hash_db.json"
        (self.media / "a.mp4").write_bytes(b"A" * 4096)
        (self.media / "a_copy.MOV").write_bytes(b"A" * 4096)  # upper-case ext
        (self.media / "b.png").write_bytes(b"B" * 2048)
        (self.media / "._a.mp4").write_bytes(b"A" * 4096)  # AppleDouble — skipped
        (self.media / "notes.json").write_text("{}")  # not media — skipped
        sub = self.media / "sub"
        sub.mkdir()
        (sub / "b_again.png").write_bytes(b"B" * 2048)

    def tearDown(self):
        self.tmp.cleanup()

    def _scan(self, **kw):
        return eng.scan([self.media], db_path=self.db, repo_root=self.root, verbose=False, **kw)

    def test_media_filter(self):
        names = sorted(p.name for p in eng.iter_media(self.media))
        self.assertEqual(names, ["a.mp4", "a_copy.MOV", "b.png", "b_again.png"])

    def test_groups_and_reclaimable(self):
        s = self._scan()
        self.assertEqual(s["files_scanned"], 4)
        self.assertEqual(s["duplicate_groups"], 2)
        self.assertEqual(s["duplicate_files"], 2)
        self.assertEqual(s["reclaimable_bytes"], 4096 + 2048)
        self.assertEqual(s["groups"][0]["size"], 4096)  # biggest first

    def test_read_only_on_media(self):
        before = sorted(p.name for p in self.media.rglob("*"))
        self._scan()
        self.assertEqual(before, sorted(p.name for p in self.media.rglob("*")))

    def test_incremental_cache_reuse(self):
        first = self._scan()
        self.assertEqual(first["hashed"], 4)
        self.assertTrue(self.db.is_file())
        second = self._scan()
        self.assertEqual(second["hashed"], 0)
        self.assertEqual(second["reused"], 4)

    def test_changed_file_rehashed_and_gone_file_pruned(self):
        self._scan()
        (self.media / "a_copy.MOV").write_bytes(b"C" * 5000)
        (self.media / "b.png").unlink()
        s = self._scan()
        self.assertEqual(s["hashed"], 1)
        self.assertEqual(s["pruned"], 1)
        self.assertEqual(s["duplicate_groups"], 0)

    def test_dry_run_does_not_save(self):
        s = self._scan(dry_run=True)
        self.assertFalse(s["db_saved"])
        self.assertFalse(self.db.exists())

    def test_hardlink_not_counted_as_reclaimable(self):
        os.link(self.media / "b.png", self.media / "b_link.png")
        s = self._scan()
        g = [g for g in s["groups"] if g["size"] == 2048][0]
        self.assertEqual(g["count"], 3)
        self.assertEqual(g["reclaimable_bytes"], 2048)  # 2 distinct inodes
        self.assertEqual(len(g["hardlinks"]), 1)

    def test_check_file_for_duplicates(self):
        self._scan()
        db = eng.load_hash_db(self.db)
        dups = eng.check_file_for_duplicates(self.media / "a.mp4", db, repo_root=self.root)
        self.assertEqual(dups, ["media/a_copy.MOV"])
        extra = self.root / "fresh.mp4"
        extra.write_bytes(b"Z" * 10)
        self.assertEqual(eng.check_file_for_duplicates(extra, db, repo_root=self.root), [])

    def test_cache_json_shape(self):
        self._scan()
        d = json.loads(self.db.read_text())
        self.assertEqual(d["version"], eng.DB_VERSION)
        self.assertEqual(len(d["files"]), 4)
        self.assertEqual(d["last_run"]["duplicate_groups"], 2)

    def test_status_and_soft_fail_never_raise(self):
        info = hd.status()
        self.assertIn("readiness", info)
        self.assertEqual(info["soft_fail_prefix"], "Hash dedupe unavailable:")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = hd.main(["bogus-cmd"])
        self.assertEqual(rc, 0)
        self.assertIn("Hash dedupe unavailable:", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
