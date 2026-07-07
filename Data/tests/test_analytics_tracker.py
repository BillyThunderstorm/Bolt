"""Tests for Analytics_Tracker (Tier 2.4).

Verifies:
1. Loads JSONL rows correctly (skips blanks/bad lines).
2. Groups by trigger / game / platform and computes stats.
3. Best-posting-hours buckets rows by hour-of-day from timestamp.
4. Days filter cuts off old rows.
5. Empty data returns a clean summary (no crash).
6. summary() output is JSON-serializable.
"""

import sys
from pathlib import Path
_repo_root = Path(__file__).resolve().parents[2]
for _p in [_repo_root / 'Core']:
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from modules import Analytics_Tracker as at


def _row(timestamp, trigger, game, platform, views, likes, success=True, note=""):
    """Build a performance_outcomes-shaped row."""
    return {
        "timestamp": timestamp,
        "trigger": trigger,
        "game": game,
        "platform": platform,
        "views": views,
        "likes": likes,
        "like_rate": round((likes / views) * 100, 2) if views else 0.0,
        "success": success,
        "clip_path": f"/tmp/{trigger}_{views}.mp4",
        "note": note,
    }


class AnalyticsTrackerTests(unittest.TestCase):

    def test_empty_file_returns_clean_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.jsonl"
            path.write_text("")
            s = at.summarize(path=path)
            self.assertEqual(s["row_count"], 0)
            self.assertEqual(s["total_views"], 0)
            self.assertEqual(s["by_trigger"], [])
            self.assertEqual(s["by_game"], [])
            self.assertEqual(s["best_posting_hours"], [])

    def test_load_skips_blank_and_bad_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mixed.jsonl"
            good = _row("2026-07-01T19:00:00", "ace", "Marvel Rivals", "tiktok", 1000, 50)
            path.write_text(
                "\n"  # blank
                + json.dumps(good) + "\n"
                + "this is not json\n"
                + json.dumps(_row("2026-07-02T20:00:00", "kill", "Marvel Rivals", "tiktok", 500, 20))
                + "\n"
            )
            s = at.summarize(path=path)
            self.assertEqual(s["row_count"], 2)
            self.assertEqual(s["total_views"], 1500)

    def test_group_by_trigger_sorts_by_avg_views(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "g.jsonl"
            rows = [
                _row("2026-07-01T19:00:00", "ace", "X", "tiktok", 5000, 200),
                _row("2026-07-01T20:00:00", "ace", "X", "tiktok", 3000, 150),
                _row("2026-07-01T21:00:00", "kill", "X", "tiktok", 1000, 50),
                _row("2026-07-01T22:00:00", "kill", "X", "tiktok", 2000, 80),
            ]
            path.write_text("\n".join(json.dumps(r) for r in rows))

            s = at.summarize(path=path)
            by_trigger = s["by_trigger"]
            # ace avg = 4000, kill avg = 1500 -> ace first
            self.assertEqual(by_trigger[0]["name"], "ace")
            self.assertEqual(by_trigger[0]["avg_views"], 4000)
            self.assertEqual(by_trigger[0]["count"], 2)
            self.assertEqual(by_trigger[1]["name"], "kill")
            self.assertEqual(by_trigger[1]["avg_views"], 1500)

    def test_group_by_game_and_platform(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "g.jsonl"
            rows = [
                _row("2026-07-01T19:00:00", "ace", "Marvel Rivals", "tiktok", 1000, 50),
                _row("2026-07-01T20:00:00", "kill", "Marvel Rivals", "youtube", 2000, 80),
                _row("2026-07-01T21:00:00", "win", "Warzone", "tiktok", 500, 10),
            ]
            path.write_text("\n".join(json.dumps(r) for r in rows))

            s = at.summarize(path=path)
            games = {g["name"]: g for g in s["by_game"]}
            self.assertEqual(set(games.keys()), {"Marvel Rivals", "Warzone"})
            self.assertEqual(games["Marvel Rivals"]["avg_views"], 1500)
            self.assertEqual(games["Warzone"]["avg_views"], 500)

            platforms = {p["name"]: p for p in s["by_platform"]}
            self.assertEqual(platforms["tiktok"]["avg_views"], 750)
            self.assertEqual(platforms["youtube"]["avg_views"], 2000)

    def test_best_posting_hours_buckets_by_hour(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "g.jsonl"
            # 19:00 and 19:30 should bucket into hour 19.
            rows = [
                _row("2026-07-01T19:00:00", "ace", "X", "tiktok", 5000, 200),
                _row("2026-07-01T19:30:00", "ace", "X", "tiktok", 3000, 150),
                _row("2026-07-01T20:00:00", "kill", "X", "tiktok", 1000, 50),
                _row("2026-07-01T08:00:00", "win", "X", "tiktok", 200, 5),
            ]
            path.write_text("\n".join(json.dumps(r) for r in rows))

            s = at.summarize(path=path)
            hours = {h["hour"]: h for h in s["best_posting_hours"]}
            # Hour 19 has 2 posts averaging 4000 views -> top.
            self.assertEqual(hours[19]["count"], 2)
            self.assertEqual(hours[19]["avg_views"], 4000)
            self.assertEqual(hours[20]["count"], 1)
            self.assertEqual(hours[8]["count"], 1)
            # Top of list should be hour 19.
            self.assertEqual(s["best_posting_hours"][0]["hour"], 19)

    def test_days_filter_excludes_old_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "g.jsonl"
            now = datetime.now()
            recent = (now - timedelta(days=2)).isoformat()
            old = (now - timedelta(days=30)).isoformat()
            very_old = (now - timedelta(days=200)).isoformat()
            rows = [
                _row(recent, "ace", "X", "tiktok", 5000, 200),
                _row(old, "kill", "X", "tiktok", 2000, 80),
                _row(very_old, "win", "X", "tiktok", 100, 1),
            ]
            path.write_text("\n".join(json.dumps(r) for r in rows))

            # With days=7, only the recent row should remain.
            s = at.summarize(path=path, days=7)
            self.assertEqual(s["row_count"], 1)
            self.assertEqual(s["total_views"], 5000)

            # With days=60, recent + old.
            s = at.summarize(path=path, days=60)
            self.assertEqual(s["row_count"], 2)

            # No filter, all 3.
            s = at.summarize(path=path)
            self.assertEqual(s["row_count"], 3)

    def test_success_rate_calculation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "g.jsonl"
            rows = [
                _row("2026-07-01T19:00:00", "ace", "X", "tiktok", 5000, 200, success=True),
                _row("2026-07-01T20:00:00", "ace", "X", "tiktok", 100, 1, success=False),
                _row("2026-07-01T21:00:00", "ace", "X", "tiktok", 8000, 400, success=True),
            ]
            path.write_text("\n".join(json.dumps(r) for r in rows))
            s = at.summarize(path=path)
            self.assertEqual(s["success_count"], 2)
            self.assertEqual(s["success_rate"], 66.7)
            # by_trigger inherits the same per-group calc.
            ace = next(t for t in s["by_trigger"] if t["name"] == "ace")
            self.assertEqual(ace["success_rate"], 66.7)

    def test_summary_is_json_serializable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "g.jsonl"
            path.write_text(json.dumps(_row("2026-07-01T19:00:00", "ace", "X", "tiktok", 1000, 50)))
            s = at.summarize(path=path)
            # Round-trip through json.dumps to confirm everything is serializable.
            out = json.dumps(s, default=str)
            self.assertIn("by_trigger", out)
            self.assertIn("best_posting_hours", out)


if __name__ == "__main__":
    unittest.main()
