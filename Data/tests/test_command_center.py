"""Tests for the Creator Command Center (bolt mission)."""

from __future__ import annotations

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
            '{"vision": {"career_goal": "Honest product reviewer."},'
            ' "hard_constraints": [{"id": "C6", "text": "authenticity first"}]}',
            encoding="utf-8",
        )

        self.patches = [
            patch.object(cc, "MISSIONS_DIR", self.missions),
            patch.object(cc, "SKILL_FILE", self.skill),
            patch.object(cc, "USER_PROFILE", self.profile),
            patch.object(cc, "CATALOG_FILE", self.tmp / "missing_catalog.json"),
            patch.object(cc, "STOREFRONT_FILE", self.tmp / "missing_store.json"),
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


if __name__ == "__main__":
    unittest.main()
