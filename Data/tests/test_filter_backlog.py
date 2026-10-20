"""Targeted tests for READY `bolt filter-backlog` (Filter_Backlog + scripts/Filter_Backlog.py).

Temp clip folders + temp queue files only — never touches real media/clips or Data/ queues.
Scores come from synthetic detector sidecars, so no audio analysis runs.
"""

import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[2]
for _p in [_repo_root / "Core", _repo_root / "scripts"]:
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import importlib.util
import json
import os
import tempfile
import unittest

_cwd = os.getcwd()
_spec = importlib.util.spec_from_file_location(
    "fb_engine_under_test", _repo_root / "scripts" / "Filter_Backlog.py"
)
eng = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eng)
os.chdir(_cwd)

from modules import Filter_Backlog as fb  # noqa: E402

CFG = {"game": "Filter Backlog Test Game"}


def _clip(folder: Path, stem: str, score: float, *, source="detector", extras=(".jpg",)):
    (folder / f"{stem}.mp4").write_bytes(b"\x00" * 1024)
    (folder / f"{stem}.json").write_text(
        json.dumps({"highlight_score": score, "score_source": source, "trigger": "audio_spike"})
    )
    for ext in extras:
        (folder / f"{stem}{ext}").write_bytes(b"x")


class FilterBacklogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.clips = self.root / "clips"
        self.clips.mkdir()
        self.queue = self.root / "ready_to_post.json"
        self.queue.write_text(json.dumps({"clips": []}))
        # audio_spike: score*0.5 + trigger 5  → 80 → 45, 20 → 15
        _clip(self.clips, "g_clip01_audio_spike_10", 80, extras=(".jpg", ".srt"))
        _clip(self.clips, "g_clip02_audio_spike_20", 20, extras=(".jpg", ".srt"))
        _clip(self.clips, "g_clip02_audio_spike_200", 20)  # stem-prefix sibling

    def tearDown(self):
        self.tmp.cleanup()

    def run_filter(self, **kw):
        kw.setdefault("threshold", 25)
        kw.setdefault("queue_files", (self.queue,))
        return eng.run_filter(clips_dir=self.clips, config=dict(CFG), **kw)

    def test_dry_run_moves_nothing(self):
        res = self.run_filter(dry_run=True)
        self.assertEqual(len(res["kept"]), 1)
        self.assertEqual(len(res["moved"]), 2)
        self.assertFalse((self.clips / "_low_score").exists())
        self.assertTrue((self.clips / "g_clip02_audio_spike_20.mp4").exists())

    def test_real_run_moves_clip_with_all_companions_and_logs(self):
        res = self.run_filter()
        low = self.clips / "_low_score"
        moved = sorted(p.name for p in low.iterdir() if p.name != "_moves.jsonl")
        self.assertIn("g_clip02_audio_spike_20.srt", moved)
        self.assertIn("g_clip02_audio_spike_20.jpg", moved)
        self.assertIn("g_clip02_audio_spike_20.json", moved)
        self.assertIn("g_clip02_audio_spike_200.mp4", moved)
        self.assertEqual(len(res["moved"]), 2)
        self.assertTrue((self.clips / "g_clip01_audio_spike_10.srt").exists())
        log = [json.loads(l) for l in (low / "_moves.jsonl").read_text().splitlines()]
        self.assertEqual({r["action"] for r in log}, {"move"})
        side = json.loads((self.clips / "g_clip01_audio_spike_10.json").read_text())
        self.assertEqual(side.get("ranked_score"), 45.0)

    def test_queued_clip_is_kept_unless_include_queued(self):
        self.queue.write_text(json.dumps({"clips": [
            {"status": "ready", "clip_path": "/x/vertical_clips/g_clip02_audio_spike_20_tiktok.mp4"},
            {"status": "posted", "clip_path": "/x/g_clip02_audio_spike_200_tiktok.mp4"},
        ]}))
        res = self.run_filter()
        skipped = {r["stem"] for r in res["skipped"]}
        moved = {r["stem"] for r in res["moved"]}
        self.assertEqual(skipped, {"g_clip02_audio_spike_20"})  # boundary: _200 not matched
        self.assertEqual(moved, {"g_clip02_audio_spike_200"})  # posted item doesn't protect
        res2 = self.run_filter(include_queued=True)
        self.assertEqual({r["stem"] for r in res2["moved"]}, {"g_clip02_audio_spike_20"})

    def test_multi_platform_item_all_posted_does_not_protect(self):
        mpq = self.root / "multi_platform_queue.json"
        mpq.write_text(json.dumps({"items": [{"platforms": [
            {"status": "posted", "clip_path": "/x/g_clip02_audio_spike_20.mp4"}]}]}))
        res = self.run_filter(queue_files=(mpq,))
        self.assertIn("g_clip02_audio_spike_20", {r["stem"] for r in res["moved"]})

    def test_unscored_clip_is_kept(self):
        _clip(self.clips, "g_clip03_audio_spike_30", 0, source="none")
        res = self.run_filter()
        self.assertIn("g_clip03_audio_spike_30", {r["stem"] for r in res["skipped"]})
        self.assertTrue((self.clips / "g_clip03_audio_spike_30.mp4").exists())

    def test_never_overwrites_existing_low_score_file(self):
        low = self.clips / "_low_score"
        low.mkdir()
        (low / "g_clip02_audio_spike_20.jpg").write_bytes(b"older")
        res = self.run_filter()
        self.assertIn("g_clip02_audio_spike_20", {r["stem"] for r in res["skipped"]})
        self.assertEqual((low / "g_clip02_audio_spike_20.jpg").read_bytes(), b"older")
        self.assertTrue((self.clips / "g_clip02_audio_spike_20.mp4").exists())

    def test_restore_by_name_and_all(self):
        self.run_filter()
        res = eng.run_restore(["g_clip02_audio_spike_20.mp4"], clips_dir=self.clips)
        self.assertTrue(res["ok"])
        self.assertTrue((self.clips / "g_clip02_audio_spike_20.srt").exists())
        self.assertEqual(eng.low_score_stems(self.clips), ["g_clip02_audio_spike_200"])
        res = eng.run_restore([], restore_all=True, clips_dir=self.clips)
        self.assertEqual(eng.low_score_stems(self.clips), [])
        self.assertTrue((self.clips / "_low_score" / "_moves.jsonl").exists())
        bad = eng.run_restore(["nope"], clips_dir=self.clips)
        self.assertFalse(bad["ok"])

    def test_threshold_sources(self):
        self.assertEqual(eng.resolve_threshold("x", 33, {}), (33.0, "--threshold"))
        thr, src = eng.resolve_threshold("x", None, {"min_clip_score": 27})
        self.assertEqual(thr, 27.0)
        self.assertIn("config", src)
        thr, src = eng.resolve_threshold("league of legends", None, {})
        self.assertIn(src, ("game profile (builtin)", "game profile (override)"))

    def test_empty_folder(self):
        empty = self.root / "empty"
        empty.mkdir()
        res = eng.run_filter(clips_dir=empty, threshold=25, config=dict(CFG), queue_files=())
        self.assertIn("No clips", res["note"])

    def test_wrapper_status_ready(self):
        info = fb.status()
        self.assertEqual(info["readiness"], "READY")
        self.assertIn("ready", info)


if __name__ == "__main__":
    unittest.main()
