"""Targeted tests for `bolt performance` (scripts/performance_baseline.py + Performance_Baseline).

Everything writes to temp folders: the real logs/performance/ is never touched.
The one real engine run is trimmed to tiny module/library lists so it takes ~1 s.
"""

import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[2]
for _p in [_repo_root, _repo_root / "Core", _repo_root / "scripts"]:
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import performance_baseline as pb
from modules import Performance_Baseline as PB

_CWD = os.getcwd()


def _v2(ts, items, startup=0.02):
    return {
        "timestamp": ts, "method": pb.METHOD, "system": {"disk_free_gb": 100.0},
        "items": [{"name": n, "seconds": s} for n, s in items],
        "summary": {"bolt_startup_sec": startup, "verdict": "All good"},
    }


class CompareTests(unittest.TestCase):
    def test_no_previous(self):
        c = pb.compare(_v2("t", [("a", 0.1)]), None)
        self.assertFalse(c["comparable"])
        self.assertIn("No earlier baseline", c["note"])

    def test_old_method_not_comparable(self):
        old = {"timestamp": "x", "system": {"disk_free_gb": 50.0},
               "module_imports": [{"module": "a", "import_time_sec": 0.0}]}
        c = pb.compare(_v2("t", [("a", 0.1)]), old)
        self.assertFalse(c["comparable"])
        self.assertIn("old in-process", c["note"])
        self.assertEqual(c["disk_free_change_gb"], 50.0)

    def test_slower_needs_both_seconds_and_percent(self):
        prev = _v2("p", [("big", 0.20), ("tiny", 0.004), ("same", 0.30), ("quick", 0.50)])
        cur = _v2("c", [("big", 0.40), ("tiny", 0.010), ("same", 0.32), ("quick", 0.20), ("fresh", 0.1)])
        c = pb.compare(cur, prev)
        self.assertTrue(c["comparable"])
        self.assertEqual([r["name"] for r in c["slower"]], ["big"])   # tiny: +150% but only 6 ms
        self.assertEqual([r["name"] for r in c["faster"]], ["quick"])
        self.assertEqual(c["new"], ["fresh"])
        self.assertIn("1 item(s) got noticeably slower", c["note"])


class EngineRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.results = Path(self.tmp.name) / "performance"

    def tearDown(self):
        os.chdir(_CWD)
        self.tmp.cleanup()

    def _run(self, **kw):
        with patch.object(pb, "RESULTS_DIR", self.results), \
             patch.object(pb, "CORE_MODULES", ["modules.Config_Loader", "modules.Does_Not_Exist"]), \
             patch.object(pb, "LIBRARIES", ["json", "no_such_lib_xyz"]):
            return pb.run_baseline(repeats=1, quiet=True, **kw)

    def test_real_run_saves_json_and_compares(self):
        first = self._run()
        saved = Path(first["saved_to"])
        self.assertTrue(saved.is_file())
        data = json.loads(saved.read_text())
        self.assertEqual(data["method"], pb.METHOD)
        by = {i["name"]: i for i in data["items"]}
        self.assertIsNotNone(by["modules.Config_Loader"]["seconds"])
        self.assertTrue(by["modules.Does_Not_Exist"]["missing"])
        self.assertTrue(by["no_such_lib_xyz"]["missing"])
        self.assertIsNone(by["no_such_lib_xyz"]["error"])
        self.assertIsNotNone(data["summary"]["bolt_startup_sec"])
        self.assertEqual(data["summary"]["error_count"], 0)
        self.assertIn("Verdict:", data["report"])
        self.assertIn("not installed (optional)", data["report"])
        # second run compares against the first (new method)
        # (may land in the same second: must still compare and not overwrite)
        second = self._run()
        self.assertTrue(second["comparison"]["comparable"])
        self.assertEqual(second["comparison"]["previous"], str(saved))
        self.assertNotEqual(second["saved_to"], str(saved))
        self.assertEqual(len(list(self.results.glob("baseline_*.json"))), 2)
        third = self._run(save=False)
        self.assertEqual(third["comparison"]["previous"], second["saved_to"])


class ModuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.results = Path(self.tmp.name) / "performance"
        self.results.mkdir()
        (self.results / "baseline_20260101_000000.json").write_text(json.dumps(
            {"timestamp": "2026-01-01T00:00:00", "module_imports": []}))
        (self.results / "baseline_20261020_120000.json").write_text(json.dumps(
            dict(_v2("2026-10-20T12:00:00", [("a", 0.1)]), report="REPORT TEXT")))
        self.p = patch.object(PB, "_RESULTS", self.results)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def test_status_ready_and_last(self):
        info = PB.status()
        self.assertTrue(info["ready"])
        self.assertEqual(info["readiness"], "READY")
        self.assertEqual(info["recent_count"], 2)
        self.assertEqual(info["last_baseline"]["name"], "baseline_20261020_120000.json")
        self.assertIn("last: Bolt startup 20 ms", info["hint"])

    def test_status_missing_engine_soft_fails(self):
        with patch.object(PB, "_SCRIPT", Path(self.tmp.name) / "nope.py"):
            info = PB.status()
        self.assertFalse(info["ready"])
        self.assertTrue(info["error"].startswith("Baseline unavailable:"))

    def test_last_and_list_print(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(PB.main(["last"]), 0)
            self.assertEqual(PB.main(["list"]), 0)
        out = buf.getvalue()
        self.assertIn("REPORT TEXT", out)
        self.assertIn("old method", out)

    def test_dry_run_and_args(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            PB.main(["run", "--dry-run", "--json", "--repeats", "2", "--no-save"])
        data = json.loads(buf.getvalue())
        self.assertTrue(data["dry_run"])
        self.assertEqual(data["would_run"][1:], ["--repeats", "2", "--no-save"])


if __name__ == "__main__":
    unittest.main()
