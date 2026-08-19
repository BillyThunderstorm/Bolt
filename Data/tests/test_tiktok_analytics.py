"""Tests for TikTok_Analytics and Performance_Sync (stats pull → learning log)."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_repo_root = Path(__file__).resolve().parents[2]
for _p in [_repo_root / "Core"]:
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

from modules.TikTok_Analytics import TikTokAnalytics, TikTokVideoStats  # noqa: E402
from modules import Performance_Sync as ps  # noqa: E402


class TikTokVideoStatsTests(unittest.TestCase):
    def test_from_api_normalizes_fields(self):
        v = TikTokVideoStats.from_api(
            {
                "id": "abc123",
                "title": "Clutch play",
                "view_count": 1500,
                "like_count": 90,
                "comment_count": 4,
                "share_count": 2,
                "create_time": 1_720_000_000,
            }
        )
        self.assertEqual(v.id, "abc123")
        self.assertEqual(v.view_count, 1500)
        self.assertEqual(v.like_count, 90)
        self.assertEqual(v.to_dict()["share_count"], 2)


class TikTokAnalyticsClientTests(unittest.TestCase):
    def test_list_videos_paginates(self):
        page1 = {
            "data": {
                "videos": [
                    {"id": "1", "title": "A", "view_count": 10, "like_count": 1},
                    {"id": "2", "title": "B", "view_count": 20, "like_count": 2},
                ],
                "cursor": 100,
                "has_more": True,
            },
            "error": {"code": "ok"},
        }
        page2 = {
            "data": {
                "videos": [
                    {"id": "3", "title": "C", "view_count": 30, "like_count": 3},
                ],
                "cursor": 200,
                "has_more": False,
            },
            "error": {"code": "ok"},
        }
        client = TikTokAnalytics(access_token="act.test")
        with patch.object(client, "_post", side_effect=[page1, page2]) as post:
            videos = client.list_videos(limit=10)

        self.assertEqual(len(videos), 3)
        self.assertEqual(videos[2].id, "3")
        self.assertEqual(post.call_count, 2)

    def test_api_error_raises(self):
        client = TikTokAnalytics(access_token="act.test")
        with patch.object(
            client,
            "_post",
            side_effect=Exception("should not be used"),
        ):
            # Inject a fake _post that returns a TikTok-shaped error via real path
            pass

        def bad_post(*_a, **_k):
            from modules.TikTok_Analytics import TikTokAnalyticsError

            raise TikTokAnalyticsError("scope missing")

        with patch.object(client, "_post", side_effect=bad_post):
            from modules.TikTok_Analytics import TikTokAnalyticsError

            with self.assertRaises(TikTokAnalyticsError):
                client.list_page()


class PerformanceSyncHelpersTests(unittest.TestCase):
    def test_infer_trigger_from_path(self):
        path = "media/vertical_clips/2026-07-09_clip03_audio_spike_988_tiktok.mp4"
        self.assertEqual(ps.infer_trigger_from_path(path), "audio_spike")
        self.assertEqual(ps.infer_trigger_from_path("nope.mp4"), "unknown")
        self.assertEqual(
            ps.infer_trigger_from_text("My Video - highlighter"), "unknown"
        )
        self.assertEqual(
            ps.infer_trigger_from_text("Hades 2 highlight #Hades2"), "highlight"
        )

    def test_infer_game_from_text(self):
        self.assertEqual(ps.infer_game_from_text("#Hades2 clutch"), "Hades 2")
        self.assertEqual(ps.infer_game_from_text("Hades Highlight 🔥 #Hades"), "Hades 2")
        self.assertEqual(
            ps.infer_game_from_text("Deadpool down #MarvelRival"), "Marvel Rivals"
        )
        self.assertEqual(
            ps.infer_game_from_text("#SplitFiction #HazelightStudios"),
            "Split Fiction",
        )
        self.assertEqual(
            ps.infer_game_from_text("Just got my hands on 007 First Light"),
            "007 First Light",
        )
        self.assertEqual(
            ps.infer_game_from_text("Escaping Hell #DeadByDaylight"),
            "Dead by Daylight",
        )
        self.assertIsNone(ps.infer_game_from_text("June 30, 2026"))
        self.assertIsNone(ps.infer_game_from_text(""))

    def test_unmatched_video_does_not_inherit_config_game(self):
        game, trigger = ps.resolve_video_metadata(
            title="Fighting for my life #Hades2",
            clip_path="",
            match=None,
        )
        self.assertEqual(game, "Hades 2")
        self.assertEqual(trigger, "unknown")
        unknown_game, _ = ps.resolve_video_metadata(
            title="Wins", clip_path="", match=None
        )
        self.assertEqual(unknown_game, "Unknown")

    def test_retag_and_rebuild_history_drops_seed_and_wrong_game(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            outcomes = tmp_path / "performance_outcomes.jsonl"
            yt_state = tmp_path / "youtube_stats_state.json"
            tk_state = tmp_path / "tiktok_stats_state.json"
            history = tmp_path / "clip_history.json"
            outcomes.write_text(
                json.dumps(
                    {
                        "game": "007 First Light",
                        "trigger": "unknown",
                        "views": 100,
                        "likes": 2,
                        "title": "Deadpool down #MarvelRivals",
                        "note": "synced from YouTube API (unmatched to queue)",
                        "timestamp": "2026-08-01T00:00:00",
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "game": "007 First Light",
                        "trigger": "unknown",
                        "views": 50,
                        "likes": 0,
                        "title": "Hades 2 highlight #Hades2",
                        "note": "synced from YouTube API (unmatched to queue)",
                        "timestamp": "2026-08-02T00:00:00",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            yt_state.write_text(
                json.dumps(
                    {
                        "videos": {
                            "abc": {
                                "title": "Deadpool down #MarvelRivals",
                                "game": "007 First Light",
                                "trigger": "unknown",
                                "clip_path": "",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            tk_state.write_text("{}", encoding="utf-8")
            result = ps.retag_outcomes_from_titles(
                outcomes_path=outcomes,
                youtube_state_path=yt_state,
                tiktok_state_path=tk_state,
            )
            self.assertEqual(result["outcomes_updated"], 2)
            rows = [
                json.loads(line)
                for line in outcomes.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(rows[0]["game"], "Marvel Rivals")
            self.assertEqual(rows[1]["game"], "Hades 2")
            self.assertEqual(rows[1]["trigger"], "highlight")
            rebuilt = ps.rebuild_clip_history_from_outcomes(
                outcomes_path=outcomes, history_path=history
            )
            self.assertIn("Marvel Rivals", rebuilt)
            self.assertIn("Hades 2", rebuilt)
            self.assertNotIn("007 First Light", rebuilt)
            self.assertNotIn("multi_kill", rebuilt.get("Marvel Rivals", {}))

    def test_title_similarity(self):
        self.assertGreater(
            ps._title_similarity(
                "You have to see this Gaming clip",
                "You have to see this #Gaming clip",
            ),
            0.5,
        )
        self.assertEqual(ps._title_similarity("", "x"), 0.0)

    def test_match_video_to_clip_by_title(self):
        video = TikTokVideoStats(
            id="v1",
            title="You have to see this Gaming clip",
            create_time=1_720_000_000,
        )
        posted = [
            {
                "id": "q1",
                "title": "You have to see this #Gaming clip",
                "clip_path": "/tmp/clip_audio_spike_1_tiktok.mp4",
                "posted_at": "2024-07-03T12:00:00+00:00",
                "status": "posted",
                "platform_plan": [
                    {
                        "platform": "tiktok",
                        "status": "posted",
                        "caption": "You have to see this #Gaming clip",
                        "posted_at": "2024-07-03T12:00:00+00:00",
                    }
                ],
            }
        ]
        # create_time 1720000000 ≈ 2024-07-03 — within 48h of posted_at
        match = ps.match_video_to_clip(video, posted, max_hours_delta=72)
        self.assertIsNotNone(match)
        self.assertEqual(match["id"], "q1")

    def test_upsert_outcome_dedupes_by_video_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "outcomes.jsonl"
            first = ps._build_outcome_entry(
                video_id="vid-1",
                views=100,
                likes=5,
                comments=0,
                shares=0,
                game="Marvel Rivals",
                trigger="kill",
                clip_path="a.mp4",
                share_url="https://tiktok.com/x",
                title="first",
            )
            saved, is_new = ps.upsert_outcome(first, path=path)
            self.assertTrue(is_new)
            self.assertEqual(saved["views"], 100)

            second = ps._build_outcome_entry(
                video_id="vid-1",
                views=500,
                likes=40,
                comments=2,
                shares=1,
                game="Marvel Rivals",
                trigger="kill",
                clip_path="a.mp4",
                share_url="https://tiktok.com/x",
                title="first",
            )
            saved2, is_new2 = ps.upsert_outcome(second, path=path)
            self.assertFalse(is_new2)
            self.assertEqual(saved2["views"], 500)

            lines = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            self.assertEqual(json.loads(lines[0])["views"], 500)

    def test_sync_tiktok_stats_dry_run_and_live(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            outcomes = tmp_path / "performance_outcomes.jsonl"
            state = tmp_path / "tiktok_stats_state.json"
            queue = tmp_path / "ready_to_post.json"
            queue.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "q99",
                                "title": "Ace clutch moment",
                                "clip_path": "/clips/clip01_ace_12_tiktok.mp4",
                                "status": "posted",
                                "posted_at": "2026-07-01T12:00:00+00:00",
                                "platform_plan": [
                                    {
                                        "platform": "tiktok",
                                        "status": "posted",
                                        "caption": "Ace clutch moment",
                                        "posted_at": "2026-07-01T12:00:00+00:00",
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            fake_videos = [
                TikTokVideoStats(
                    id="tt-1",
                    title="Ace clutch moment",
                    view_count=1200,
                    like_count=80,
                    create_time=1_720_000_000,  # ~2024 — far from queue date
                )
            ]

            class FakeClient:
                def list_videos(self, limit=50):
                    return fake_videos

            with patch(
                "modules.TikTok_Analytics.TikTokAnalytics", return_value=FakeClient()
            ), patch.object(ps, "_feed_learning"), patch(
                "modules.Checkup_Writer.update_checkup"
            ), patch(
                "modules.Memory_Index.refresh_memory_index"
            ):
                # Force match by widening window and aligning times
                fake_videos[0].create_time = int(
                    __import__("datetime")
                    .datetime(2026, 7, 1, 12, 0, tzinfo=__import__("datetime").timezone.utc)
                    .timestamp()
                )

                dry = ps.sync_tiktok_stats(
                    dry_run=True,
                    outcomes_path=outcomes,
                    state_path=state,
                    queue_path=queue,
                    default_game="Marvel Rivals",
                    feed_learning=False,
                    refresh_memory=False,
                )
                self.assertTrue(dry["ok"])
                self.assertEqual(dry["fetched"], 1)
                self.assertFalse(outcomes.exists())

                live = ps.sync_tiktok_stats(
                    dry_run=False,
                    outcomes_path=outcomes,
                    state_path=state,
                    queue_path=queue,
                    default_game="Marvel Rivals",
                    feed_learning=True,
                    refresh_memory=False,
                )
                self.assertTrue(live["ok"])
                self.assertEqual(live["logged_new"], 1)
                self.assertTrue(outcomes.exists())
                row = json.loads(outcomes.read_text(encoding="utf-8").splitlines()[0])
                self.assertEqual(row["tiktok_video_id"], "tt-1")
                self.assertEqual(row["views"], 1200)
                self.assertEqual(row["trigger"], "ace")
                self.assertEqual(row["source"], "tiktok_api")

                # Second sync updates, does not duplicate
                fake_videos[0].view_count = 2000
                live2 = ps.sync_tiktok_stats(
                    dry_run=False,
                    outcomes_path=outcomes,
                    state_path=state,
                    queue_path=queue,
                    default_game="Marvel Rivals",
                    feed_learning=True,
                    refresh_memory=False,
                )
                self.assertEqual(live2["logged_new"], 0)
                self.assertEqual(live2["updated"], 1)
                lines = outcomes.read_text(encoding="utf-8").strip().splitlines()
                self.assertEqual(len(lines), 1)
                self.assertEqual(json.loads(lines[0])["views"], 2000)


if __name__ == "__main__":
    unittest.main()
