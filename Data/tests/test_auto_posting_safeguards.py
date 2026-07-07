

import sys
from pathlib import Path
_repo_root = Path(__file__).resolve().parents[2]
for _p in [_repo_root / 'Core']:
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

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
        with (
            self._patch_files(),
            patch.object(notifier, "_now", return_value=now),
            patch.object(notifier, "_send_discord") as send,
        ):
            notifier.queue_clip(str(self.clip), "Ready clip", ["#Gaming"], score=90)
            count = notifier.alert_review_window(now)
            data = notifier._load_ready()

        self.assertEqual(count, 1)
        self.assertTrue(send.called)
        self.assertEqual(data["clips"][0]["auto_post"]["status"], "awaiting_approval")

    def test_deadline_missed_auto_posts(self):
        queued = datetime.fromisoformat("2026-05-27T18:31:00-05:00")
        deadline = datetime.fromisoformat("2026-05-27T19:00:00-05:00")
        with (
            self._patch_files(),
            patch.object(notifier, "_now", return_value=queued),
            patch.object(notifier, "_send_discord"),
            patch(
                "modules.TikTok_Publisher.publish_clip",
                return_value={"success": True, "url": "https://example.com/post"},
            ),
        ):
            notifier.queue_clip(str(self.clip), "Ready clip", ["#Gaming"], score=90)
            notifier.alert_review_window(queued)
            stats = notifier.process_auto_post_queue(deadline)
            data = notifier._load_ready()

        self.assertEqual(stats["posted"], 1)
        self.assertEqual(data["clips"][0]["status"], "posted")
        self.assertEqual(data["clips"][0]["auto_post"]["status"], "posted")

    def test_reject_holds_and_logs_reason(self):
        now = datetime.fromisoformat("2026-05-27T18:31:00-05:00")
        with (
            self._patch_files(),
            patch.object(notifier, "_now", return_value=now),
            patch.object(notifier, "_send_discord"),
        ):
            notifier.queue_clip(str(self.clip), "Ready clip", ["#Gaming"], score=90)
            notifier.alert_review_window(now)
            held = notifier.reject_next_clip("bad hook")

        self.assertEqual(held["status"], "held")
        self.assertIn("bad hook", self.rejections.read_text())

    def test_chat_helpers_route_overrides(self):
        with patch(
            "modules.Peak_Hour_Notifier.approve_next_clip",
            return_value={"id": "abc123"},
        ):
            self.assertIn("approved clip abc123", chat.approve_next_post())
        with patch(
            "modules.Peak_Hour_Notifier.reject_next_clip", return_value={"id": "abc123"}
        ):
            self.assertIn(
                "held clip abc123", chat.reject_next_post("abc123 weak ending")
            )

    def test_rank_override_promotes_clip(self):
        now = datetime.fromisoformat("2026-05-27T18:31:00-05:00")
        with self._patch_files(), patch.object(notifier, "_now", return_value=now):
            notifier.queue_clip(
                str(self.clip), "Ready clip", ["#Gaming"], score=70, tier="mid"
            )
            clip = notifier.override_clip_score(95)

        self.assertEqual(clip["score"], 95.0)
        self.assertEqual(clip["tier"], "queue")
        self.assertEqual(clip["auto_post"]["status"], "scheduled")

    def test_chat_rank_helper_validates_number(self):
        self.assertIn("rank needs a number", chat.rank_next_clip("not-a-score"))
        with patch(
            "modules.Peak_Hour_Notifier.override_clip_score",
            return_value={
                "id": "abc123",
                "score": 95.0,
                "tier": "queue",
            },
        ):
            self.assertIn(
                "clip abc123 is now score 95.0/100", chat.rank_next_clip("95")
            )


class PublishBackoffTests(unittest.TestCase):
    """Tests for the backoff retry logic in _publish_clip / process_auto_post_queue.

    Verifies:
    1. A failed publish increments attempt_count and sets next_eligible_at.
    2. A clip with next_eligible_at in the future is NOT retried.
    3. A clip with next_eligible_at in the past IS retried.
    4. After max_publish_attempts failures the clip is auto-held.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ready = self.root / "ready_to_post.json"
        self.config = self.root / "config.json"
        self.rejections = self.root / "post_rejections.jsonl"
        self.clip = self.root / "clip.mp4"
        self.clip.write_bytes(b"fake video")
        self.config.write_text(
            '{"min_clip_score": 65, "auto_posting": {'
            '"enabled": true, "review_window_minutes": 30, '
            '"auto_post_if_deadline_missed": true, '
            '"max_publish_attempts": 3, "min_retry_gap_minutes": 5}}'
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

    def test_failed_publish_increments_attempt_and_sets_next_eligible(self):
        from datetime import timedelta
        now = datetime.fromisoformat("2026-05-27T19:00:00-05:00")
        with (
            self._patch_files(),
            patch.object(notifier, "_now", return_value=now),
            patch.object(notifier, "_send_discord"),
            patch(
                "modules.TikTok_Publisher.publish_clip",
                return_value={"success": False, "error": "tiktok api down"},
            ),
        ):
            notifier.queue_clip(str(self.clip), "Test", ["#Gaming"], score=90)
            # Force the plan into a state where publish will fire:
            # deadline in the past, status=awaiting_approval.
            data = notifier._load_ready()
            plan = data["clips"][0]["auto_post"]
            plan["status"] = "awaiting_approval"
            plan["scheduled_for"] = (now - timedelta(minutes=1)).isoformat()
            plan["review_starts_at"] = (now - timedelta(minutes=31)).isoformat()
            plan["approval_deadline"] = (now - timedelta(minutes=1)).isoformat()
            notifier._save_ready(data)
            stats = notifier.process_auto_post_queue(now)
            data = notifier._load_ready()
            plan = data["clips"][0]["auto_post"]

        self.assertEqual(stats["failed"], 1)
        self.assertEqual(plan["attempt_count"], 1)
        self.assertIn("next_eligible_at", plan)
        self.assertEqual(plan["status"], "publish_failed")
        # next_eligible should be 5 min in the future (config default).
        expected = now + timedelta(minutes=5)
        actual = datetime.fromisoformat(plan["next_eligible_at"])
        self.assertEqual(actual, expected)

    def test_publish_failed_clip_not_retried_before_next_eligible(self):
        now = datetime.fromisoformat("2026-05-27T19:00:00-05:00")
        with (
            self._patch_files(),
            patch.object(notifier, "_now", return_value=now),
            patch.object(notifier, "_send_discord"),
            patch(
                "modules.TikTok_Publisher.publish_clip",
                return_value={"success": False, "error": "transient"},
            ) as publish,
        ):
            notifier.queue_clip(str(self.clip), "Test", ["#Gaming"], score=90)
            data = notifier._load_ready()
            plan = data["clips"][0]["auto_post"]
            plan["status"] = "awaiting_approval"
            plan["scheduled_for"] = (now.replace(hour=18, minute=0)).isoformat()
            plan["review_starts_at"] = (now.replace(hour=17, minute=30)).isoformat()
            plan["approval_deadline"] = (now.replace(hour=18, minute=0)).isoformat()
            notifier._save_ready(data)

            # First attempt fails
            notifier.process_auto_post_queue(now)
            self.assertEqual(publish.call_count, 1)

            # Run again immediately — should NOT retry (still in backoff window)
            publish.reset_mock()
            stats = notifier.process_auto_post_queue(now)

        self.assertEqual(publish.call_count, 0,
                         "publish_clip should not be called during backoff window")
        self.assertEqual(stats["failed"], 0)
        self.assertEqual(stats["posted"], 0)

    def test_publish_failed_clip_retried_after_next_eligible(self):
        from datetime import timedelta
        now = datetime.fromisoformat("2026-05-27T19:00:00-05:00")
        later = datetime.fromisoformat("2026-05-27T19:10:00-05:00")  # 10 min later
        with (
            self._patch_files(),
            patch.object(notifier, "_now", return_value=now),
            patch.object(notifier, "_send_discord"),
            patch(
                "modules.TikTok_Publisher.publish_clip",
                side_effect=[
                    {"success": False, "error": "transient"},
                    {"success": True, "url": "https://example.com/post"},
                ],
            ) as publish,
        ):
            notifier.queue_clip(str(self.clip), "Test", ["#Gaming"], score=90)
            data = notifier._load_ready()
            plan = data["clips"][0]["auto_post"]
            plan["status"] = "awaiting_approval"
            # Deadline 1 min ago so process_auto_post_queue will fire.
            plan["scheduled_for"] = (now - timedelta(minutes=1)).isoformat()
            plan["review_starts_at"] = (now - timedelta(minutes=31)).isoformat()
            plan["approval_deadline"] = (now - timedelta(minutes=1)).isoformat()
            notifier._save_ready(data)

            # First attempt fails
            notifier.process_auto_post_queue(now)
            self.assertEqual(publish.call_count, 1)

            # 10 min later: backoff window has passed, should retry and succeed
            stats = notifier.process_auto_post_queue(later)
            self.assertEqual(publish.call_count, 2)
            self.assertEqual(stats["posted"], 1)
            data = notifier._load_ready()
            self.assertEqual(data["clips"][0]["status"], "posted")
            self.assertEqual(data["clips"][0]["auto_post"]["attempt_count"], 2)

    def test_clip_held_after_max_failed_attempts(self):
        from datetime import timedelta
        # max=2 so the test is quick.
        self.config.write_text(
            '{"min_clip_score": 65, "auto_posting": {'
            '"enabled": true, "review_window_minutes": 30, '
            '"auto_post_if_deadline_missed": true, '
            '"max_publish_attempts": 2, "min_retry_gap_minutes": 5}}'
        )
        now = datetime.fromisoformat("2026-05-27T19:00:00-05:00")
        later1 = datetime.fromisoformat("2026-05-27T19:10:00-05:00")
        later2 = datetime.fromisoformat("2026-05-27T19:20:00-05:00")

        with (
            self._patch_files(),
            patch.object(notifier, "_now", return_value=now),
            patch.object(notifier, "_send_discord"),
            patch(
                "modules.TikTok_Publisher.publish_clip",
                return_value={"success": False, "error": "rate limited"},
            ),
        ):
            notifier.queue_clip(str(self.clip), "Test", ["#Gaming"], score=90)
            data = notifier._load_ready()
            plan = data["clips"][0]["auto_post"]
            plan["status"] = "awaiting_approval"
            plan["scheduled_for"] = (now - timedelta(minutes=1)).isoformat()
            plan["review_starts_at"] = (now - timedelta(minutes=31)).isoformat()
            plan["approval_deadline"] = (now - timedelta(minutes=1)).isoformat()
            notifier._save_ready(data)

            notifier.process_auto_post_queue(now)    # attempt 1
            notifier.process_auto_post_queue(later1)  # attempt 2 — should hold
            data = notifier._load_ready()
            clip = data["clips"][0]
            plan = clip["auto_post"]

            # After 2 attempts, clip should be auto-held.
            self.assertEqual(clip["status"], "held")
            self.assertIn("publish_failed_after_2_attempts", clip["hold_reason"])
            self.assertIn("rate limited", clip["hold_reason"])
            self.assertEqual(plan["status"], "held_after_retries")
            # A third process call should NOT touch it (held clips are filtered out).
            before_count = plan["attempt_count"]
            notifier.process_auto_post_queue(later2)
            after_count = notifier._load_ready()["clips"][0]["auto_post"]["attempt_count"]
            self.assertEqual(before_count, after_count,
                             "held clip should not be retried further")


if __name__ == "__main__":
    unittest.main()
