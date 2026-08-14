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

    def test_tiktok_publish_status_reports_missing_creds(self):
        # With no real creds in .env, the status report should flag
        # exactly what's missing and give actionable next steps.
        st = cm.tiktok_publish_status()
        self.assertIn("checks", st)
        self.assertIn("next_steps", st)
        # ready=False unless someone has filled in real values
        self.assertFalse(st["ready"])
        # At least one of the next_steps should mention the OAuth flow
        self.assertTrue(any("tiktok_token" in s for s in st["next_steps"]))

    def test_tiktok_publish_status_with_fake_full_env(self):
        # Pretend .env is fully populated. Use a temp env file via
        # monkey-patching load_env.
        from modules import TikTok_Auth as auth
        real_load = auth.load_env

        def fake_load():
            return {
                "TIKTOK_CLIENT_KEY": "key123",
                "TIKTOK_CLIENT_SECRET": "secret-abc",
                "TIKTOK_ACCESS_TOKEN": "act.real.token",
                "TIKTOK_SCOPE": "user.info.basic,video.publish",
            }

        with mock.patch.object(auth, "load_env", fake_load):
            st = cm.tiktok_publish_status()
            self.assertTrue(st["ready"])
            self.assertTrue(all(c["ok"] for c in st["checks"]))
        # restore
        auth.load_env = real_load

    def test_tiktok_publish_item_refuses_without_approve(self):
        # The approval gate must be enforced — even with valid creds.
        cm.add_item("PostMe", lane="tech", status="testing", asin="B0POST1")
        cm.add_note("PostMe", "Works fine")
        cm.build_draft("PostMe", format="short")
        cm.mark_ready("PostMe")
        with self.assertRaises(PermissionError) as ctx:
            cm.tiktok_publish_item("PostMe", approve=False)
        self.assertIn("--approve", str(ctx.exception).lower())

    def test_tiktok_publish_dry_run_does_not_touch_network(self):
        # Build a draft, dry-run should report what would happen
        # without actually publishing.
        cm.add_item("DryRunMe", lane="tech", status="testing", asin="B0DRY1")
        cm.add_note("DryRunMe", "Sample note")
        cm.build_draft("DryRunMe", format="short")
        # build_draft itself moves testing -> drafting; that's documented.
        # The dry-run must NOT advance it further (still 'drafting', not
        # 'ready' or 'posted').
        result = cm.tiktok_publish_dry_run("DryRunMe")
        self.assertEqual(result["name"], "DryRunMe")
        self.assertIn("publisher_status", result)
        still = next(
            i for i in cm.list_items() if i["name"] == "DryRunMe"
        )
        self.assertEqual(still["status"], "drafting")

    def test_tiktok_publish_item_with_mocked_publisher(self):
        # Mock the actual TikTok call to confirm the bridge advances
        # the catalog to 'posted' on success.
        from modules import TikTok_Publisher as tp

        def fake_publish(video_path, title, hashtags=None, **kwargs):
            return {
                "success": True,
                "publish_id": "pub_abc",
                "url": "https://www.tiktok.com/video/abc",
            }

        cm.add_item("MockedPost", lane="tech", status="testing", asin="B0MOCK1")
        cm.add_note("MockedPost", "Good value")
        cm.build_draft("MockedPost", format="short")
        cm.mark_ready("MockedPost")

        with mock.patch.object(tp, "publish_clip", fake_publish):
            with mock.patch.object(cm, "tiktok_publish_status",
                                   return_value={"ready": True, "checks": [], "next_steps": []}):
                # Touch a real video file so the path-resolution check passes
                fake_video = cm.REPO_ROOT / "media" / "clips" / "mockedpost.mp4"
                fake_video.parent.mkdir(parents=True, exist_ok=True)
                fake_video.write_bytes(b"")
                try:
                    result = cm.tiktok_publish_item("MockedPost", approve=True)
                    self.assertTrue(result["success"])
                    self.assertEqual(result["url"], "https://www.tiktok.com/video/abc")
                    self.assertEqual(
                        result["post_record"]["catalog_item"]["status"], "posted"
                    )
                    self.assertEqual(
                        result["post_record"]["review_entry"]["name"], "MockedPost"
                    )
                finally:
                    fake_video.unlink(missing_ok=True)

    def test_youtube_package_shape_and_lengths(self):
        cm.add_item("Webcam", lane="tech", status="testing", asin="B0CAM1")
        cm.add_note("Webcam", "Image is sharp; mic is weak")
        cm.add_note("Webcam", "Mounting clip is awkward")
        cm.build_draft("Webcam", format="short")
        pkg = cm.build_youtube_package("Webcam")
        self.assertEqual(pkg["platform"], "youtube")
        self.assertEqual(pkg["platform_status"], "manual_assisted")
        # Title length within YouTube's 100-char limit
        self.assertLessEqual(len(pkg["title"]), 100)
        # Description within YouTube's 5000-char limit
        self.assertLessEqual(len(pkg["description"]), 5000)
        # Each tag is short and there are not too many
        self.assertLessEqual(len(pkg["tags"]), 15)
        for t in pkg["tags"]:
            self.assertLessEqual(len(t), 30)
        # The package points at the YouTube studio and gives a next step
        self.assertIn("studio.youtube.com", pkg["upload_url"])
        self.assertIn("mark-posted", pkg["next_step"])
        # Disclosure language is present
        self.assertIn("affiliate", pkg["description"].lower())

    def test_youtube_package_handles_missing_asin(self):
        # When the catalog item has no ASIN, the description should
        # explain that, not silently include a broken link.
        cm.add_item("NoAsinYet", lane="tech", status="testing")
        cm.add_note("NoAsinYet", "TBD review")
        cm.build_draft("NoAsinYet", format="short")
        pkg = cm.build_youtube_package("NoAsinYet")
        self.assertIn("add ASIN", pkg["description"])

    def test_x_package_within_280_chars(self):
        cm.add_item("Mouse", lane="tech", status="testing", asin="B085HNRKPX")
        cm.add_note("Mouse", "Comfortable grip")
        cm.build_draft("Mouse", format="short")
        pkg = cm.build_x_package("Mouse")
        self.assertEqual(pkg["platform"], "x")
        self.assertEqual(pkg["platform_status"], "manual_assisted")
        # X post must be <= 280 chars
        self.assertLessEqual(len(pkg["post_text"]), 280)
        # Hashtags are present and short
        self.assertGreater(len(pkg["hashtags"]), 0)
        self.assertLessEqual(len(pkg["hashtags"]), 3)
        # Disclosure is in the body
        self.assertIn("affiliate", pkg["post_text"].lower())
        # Points at the X compose UI and gives a next step
        self.assertIn("x.com/compose", pkg["upload_url"])
        self.assertIn("mark-posted", pkg["next_step"])

    def test_youtube_and_x_readiness_reports_manual_mode(self):
        # Until the OAuth app is reviewed, both readiness reports
        # should be ready=False but with a clear 'manual pkg available'
        # message and concrete next steps.
        for readiness in (cm.youtube_readiness(), cm.x_readiness()):
            self.assertFalse(readiness["ready"])
            # At least one of the checks should confirm the manual pkg
            # generator is available.
            ok_checks = [c for c in readiness["checks"] if c["ok"]]
            self.assertTrue(ok_checks, "at least one ok check should be present")
            self.assertTrue(
                any("pkg" in c["detail"] for c in ok_checks),
                f"no 'pkg' mention in any ok check: {ok_checks}",
            )
            self.assertGreater(len(readiness["next_steps"]), 0)
            self.assertTrue(
                any("mark-posted" in s for s in readiness["next_steps"])
            )

    def test_youtube_and_x_packages_require_draft(self):
        # No draft, no package.
        cm.add_item("NoDraftM12", lane="tech", status="testing")
        with self.assertRaises(ValueError) as yt_ctx:
            cm.build_youtube_package("NoDraftM12")
        self.assertIn("no draft", str(yt_ctx.exception).lower())
        with self.assertRaises(ValueError) as x_ctx:
            cm.build_x_package("NoDraftM12")
        self.assertIn("no draft", str(x_ctx.exception).lower())

    def test_sponsors_add_creates_and_dedupes(self):
        # Adding a new prospect should create a row at 'prospect' stage.
        row = cm.sponsors_add("WD-40", lanes=["tech"], type="brand", fit=4)
        self.assertEqual(row["name"], "WD-40")
        self.assertEqual(row["status"], "prospect")
        self.assertEqual(row["fit"], 4)
        self.assertIn("tech", row["lanes"])
        # Adding the same name again returns the existing row, not a duplicate.
        again = cm.sponsors_add("WD-40", lanes=["game"], fit=10)
        self.assertEqual(again["id"], row["id"])
        # Fit should NOT have been overwritten by the second add.
        self.assertEqual(again["fit"], 4)

    def test_sponsors_enrich_appends_note_and_optional_status_change(self):
        cm.sponsors_add("Corsair", lanes=["tech", "game"], fit=8)
        enriched = cm.sponsors_enrich(
            "Corsair",
            note="Found creator-program page; sent DM on X",
            link="https://x.com/corsair/status/123",
            mark_contacted=True,
        )
        self.assertEqual(enriched["status"], "contacted")
        # The note was appended...
        last_note = enriched["notes"][-1]
        self.assertIn("creator-program", last_note["text"])
        self.assertIn("x.com", last_note["link"])
        # ...and an outreach entry was recorded for the status change.
        statuses = [o.get("status") for o in enriched["outreach"]]
        self.assertIn("contacted", statuses)

    def test_sponsors_enrich_without_mark_contacted_keeps_status(self):
        cm.sponsors_add("BenQ", lanes=["tech"], fit=6)
        # First call: just a note, no status change.
        first = cm.sponsors_enrich("BenQ", note="Saw a sale on Amazon")
        self.assertEqual(first["status"], "prospect")
        # Second call: enrich with --mark-contacted should advance.
        second = cm.sponsors_enrich("BenQ", note="Sent pitch", mark_contacted=True)
        self.assertEqual(second["status"], "contacted")

    def test_sponsors_enrich_unknown_raises(self):
        # Can't enrich a prospect that doesn't exist.
        with self.assertRaises(ValueError) as ctx:
            cm.sponsors_enrich("NeverExistedBrand", note="test")
        self.assertIn("add it first", str(ctx.exception).lower())

    def test_sponsors_pipeline_summary(self):
        # Add a few prospects in different states, confirm the summary
        # correctly counts by stage and surfaces the highest-fit
        # uncontacted one.
        cm.sponsors_add("BrandA", lanes=["tech"], fit=8)
        cm.sponsors_add("BrandB", lanes=["game"], fit=9)
        cm.sponsors_add("BrandC", lanes=["tech"], fit=5)
        # Advance BrandB through pitch -> contacted
        cm.sponsors_pitch("BrandB")
        cm.sponsors_enrich("BrandB", note="Sent", mark_contacted=True)
        # Mark BrandA as won
        cm.sponsors_log("BrandA", "won", note="closed deal")
        pipe = cm.sponsors_pipeline()
        self.assertIn("by_stage", pipe)
        self.assertIn("total", pipe)
        self.assertIn("active", pipe)
        self.assertIn("top_fit_uncontacted", pipe)
        # BrandB should be in 'contacted', BrandA in 'won'.
        # Note: the seed list in sponsors.json may also have prospects;
        # we only assert the things we know we added.
        # BrandC is fit=5 still at 'prospect'. BrandB is fit=9 at
        # 'contacted', not in 'uncontacted'. So the top uncontacted
        # we added is BrandC (fit=5) — but the seed list may have a
        # higher-fit uncontacted prospect. We just assert our
        # BrandC is among the uncontacted options.
        uncontacted_names = {p["name"] for p in cm.load_sponsors()["prospects"]
                             if p.get("status") in ("prospect", "pitch_ready")}
        self.assertIn("BrandC", uncontacted_names)

    def test_sponsors_research_attaches_results_and_finds_email(self):
        cm.sponsors_add("ResearchBrand", lanes=["tech"], fit=7)
        fake_results = [
            {
                "url": "https://researchbrand.example.com/creators",
                "title": "ResearchBrand Creator Program",
                "description": (
                    "Email partnerships@researchbrand.example.com to apply. "
                    "We pay in product + commission."
                ),
            },
            {
                "url": "https://researchbrand.example.com/about",
                "title": "About Us",
                "description": "We make widgets.",
            },
        ]
        updated = cm.sponsors_research(
            "ResearchBrand", query="ResearchBrand creator program", results=fake_results
        )
        self.assertIn("research_log", updated)
        self.assertEqual(len(updated["research_log"]), 1)
        log = updated["research_log"][0]
        self.assertEqual(log["query"], "ResearchBrand creator program")
        self.assertEqual(log["result_count"], 2)
        self.assertEqual(len(log["results"]), 2)
        # The first plausible email was auto-extracted.
        self.assertEqual(updated["contact"], "partnerships@researchbrand.example.com")
        # A note was added explaining where the contact came from.
        last_note = updated["notes"][-1]
        self.assertIn("Auto-set contact", last_note["text"])
        self.assertIn("partnerships@", last_note["text"])

    def test_sponsors_research_skips_noreply_emails(self):
        # If the only emails found are noreply addresses, contact
        # should stay empty rather than get a useless value.
        cm.sponsors_add("NoReplyCo", lanes=["tech"], fit=4)
        fake_results = [
            {
                "url": "https://noreplyco.example.com",
                "title": "NoReplyCo",
                "description": "Send questions to noreply@noreplyco.example.com.",
            },
        ]
        updated = cm.sponsors_research(
            "NoReplyCo", query="NoReplyCo contact", results=fake_results
        )
        self.assertNotIn("@", updated.get("contact", ""))
        self.assertEqual(updated.get("contact", ""), "")

    def test_sponsors_research_no_update_contact_keeps_existing(self):
        # If update_contact=False, the function shouldn't touch the
        # contact field even if an email is in the results.
        cm.sponsors_add("KeepContact", lanes=["tech"], fit=5, contact="existing@example.com")
        fake_results = [
            {"url": "https://x.example", "title": "X", "description": "Email new@example.com"},
        ]
        updated = cm.sponsors_research(
            "KeepContact", query="test", results=fake_results, update_contact=False
        )
        self.assertEqual(updated["contact"], "existing@example.com")

    def test_sponsors_research_handles_empty_results(self):
        # Empty results list: research_log still gets an entry, but
        # result_count=0 and no auto-contact.
        cm.sponsors_add("QuietBrand", lanes=["tech"], fit=5)
        updated = cm.sponsors_research("QuietBrand", query="QuietBrand info", results=[])
        self.assertEqual(updated["research_log"][-1]["result_count"], 0)
        self.assertNotIn("@", updated.get("contact", ""))

    def test_sponsors_research_unknown_prospect_raises(self):
        with self.assertRaises(ValueError) as ctx:
            cm.sponsors_research("DoesNotExist", query="x", results=[])
        self.assertIn("add it first", str(ctx.exception).lower())

    def test_sponsors_research_empty_query_raises(self):
        cm.sponsors_add("TestBrand", lanes=["tech"], fit=5)
        with self.assertRaises(ValueError) as ctx:
            cm.sponsors_research("TestBrand", query="   ", results=[])
        self.assertIn("empty", str(ctx.exception).lower())

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

    def test_parse_review_json_and_text_blocks(self):
        rows = cm.parse_review_text(
            json.dumps(
                [
                    {
                        "name": "ORYNA Hydrogen Water Bottle",
                        "asin": "B0FXVX5T5M",
                        "rating": 5,
                        "text": "I use it every day.",
                    }
                ]
            )
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["asin"], "B0FXVX5T5M")
        self.assertEqual(rows[0]["rating"], 5.0)
        self.assertEqual(rows[0]["lane"], "product")

        blocks = cm.parse_review_text(
            "Name: Budget Lavalier Mic\nASIN: B0H5WXNPZN\nRating: 5\n"
            "Review: Clear audio, easy to charge.\n"
        )
        self.assertEqual(blocks[0]["name"], "Budget Lavalier Mic")
        self.assertEqual(blocks[0]["lane"], "tech")
        self.assertEqual(blocks[0]["asin"], "B0H5WXNPZN")

    def test_parse_review_html_marks_purchase_prompts_unposted(self):
        html = """
        <html><title>Review Your Purchases</title>
        <a href="/dp/B0FTWQG28M">K&amp;F CONCEPT Phone Holder</a>
        <p>Review your purchases</p>
        </html>
        """
        rows = cm.parse_review_html(html)
        self.assertTrue(rows)
        self.assertEqual(rows[0]["asin"], "B0FTWQG28M")
        self.assertFalse(rows[0]["posted"])

    def test_record_existing_review_skips_draft_loop(self):
        result = cm.record_existing_review(
            "ORYNA Hydrogen Water Bottle",
            asin="B0FXVX5T5M",
            rating=5,
            text="I use it every day.",
            url="https://www.amazon.com/dp/B0FXVX5T5M",
        )
        item = result["catalog_item"]
        self.assertEqual(item["status"], "posted")
        self.assertEqual(item["posted_platforms"], ["amazon"])
        self.assertEqual(item["verdict"], "5 stars on Amazon")
        self.assertEqual(result["review_entry"]["kind"], "import")
        self.assertEqual(cm.shipped_summary()["total"], 1)
        store = cm.store_list()
        self.assertEqual(store[0]["asin"], "B0FXVX5T5M")

    def test_record_existing_review_dedupes_by_asin(self):
        cm.record_existing_review("Mouse", asin="B085HNRKPX", rating=5, text="Cute and light.")
        again = cm.record_existing_review(
            "Wireless Mouse", asin="B085HNRKPX", rating=5, text="Still love it."
        )
        mice = [
            i for i in cm.load_catalog()["items"] if (i.get("asin") or "") == "B085HNRKPX"
        ]
        self.assertEqual(len(mice), 1)
        self.assertTrue(again["skipped"])
        self.assertEqual(cm.shipped_summary()["total"], 1)

    def test_import_inbox_json_moves_file(self):
        inbox = cm.DOCS_REVIEWS / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        payload = [
            {
                "name": "Zeadio Phone Stabilizer",
                "asin": "B07939PF1Q",
                "rating": 5,
                "text": "Holds the phone steady.",
            }
        ]
        (inbox / "reviews.json").write_text(json.dumps(payload), encoding="utf-8")
        report = cm.import_inbox()
        self.assertEqual(report["imported"], 1)
        self.assertFalse((inbox / "reviews.json").exists())
        self.assertTrue((cm.DOCS_REVIEWS / "imported" / "reviews.json").exists())
        item = cm._find_item(cm.load_catalog(), "Zeadio Phone Stabilizer")
        self.assertIsNotNone(item)
        self.assertEqual(item["status"], "posted")
        self.assertEqual(item["asin"], "B07939PF1Q")

    def test_import_inbox_dry_run_leaves_files(self):
        inbox = cm.DOCS_REVIEWS / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox / "one.txt").write_text(
            "Name: Test Serum\nASIN: B0CNDCKXDX\nRating: 4\nReview: Fine so far.\n",
            encoding="utf-8",
        )
        report = cm.import_inbox(apply=False)
        self.assertEqual(report["imported"], 1)
        self.assertTrue((inbox / "one.txt").exists())
        self.assertEqual(cm.load_catalog().get("items"), [])

    def test_import_inbox_empty(self):
        report = cm.import_inbox()
        self.assertEqual(report["files"], 0)
        self.assertEqual(report["imported"], 0)

    def test_infer_review_lane(self):
        self.assertEqual(cm.infer_review_lane("Budget Lavalier Mic"), "tech")
        self.assertEqual(cm.infer_review_lane("Rice Peel Shot"), "skincare")
        self.assertEqual(cm.infer_review_lane("Incense Sticks"), "product")


if __name__ == "__main__":
    unittest.main()
