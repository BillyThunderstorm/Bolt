#!/usr/bin/env python3
"""
Bolt layout checker.

Walks the repo root and reports any files that don't belong at the
top level according to the rules in `scripts/_layout_rules.py`.

This is a REPORT-ONLY tool. It never moves, edits, or deletes files.
Run it before/after a reorg to confirm the layout is clean:

    python3 scripts/check_layout.py            # full report
    python3 scripts/check_layout.py --quiet    # only the summary line
    python3 scripts/check_layout.py --json     # machine-readable output

Or via the wrapper:

    bolt layout
    bolt layout --quiet
    bolt layout --json

Exit codes
----------
  0 - no misplaced files found (clean layout)
  1 - one or more misplaced files found
  2 - usage error / unexpected runtime error

The scanner is intentionally narrow: it only looks at the top level
of the repo. Files nested inside `Core/`, `Data/`, etc. are out of
scope; they are already inside their canonical home by definition.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from pathlib import Path
from typing import List, Optional

# Make `from _paths import ...` and `from _layout_rules import ...`
# work whether this file is invoked directly or via the `bin/bolt`
# wrapper, which already does its own sys.path bootstrap.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _paths import REPO_ROOT  # noqa: E402
from _layout_rules import (  # noqa: E402
    RULES,
    is_root_allowed,
    KNOWN_TOP_LEVEL_DIRS,
)


def find_misplaced(repo_root: Path) -> List[dict]:
    """Return a list of findings, one per (file, rule) mismatch.

    Each finding is a dict:

        {
            "file":       "Multi_Publisher.py",   # basename
            "expected":   "Core/modules/Multi_Publisher.py",
            "reason":     "Publisher logic belongs in ...",
            "rule":       "Multi_Publisher.py",   # the matcher that fired
        }

    The function only inspects the top level of `repo_root`. Known
    subdirectories are skipped entirely. Files on the explicit
    allow-list are ignored.
    """
    findings: List[dict] = []
    if not repo_root.is_dir():
        raise NotADirectoryError(f"repo root not found: {repo_root}")

    for entry in sorted(repo_root.iterdir()):
        name = entry.name

        # Skip hidden files (e.g. .env, .git) and known canonical dirs.
        # We do NOT recurse into anything.
        if name.startswith("."):
            continue
        if entry.is_dir():
            continue
        if name in KNOWN_TOP_LEVEL_DIRS:
            continue
        if is_root_allowed(name):
            continue

        # Try every rule; one file can match multiple (e.g. *.mp4 plus
        # a more specific rule).  The first matcher wins, but later
        # matches with different `expected` paths are still reported
        # as separate findings so the user sees the full picture.
        for matcher, expected, reason in RULES:
            if fnmatch.fnmatch(name, matcher):
                findings.append(
                    {
                        "file": name,
                        "expected": expected,
                        "reason": reason,
                        "rule": matcher,
                    }
                )

    return findings


def format_text(findings: List[dict], repo_root: Path) -> str:
    """Human-readable report. Always prints the summary, then a
    per-finding block when there are findings."""
    lines: List[str] = []
    repo = str(repo_root)
    if not findings:
        lines.append(f"[OK] Layout clean. No misplaced files at the repo root ({repo}).")
        return "\n".join(lines)

    lines.append(
        f"[WARN] Found {len(findings)} misplaced file(s) at the repo root ({repo}):"
    )
    lines.append("")
    # Group findings by source file for readability
    by_file: dict = {}
    for f in findings:
        by_file.setdefault(f["file"], []).append(f)
    for fname in sorted(by_file):
        for f in by_file[fname]:
            lines.append(f"  - {f['file']}")
            lines.append(f"      expected: {f['expected']}")
            lines.append(f"      why:      {f['reason']}")
            lines.append(f"      rule:     {f['rule']}")
    lines.append("")
    lines.append(
        "These are REPORT ONLY. No files were moved. To fix them, "
        "review the expected paths and run an explicit migration."
    )
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check the repo-root layout for misplaced files (report only).",
    )
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT),
        help="Path to the repo root (default: detected from this script's location).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only print the one-line summary (still exits non-zero on findings).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Emit a machine-readable JSON object instead of the text report.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.root).resolve()
    try:
        findings = find_misplaced(repo_root)
    except NotADirectoryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.as_json:
        payload = {
            "repo_root": str(repo_root),
            "ok": not findings,
            "count": len(findings),
            "findings": findings,
        }
        print(json.dumps(payload, indent=2))
        return 0 if not findings else 1

    if args.quiet:
        status = "OK" if not findings else "WARN"
        print(f"[{status}] {len(findings)} misplaced file(s) at {repo_root}")
        return 0 if not findings else 1

    print(format_text(findings, repo_root))
    return 0 if not findings else 1


if __name__ == "__main__":
    sys.exit(main())
