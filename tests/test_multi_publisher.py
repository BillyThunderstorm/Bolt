import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from modules import Multi_Publisher as mp
from modules import Peak_Hour_Notifier as notifier


class MultiPublisherTests(unittest.TestCase):
    def test_build_platform_plan_is_local_and_staggered(self):
        queued_at = datetime.fromisoformat("2026-05-27T13:00:00-05:00")

        plan = mp.build_platform_plan(
            clip_path="vertical_clips/highlight.mp4",
            title="Billy just erased the lobby.",
            hashtags=["Marvel Rivals", "#Gaming"],
            queued_at=queued_at,
            timezone="America/Chicago",
        )

        self.assertEqual(
            [item["platform"] for item in plan],
            [
                "tiktok",
                "youtube_shorts",
                "instagram_reels",
                "kick",
            ],
        )
        self.assertTrue(all(item["status"] == "manual_upload_ready" for item in plan))
        self.assertIn("#MarvelRivals", plan[0]["caption"])
        self.assertIn("#Shorts", plan[1]["description"])

    def test_queue_clip_embeds_and_persists_platform_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            clip = tmp_path / "clip.mp4"
            clip.write_bytes(b"fake video")
            ready_file = tmp_path / "ready_to_post.json"
            platform_file = tmp_path / "multi_platform_queue.json"

            with (
                patch.object(notifier, "READY_FILE", ready_file),
                patch.object(notifier, "CONFIG_FILE", tmp_path / "config.json"),
                patch.object(mp, "PLATFORM_QUEUE_FILE", platform_file),
            ):
                item = notifier.queue_clip(
                    clip_path=str(clip),
                    title="A free reach test.",
                    hashtags=["#Gaming"],
                    score=90,
                    tier="queue",
                )

            self.assertEqual(len(item["platform_plan"]), 4)
            self.assertTrue(ready_file.exists())
            self.assertTrue(platform_file.exists())


if __name__ == "__main__":
    unittest.main()
