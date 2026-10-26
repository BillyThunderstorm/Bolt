"""Product-cut approval schedules Buffer with no second confirmation."""

import json
import os
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

from modules import Buffer_Product_Posting as buffer
from modules import Multi_Publisher as mp
from modules import Peak_Hour_Notifier as notifier


RULE = _repo_root / "Data" / "configs" / "buffer_product_posting.json"


class RuleFileTests(unittest.TestCase):
    def test_locked_rule_names_both_channels_and_zero_extra_confirmations(self):
        rule = json.loads(RULE.read_text(encoding="utf-8"))
        self.assertEqual(rule["trigger"], "product_cut_approved")
        self.assertEqual(rule["confirmations_after_approval"], 0)
        self.assertEqual(rule["via"], "buffer")
        self.assertEqual(rule["mode"], "addToQueue")
        self.assertEqual(rule["scheduling_type"], "automatic")
        self.assertTrue(rule["enabled"])
        channels = rule["channels"]
        self.assertEqual(channels[0]["handle"], "@itssimplybilly")
        self.assertEqual(channels[0]["service"], "tiktok")
        self.assertIn("SimplyBilly", channels[1]["display_name"])
        self.assertIn("Tune in", channels[1]["display_name"])
        self.assertEqual(channels[1]["service"], "youtube")
        self.assertEqual(channels[0]["buffer_channel_id"], "")
        self.assertEqual(channels[1]["buffer_channel_id"], "")
        self.assertEqual(rule["credentials_env"], "BUFFER_ACCESS_TOKEN")
        self.assertNotIn("Bearer ", json.dumps(rule))


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.queue = root / "buffer_product_queue.json"
        self.catalog = root / "catalog.json"
        self.catalog.write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "id": "neck-holder",
                            "name": "Neck Holder",
                            "status": "drafting",
                            "last_draft": {"script": "Hook: it holds the phone."},
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        self.video = root / "cut.mp4"
        self.video.write_bytes(b"fake")
        self.patches = [
            patch.object(buffer, "QUEUE_FILE", self.queue),
            patch.object(buffer, "CATALOG_FILE", self.catalog),
            patch.object(buffer, "RULE_FILE", RULE),
            patch.dict(os.environ, {"BUFFER_ACCESS_TOKEN": ""}, clear=False),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_approval_enqueues_both_channels_without_a_token_or_second_prompt(self):
        calls = []

        def poster(token, query, variables):
            calls.append((token, query, variables))
            return {"ok": False, "error": "should not be called"}

        job = buffer.schedule_approved_product_cut(
            "Neck Holder",
            str(self.video),
            poster=poster,
            catalog_path=self.catalog,
        )

        self.assertTrue(job["ok"])
        self.assertFalse(job["scheduled"])
        self.assertEqual(job["status"], "awaiting_buffer_credentials")
        self.assertEqual(job["confirmations_after_approval"], 0)
        self.assertEqual(
            [ch["label"] for ch in job["channels"]],
            [
                "TikTok @itssimplybilly",
                "YouTube Shorts — Tune in, it’s SimplyBilly",
            ],
        )
        self.assertTrue(all(ch["status"] == "awaiting_buffer_credentials" for ch in job["channels"]))
        self.assertEqual(calls, [])
        saved = json.loads(self.queue.read_text(encoding="utf-8"))
        self.assertEqual(len(saved["items"]), 1)
        self.assertNotIn("bearer ", json.dumps(saved).lower())
        self.assertIn("BUFFER_ACCESS_TOKEN", saved["items"][0]["detail"])
        catalog = json.loads(self.catalog.read_text(encoding="utf-8"))
        draft = catalog["items"][0]["last_draft"]
        self.assertEqual(draft["buffer_job_id"], job["id"])
        self.assertEqual(draft["cut_approved_by"], "William")
        self.assertEqual(catalog["items"][0]["status"], "drafting")

    def test_second_approval_of_the_same_cut_does_not_duplicate_the_job(self):
        first = buffer.schedule_approved_product_cut(
            "Neck Holder", str(self.video), catalog_path=self.catalog
        )
        second = buffer.schedule_approved_product_cut(
            "Neck Holder", str(self.video), catalog_path=self.catalog
        )
        self.assertEqual(first["id"], second["id"])
        saved = json.loads(self.queue.read_text(encoding="utf-8"))
        self.assertEqual(len(saved["items"]), 1)

    def test_local_file_is_not_uploaded_even_when_a_token_exists(self):
        calls = []

        def poster(token, query, variables):
            calls.append(query)
            if "AccountOrgs" in query:
                return {
                    "ok": True,
                    "body": {"data": {"account": {"organizations": [{"id": "org1"}]}}},
                }
            if "GetChannels" in query:
                return {
                    "ok": True,
                    "body": {
                        "data": {
                            "channels": [
                                {
                                    "id": "aaaaaaaaaaaaaaaaaaaaaaaa",
                                    "name": "itssimplybilly",
                                    "service": "tiktok",
                                    "displayName": "Simply Billy",
                                },
                                {
                                    "id": "bbbbbbbbbbbbbbbbbbbbbbbb",
                                    "name": "SimplyBilly",
                                    "service": "youtube",
                                    "displayName": "Tune in, it's SimplyBilly",
                                },
                            ]
                        }
                    },
                }
            return {"ok": False, "error": "createPost should not run"}

        with patch.dict(os.environ, {"BUFFER_ACCESS_TOKEN": "secret-token"}):
            job = buffer.schedule_approved_product_cut(
                "Neck Holder",
                str(self.video),
                poster=poster,
                catalog_path=self.catalog,
            )

        self.assertEqual(job["status"], "awaiting_public_video_url")
        self.assertNotIn("CreatePost", " ".join(calls))
        self.assertEqual(job["channels"][0]["buffer_channel_id"], "aaaaaaaaaaaaaaaaaaaaaaaa")
        self.assertEqual(job["channels"][1]["buffer_channel_id"], "bbbbbbbbbbbbbbbbbbbbbbbb")
        blob = self.queue.read_text(encoding="utf-8")
        self.assertNotIn("secret-token", blob)

    def test_public_url_and_token_schedule_both_channels_automatically(self):
        seen = []

        def poster(token, query, variables):
            if "AccountOrgs" in query:
                return {
                    "ok": True,
                    "body": {"data": {"account": {"organizations": [{"id": "org1"}]}}},
                }
            if "GetChannels" in query:
                return {
                    "ok": True,
                    "body": {
                        "data": {
                            "channels": [
                                {
                                    "id": "aaaaaaaaaaaaaaaaaaaaaaaa",
                                    "name": "itssimplybilly",
                                    "service": "tiktok",
                                },
                                {
                                    "id": "bbbbbbbbbbbbbbbbbbbbbbbb",
                                    "name": "SimplyBilly",
                                    "service": "youtube",
                                    "displayName": "Tune in, it's SimplyBilly",
                                },
                            ]
                        }
                    },
                }
            if "CreatePost" in query:
                seen.append(variables["input"])
                channel_id = variables["input"]["channelId"]
                return {
                    "ok": True,
                    "body": {
                        "data": {
                            "createPost": {
                                "post": {
                                    "id": f"post-{channel_id[:4]}",
                                    "dueAt": "2026-10-27T01:00:00Z",
                                }
                            }
                        }
                    },
                }
            raise AssertionError(query)

        with patch.dict(os.environ, {"BUFFER_ACCESS_TOKEN": "secret-token"}):
            job = buffer.schedule_approved_product_cut(
                "Neck Holder",
                video_url="https://cdn.example.com/neck.mp4",
                poster=poster,
                catalog_path=self.catalog,
            )

        self.assertTrue(job["scheduled"])
        self.assertEqual(job["status"], "scheduled")
        self.assertEqual(len(seen), 2)
        modes = {row["mode"] for row in seen}
        kinds = {row["schedulingType"] for row in seen}
        self.assertEqual(modes, {"addToQueue"})
        self.assertEqual(kinds, {"automatic"})
        for row in seen:
            self.assertNotIn("needsApproval", row)
            self.assertEqual(row["assets"], [{"video": {"url": "https://cdn.example.com/neck.mp4"}}])
        youtube = next(row for row in seen if "youtube" in row["metadata"])
        tiktok = next(row for row in seen if "tiktok" in row["metadata"])
        self.assertEqual(youtube["metadata"]["youtube"]["title"], "Neck Holder")
        self.assertEqual(youtube["metadata"]["youtube"]["categoryId"], "26")
        self.assertEqual(tiktok["channelId"], "aaaaaaaaaaaaaaaaaaaaaaaa")
        self.assertEqual(youtube["channelId"], "bbbbbbbbbbbbbbbbbbbbbbbb")
        self.assertNotIn("secret-token", self.queue.read_text(encoding="utf-8"))

    def test_missing_video_does_not_write_a_job(self):
        job = buffer.schedule_approved_product_cut(
            "Neck Holder",
            str(Path(self.tmp.name) / "nope.mp4"),
            catalog_path=self.catalog,
        )
        self.assertFalse(job["ok"])
        self.assertEqual(job["status"], "video_missing")
        self.assertFalse(self.queue.exists())


class PeakQueueTests(unittest.TestCase):
    def test_stream_clip_approval_does_not_open_a_buffer_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            clip = tmp_path / "clip.mp4"
            clip.write_bytes(b"fake video")
            ready_file = tmp_path / "ready_to_post.json"
            platform_file = tmp_path / "multi_platform_queue.json"
            buffer_file = tmp_path / "buffer_product_queue.json"
            with (
                patch.object(notifier, "READY_FILE", ready_file),
                patch.object(notifier, "CONFIG_FILE", tmp_path / "config.json"),
                patch.object(mp, "PLATFORM_QUEUE_FILE", platform_file),
                patch.object(buffer, "QUEUE_FILE", buffer_file),
            ):
                item = notifier.queue_clip(
                    clip_path=str(clip),
                    title="A stream moment.",
                    hashtags=["#Gaming"],
                    score=90,
                    tier="queue",
                )
                approved = notifier.approve_next_clip(item["id"])
            self.assertEqual(approved["auto_post"]["status"], "approved")
            self.assertNotIn("buffer_job_id", approved)
            self.assertFalse(buffer_file.exists())

    def test_product_flag_and_approve_enqueues_buffer(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            clip = tmp_path / "cut.mp4"
            clip.write_bytes(b"fake video")
            ready_file = tmp_path / "ready_to_post.json"
            platform_file = tmp_path / "multi_platform_queue.json"
            buffer_file = tmp_path / "buffer_product_queue.json"
            catalog = tmp_path / "catalog.json"
            catalog.write_text(json.dumps({"items": []}), encoding="utf-8")
            with (
                patch.object(notifier, "READY_FILE", ready_file),
                patch.object(notifier, "CONFIG_FILE", tmp_path / "config.json"),
                patch.object(mp, "PLATFORM_QUEUE_FILE", platform_file),
                patch.object(buffer, "QUEUE_FILE", buffer_file),
                patch.object(buffer, "CATALOG_FILE", catalog),
                patch.object(buffer, "RULE_FILE", RULE),
                patch.dict(os.environ, {"BUFFER_ACCESS_TOKEN": ""}, clear=False),
            ):
                item = notifier.add_manual_clip(
                    clip,
                    title="Neck holder take",
                    approve=True,
                    product_name="Neck Holder",
                )
                posted = notifier.post_now(item["id"])
            self.assertEqual(posted["result"]["via"], "buffer")
            self.assertFalse(posted["result"]["paused"])
            self.assertEqual(item["content_kind"], "product")
            self.assertEqual(item["buffer_status"], "awaiting_buffer_credentials")
            saved = json.loads(buffer_file.read_text(encoding="utf-8"))
            self.assertEqual(saved["items"][0]["confirmations_after_approval"], 0)
            self.assertEqual(len(saved["items"][0]["channels"]), 2)


if __name__ == "__main__":
    unittest.main()
