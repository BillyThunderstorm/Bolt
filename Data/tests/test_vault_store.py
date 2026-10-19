"""Vault_Store safety: temp vaults only. Never touches tracked Data/ files."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_repo_root / "Core"))

from modules import Vault_Store as vs


class VaultPathTests(unittest.TestCase):
    def test_env_wins_over_config_and_default(self):
        with patch.dict(os.environ, {"BOLT_VAULT_PATH": "/tmp/bolt-vault-env"}):
            with patch.object(vs, "_config_vault_path", return_value="/tmp/from-config"):
                self.assertEqual(vs.resolve_vault_path(), Path("/tmp/bolt-vault-env"))

    def test_config_used_when_env_missing(self):
        env = os.environ.copy()
        env.pop("BOLT_VAULT_PATH", None)
        with patch.dict(os.environ, env, clear=True):
            with patch.object(vs, "_config_vault_path", return_value="/tmp/from-config"):
                self.assertEqual(vs.resolve_vault_path(), Path("/tmp/from-config"))

    def test_default_is_williams_mac_vault(self):
        env = os.environ.copy()
        env.pop("BOLT_VAULT_PATH", None)
        with patch.dict(os.environ, env, clear=True):
            with patch.object(vs, "_config_vault_path", return_value=""):
                self.assertEqual(
                    vs.resolve_vault_path(),
                    Path("/Users/carter/Documents/Obsidian/Bolt Vault"),
                )

    def test_missing_vault_is_not_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "not-here"
            info = vs.VaultStore(missing).status()
            self.assertFalse(info["exists"])
            self.assertFalse(missing.exists())


class VaultStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "vault"
        self.root.mkdir()
        (self.root / "00 Inbox").mkdir()
        (self.root / "30 Product Testing").mkdir()
        (self.root / "Home.md").write_text(
            "---\ntags: [home]\n---\n# Home\n\nK&F lives in product testing.\n",
            encoding="utf-8",
        )
        self.store = vs.VaultStore(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_scaffold_creates_phase0_names_once(self):
        created = self.store.ensure_scaffold()
        self.assertIn(vs.BOARD_REL, created)
        self.assertIn(vs.TIMELINE_REL, created)
        self.assertIn(vs.ACTIVITY_REL, created)
        self.assertTrue((self.root / "10 Bolt" / "Tasks").is_dir())
        self.assertTrue((self.root / "10 Bolt" / "Calendar").is_dir())
        board = (self.root / vs.BOARD_REL).read_text(encoding="utf-8")
        self.assertIn("kanban-plugin: board", board)
        for lane in ("## Inbox", "## This Week", "## Doing", "## Done"):
            self.assertIn(lane, board)
        self.assertIn("**Complete**", board.split("## Done", 1)[1])
        timeline = (self.root / vs.TIMELINE_REL).read_text(encoding="utf-8")
        self.assertIn("bolt:timeline:start", timeline)
        self.assertIn("bolt:timeline:end", timeline)
        log = (self.root / vs.ACTIVITY_REL).read_text(encoding="utf-8")
        self.assertIn("| When (CT) | Action | Note | Details |", log)
        self.assertFalse((self.root / vs.CALENDAR_INDEX_REL).exists())

        board_path = self.root / vs.BOARD_REL
        board_path.write_text(board + "\nDO NOT WIPE\n", encoding="utf-8")
        again = self.store.ensure_scaffold()
        self.assertEqual(again, [])
        self.assertIn("DO NOT WIPE", board_path.read_text(encoding="utf-8"))

    def test_add_task_lands_in_bolt_tasks_and_logs(self):
        note = self.store.add_note(
            "Film K&F short",
            kind="task",
            area="30 Product Testing",
            due="2026-10-23",
            body="Shoot the neck holder.",
            source="cli",
        )
        self.assertEqual(note.rel, "10 Bolt/Tasks/Film K&F short.md")
        self.assertEqual(note.frontmatter["area"], "30 Product Testing")
        self.assertEqual(note.frontmatter["due"], "2026-10-23")
        self.assertEqual(note.frontmatter["status"], "inbox")
        self.assertIn("Shoot the neck holder.", note.body)
        log = (self.root / vs.ACTIVITY_REL).read_text(encoding="utf-8")
        self.assertIn("Film K&F short", log)
        self.assertIn("| add task |", log)

    def test_add_note_uses_area_folder(self):
        note = self.store.add_note("Podcast idea", kind="note", area="20 Creator HQ & Content", body="Cold open.")
        self.assertTrue(note.rel.startswith("20 Creator HQ & Content/"))
        self.assertFalse(note.rel.startswith("10 Bolt/Tasks/"))

    def test_existing_activity_log_is_appended_not_replaced(self):
        self.store.ensure_scaffold()
        log_path = self.root / vs.ACTIVITY_REL
        log_path.write_text(
            "# Bolt Activity Log\n\nKeep this intro.\n\n"
            "| When (CT) | Action | Note | Details |\n"
            "| --- | --- | --- | --- |\n"
            "| 2026-10-01 1:00 PM | old | Keep me | prior |\n",
            encoding="utf-8",
        )
        self.store.add_note("Second task", kind="task")
        text = log_path.read_text(encoding="utf-8")
        self.assertIn("Keep this intro.", text)
        self.assertIn("Keep me", text)
        self.assertIn("Second task", text)
        self.assertLess(text.index("Keep me"), text.index("Second task"))

    def test_find_and_list(self):
        self.store.add_note("Film K&F short", kind="task", area="product testing")
        self.store.add_note("Habit check", kind="note", area="personal", body="Sleep.")
        tasks = self.store.list_notes(kind="task")
        self.assertEqual([n.title for n in tasks], ["Film K&F short"])
        personal = self.store.list_notes(area="Personal")
        self.assertEqual(personal[0].title, "Habit check")
        found = self.store.find("K&F")
        self.assertTrue(any("K&F" in n.title for n in found))

    def test_calendar_index_is_not_an_event(self):
        self.store.ensure_scaffold()
        index = self.root / vs.CALENDAR_INDEX_REL
        index.parent.mkdir(parents=True, exist_ok=True)
        index.write_text("---\ntitle: Bolt Calendar\ndate: 2026-10-19\n---\n# Index\n", encoding="utf-8")
        decoy = self.root / vs.CALENDAR_REL / "Bolt Calendar.md"
        decoy.write_text("---\ntitle: Bolt Calendar\ndate: 2026-10-19\nallDay: true\n---\n# Nope\n", encoding="utf-8")
        real = self.root / vs.CALENDAR_REL / "Film night.md"
        real.write_text(
            '---\ntitle: "Film night"\nallDay: false\ndate: "2026-10-22"\nstartTime: "19:00"\nendTime: "20:00"\n---\n# Film night\n',
            encoding="utf-8",
        )
        titles = [n.title for n in self.store.list_events()]
        self.assertEqual(titles, ["Film night"])

    def test_refuses_paths_outside_the_vault(self):
        outside = self.root.parent / "outside.md"
        with self.assertRaises(vs.VaultError):
            self.store.checked("../outside.md")
        with self.assertRaises(vs.VaultError):
            with self.store.changing("bad"):
                self.store.write_text("../outside.md", "nope")
        self.assertFalse(outside.exists())

    def test_refuses_symlink_escape(self):
        outside = Path(self._tmp.name) / "outside"
        outside.mkdir()
        link = self.root / "escape"
        link.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(vs.VaultError):
            with self.store.changing("bad"):
                self.store.write_text("escape/pwn.md", "nope")
        self.assertFalse((outside / "pwn.md").exists())

    def test_backup_and_undo_modify(self):
        note = self.store.add_note("Film K&F short", kind="task")
        original = note.path.read_text(encoding="utf-8")
        self.store.update_frontmatter(note.rel, {"status": "doing"}, summary="mark doing")
        self.assertEqual(self.store.read_note(note.rel).frontmatter["status"], "doing")
        backups = list((self.root / ".bolt" / "backups").rglob("*"))
        self.assertTrue(any(p.is_file() and original in p.read_text(encoding="utf-8") for p in backups))
        message = self.store.undo()
        self.assertIn("Undid", message)
        self.assertEqual(self.store.read_note(note.rel).frontmatter["status"], "inbox")

    def test_undo_create_parks_the_file_instead_of_deleting(self):
        note = self.store.add_note("Temp task", kind="task", body="keep these bytes")
        text = note.path.read_text(encoding="utf-8")
        self.store.undo()
        self.assertFalse(note.path.exists())
        parked = list((self.root / ".bolt" / "undone").rglob("*.md"))
        self.assertTrue(any(p.read_text(encoding="utf-8") == text for p in parked))

    def test_failed_change_rolls_back_without_deleting_bytes(self):
        with self.assertRaises(vs.VaultError):
            with self.store.changing("boom"):
                self.store.write_text("10 Bolt/Tasks/X.md", "hello bytes")
                raise vs.VaultError("nope")
        self.assertFalse((self.root / "10 Bolt" / "Tasks" / "X.md").exists())
        parked = list((self.root / ".bolt" / "undone").rglob("X.md"))
        self.assertEqual(parked[0].read_text(encoding="utf-8"), "hello bytes")

    def test_frontmatter_roundtrip_keeps_quoted_title(self):
        meta = {"title": "Film: the K&F short", "allDay": False, "startTime": "19:00", "tags": ["bolt", "task"]}
        text = vs.dump_frontmatter(meta, "\n# Film: the K&F short\n")
        parsed, body = vs.parse_frontmatter(text)
        self.assertEqual(parsed["title"], "Film: the K&F short")
        self.assertIs(parsed["allDay"], False)
        self.assertEqual(parsed["startTime"], "19:00")
        self.assertEqual(parsed["tags"], ["bolt", "task"])
        self.assertIn("K&F", body)

    def test_cli_status_list_find_add_undo(self):
        from io import StringIO
        from contextlib import redirect_stdout

        with patch.object(vs, "resolve_vault_path", return_value=self.root):
            buf = StringIO()
            with redirect_stdout(buf):
                code = vs.main(["status"])
            self.assertEqual(code, 0)
            self.assertIn(str(self.root), buf.getvalue())

            buf = StringIO()
            with redirect_stdout(buf):
                code = vs.main(["add", "CLI task", "--area", "Inbox", "--due", "2026-10-23"])
            self.assertEqual(code, 0)
            self.assertIn("10 Bolt/Tasks/CLI task.md", buf.getvalue())

            buf = StringIO()
            with redirect_stdout(buf):
                code = vs.main(["find", "CLI"])
            self.assertEqual(code, 0)
            self.assertIn("CLI task", buf.getvalue())

            buf = StringIO()
            with redirect_stdout(buf):
                code = vs.main(["--json", "list", "--kind", "task"])
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload[0]["title"], "CLI task")
            self.assertEqual(code, 0)

            buf = StringIO()
            with redirect_stdout(buf):
                code = vs.main(["undo"])
            self.assertEqual(code, 0)
            self.assertIn("Undid", buf.getvalue())
            self.assertFalse((self.root / "10 Bolt" / "Tasks" / "CLI task.md").exists())


if __name__ == "__main__":
    unittest.main()
