import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from modules import Bolt_Chat as chat
from modules import Peak_Hour_Notifier as notifier


class AutoPostingSafeguardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ready = self.root / "ready_to_post.json"
        self.config = self.root / "config.json"
        self.rejections = self.root / "post_rejections.jsonl"
        self.clip = self.root / "clip.mp4"
        self.clip.write_bytes(b"fake video")
        self.config.write_text(
            '{"min_clip_score": 65, "auto_posting": {"enabled": true, "review_window_minutes": 30, "auto_post_if_deadline_missed": true}}'
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _patch_files(self):
        return patch.multiple(
            notifier,
            READY_FILE=self.ready,
            CONFIG_FILE=self.config,
            REJECTION_LOG=self.rejections,
            POSTING_TIMEZONE="America/Chicago",
        )

    def test_review_window_alerts_before_peak(self):
        now = datetime.fromisoformat("2026-05-27T18:31:00-05:00")
        with self._patch_files(), \
             patch.object(notifier, "_now", return_value=now), \
             patch.object(notifier, "_send_discord") as send:
            notifier.queue_clip(str(self.clip), "Ready clip", ["#Gaming"], score=90)
            count = notifier.alert_review_window(now)
            data = notifier._load_ready()

        self.assertEqual(count, 1)
        self.assertTrue(send.called)
        self.assertEqual(data["clips"][0]["auto_post"]["status"], "awaiting_approval")

    def test_deadline_missed_auto_posts(self):
        queued = datetime.fromisoformat("2026-05-27T18:31:00-05:00")
        deadline = datetime.fromisoformat("2026-05-27T19:00:00-05:00")
        with self._patch_files(), \
             patch.object(notifier, "_now", return_value=queued), \
             patch.object(notifier, "_send_discord"), \
             patch("modules.TikTok_Publisher.publish_clip", return_value={"success": True, "url": "https://example.com/post"}):
            notifier.queue_clip(str(self.clip), "Ready clip", ["#Gaming"], score=90)
            notifier.alert_review_window(queued)
            stats = notifier.process_auto_post_queue(deadline)
            data = notifier._load_ready()

        self.assertEqual(stats["posted"], 1)
        self.assertEqual(data["clips"][0]["status"], "posted")
        self.assertEqual(data["clips"][0]["auto_post"]["status"], "posted")

    def test_reject_holds_and_logs_reason(self):
        now = datetime.fromisoformat("2026-05-27T18:31:00-05:00")
        with self._patch_files(), \
             patch.object(notifier, "_now", return_value=now), \
             patch.object(notifier, "_send_discord"):
            notifier.queue_clip(str(self.clip), "Ready clip", ["#Gaming"], score=90)
            notifier.alert_review_window(now)
            held = notifier.reject_next_clip("bad hook")

        self.assertEqual(held["status"], "held")
        self.assertIn("bad hook", self.rejections.read_text())

    def test_chat_helpers_route_overrides(self):
        with patch("modules.Peak_Hour_Notifier.approve_next_clip", return_value={"id": "abc123"}):
            self.assertIn("approved clip abc123", chat.approve_next_post())
        with patch("modules.Peak_Hour_Notifier.reject_next_clip", return_value={"id": "abc123"}):
            self.assertIn("held clip abc123", chat.reject_next_post("abc123 weak ending"))

    def test_rank_override_promotes_clip(self):
        now = datetime.fromisoformat("2026-05-27T18:31:00-05:00")
        with self._patch_files(), patch.object(notifier, "_now", return_value=now):
            notifier.queue_clip(str(self.clip), "Ready clip", ["#Gaming"], score=70, tier="mid")
            clip = notifier.override_clip_score(95)

        self.assertEqual(clip["score"], 95.0)
        self.assertEqual(clip["tier"], "queue")
        self.assertEqual(clip["auto_post"]["status"], "scheduled")

    def test_chat_rank_helper_validates_number(self):
        self.assertIn("rank needs a number", chat.rank_next_clip("not-a-score"))
        with patch("modules.Peak_Hour_Notifier.override_clip_score", return_value={
            "id": "abc123",
            "score": 95.0,
            "tier": "queue",
        }):
            self.assertIn("clip abc123 is now score 95.0/100", chat.rank_next_clip("95"))


if __name__ == "__main__":
    unittest.main()
