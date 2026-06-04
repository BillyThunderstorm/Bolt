import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from modules import TikTok_Auth as auth


class TikTokAuthTests(unittest.TestCase):
    def test_write_env_values_updates_and_appends(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("A=1\nTIKTOK_ACCESS_TOKEN=old\n", encoding="utf-8")

            auth.write_env_values({"TIKTOK_ACCESS_TOKEN": "new", "TIKTOK_REFRESH_TOKEN": "refresh"}, path=path)

            text = path.read_text(encoding="utf-8")
            self.assertIn("A=1", text)
            self.assertIn("TIKTOK_ACCESS_TOKEN=new", text)
            self.assertIn("TIKTOK_REFRESH_TOKEN=refresh", text)

    def test_access_token_fresh_uses_expiry(self):
        env = {
            "TIKTOK_ACCESS_TOKEN": "act.test",
            "TIKTOK_ACCESS_TOKEN_EXPIRES_AT": str(time.time() + 3600),
        }
        self.assertTrue(auth.access_token_is_fresh(env))

    def test_refresh_access_token_saves_new_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(
                "TIKTOK_CLIENT_KEY=key\n"
                "TIKTOK_CLIENT_SECRET=secret\n"
                "TIKTOK_REFRESH_TOKEN=old-refresh\n",
                encoding="utf-8",
            )
            response = {
                "access_token": "act.new",
                "refresh_token": "rft.new",
                "expires_in": 86400,
                "refresh_expires_in": 31536000,
                "scope": "user.info.basic,video.publish",
                "token_type": "Bearer",
                "open_id": "open-id",
            }

            with patch.object(auth, "post_token_request", return_value=response):
                token = auth.refresh_access_token(path=path)

            self.assertEqual(token, "act.new")
            saved = auth.load_env(path)
            self.assertEqual(saved["TIKTOK_ACCESS_TOKEN"], "act.new")
            self.assertEqual(saved["TIKTOK_REFRESH_TOKEN"], "rft.new")

    def test_save_token_bundle_rejects_empty_token_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            with self.assertRaises(RuntimeError):
                auth.save_token_bundle({"error": "invalid_grant", "log_id": "abc"}, path=path)


if __name__ == "__main__":
    unittest.main()
