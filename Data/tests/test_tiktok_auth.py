

import sys
from pathlib import Path
_repo_root = Path(__file__).resolve().parents[2]
for _p in [_repo_root / 'Core']:
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from modules import TikTok_Auth as auth


class TikTokApiGateTests(unittest.TestCase):
    def test_default_off_when_unset(self):
        with patch.dict("os.environ"):
            os.environ.pop("TIKTOK_API_ENABLED", None)
            self.assertFalse(auth.tiktok_api_enabled({}))

    def test_process_env_true_overrides_file(self):
        with patch.dict("os.environ", {"TIKTOK_API_ENABLED": "true"}):
            self.assertTrue(auth.tiktok_api_enabled({"TIKTOK_API_ENABLED": "false"}))

    def test_process_env_false_overrides_file(self):
        with patch.dict("os.environ", {"TIKTOK_API_ENABLED": "false"}):
            self.assertFalse(auth.tiktok_api_enabled({"TIKTOK_API_ENABLED": "true"}))


class TikTokAuthTests(unittest.TestCase):
    def test_write_env_values_updates_and_appends(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("A=1\nTIKTOK_ACCESS_TOKEN=old\n", encoding="utf-8")

            auth.write_env_values(
                {"TIKTOK_ACCESS_TOKEN": "new", "TIKTOK_REFRESH_TOKEN": "refresh"},
                path=path,
            )

            text = path.read_text(encoding="utf-8")
            self.assertIn("A=1", text)
            self.assertIn("TIKTOK_ACCESS_TOKEN=new", text)
            self.assertIn("TIKTOK_REFRESH_TOKEN=refresh", text)

    def test_write_env_values_does_not_concat_when_file_lacks_newline(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("TIKTOK_CLIENT_SECRET=abc", encoding="utf-8")

            auth.write_env_values({"TIKTOK_REDIRECT_URI": "https://example/cb"}, path=path)

            text = path.read_text(encoding="utf-8")
            self.assertIn("TIKTOK_CLIENT_SECRET=abc\n", text)
            self.assertIn("TIKTOK_REDIRECT_URI=https://example/cb\n", text)
            self.assertNotIn("abcTIKTOK_REDIRECT_URI", text)

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
                auth.save_token_bundle(
                    {"error": "invalid_grant", "log_id": "abc"}, path=path
                )


if __name__ == "__main__":
    unittest.main()
