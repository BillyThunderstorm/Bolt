"""Tests for scripts/twitch_vod_downloader.py (`bolt vods`)."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

_repo_root = Path(__file__).resolve().parents[2]
for _p in (_repo_root, _repo_root / "scripts", _repo_root / "Core"):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

from scripts import twitch_vod_downloader as tvd  # noqa: E402


class DurationTests(unittest.TestCase):
    def test_parse_iso8601_duration(self):
        self.assertEqual(tvd.parse_iso8601_duration("2h13m47s"), 2 * 3600 + 13 * 60 + 47)
        self.assertEqual(tvd.parse_iso8601_duration("5m40s"), 340)
        self.assertEqual(tvd.parse_iso8601_duration(""), 0)
        self.assertEqual(tvd.parse_iso8601_duration("1h"), 3600)

    def test_derive_sample_start_skips_intro(self):
        start = tvd.derive_sample_start(3600, 300)
        self.assertGreater(start, 60)
        self.assertLessEqual(start + 300, 3600)

    def test_derive_sample_start_short_vod(self):
        self.assertEqual(tvd.derive_sample_start(200, 300), 0)


class YtdlpCmdTests(unittest.TestCase):
    def test_cmd_uses_signed_twitch_url_and_ffmpeg_location(self):
        out = Path("/tmp/vod.mp4")
        cmd = tvd.ytdlp_sample_cmd(
            "/opt/homebrew/bin/yt-dlp",
            "2865166953",
            out,
            start_seconds=10,
            sample_seconds=8,
            ffmpeg_path="/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
        )
        self.assertEqual(cmd[0], "/opt/homebrew/bin/yt-dlp")
        self.assertIn("--ffmpeg-location", cmd)
        loc = cmd[cmd.index("--ffmpeg-location") + 1]
        self.assertEqual(loc, "/opt/homebrew/opt/ffmpeg-full/bin")
        self.assertIn("--download-sections", cmd)
        self.assertIn("*10-18", cmd)
        self.assertIn("https://www.twitch.tv/videos/2865166953", cmd)
        self.assertNotIn("usher.ttvnw.net", " ".join(cmd))


class CliArgvTests(unittest.TestCase):
    """main() must honor the passed argv, not leftover sys.argv."""

    def test_status_json_uses_argv(self):
        info = {
            "ready": True,
            "client_id_set": True,
            "client_secret_set": True,
            "channel_set": True,
            "channel": "itssimplybilly",
            "yt_dlp_found": True,
            "yt_dlp_path": "/opt/homebrew/bin/yt-dlp",
            "ffmpeg_found": True,
            "ffmpeg_path": "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
            "hint": "ok",
        }
        buf = io.StringIO()
        with patch.object(tvd, "vod_status", return_value=info):
            with redirect_stdout(buf):
                rc = tvd.main(["status", "--json"])
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertTrue(payload["ready"])
        self.assertIn("ffmpeg-full", payload["ffmpeg_path"])

    def test_list_verb_is_dry_run_and_uses_passed_argv(self):
        videos = [
            {
                "id": "1",
                "title": "Dawnwalker",
                "created_at": "2026-09-10",
                "duration": "5m40s",
                "view_count": 4,
                "url": "https://www.twitch.tv/videos/1",
            }
        ]
        buf = io.StringIO()
        with patch.object(tvd, "list_videos", return_value=videos) as listed:
            with patch.object(tvd, "download_sample") as dl:
                with redirect_stdout(buf):
                    rc = tvd.main(["list", "--limit", "1", "--channel", "itssimplybilly"])
        self.assertEqual(rc, 0)
        listed.assert_called_once()
        dl.assert_not_called()
        self.assertIn("Dawnwalker", buf.getvalue())

    def test_download_fails_fast_without_working_ffmpeg(self):
        err = io.StringIO()
        with patch.object(tvd, "find_yt_dlp", return_value="/opt/homebrew/bin/yt-dlp"):
            with patch.object(tvd, "find_ffmpeg", return_value=None):
                with patch.object(tvd, "TwitchStats") as ts:
                    ts.try_create.return_value = (None, "unused")
                    with redirect_stderr(err):
                        rc = tvd.main(["download", "--channel", "itssimplybilly"])
        self.assertEqual(rc, 1)
        self.assertIn("working ffmpeg", err.getvalue())

    def test_download_writes_metadata_and_uses_ytdlp(self):
        videos = [
            {
                "id": "2865166953",
                "title": "The Blood of Dawnwalker",
                "created_at": "2026-09-04",
                "duration": "5m40s",
                "view_count": 4,
                "url": "https://www.twitch.tv/videos/2865166953",
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            buf = io.StringIO()
            with patch.object(tvd, "list_videos", return_value=videos):
                with patch.object(tvd, "find_yt_dlp", return_value="/opt/homebrew/bin/yt-dlp"):
                    with patch.object(
                        tvd, "find_ffmpeg",
                        return_value="/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
                    ):
                        with patch.object(tvd, "download_sample", return_value=True) as dl:
                            with redirect_stdout(buf):
                                rc = tvd.main([
                                    "--channel", "itssimplybilly",
                                    "--limit", "1",
                                    "--sample-minutes", "1",
                                    "--output-dir", str(out),
                                ])
            self.assertEqual(rc, 0)
            dl.assert_called_once()
            meta = json.loads((out / "metadata.json").read_text())
            self.assertEqual(meta[0]["id"], "2865166953")
            self.assertTrue(meta[0]["download_ok"])
            self.assertIn("Downloaded 1 / 1", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
