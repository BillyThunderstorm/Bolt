"""Tests for Core/modules/Voice_Checklist.py (bolt checklist).

Everything runs on temp progress/task files with fake verify functions.
No mic, no network, no OBS, no Twitch, no config writes.
"""

import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from modules import Voice_Checklist as VC


def _tasks(ok_map):
    rows = []
    for tid, ok in ok_map.items():
        def fn(ok=ok, tid=tid):
            return ok, f"{tid} {'fine' if ok else 'broken'}"
        rows.append({"id": tid, "task": f"Task {tid}", "keywords": [tid, f"{tid} ready"],
                     "done": False, "verify": fn})
    return rows


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.p1 = patch.object(VC, "PROGRESS_FILE", self.tmp / "logs" / "checklist_progress.json")
        self.p2 = patch.object(VC, "TASKS_FILE", self.tmp / "session_tasks.json")
        self.p1.start(); self.p2.start()
        self._out = patch("sys.stdout", new_callable=io.StringIO)
        self.out = self._out.start()

    def tearDown(self):
        self._out.stop(); self.p1.stop(); self.p2.stop()


class TestMatching(Base):
    def test_keyword_id_and_name_prefix(self):
        cl = VC.VoiceChecklist(tasks=_tasks({"obs": True, "title": True}), use_voice=False)
        self.assertEqual(cl._match_task("OBS is good"), "obs")
        self.assertEqual(cl._match_task("title"), "title")
        cl2 = VC.VoiceChecklist(tasks=[dict(t) for t in VC.DEFAULT_TASKS], use_voice=False)
        self.assertEqual(cl2._match_task("obs_setup"), "obs_setup")
        self.assertEqual(cl2._match_task("announce"), "socials")
        self.assertIsNone(cl2._match_task("banana"))
        self.assertIsNone(cl2._match_task("ok done"))  # weak-only words never latch on... unless 2+

    def test_done_tasks_not_rematched(self):
        cl = VC.VoiceChecklist(tasks=_tasks({"obs": True}), use_voice=False)
        cl._verify_task("obs")
        self.assertIsNone(cl._match_task("obs"))


class TestVerify(Base):
    def test_failed_check_ticks_and_is_remembered(self):
        cl = VC.VoiceChecklist(tasks=_tasks({"obs": False, "title": True}), use_voice=False)
        self.assertTrue(cl._verify_task("obs"))
        t = cl.tasks[0]
        self.assertTrue(t["done"]); self.assertFalse(t["verified"]); self.assertIn("broken", t["note"])
        self.assertEqual([x["id"] for x in cl.needs_attention()], ["obs"])
        saved = json.loads(VC.PROGRESS_FILE.read_text())
        self.assertEqual(saved["done"], 1)
        self.assertNotIn("verify", saved["tasks"][0])

    def test_slow_check_times_out(self):
        def slow():
            time.sleep(3)
            return True, "late"
        ok, msg = VC._run_verify(slow, timeout=0.3)
        self.assertFalse(ok); self.assertIn("timed out", msg)

    def test_raising_check(self):
        def boom():
            raise RuntimeError("nope")
        ok, msg = VC._run_verify(boom, timeout=2)
        self.assertFalse(ok); self.assertIn("nope", msg)


class TestResume(Base):
    def _write(self, done_ids, *, age_h=0.0, completed=False):
        VC.PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        VC.PROGRESS_FILE.write_text(json.dumps({
            "saved_epoch": int(time.time() - age_h * 3600), "completed": completed,
            "tasks": [{"id": i, "done": True, "verified": True, "note": "x"} for i in done_ids]}))

    def test_resume_recent_unfinished(self):
        self._write(["obs"])
        cl = VC.VoiceChecklist(tasks=_tasks({"obs": True, "title": True}), use_voice=False, resume=True)
        self.assertEqual(cl.resumed, 1)
        self.assertTrue(cl.tasks[0]["done"]); self.assertFalse(cl.tasks[1]["done"])

    def test_no_resume_when_old_or_completed_or_flag_off(self):
        self._write(["obs"], age_h=7)
        self.assertEqual(VC.VoiceChecklist(tasks=_tasks({"obs": True}), use_voice=False, resume=True).resumed, 0)
        self._write(["obs"], completed=True)
        self.assertEqual(VC.VoiceChecklist(tasks=_tasks({"obs": True}), use_voice=False, resume=True).resumed, 0)
        self._write(["obs"])
        self.assertEqual(VC.VoiceChecklist(tasks=_tasks({"obs": True}), use_voice=False).resumed, 0)


class TestRunTyped(Base):
    def _run_with_input(self, cl, text, timeout_min=1):
        r, w = os.pipe()
        rf = os.fdopen(r, "r")
        os.write(w, text.encode()); os.close(w)
        with patch("sys.stdin", rf):
            res = cl.run(timeout_minutes=timeout_min)
        rf.close()
        return res

    def test_typed_run_completes(self):
        cl = VC.VoiceChecklist(tasks=_tasks({"obs": True, "title": False}), use_voice=False)
        res = self._run_with_input(cl, "obs\ntitle\n")
        self.assertTrue(all(t["done"] for t in res))
        saved = json.loads(VC.PROGRESS_FILE.read_text())
        self.assertTrue(saved["completed"])
        self.assertIn("Needs a look", self.out.getvalue())

    def test_skip_saves_partial(self):
        cl = VC.VoiceChecklist(tasks=_tasks({"obs": True, "title": True}), use_voice=False)
        self._run_with_input(cl, "obs\nskip\n")
        saved = json.loads(VC.PROGRESS_FILE.read_text())
        self.assertEqual(saved["done"], 1); self.assertFalse(saved["completed"])
        self.assertIn("skipped", self.out.getvalue())

    def test_eof_ends_typed_run(self):
        cl = VC.VoiceChecklist(tasks=_tasks({"obs": True}), use_voice=False)
        t0 = time.time()
        self._run_with_input(cl, "")
        self.assertLess(time.time() - t0, 5)


class TestCli(Base):
    def test_status_ready_and_check_report(self):
        info = VC.status()
        self.assertTrue(info["ready"]); self.assertEqual(info["readiness"], "READY")
        with patch.object(VC, "DEFAULT_TASKS", _tasks({"a": True, "b": False})):
            rows = VC.check_all()
        self.assertEqual([r["ok"] for r in rows], [True, False])

    def test_check_command_routes_to_check(self):
        with patch.object(VC, "check_all", return_value=[{"id": "a", "task": "A", "ok": True, "message": "m"}]):
            VC.main(["check"])
        self.assertIn("1/1 look good", self.out.getvalue())

    def test_reset_and_non_tty_run(self):
        VC.PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        VC.PROGRESS_FILE.write_text("{}")
        VC.main(["reset"])
        self.assertFalse(VC.PROGRESS_FILE.exists())
        err = io.StringIO()
        with patch("sys.stdin", io.StringIO("")), patch("sys.stderr", err):
            self.assertEqual(VC.main(["run", "--keyboard"]), 0)
        self.assertIn("Checklist unavailable:", err.getvalue())


if __name__ == "__main__":
    unittest.main()
