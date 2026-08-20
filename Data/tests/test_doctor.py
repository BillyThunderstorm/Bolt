"""Tests for scripts/doctor.py (`bolt doctor`)."""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

_repo_root = Path(__file__).resolve().parents[2]
for _p in (_repo_root, _repo_root / "scripts", _repo_root / "Core"):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

from scripts import doctor  # noqa: E402


class ClassifyPathTests(unittest.TestCase):
    def _touch(self, root: Path, rel: str) -> Path:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")
        return path

    def test_same_existing_path_is_live(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self._touch(root, "Data/ready_to_post.json")
            self.assertEqual(doctor.classify_path(path, path), "live")

    def test_different_existing_paths_are_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            found = self._touch(root, "Core/data/title_cache.json")
            expected = self._touch(root, "Data/title_cache.json")
            self.assertEqual(doctor.classify_path(found, expected), "stale_path")

    def test_module_points_at_missing_canonical_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            found = self._touch(root, "memory/MEMORY.md")
            expected = root / "Data" / "memory" / "MEMORY.md"
            self.assertEqual(doctor.classify_path(found, expected), "stale_path")

    def test_both_missing_is_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            found = root / "nowhere.json"
            expected = root / "Data" / "nowhere.json"
            self.assertEqual(doctor.classify_path(found, expected), "missing_file")

    def test_none_found_when_canonical_exists_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = self._touch(root, "Data/MEMORY.md")
            self.assertEqual(doctor.classify_path(None, expected), "stale_path")


class KeyStatusTests(unittest.TestCase):
    def test_rejects_placeholders(self):
        self.assertFalse(doctor._key_set(""))
        self.assertFalse(doctor._key_set("your_key_here"))
        self.assertFalse(doctor._key_set("TODO_get_from_platform_openai"))
        self.assertFalse(doctor._key_set("sk_your_key_here"))
        self.assertTrue(doctor._key_set("xai-real-looking-key"))


class ReportTests(unittest.TestCase):
    def test_format_groups_subsystems_and_flags_stale(self):
        checks = [
            doctor.Check(
                "paths",
                "title cache",
                "stale_path",
                "module path does not match",
                expected="Data/title_cache.json",
                found="Core/data/title_cache.json",
                fix="fix PROJECT_ROOT",
            ),
            doctor.Check("titles", "ai titles", "live", "on"),
            doctor.Check("titles", "title trainer", "info", "no trainer"),
        ]
        text = doctor.format_report(checks)
        self.assertIn("Bolt doctor", text)
        self.assertIn("paths", text)
        self.assertIn("titles", text)
        self.assertIn("STALE", text)
        self.assertIn("Core/data/title_cache.json", text)
        self.assertIn("Data/title_cache.json", text)

    def test_json_payload_fails_on_stale_path(self):
        checks = [
            doctor.Check("paths", "memory", "stale_path", "wrong folder"),
            doctor.Check("llm", "ollama", "live", "up"),
        ]
        payload = doctor.report_payload(checks)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["summary"]["stale_path"], 1)
        self.assertEqual(payload["checks"][0]["name"], "memory")

    def test_json_payload_ok_when_only_disabled_or_info(self):
        checks = [
            doctor.Check("integrations", "twitch", "disabled", "off"),
            doctor.Check("titles", "title trainer", "info", "no trainer"),
            doctor.Check("queue", "ready_to_post.json", "live", "3 ready"),
        ]
        payload = doctor.report_payload(checks)
        self.assertTrue(payload["ok"])

    def test_main_json_uses_collect_checks(self):
        fake = [
            doctor.Check("paths", "title cache", "stale_path", "wrong"),
            doctor.Check("titles", "ai titles", "live", "on"),
        ]
        buf = io.StringIO()
        with patch.object(doctor, "collect_checks", return_value=fake), redirect_stdout(buf):
            code = doctor.main(["--json"])
        self.assertEqual(code, 1)
        payload = json.loads(buf.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["summary"]["stale_path"], 1)


class CollectSmokeTests(unittest.TestCase):
    def test_collect_checks_covers_core_subsystems(self):
        ollama = {"healthy": False, "url": "http://localhost:11434/api/tags", "models": []}
        checks = doctor.collect_checks(ollama=ollama)
        subsystems = {c.subsystem for c in checks}
        for needed in ("paths", "titles", "llm", "nexus", "queue", "social", "memory"):
            self.assertIn(needed, subsystems)
        names = {c.name for c in checks}
        self.assertIn("title trainer", names)
        self.assertIn("ai titles", names)
        self.assertIn("ready_to_post.json", names)


if __name__ == "__main__":
    unittest.main()
