"""Targeted tests for scripts/site_data_writer.py (progress, briefing, scoped push).

Temp dirs and a temp bare git remote only — never touches the real repo's
git, Data/site-data.json, GitHub or Google Docs.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

_repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_repo / "Core"))
sys.path.insert(0, str(_repo / "scripts"))

import site_data_writer as w  # noqa: E402

READINESS = """# Bolt readiness audit

*14 September 2026 (last updated 20 Oct 2026, ~7:45 AM CT) · Goddess.local*

## How you actually run it

| not | counted |
|---|---|
| x | y |

## READY — another person could use this

| Surface | Path | Why |
|---|---|---|
| CLI | `bin/bolt` | Works. |
| Clip compress | `bolt compress` | **READY (20 Oct 2026 ~5:40 AM CT, Shells).** ffmpeg. |
| Weekly analysis | `bolt weekly` | **READY (19 Oct 2026 ~7:45 PM CT, Shells).** Real numbers. |
| Old thing | `bolt old` | **READY (7 Sep 2026).** No time. |

## PARTIAL — real code, incomplete

| Surface | Why |
|---|---|
| TikTok | gated |

### Services

| ffmpeg | required |
|---|---|
| a | b |

## SHELL — stub

*(none left)*

## IDEA — named

| Idea | Note |
|---|---|
| Robot arm | someday |
"""


def _git(args, cwd, **kw):
    return subprocess.run(["git", *args], cwd=str(cwd), check=True,
                          capture_output=True, text=True, **kw).stdout.strip()


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "READINESS.md"
        self.path.write_text(READINESS)

    def tearDown(self):
        self.tmp.cleanup()

    def test_counts_only_level_tables(self):
        p = w._progress(self.path)
        self.assertEqual(p["counts"], {"READY": 4, "PARTIAL": 1, "SHELL": 0, "IDEA": 1})
        self.assertEqual(p["total"], 6)
        self.assertEqual(p["percent_ready"], 67)
        self.assertEqual(p["updated"], "20 Oct 2026, ~7:45 AM CT")

    def test_recent_newest_first(self):
        recent = w._progress(self.path, recent_limit=2)["recent"]
        self.assertEqual([r["name"] for r in recent], ["Clip compress", "Weekly analysis"])
        self.assertEqual(recent[0]["date"], "2026-10-20")
        self.assertEqual(recent[0]["display"], "Oct 20, 5:40 AM CT")

    def test_missing_file_soft(self):
        p = w._progress(Path(self.tmp.name) / "nope.md")
        self.assertFalse(p["available"])
        self.assertEqual(p["total"], 0)


class BriefingTests(unittest.TestCase):
    def test_picks_newest_dated_name_not_alphabetical(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "briefing_20260704.md").write_text("## Action Items\n1. old july\n")
            (d / "2026-07-13.md").write_text("## Action Items\n1. mid july\n")
            (d / "morning_2026-10-19.md").write_text("## Action Items For Today\n\n1. Draft the short\n2. Stream\n---\n3. not me\n")
            b = w._latest_briefing(d)
            self.assertEqual(b["date"], "Monday, October 19, 2026")
            self.assertEqual(b["action_items"], ["Draft the short", "Stream"])
            self.assertEqual(b["source"], "morning_2026-10-19.md")

    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as d:
            b = w._latest_briefing(Path(d))
            self.assertEqual(b["action_items"], [])


class ScopedPushTests(unittest.TestCase):
    """push_site_data must publish only the data file and never touch other work."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.remote = root / "remote.git"
        self.repo = root / "work"
        env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        self.env = patch.dict(os.environ, env)
        self.env.start()
        _git(["init", "-q", "--bare", "-b", "main", str(self.remote)], root)
        _git(["init", "-q", "-b", "main", str(self.repo)], root)
        (self.repo / "Data").mkdir()
        (self.repo / "Data" / "site-data.json").write_text('{"v": 1}\n')
        (self.repo / "code.py").write_text("print(1)\n")
        _git(["add", "."], self.repo)
        _git(["commit", "-q", "-m", "init"], self.repo)
        _git(["remote", "add", "origin", str(self.remote)], self.repo)
        _git(["push", "-q", "origin", "main"], self.repo)
        _git(["fetch", "-q", "origin"], self.repo)
        self.log = patch.object(w, "PUSH_LOG", root / "push.log")
        self.log.start()

    def tearDown(self):
        self.log.stop()
        self.env.stop()
        self.tmp.cleanup()

    def _remote_files(self):
        return _git(["ls-tree", "-r", "--name-only", "main"], self.remote).splitlines()

    def _push(self):
        return w.push_site_data(repo=self.repo, files=[self.repo / "Data" / "site-data.json"])

    def test_pushes_only_data_and_leaves_other_changes(self):
        (self.repo / "Data" / "site-data.json").write_text('{"v": 2}\n')
        (self.repo / "code.py").write_text("print('dirty')\n")
        (self.repo / "new.txt").write_text("untracked\n")
        _git(["add", "new.txt"], self.repo)  # staged unrelated work
        self.assertEqual(self._push(), "pushed")
        self.assertEqual(_git(["show", "main:Data/site-data.json"], self.remote), '{"v": 2}')
        self.assertEqual(_git(["show", "main:code.py"], self.remote), "print(1)")
        self.assertNotIn("new.txt", self._remote_files())
        self.assertTrue(_git(["log", "-1", "--format=%s", "main"], self.remote).startswith("site data update"))
        # Local branch fast-forwarded; unrelated staged/dirty work untouched.
        self.assertEqual(_git(["rev-parse", "main"], self.repo), _git(["rev-parse", "main"], self.remote))
        st = subprocess.run(["git", "status", "--porcelain"], cwd=str(self.repo),
                            capture_output=True, text=True, check=True).stdout
        self.assertIn("A  new.txt", st)
        self.assertIn(" M code.py", st)
        self.assertNotIn("site-data.json", st)

    def test_unchanged_is_noop(self):
        self.assertEqual(self._push(), "unchanged")

    def test_races_remote_without_conflict(self):
        other = Path(self.tmp.name) / "other"
        _git(["clone", "-q", str(self.remote), str(other)], Path(self.tmp.name))
        (other / "code.py").write_text("print(2)\n")
        _git(["commit", "-qam", "other work"], other)
        _git(["push", "-q", "origin", "main"], other)
        (self.repo / "Data" / "site-data.json").write_text('{"v": 3}\n')
        self.assertEqual(self._push(), "pushed")
        self.assertEqual(_git(["show", "main:code.py"], self.remote), "print(2)")
        self.assertEqual(_git(["show", "main:Data/site-data.json"], self.remote), '{"v": 3}')
        # local main was behind → left alone, logged
        self.assertIn("left it alone", (Path(self.tmp.name) / "push.log").read_text())

    def test_push_failure_soft_fails_and_logs(self):
        _git(["remote", "set-url", "origin", str(Path(self.tmp.name) / "missing.git")], self.repo)
        (self.repo / "Data" / "site-data.json").write_text('{"v": 4}\n')
        self.assertEqual(self._push(), "failed")
        self.assertIn("Sites unavailable", (Path(self.tmp.name) / "push.log").read_text())
        self.assertFalse((self.repo / ".git" / "site-data-push.index").exists())


class WriteTests(unittest.TestCase):
    def test_write_includes_progress_and_custom_path_skips_push(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "site.json"
            with patch.object(w, "push_site_data") as push:
                w.write_site_data(push=True, output_path=str(out))
                push.assert_not_called()
            data = json.loads(out.read_text())
            self.assertIn("progress", data)
            self.assertIn("counts", data["progress"])


if __name__ == "__main__":
    unittest.main()
