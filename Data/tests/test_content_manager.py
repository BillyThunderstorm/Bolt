"""Tests for Bolt Content Manager — catalog, morning phrase, store, sponsors."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_repo_root = Path(__file__).resolve().parents[2]
_core = _repo_root / "Core"
if str(_core) not in sys.path:
    sys.path.insert(0, str(_core))

from modules import Content_Manager as cm  # noqa: E402


class ContentManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        content = root / "content"
        business = root / "business"
        briefings = root / "briefings"
        reviews = root / "reviews"
        content.mkdir()
        business.mkdir()
        briefings.mkdir()
        reviews.mkdir()

        self.patches = [
            mock.patch.object(cm, "CONTENT_DIR", content),
            mock.patch.object(cm, "BUSINESS_DIR", business),
            mock.patch.object(cm, "BRIEFINGS_DIR", briefings),
            mock.patch.object(cm, "DOCS_REVIEWS", reviews),
            mock.patch.object(cm, "CATALOG_FILE", content / "catalog.json"),
            mock.patch.object(cm, "STOREFRONT_FILE", content / "storefront.json"),
            mock.patch.object(cm, "SPONSORS_FILE", content / "sponsors.json"),
            mock.patch.object(cm, "SOCIAL_FILE", content / "social_connections.json"),
            mock.patch.object(cm, "REVIEW_TRACKER", reviews / "review_tracker.json"),
            mock.patch.object(cm, "BUSINESS_PLAYBOOK", business / "business-playbook.md"),
            mock.patch.object(cm, "ADVANCEMENT_FILE", business / "bolt-advancement.md"),
        ]
        for p in self.patches:
            p.start()
        cm._ensure_seed_files()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_add_and_note(self):
        item = cm.add_item("Test Headset", lane="tech", status="testing")
        self.assertEqual(item["lane"], "tech")
        updated = cm.add_note("Test Headset", "Mic is clear", day=1)
        self.assertEqual(len(updated["notes_log"]), 1)

    def test_preferred_lane_sort(self):
        cm.add_item("Serum", lane="skincare")
        cm.add_item("FPS Title", lane="game")
        items = cm.list_items()
        self.assertEqual(items[0]["lane"], "game")

    def test_draft_includes_affiliate_tag(self):
        cm.add_item("Mouse", lane="tech", asin="B00TEST123")
        draft = cm.build_draft("Mouse", format="short")
        self.assertIn("billycarter-20", draft["affiliate_link"])
        self.assertIn("Hook:", draft["script"])

    def test_good_morning_phrase(self):
        self.assertTrue(cm.is_good_morning_phrase("Good Morning Bolt"))
        self.assertTrue(cm.is_good_morning_phrase("morning bolt!"))
        self.assertFalse(cm.is_good_morning_phrase("good night bolt"))

    def test_morning_briefing_file(self):
        result = cm.morning(speak_aloud=False)
        self.assertIn("William", result["spoken"])
        self.assertTrue(Path(result["path"]).exists())

    def test_store_and_feature(self):
        cm.store_add("Keyboard", asin="B0KEY123", category="tech")
        items = cm.store_list()
        self.assertEqual(len(items), 1)
        self.assertIn("billycarter-20", items[0]["affiliate_link"])
        feat = cm.store_feature_next()
        self.assertIn("message", feat)

    def test_store_missing_asins_and_summary(self):
        # Add one item with an ASIN and one without — mirrors the
        # real-world M9 state ("Daily Driver Gaming Headset" without
        # ASIN, "Mouse" with ASIN B0...).
        cm.store_add("Headphones", asin="", category="tech")
        cm.store_add("Webcam", asin="B0ABC123", category="tech")
        missing = cm.store_missing_asins()
        self.assertEqual([m["name"] for m in missing], ["Headphones"])
        summary = cm.store_summary()
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["with_asin"], 1)
        self.assertEqual(summary["missing_asin"], 1)
        self.assertEqual(summary["missing_asin_names"], ["Headphones"])

    def test_store_add_records_verify_error_on_bad_asin(self):
        # No network: --verify with a fake ASIN should still save the
        # item, but record a verify_status of "error" or "no_match"
        # so the operator notices later.
        item = cm.store_add("Mystery Item", asin="B0ZZZZZZ", category="tech", verify=True)
        self.assertIn("asin", item)
        self.assertIn("verify_status", item)
        self.assertIn(item["verify_status"], {"ok", "no_match", "error"})

    def test_mark_ready_requires_draft(self):
        # An item with no draft can't be marked ready.
        cm.add_item("NoDraftYet", lane="tech", status="testing")
        with self.assertRaises(ValueError) as ctx:
            cm.mark_ready("NoDraftYet")
        self.assertIn("no draft", str(ctx.exception).lower())

    def test_mark_ready_then_posted_records_review(self):
        # Build a draft, mark it ready, then post it. The shipped
        # summary should reflect the post.
        cm.add_item("ShipMe", lane="tech", status="testing", asin="B0SHIP1")
        cm.add_note("ShipMe", "It works, sound is clear.")
        cm.add_note("ShipMe", "Mic arm is flimsy but the audio is good.")
        cm.build_draft("ShipMe", format="short")
        ready = cm.mark_ready("ShipMe", verdict="Recommended for budget buyers")
        self.assertEqual(ready["status"], "ready")
        self.assertEqual(ready["verdict"], "Recommended for budget buyers")

        result = cm.mark_posted(
            "ShipMe", platforms=["tiktok", "youtube_shorts"], where="vid_12345"
        )
        self.assertEqual(result["catalog_item"]["status"], "posted")
        self.assertEqual(result["catalog_item"]["posted_platforms"], ["tiktok", "youtube_shorts"])
        self.assertEqual(result["review_entry"]["name"], "ShipMe")
        self.assertEqual(result["review_entry"]["where"], "vid_12345")

        ship = cm.shipped_summary()
        self.assertEqual(ship["total"], 1)
        self.assertEqual(ship["by_lane"].get("tech"), 1)
        self.assertIsNotNone(ship["last_posted_at"])

        reviews = cm.shipped_reviews()
        self.assertEqual(reviews[0]["name"], "ShipMe")
        self.assertIn("tiktok", reviews[0]["platforms"])

    def test_mark_posted_refuses_unready_items(self):
        # An idea-status item (never tested, never drafted) can't be
        # marked posted.
        cm.add_item("NotReady", lane="tech", status="idea")
        with self.assertRaises(ValueError) as ctx:
            cm.mark_posted("NotReady", platforms=["tiktok"])
        self.assertIn("mark it ready", str(ctx.exception).lower())

    def test_sponsors_find_game(self):
        found = cm.sponsors_find(lane="game", limit=3)
        self.assertTrue(found)
        self.assertTrue(any("game" in p.get("lanes", []) for p in found))

    def test_sponsors_pitch(self):
        pitch = cm.sponsors_pitch("Razer")
        self.assertIn("Razer", pitch["subject"])
        self.assertIn("billycarter-20", pitch["body"])
        self.assertIn("@itssimplybilly", pitch["body"])

    def test_social_package_awaits_approval(self):
        cm.add_item("Controller", lane="game")
        entry = cm.social_package("Controller", ["tiktok", "x"])
        self.assertEqual(entry["status"], "awaiting_approval")
        self.assertEqual(len(entry["packages"]), 2)

    def test_next_actions_not_empty(self):
        actions = cm.next_actions()
        self.assertGreaterEqual(len(actions), 1)
        self.assertIn(actions[0]["type"], {"content", "business", "advance"})


if __name__ == "__main__":
    unittest.main()
