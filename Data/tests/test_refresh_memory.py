"""Targeted tests for READY `bolt refresh-memory` (Refresh_Memory + atomic index write).

Temp files only — never touches the real Data/memory_index.json.
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
import types
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from modules import Memory_Index as mi
from modules import Refresh_Memory as rm


def _fake_mi(entries, write_count=None):
    """Stand-in Memory_Index that writes a small index to out_file."""

    def refresh_memory_index(project_root=None, out_file=None):
        n = len(entries) if write_count is None else write_count
        payload = {
            "generated_at": "2099-01-01T00:00:00",
            "version": 2,
            "entry_count": len(entries),
            "entries": [{"id": str(i)} for i in range(n)],
        }
        Path(out_file).write_text(json.dumps(payload), encoding="utf-8")
        return payload

    return types.SimpleNamespace(
        build_memory_entries=lambda root: list(entries),
        refresh_memory_index=refresh_memory_index,
    )


class RefreshMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.index = self.dir / "memory_index.json"
        self._p = patch.object(rm, "_INDEX", self.index)
        self._p.start()

    def tearDown(self):
        self._p.stop()
        self.tmp.cleanup()

    def test_status_is_ready_with_freshness(self):
        st = rm.status()
        self.assertEqual(st["readiness"], "READY")
        self.assertTrue(st["ready"])
        self.assertFalse(st["partial"])
        self.assertTrue(st["index_stale"])  # temp index missing
        self.assertEqual(st["index_stale_reason"], "index missing")
        for key in ("newest_source", "newest_source_at"):
            self.assertIn(key, st)

    def test_run_writes_and_verifies(self):
        with patch.object(rm, "_load_memory_mod", return_value=_fake_mi([1, 2, 3])):
            out = rm.try_run([])
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["entry_count"], 3)
        self.assertIsNone(out["before_count"])
        self.assertIn("(new index)", out["report"])
        self.assertIsNotNone(out["elapsed_s"])
        self.assertEqual(json.loads(self.index.read_text())["entry_count"], 3)

    def test_run_reports_previous_count(self):
        self.index.write_text(
            json.dumps({"generated_at": "2000-01-01T00:00:00", "entry_count": 1, "entries": [{}]})
        )
        with patch.object(rm, "_load_memory_mod", return_value=_fake_mi([1, 2])):
            out = rm.try_run([])
        self.assertTrue(out["ok"], out)
        self.assertIn("(was 1)", out["report"])

    def test_verify_mismatch_soft_fails(self):
        with patch.object(rm, "_load_memory_mod", return_value=_fake_mi([1, 2, 3], write_count=1)):
            out = rm.try_run([])
        self.assertFalse(out["ok"])
        self.assertTrue(out["error"].startswith("Memory refresh unavailable:"))
        self.assertIn("mismatch", out["error"])

    def test_empty_sources_note(self):
        with patch.object(rm, "_load_memory_mod", return_value=_fake_mi([])):
            out = rm.try_run([])
        self.assertTrue(out["ok"], out)
        self.assertIn("valid empty index", out["report"])

    def test_if_stale_skips_when_fresh(self):
        fake = _fake_mi([1])
        with patch.object(rm, "_freshness", return_value={"stale": False, "reason": "up to date",
                                                          "newest_source": "", "newest_source_at": ""}):
            self.index.write_text(json.dumps({"generated_at": "2099-01-01T00:00:00",
                                              "entry_count": 5, "entries": [{}] * 5}))
            with patch.object(rm, "_load_memory_mod", return_value=fake):
                out = rm.try_run(["--if-stale"])
        self.assertTrue(out["ok"])
        self.assertTrue(out["skipped"])
        self.assertEqual(json.loads(self.index.read_text())["entry_count"], 5)

    def test_if_stale_rebuilds_when_stale(self):
        with patch.object(rm, "_load_memory_mod", return_value=_fake_mi([1, 2])):
            out = rm.try_run(["--if-stale"])  # temp index missing -> stale
        self.assertTrue(out["ok"])
        self.assertFalse(out["skipped"])
        self.assertEqual(out["entry_count"], 2)

    def test_dry_run_does_not_write(self):
        with patch.object(rm, "_load_memory_mod", return_value=_fake_mi([1, 2, 3, 4])):
            out = rm.try_run(["--dry-run"])
        self.assertTrue(out["ok"])
        self.assertEqual(out["entry_count"], 4)
        self.assertFalse(self.index.exists())

    def test_cli_run_json_exit_zero(self):
        buf = io.StringIO()
        with patch.object(rm, "_load_memory_mod", return_value=_fake_mi([1])), redirect_stdout(buf):
            code = rm.main(["run", "--json"])
        self.assertEqual(code, 0)
        data = json.loads(buf.getvalue())
        self.assertTrue(data["ok"])
        self.assertEqual(data["entry_count"], 1)


class AtomicIndexWriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "memory").mkdir()
        (self.root / "memory" / "note.md").write_text("# Note\n\n## Clips\nHonest clips.", encoding="utf-8")
        self.out = self.root / "memory_index.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_atomic_write_leaves_no_temp(self):
        with patch.object(mi, "MEMORY_DIR", self.root / "memory"):
            payload = mi.refresh_memory_index(project_root=self.root, out_file=self.out)
        self.assertGreaterEqual(payload["entry_count"], 1)
        self.assertEqual(json.loads(self.out.read_text())["entry_count"], payload["entry_count"])
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.endswith(".tmp")], [])

    def test_failed_swap_keeps_old_index(self):
        self.out.write_text('{"entry_count": 7, "entries": []}', encoding="utf-8")
        with patch.object(mi, "MEMORY_DIR", self.root / "memory"), \
                patch.object(mi.os, "replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                mi.refresh_memory_index(project_root=self.root, out_file=self.out)
        self.assertEqual(json.loads(self.out.read_text())["entry_count"], 7)
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.endswith(".tmp")], [])


if __name__ == "__main__":
    unittest.main()
