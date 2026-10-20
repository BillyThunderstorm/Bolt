"""Tests for `bolt error-recovery` (Core/modules/Error_Recovery.py) — temp files only.

Every path (error log, quarantine, moves log) is pointed at a temp folder and
Discord is disabled, so nothing touches real recordings, logs or webhooks.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

_repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_repo_root / "Core"))
sys.path.insert(0, str(_repo_root / "scripts"))

from modules import Error_Recovery as er  # noqa: E402


class ErrorRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.root = root
        self.log = root / "pipeline_errors.jsonl"
        self.qdir = root / "quarantine"
        self.patches = [
            patch.object(er, "_ERROR_LOG", self.log),
            patch.object(er, "_ARCHIVE", root / "archive.jsonl"),
            patch.object(er, "_QUARANTINE", self.qdir),
            patch.object(er, "_tracker", None),
            patch.dict("os.environ", {"ERROR_RECOVERY_DISCORD": ""}),
        ]
        for p in self.patches:
            p.start()
        er.set_context(None)

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        er.set_context(None)
        self.tmp.cleanup()

    def _rows(self):
        return [json.loads(l) for l in self.log.read_text().splitlines() if l.strip()]

    def test_record_error_persists_with_context(self):
        er.set_context("/rec/one.mp4")
        er.record_error("Clip_Generator", "", RuntimeError("ffmpeg died"), quiet=True)
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["stage"], "Clip_Generator")
        self.assertEqual(rows[0]["recording_name"], "one.mp4")
        self.assertEqual(rows[0]["error_type"], "RuntimeError")

    def test_record_error_never_raises(self):
        with patch.object(er, "_append_log", side_effect=OSError("disk full")):
            self.assertIsNone(er.record_error("x", "y", ValueError("z"), quiet=True))

    def test_threshold_does_not_post_discord_by_default(self):
        with patch.object(er, "DISCORD_WEBHOOK", "https://discord.example/hook"), \
                patch("urllib.request.urlopen") as op:
            for _ in range(5):
                er.record_error("Title_Generator", "r.mp4", RuntimeError("llm"), quiet=True)
            op.assert_not_called()

    def test_load_errors_window(self):
        old = (datetime.now().astimezone() - timedelta(days=30)).isoformat()
        utc_new = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        self.log.write_text(
            json.dumps({"time": old, "stage": "old", "error": "e"}) + "\n"
            + json.dumps({"time": utc_new, "stage": "new", "error": "e"}) + "\n"
            + "not json\n"
        )
        self.assertEqual([r["stage"] for r in er.load_errors(7)], ["new"])
        self.assertEqual(len(er.load_errors(None)), 2)

    def test_report_groups_stages_and_flags_unreadable(self):
        bad = self.root / "broken.mp4"
        bad.write_bytes(b"not a video at all" * 100)
        er.record_error("Recording unreadable", str(bad), RuntimeError("won't open"), quiet=True)
        er.record_error("Subtitle_Generator (clip01.mp4)", str(bad), RuntimeError("w"), quiet=True)
        er.record_error("Subtitle_Generator (clip02.mp4)", str(bad), RuntimeError("w"), quiet=True)
        with patch.object(er, "probe_readable",
                          return_value={"exists": True, "readable": False, "duration": None,
                                        "detail": "won't open: Invalid data"}):
            rep = er.build_report(7)
        self.assertEqual(rep["total"], 3)
        self.assertEqual(rep["stages"][0]["stage"], "Subtitle_Generator")
        self.assertEqual(rep["stages"][0]["count"], 2)
        self.assertIn("Captions", rep["stages"][0]["hint"])
        self.assertEqual(rep["unreadable"], [str(bad)])
        self.assertIn("quarantine", rep["recordings"][0]["suggest"])

    def test_probe_readable_on_garbage_and_missing(self):
        bad = self.root / "garbage.mp4"
        bad.write_bytes(b"\x00\x01garbage" * 5000)
        res = er.probe_readable(str(bad))
        if res["detail"] == "no ffprobe to check with":
            self.skipTest("no ffprobe")
        self.assertFalse(res["readable"])
        self.assertNotIn(str(bad), res["detail"])
        gone = er.probe_readable(str(self.root / "nope.mp4"))
        self.assertFalse(gone["exists"])
        self.assertIsNone(gone["readable"])

    def test_probe_readable_on_real_video(self):
        probe = er._ffprobe()
        try:
            sys.path.insert(0, str(_repo_root / "Core" / "modules"))
            from FFmpeg_Bin import working_ffmpeg
            ff = working_ffmpeg()
        except Exception:
            ff = None
        if not (probe and ff):
            self.skipTest("no ffmpeg")
        vid = self.root / "ok.mp4"
        subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=10",
                        "-t", "1", "-pix_fmt", "yuv420p", str(vid)], check=True, timeout=60)
        self.assertTrue(er.probe_readable(str(vid))["readable"])

    def test_quarantine_and_restore_never_overwrite(self):
        src_dir = self.root / "Recordings"
        src_dir.mkdir()
        f = src_dir / "bad.mp4"
        f.write_bytes(b"x" * 10)
        self.assertTrue(er.quarantine_file(str(f), dry_run=True)["ok"])
        self.assertTrue(f.exists())
        res = er.quarantine_file(str(f), reason="test")
        self.assertTrue(res["ok"], res)
        self.assertFalse(f.exists())
        self.assertTrue((self.qdir / "bad.mp4").exists())
        # a second file with the same name is refused, not overwritten
        f.write_bytes(b"y" * 10)
        res2 = er.quarantine_file(str(f))
        self.assertFalse(res2["ok"])
        self.assertIn("not overwriting", res2["error"])
        # restore refuses while the original spot is taken
        r = er.restore_files(["bad.mp4"])
        self.assertEqual(r["restored"], [])
        f.unlink()
        r = er.restore_files(all_files=True)
        self.assertEqual(len(r["restored"]), 1)
        self.assertEqual(f.read_bytes(), b"x" * 10)
        self.assertEqual(er._quarantine_count(), 0)  # _moves.jsonl not counted

    def test_quarantine_missing_file_soft_fails(self):
        res = er.quarantine_file(str(self.root / "missing.mp4"))
        self.assertFalse(res["ok"])
        self.assertTrue(res["error"].startswith(er._SOFT))

    def test_clear_archives(self):
        er.record_error("a", "b", RuntimeError("c"), quiet=True)
        res = er.clear_log()
        self.assertTrue(res["ok"])
        self.assertEqual(res["archived"], 1)
        self.assertFalse(self.log.exists())
        self.assertEqual(er.load_errors(None), [])

    def test_status_ready_and_wired(self):
        st = er.status()
        self.assertTrue(st["wired_into_pipeline"])
        self.assertEqual(st["readiness"], "READY")
        self.assertEqual(st["errors_last_7_days"], 0)

    def test_notifier_notify_error_logs_once_without_discord(self):
        from modules import notifier

        er.set_context("/rec/two.mp4")
        with patch.object(notifier, "_discord_webhooks", return_value=[]), \
                patch.object(notifier, "_write_log"), \
                patch.object(notifier, "_send_discord") as sd:
            notifier.notify_error("Highlight_Detector", RuntimeError("boom"), recoverable=False)
            sd.assert_not_called()
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["stage"], "Highlight_Detector")
        self.assertEqual(rows[0]["recording_name"], "two.mp4")

    def test_notifier_posts_discord_once_per_error(self):
        from modules import notifier

        with patch.object(notifier, "_discord_webhooks", return_value=["https://x"]), \
                patch.object(notifier, "_write_log"), \
                patch.object(notifier, "_send_discord") as sd:
            notifier.notify_error("Clip_Generator", RuntimeError("boom"))
        self.assertEqual(sd.call_count, 1)

    def test_folder_watch_marks_unreadable_as_failed(self):
        from modules import Folder_Watch as fw

        class W:
            def mark_processed(self, name):
                self.name = name

        w = W()
        row = fw._process_one(w, self.root / "bad.mp4", lambda p: "unreadable")
        self.assertFalse(row["ok"])
        self.assertIn("error-recovery", row["error"])
        self.assertEqual(w.name, "bad.mp4")


if __name__ == "__main__":
    unittest.main()
