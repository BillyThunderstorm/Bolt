"""Tests for the Creator Command Center (bolt mission)."""

from __future__ import annotations

import json
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

from modules import Command_Center as cc  # noqa: E402


class CommandCenterTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.missions = self.tmp / "missions"
        self.missions.mkdir()
        self.skill = self.tmp / "SKILL.md"
        self.skill.write_text("# Playbook\n\nTest skill body.\n", encoding="utf-8")
        self.profile = self.tmp / "user_profile.json"
        self.profile.write_text(
            json.dumps(
                {
                    "vision": {"career_goal": "Honest product reviewer."},
                    "hard_constraints": [
                        {"id": "C6", "text": "authenticity first"}
                    ],
                    "near_term_horizon": {
                        "target_date": "2026-12-31",
                        "success_is": "Direction plus proof, not a finished career.",
                    },
                }
            ),
            encoding="utf-8",
        )
        self.catalog = self.tmp / "catalog.json"
        self.catalog.write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "name": "Test Mic",
                            "lane": "tech",
                            "status": "idea",
                            "asin": "B0TESTMIC01",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        self.patches = [
            patch.object(cc, "MISSIONS_DIR", self.missions),
            patch.object(cc, "SKILL_FILE", self.skill),
            patch.object(cc, "USER_PROFILE", self.profile),
            patch.object(cc, "CATALOG_FILE", self.catalog),
            patch.object(cc, "STOREFRONT_FILE", self.tmp / "missing_store.json"),
            patch.object(
                cc,
                "_week_snapshot",
                lambda: {
                    "this_week": "tech",
                    "this_week_note": "",
                    "this_week_done": [],
                    "last_week": "",
                    "last_week_note": "",
                    "bans": ["snail care as this week's post"],
                },
            ),
            patch.object(
                cc,
                "_kept_candidates",
                lambda limit=6: [
                    {
                        "name": "MKBHD (Marques Brownlee)",
                        "platform": "YouTube",
                        "why": "Long-form tech reviews with HQ visits.",
                    }
                ],
            ),
            patch.object(
                cc,
                "_research_snapshot",
                lambda: {
                    "research_log_total": 3,
                    "candidates_pending_c5": 0,
                    "candidates_kept": 1,
                    "next_action": "Stay on this week's tech lane.",
                    "user_career_goal": "Honest product reviewer.",
                },
            ),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self._tmp.cleanup()

    def test_load_playbook(self):
        text = cc.load_playbook()
        self.assertIn("Playbook", text)

    def test_checkin_has_five_questions(self):
        qs = cc.checkin_questions()
        self.assertEqual(len(qs), 5)
        self.assertTrue(all("prompt" in q and "why" in q for q in qs))

    def test_start_mission_writes_file(self):
        path = cc.start_mission(
            "fund a new mic",
            hours="6",
            budget="50",
            assets="OBS, USB mic",
            use_nexus=False,
        )
        self.assertTrue(path.exists())
        body = path.read_text(encoding="utf-8")
        self.assertIn("fund a new mic", body)
        self.assertIn("Mission title and objective", body)
        self.assertIn("Printable checklist", body)
        self.assertIn("Honest product reviewer", body)
        self.assertIn("authenticity first", body)
        self.assertTrue("50" in body)
        self.assertIn("Direction plus proof", body)
        self.assertIn("2026-12-31", body)
        self.assertIn("Test Mic", body)
        self.assertIn("This week:** tech", body)
        self.assertIn("MKBHD", body)
        self.assertNotIn("_(Where · what to enter/create", body)
        self.assertIn("**Do this first:**", body)
        self.assertIn("billycarter-20", body)

    def test_list_and_latest(self):
        cc.start_mission("goal one", use_nexus=False)
        cc.start_mission("goal two", use_nexus=False)
        files = cc.list_missions()
        self.assertEqual(len(files), 2)
        latest = cc.latest_mission()
        self.assertIsNotNone(latest)
        self.assertIn("goal-two", latest.name)

    def test_resolve_mission_latest(self):
        path = cc.start_mission("resolve me", use_nexus=False)
        self.assertEqual(cc.resolve_mission("latest"), path)

    def test_extract_next_command(self):
        md = "## 13. Next command\n\nDo the thing\n\n---\n"
        self.assertIn("Do the thing", cc.extract_next_command(md))

    def test_status_shape(self):
        s = cc.status()
        self.assertTrue(s["skill_present"])
        self.assertEqual(s["mission_count"], 0)

    def test_cli_start_and_list(self):
        code = cc.main(
            [
                "start",
                "cli goal",
                "--hours",
                "4",
                "--budget",
                "20",
                "--no-nexus",
            ]
        )
        self.assertEqual(code, 0)
        code = cc.main(["list"])
        self.assertEqual(code, 0)
        self.assertEqual(cc.status()["mission_count"], 1)

    def test_start_requires_goal(self):
        with self.assertRaises(ValueError):
            cc.start_mission("  ", use_nexus=False)

    def test_mission_status_speaks_latest(self):
        cc.start_mission("fund a new mic", hours="6", budget="50", assets="OBS", use_nexus=False)
        spoken = cc.mission_status()
        self.assertIn("fund a new mic", spoken)
        self.assertIn("Planning only", spoken)
        self.assertIn("Next command", spoken)

    def test_mission_status_empty(self):
        spoken = cc.mission_status()
        self.assertIn("No missions", spoken)

    def test_update_checkin_patches_table(self):
        path = cc.start_mission("patch me", use_nexus=False)
        cc.update_mission_checkin(path, hours="5", budget="25", assets="OBS, Test Mic")
        body = path.read_text(encoding="utf-8")
        self.assertIn("| Time available | 5 |", body)
        self.assertIn("| Max budget | 25 |", body)
        self.assertIn("| Already owned / usable | OBS, Test Mic |", body)
        fields = cc.parse_mission_fields(body)
        self.assertEqual(fields["hours"], "5")
        self.assertEqual(fields["budget"], "25")
        self.assertEqual(fields["assets"], "OBS, Test Mic")

    def test_fill_rebuilds_from_checkin(self):
        path = cc.start_mission("fill me", hours="4", budget="10", assets="OBS", use_nexus=False)
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "## 5. Mission strategy",
                "## 5. Mission strategy\n\n- **Offer:** WIPE ME",
            ),
            encoding="utf-8",
        )
        cc.fill_mission(path, use_nexus=False)
        body = path.read_text(encoding="utf-8")
        self.assertNotIn("WIPE ME", body)
        self.assertIn("fill me", body)
        self.assertIn("| Time available | 4 |", body)
        self.assertIn("Printable checklist", body)

    def test_cli_fill_and_update(self):
        self.assertEqual(
            cc.main(["start", "cli fill", "--hours", "3", "--no-nexus"]),
            0,
        )
        self.assertEqual(cc.main(["update", "latest", "--budget", "15", "--assets", "OBS"]), 0)
        self.assertEqual(cc.main(["fill", "latest", "--no-nexus"]), 0)
        latest = cc.latest_mission()
        self.assertIsNotNone(latest)
        body = latest.read_text(encoding="utf-8")
        self.assertIn("| Max budget | 15 |", body)
        self.assertIn("OBS", body)

    def test_sanitize_drops_invented_urls(self):
        evidence = {"catalog_items": [{"name": "Test Mic", "asin": "B0TESTMIC01"}]}
        cleaned = cc._sanitize_sources(
            [
                {"name": "owned", "url": "https://www.amazon.com/dp/B0TESTMIC01?tag=billycarter-20"},
                {"name": "invented", "url": "https://totally-real-grants.example/apply"},
                {"name": "playbook", "url": "Core/skills/creator-command-center/SKILL.md"},
            ],
            evidence,
        )
        urls = [s["url"] for s in cleaned]
        self.assertTrue(any("B0TESTMIC01" in u for u in urls))
        self.assertIn("Core/skills/creator-command-center/SKILL.md", urls)
        self.assertFalse(any("totally-real-grants" in u for u in urls))

    def test_extract_json_from_fenced_block(self):
        data = cc._extract_json('```json\n{"pitch": "hello", "steps": ["one"]}\n```')
        self.assertEqual(data["pitch"], "hello")
        self.assertEqual(data["steps"], ["one"])

    def test_upgrade_goal_does_not_lead_with_c5(self):
        path = cc.start_mission(
            "fund a new mic",
            hours="6",
            budget="50",
            assets="OBS, USB mic",
            use_nexus=False,
        )
        body = path.read_text(encoding="utf-8")
        self.assertIn("optional, justified upgrade", body)
        self.assertIn("is this the blocker", body)
        nxt = cc.extract_next_command(body)
        self.assertNotIn("bolt research pending", nxt)
        self.assertIn("do not buy", nxt.lower())

    def test_direction_goal_leads_with_c5_when_pending(self):
        with patch.object(
            cc,
            "_research_snapshot",
            lambda: {
                "research_log_total": 3,
                "candidates_pending_c5": 2,
                "candidates_kept": 1,
                "next_action": "Clear C5.",
            },
        ):
            path = cc.start_mission(
                "build a career from thin air",
                hours="8",
                budget="40",
                assets="OBS",
                use_nexus=False,
            )
        nxt = cc.extract_next_command(path.read_text(encoding="utf-8"))
        self.assertIn("bolt research pending", nxt)

    def test_goal_kind(self):
        self.assertEqual(cc._goal_kind("fund a new mic", "tech"), "upgrade")
        self.assertEqual(cc._goal_kind("build a career from thin air"), "direction")
        self.assertEqual(cc._goal_kind("first Amazon review", "tech"), "content")


if __name__ == "__main__":
    unittest.main()
