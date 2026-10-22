"""Targeted tests for Discord webhook alerts (notifier.post_webhooks).

Fully mocked: never talks to Discord, never writes the real logs/discord.jsonl.
"""
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Core"))

from modules import notifier  # noqa: E402


class _Resp:
    status = 204

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return b""


class DiscordNotifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "discord.jsonl"
        self.p_log = patch.object(notifier, "DISCORD_LOG", self.log)
        self.p_dir = patch.object(notifier, "_LOG_DIR", Path(self.tmp.name))
        self.p_log.start()
        self.p_dir.start()

    def tearDown(self):
        self.p_log.stop()
        self.p_dir.stop()
        self.tmp.cleanup()

    def test_sends_user_agent_and_no_mentions(self):
        seen = []

        def fake_open(req, timeout=0):
            seen.append(req)
            return _Resp()

        with patch.object(notifier, "_discord_webhooks", return_value=["https://discord.test/api/webhooks/1/abcdef"]), \
                patch("urllib.request.urlopen", side_effect=fake_open):
            res = notifier.post_webhooks("hello @everyone", source="test")
        self.assertTrue(res["ok"])
        self.assertEqual(res["sent"], 1)
        req = seen[0]
        self.assertNotIn("Python-urllib", req.get_header("User-agent"))
        body = json.loads(req.data)
        self.assertEqual(body["allowed_mentions"], {"parse": []})
        entry = json.loads(self.log.read_text().strip().splitlines()[-1])
        self.assertEqual(entry["sent"], 1)
        self.assertEqual(entry["source"], "test")

    def test_long_message_split_under_limit(self):
        text = "\n".join(f"clip {i} " + "x" * 80 for i in range(60))
        parts = notifier._split_message(text)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(p) <= notifier.DISCORD_LIMIT for p in parts))
        self.assertEqual("".join(parts).replace("\n", ""), text.replace("\n", ""))

    def test_http_error_reported_not_raised(self):
        err = urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO(b"{}"))
        with patch.object(notifier, "_discord_webhooks", return_value=["https://discord.test/api/webhooks/1/abcdef"]), \
                patch("urllib.request.urlopen", side_effect=err):
            res = notifier.post_webhooks("hi")
        self.assertFalse(res["ok"])
        self.assertIn("404", res["error"])
        self.assertIn("deleted", res["error"])
        self.assertIn("Discord unavailable", res["error"])

    def test_429_retries_once(self):
        calls = {"n": 0}

        def fake_open(req, timeout=0):
            calls["n"] += 1
            if calls["n"] == 1:
                raise urllib.error.HTTPError("u", 429, "Too Many", {}, io.BytesIO(b'{"retry_after": 0.1}'))
            return _Resp()

        with patch.object(notifier, "_discord_webhooks", return_value=["https://discord.test/api/webhooks/1/abcdef"]), \
                patch("urllib.request.urlopen", side_effect=fake_open), \
                patch("time.sleep"):
            res = notifier.post_webhooks("hi")
        self.assertTrue(res["ok"])
        self.assertEqual(calls["n"], 2)

    def test_no_webhook_soft_fails(self):
        with patch.object(notifier, "_discord_webhooks", return_value=[]):
            res = notifier.post_webhooks("hi")
        self.assertFalse(res["ok"])
        self.assertIn("Discord unavailable", res["error"])

    def test_probe_posts_nothing(self):
        methods = []

        def fake_open(req, timeout=0):
            methods.append(req.get_method())

            class R(_Resp):
                def read(self):
                    return b'{"name": "Bolt", "channel_id": "1"}'
            return R()

        with patch.object(notifier, "_discord_webhooks", return_value=["https://discord.test/api/webhooks/1/abcdef"]), \
                patch("urllib.request.urlopen", side_effect=fake_open):
            info = notifier.status(probe=True)
        self.assertTrue(info["probe_ok"])
        self.assertEqual(methods, ["GET"])

    def test_peak_hour_uses_shared_sender(self):
        from modules import Peak_Hour_Notifier as ph
        with patch.object(ph, "_discord_webhooks", return_value=["https://discord.test/api/webhooks/1/abcdef"]), \
                patch.object(notifier, "post_webhooks", return_value={"ok": True, "sent": 1, "errors": []}) as pw:
            ph._send_discord("peak time!")
        pw.assert_called_once()
        self.assertEqual(pw.call_args.kwargs.get("source"), "peak_hour")


if __name__ == "__main__":
    unittest.main()
