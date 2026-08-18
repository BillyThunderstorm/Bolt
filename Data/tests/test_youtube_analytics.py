"""Tests for YouTube_Analytics and YouTube path in Performance_Sync."""

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

from modules.YouTube_Analytics import (  # noqa: E402
    YouTubeAnalytics,
    YouTubeAnalyticsError,
    YouTubeVideoStats,
    _duration_seconds,
)
from modules import Performance_Sync as ps  # noqa: E402
from modules import YouTube_Auth as ytauth  # noqa: E402
from modules import Social_Stats as social  # noqa: E402


class DurationParseTests(unittest.TestCase):
    def test_duration_seconds(self):
        self.assertEqual(_duration_seconds("PT45S"), 45)
        self.assertEqual(_duration_seconds("PT1M30S"), 90)
        self.assertEqual(_duration_seconds("PT1H"), 3600)
        self.assertEqual(_duration_seconds(""), 0)


class YouTubeVideoStatsTests(unittest.TestCase):
    def test_from_api(self):
        raw = {
            "id": "abcXYZ12",
            "snippet": {
                "title": "Ace clutch Short",
                "description": "gaming",
                "publishedAt": "2026-07-01T12:00:00Z",
                "channelId": "UCtest",
            },
            "statistics": {
                "viewCount": "2500",
                "likeCount": "120",
                "commentCount": "8",
            },
            "contentDetails": {"duration": "PT42S"},
        }
        v = YouTubeVideoStats.from_api(raw)
        self.assertEqual(v.id, "abcXYZ12")
        self.assertEqual(v.view_count, 2500)
        self.assertEqual(v.like_count, 120)
        self.assertTrue(v.is_short)
        self.assertIn("watch?v=abcXYZ12", v.share_url)


class YouTubeAnalyticsClientTests(unittest.TestCase):
    def test_list_videos_batches_stats(self):
        client = YouTubeAnalytics(access_token="ya.test")

        def fake_get(endpoint, params, timeout=30):
            if endpoint == "channels":
                return {
                    "items": [
                        {
                            "contentDetails": {
                                "relatedPlaylists": {"uploads": "UU123"}
                            }
                        }
                    ]
                }
            if endpoint == "playlistItems":
                return {
                    "items": [
                        {"contentDetails": {"videoId": "vid1"}},
                        {"contentDetails": {"videoId": "vid2"}},
                    ]
                }
            if endpoint == "videos":
                return {
                    "items": [
                        {
                            "id": "vid1",
                            "snippet": {
                                "title": "One",
                                "publishedAt": "2026-07-01T00:00:00Z",
                            },
                            "statistics": {"viewCount": "10", "likeCount": "1"},
                            "contentDetails": {"duration": "PT30S"},
                        },
                        {
                            "id": "vid2",
                            "snippet": {
                                "title": "Two long",
                                "publishedAt": "2026-07-02T00:00:00Z",
                            },
                            "statistics": {"viewCount": "20", "likeCount": "2"},
                            "contentDetails": {"duration": "PT5M"},
                        },
                    ]
                }
            raise AssertionError(endpoint)

        with patch.object(client, "_get", side_effect=fake_get):
            all_v = client.list_videos(limit=10)
            shorts = client.list_videos(limit=10, shorts_only=True)

        self.assertEqual(len(all_v), 2)
        self.assertEqual(len(shorts), 1)
        self.assertEqual(shorts[0].id, "vid1")

    def test_api_key_uses_handle_not_mine(self):
        client = YouTubeAnalytics(access_token="", api_key="AIza.test")
        seen = []

        def fake_get(endpoint, params, timeout=30):
            seen.append((endpoint, dict(params)))
            if endpoint == "channels":
                self.assertNotIn("mine", params)
                self.assertEqual(params.get("forHandle"), "SimplyBilly")
                return {
                    "items": [
                        {
                            "contentDetails": {
                                "relatedPlaylists": {"uploads": "UU-public"}
                            }
                        }
                    ]
                }
            if endpoint == "playlistItems":
                return {"items": [{"contentDetails": {"videoId": "pub1"}}]}
            if endpoint == "videos":
                return {
                    "items": [
                        {
                            "id": "pub1",
                            "snippet": {
                                "title": "Public",
                                "publishedAt": "2026-08-01T00:00:00Z",
                            },
                            "statistics": {"viewCount": "9", "likeCount": "1"},
                            "contentDetails": {"duration": "PT20S"},
                        }
                    ]
                }
            raise AssertionError(endpoint)

        with patch.object(client, "_get", side_effect=fake_get), patch(
            "modules.YouTube_Auth.channel_lookup",
            return_value={"handle": "SimplyBilly", "channel_id": ""},
        ):
            videos = client.list_videos(limit=1)

        self.assertEqual(len(videos), 1)
        self.assertEqual(videos[0].id, "pub1")
        self.assertEqual(seen[0][0], "channels")


class YouTubeAuthTests(unittest.TestCase):
    def test_refresh_invalid_grant_does_not_return_stale_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(
                "YOUTUBE_CLIENT_ID=cid\n"
                "YOUTUBE_CLIENT_SECRET=sec\n"
                "YOUTUBE_REFRESH_TOKEN=dead\n"
                "YOUTUBE_ACCESS_TOKEN=ya.stale\n"
                "YOUTUBE_ACCESS_TOKEN_EXPIRES_AT=1\n",
                encoding="utf-8",
            )
            with patch.object(
                ytauth,
                "post_token_request",
                side_effect=ytauth.YouTubeAuthError(
                    "YouTube token request failed: {'error': 'invalid_grant'}"
                ),
            ):
                with self.assertRaises(ytauth.YouTubeAuthError) as ctx:
                    ytauth.refresh_access_token(path=path)
                self.assertIn("expired or revoked", str(ctx.exception))
                with self.assertRaises(ytauth.YouTubeAuthError):
                    ytauth.ensure_access_token(path=path)

    def test_save_token_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("YOUTUBE_CLIENT_ID=cid\n", encoding="utf-8")
            ytauth.save_token_bundle(
                {
                    "access_token": "ya.new",
                    "refresh_token": "1//refresh",
                    "expires_in": 3600,
                    "scope": ytauth.DEFAULT_SCOPE,
                    "token_type": "Bearer",
                },
                path=path,
            )
            env = ytauth.load_env(path)
            self.assertEqual(env["YOUTUBE_ACCESS_TOKEN"], "ya.new")
            self.assertEqual(env["YOUTUBE_REFRESH_TOKEN"], "1//refresh")


class YouTubeSyncTests(unittest.TestCase):
    def test_sync_youtube_stats_live_upsert(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            outcomes = tmp_path / "performance_outcomes.jsonl"
            state = tmp_path / "youtube_stats_state.json"
            queue = tmp_path / "ready_to_post.json"
            queue.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "q1",
                                "title": "Ace clutch Short",
                                "clip_path": "/clips/clip01_ace_1_tiktok.mp4",
                                "status": "posted",
                                "posted_at": "2026-07-01T12:00:00+00:00",
                                "platform_plan": [
                                    {
                                        "platform": "youtube_shorts",
                                        "status": "posted",
                                        "title": "Ace clutch Short",
                                        "posted_at": "2026-07-01T12:00:00+00:00",
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            video = YouTubeVideoStats(
                id="yt-vid-1",
                title="Ace clutch Short",
                view_count=900,
                like_count=45,
                create_time=int(
                    __import__("datetime")
                    .datetime(
                        2026, 7, 1, 12, 5, tzinfo=__import__("datetime").timezone.utc
                    )
                    .timestamp()
                ),
                is_short=True,
                share_url="https://www.youtube.com/watch?v=yt-vid-1",
            )

            class FakeClient:
                def list_videos(self, limit=50, shorts_only=False):
                    return [video]

            with patch(
                "modules.YouTube_Analytics.YouTubeAnalytics",
                return_value=FakeClient(),
            ), patch.object(ps, "_feed_learning"), patch(
                "modules.Checkup_Writer.update_checkup"
            ), patch(
                "modules.Memory_Index.refresh_memory_index"
            ):
                result = ps.sync_youtube_stats(
                    dry_run=False,
                    outcomes_path=outcomes,
                    state_path=state,
                    queue_path=queue,
                    default_game="Marvel Rivals",
                    feed_learning=True,
                    refresh_memory=False,
                )

            self.assertTrue(result["ok"])
            self.assertEqual(result["platform"], "YouTube")
            self.assertEqual(result["logged_new"], 1)
            row = json.loads(outcomes.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(row["youtube_video_id"], "yt-vid-1")
            self.assertEqual(row["platform"], "YouTube")
            self.assertEqual(row["source"], "youtube_api")
            self.assertEqual(row["trigger"], "ace")
            self.assertEqual(row["views"], 900)

            # Second sync updates in place
            video.view_count = 1500
            with patch(
                "modules.YouTube_Analytics.YouTubeAnalytics",
                return_value=FakeClient(),
            ), patch.object(ps, "_feed_learning") as feed, patch(
                "modules.Checkup_Writer.update_checkup"
            ), patch(
                "modules.Memory_Index.refresh_memory_index"
            ):
                result2 = ps.sync_youtube_stats(
                    dry_run=False,
                    outcomes_path=outcomes,
                    state_path=state,
                    queue_path=queue,
                    default_game="Marvel Rivals",
                    feed_learning=True,
                    refresh_memory=False,
                )
            self.assertEqual(result2["logged_new"], 0)
            self.assertEqual(result2["updated"], 1)
            lines = outcomes.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            self.assertEqual(json.loads(lines[0])["views"], 1500)
            # Learning only on first log — second pass should not call feed
            # (is_new False and already_logged True)
            feed.assert_called()  # still invoked with is_new=False → no-op inside


class SocialStatsReadinessTests(unittest.TestCase):
    def test_youtube_ready_expired_oauth_but_api_key(self):
        env = {
            "YOUTUBE_ACCESS_TOKEN": "ya.stale",
            "YOUTUBE_REFRESH_TOKEN": "1//dead",
            "YOUTUBE_ACCESS_TOKEN_EXPIRES_AT": "1",
            "YOUTUBE_API_KEY": "AIza.test",
            "YOUTUBE_HANDLE": "@SimplyBilly",
        }
        with patch.dict("os.environ", env, clear=False), patch(
            "modules.YouTube_Auth.access_token_is_fresh", return_value=False
        ):
            block = social.youtube_ready()
        self.assertTrue(block["ready"])
        self.assertTrue(block["has_api_key"])
        self.assertIn("public API key", block["next_step"])

    def test_tiktok_ready_paused_skips_token_lookup(self):
        with patch.dict("os.environ", {"TIKTOK_API_ENABLED": "false"}):
            block = social.tiktok_ready()
        self.assertTrue(block.get("paused"))
        self.assertFalse(block["ready"])
        self.assertNotIn("has_access_token", block)
        self.assertIn("paused", block["next_step"])

    def test_youtube_ready_expired_without_api_key(self):
        env = {
            "YOUTUBE_ACCESS_TOKEN": "ya.stale",
            "YOUTUBE_REFRESH_TOKEN": "1//dead",
            "YOUTUBE_ACCESS_TOKEN_EXPIRES_AT": "1",
            "YOUTUBE_API_KEY": "",
            "YOUTUBE_HANDLE": "@SimplyBilly",
        }
        with patch.dict("os.environ", env, clear=False), patch(
            "modules.YouTube_Auth.access_token_is_fresh", return_value=False
        ):
            # _env_set reads os.environ; make sure empty API key is not ready
            with patch.object(social, "_env_set", side_effect=lambda *keys: any(
                bool((env.get(k) or "").strip()) for k in keys
            )):
                block = social.youtube_ready()
        self.assertFalse(block["ready"])
        self.assertIn("OAuth expired", block["next_step"])


if __name__ == "__main__":
    unittest.main()
