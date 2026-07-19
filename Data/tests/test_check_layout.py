"""Tests for scripts/check_layout.py (the `bolt layout` scanner).

We only exercise the pure logic in `find_misplaced()` so the tests
don't depend on the real repo state. The scanner is report-only and
never touches the filesystem beyond reading directory entries.
"""

import sys
import tempfile
import unittest
from pathlib import Path

# Make the scripts package importable the same way other Data/tests
# files do.
_repo_root = Path(__file__).resolve().parents[2]
_scripts = _repo_root / "scripts"
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))

from scripts import check_layout  # noqa: E402


class FindMisplacedTests(unittest.TestCase):
    def _make_repo(self, names):
        """Create a tempdir with the given basenames at its root and
        return the path. Also creates one canonical dir so the
        scanner sees a realistic layout."""
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        for n in names:
            (root / n).touch()
        # A canonical top-level dir to make sure the scanner doesn't
        # flag it.
        (root / "Core").mkdir()
        self.addCleanup(tmp.cleanup)
        return root

    def test_clean_layout_returns_no_findings(self):
        root = self._make_repo(["README.md", "setup.py", "Bolt_Personality.txt"])
        self.assertEqual(check_layout.find_misplaced(root), [])

    def test_flags_known_drift_file(self):
        root = self._make_repo(["Multi_Publisher.py", "README.md"])
        findings = check_layout.find_misplaced(root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["file"], "Multi_Publisher.py")
        self.assertEqual(findings[0]["expected"], "Core/modules/Multi_Publisher.py")
        self.assertIn("Publisher logic", findings[0]["reason"])

    def test_flags_loose_rtf(self):
        root = self._make_repo(["Untitled 2.rtf"])
        findings = check_layout.find_misplaced(root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["file"], "Untitled 2.rtf")
        self.assertEqual(findings[0]["expected"], "Docs/scratch/")

    def test_allows_explicit_allowlist(self):
        # All of these are on ROOT_ALLOWED in _layout_rules.py and
        # should never appear in the report.
        allowed = [
            "Bolt_Personality.txt",
            "Scratchpad:",
            ".env",
            "launch.py",
            "_lazy_imports.py",
        ]
        root = self._make_repo(allowed)
        self.assertEqual(check_layout.find_misplaced(root), [])

    def test_unknown_top_level_dir_is_ignored(self):
        # "Core" is a known canonical dir; the scanner should skip it
        # and any files inside (we only ever look at the root level
        # anyway).
        root = self._make_repo(["some_script.py"])
        findings = check_layout.find_misplaced(root)
        # "some_script.py" has no rule, so no findings.
        self.assertEqual(findings, [])

    def test_main_exits_clean_for_clean_repo(self):
        import io
        from contextlib import redirect_stdout

        root = self._make_repo(["README.md"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = check_layout.main(["--root", str(root), "--quiet"])
        self.assertEqual(code, 0)
        self.assertIn("OK", buf.getvalue())

    def test_main_exits_nonzero_on_findings(self):
        import io
        from contextlib import redirect_stdout

        root = self._make_repo(["clip_history.json"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = check_layout.main(["--root", str(root), "--quiet"])
        self.assertEqual(code, 1)
        self.assertIn("WARN", buf.getvalue())
        self.assertIn("1 misplaced", buf.getvalue())

    def test_json_output_shape(self):
        import io
        import json
        from contextlib import redirect_stdout

        root = self._make_repo(["clip_history.json", "README.md"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = check_layout.main(["--root", str(root), "--json"])
        self.assertEqual(code, 1)
        payload = json.loads(buf.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["findings"][0]["file"], "clip_history.json")
        self.assertEqual(payload["findings"][0]["expected"], "Data/data/clip_history.json")


if __name__ == "__main__":
    unittest.main()
