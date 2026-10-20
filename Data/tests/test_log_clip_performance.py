"""Targeted tests for `bolt log-perf` (scripts/log_clip_performance.py + Log_Perf).

Everything runs on temp files: no real outcomes, clip history, decision model
or memory index is touched.
"""

import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[2]
for _p in [_repo_root, _repo_root / "Core", _repo_root / "3rd_Party" / "colabs"]:
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

import json
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from scripts import log_clip_performance as lcp


class _TempRepo(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "Data").mkdir()
        (self.root / "Core").mkdir()
        self.clips = self.root / "media" / "clips"
        self.vertical = self.root / "media" / "vertical_clips"
        self.clips.mkdir(parents=True)
        self.vertical.mkdir(parents=True)
        self.outcomes = self.root / "Data" / "performance_outcomes.jsonl"
        self.history = self.root / "Data" / "clip_history.json"
        self.queue = self.root / "Data" / "ready_to_post.json"
        self.mqueue = self.root / "Data" / "multi_platform_queue.json"
        self.config = self.root / "Core" / "config.json"
        self.config.write_text(json.dumps({"game": "Hades 2"}))

        # A cut clip with its sidecar, plus its vertical copy queued for posting.
        stem = "2026-10-18_vod_clip02_audio_spike_182"
        (self.clips / f"{stem}.mp4").write_bytes(b"x")
        (self.clips / f"{stem}.json").write_text(json.dumps({"trigger": "audio_spike", "game": "God of War"}))
        vert = self.vertical / f"{stem}_tiktok.mp4"
        vert.write_bytes(b"x")
        (self.vertical / "Hands.mp4").write_bytes(b"x")
        self.queue.write_text(json.dumps({"clips": [
            {"id": "671f95cd", "clip_path": str(vert), "title": "Big spike", "status": "ready"},
            {"id": "929da53e", "clip_path": str(self.vertical / "Hands.mp4"), "title": "Hands", "status": "posted"},
        ]}))
        self.mqueue.write_text(json.dumps({"items": [
            {"queue_id": "671f95cd", "clip_name": "", "original_clip_path": ""},
        ]}))

        self.stack = ExitStack()
        for name, val in {
            "PERFORMANCE_OUTCOMES_FILE": self.outcomes,
            "HISTORY_FILE": self.history,
            "QUEUE_FILE": self.queue,
            "MULTI_QUEUE_FILE": self.mqueue,
            "MEDIA_DIR": self.root / "media",
            "CLIPS_DIR": self.clips,
            "CONFIG_FILE": self.config,
            "REPO_ROOT": self.root,
        }.items():
            self.stack.enter_context(patch.object(lcp, name, val))
        self.update_hist = self.stack.enter_context(
            patch.object(lcp, "update_historical_performance", side_effect=self._fake_update))
        self.engine_cls = self.stack.enter_context(patch("modules.Think_Learn_Decide.ThinkLearnDecideEngine"))
        self.refresh = self.stack.enter_context(patch("modules.Memory_Index.refresh_memory_index"))

    def _fake_update(self, game, trigger, views, likes=0):
        h = json.loads(self.history.read_text()) if self.history.exists() else {}
        e = h.setdefault(game, {}).setdefault(trigger, {"total_clips": 0, "total_views": 0,
                                                         "total_likes": 0, "avg_views": 0, "observations": []})
        e["total_clips"] += 1
        e["total_views"] += views
        e["total_likes"] += likes
        e["avg_views"] = e["total_views"] // e["total_clips"]
        e["observations"].append({"at": "t", "views": views, "likes": likes})
        self.history.write_text(json.dumps(h))

    def tearDown(self):
        self.stack.close()
        self.tempdir.cleanup()

    def rows(self):
        return [json.loads(l) for l in self.outcomes.read_text().splitlines() if l.strip()]


class LogClipPerformanceTests(_TempRepo):
    def test_record_learning_outcome_writes_jsonl_and_learns(self):
        outcome = lcp._record_learning_outcome(
            game="Marvel Rivals", trigger="multi_kill", views=1200, likes=80,
            clip_path="clip.mp4", platform="TikTok", note="good hook",
        )
        self.assertTrue(outcome["success"])
        saved = self.rows()[0]
        self.assertEqual(saved["trigger"], "multi_kill")
        self.assertEqual(saved["source"], "manual")
        self.assertNotIn("action", saved)
        self.engine_cls.return_value.learn_from_outcome.assert_called_once()
        self.refresh.assert_called_once()

    def test_success_threshold_accepts_strong_like_rate(self):
        self.assertTrue(lcp._is_success(100, 8))
        self.assertFalse(lcp._is_success(100, 1))

    def test_queue_id_fills_trigger_game_title_from_sidecar(self):
        e = lcp.log_clip(clip="671f95cd", views="2.5k", likes="1,200")
        self.assertEqual((e["trigger"], e["game"], e["views"], e["likes"]), ("audio_spike", "God of War", 2500, 1200))
        self.assertEqual(e["title"], "Big spike")
        self.assertEqual(e["game_source"], "clip")
        self.assertEqual(self.rows()[0]["queue_id"], "671f95cd")

    def test_filename_resolves_and_platform_normalised(self):
        e = lcp.log_clip(clip="2026-10-18_vod_clip02_audio_spike_182_tiktok.mp4", views=10, platform="ig")
        self.assertEqual(e["queue_id"], "671f95cd")
        self.assertEqual(e["platform"], "Instagram")

    def test_relog_updates_row_and_history_without_double_count(self):
        lcp.log_clip(clip="671f95cd", views=1000, likes=50, note="first")
        lcp.log_clip(clip="671f95cd", views=3000, likes=150)
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["views"], 3000)
        self.assertEqual(rows[0]["note"], "first")
        h = json.loads(self.history.read_text())["God of War"]["audio_spike"]
        self.assertEqual((h["total_clips"], h["total_views"], h["total_likes"]), (1, 3000, 150))
        self.assertEqual([o["views"] for o in h["observations"]], [3000])
        self.engine_cls.return_value.learn_from_outcome.assert_called_once()

    def test_other_platform_is_separate_row(self):
        lcp.log_clip(clip="671f95cd", views=1000)
        lcp.log_clip(clip="671f95cd", views=40, platform="x")
        self.assertEqual([r["platform"] for r in self.rows()], ["TikTok", "X"])

    def test_relog_keeps_previous_game_when_clip_has_none(self):
        self.outcomes.write_text(json.dumps({
            "timestamp": "2026-08-16T08:24:29", "game": "007 First Light", "trigger": "unknown",
            "views": 2011, "likes": 0, "platform": "TikTok", "queue_id": "929da53e",
            "clip_path": str(self.vertical / "Hands.mp4")}) + "\n")
        e = lcp.log_clip(clip="Hands", views=2400)
        self.assertEqual(e["action"], "updated")
        self.assertEqual(e["game"], "007 First Light")
        self.assertEqual(self.rows()[0]["first_logged_at"], "2026-08-16T08:24:29")

    def test_api_rows_are_never_overwritten(self):
        api = {"timestamp": "2026-08-27T19:00:00", "game": "God of War", "trigger": "audio_spike",
               "views": 5, "platform": "TikTok", "queue_id": "671f95cd", "source": "youtube_api"}
        self.outcomes.write_text(json.dumps(api) + "\n")
        lcp.log_clip(clip="671f95cd", views=900)
        rows = self.rows()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], api)

    def test_dry_run_writes_nothing(self):
        e = lcp.log_clip(clip="671f95cd", views=100, dry_run=True)
        self.assertTrue(e["dry_run"])
        self.assertFalse(self.outcomes.exists())
        self.update_hist.assert_not_called()

    def test_default_game_reads_core_config(self):
        e = lcp.log_clip(trigger="ace", views=5)
        self.assertEqual((e["game"], e["game_source"]), ("Hades 2", "config"))

    def test_bad_input_is_a_clean_error(self):
        for kwargs in ({"trigger": "ace", "views": "-3"}, {"trigger": "ace", "views": "lots"},
                       {"clip": "nope", "views": 3}, {"views": 3}):
            with self.assertRaises(lcp.LogPerfError):
                lcp.log_clip(**kwargs)
        self.assertFalse(self.outcomes.exists())

    def test_cli_exit_codes(self):
        self.assertEqual(lcp.main(["--clip", "671f95cd", "--views", "12", "--dry-run"]), 0)
        self.assertEqual(lcp.main(["--clip", "671f95cd"]), 2)  # missing --views
        with patch("sys.stdin.isatty", return_value=False):
            self.assertEqual(lcp.main([]), 2)  # no terminal → no hang


class LogPerfWrapperTests(unittest.TestCase):
    def test_status_ready_and_probe(self):
        from modules import Log_Perf
        st = Log_Perf.status(probe=True)
        self.assertEqual(st["readiness"], "READY")
        self.assertTrue(st["probe_ok"], st.get("error"))


if __name__ == "__main__":
    unittest.main()
