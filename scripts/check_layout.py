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
try:  # newer rule tables (Oct 2026); tolerate an older _layout_rules.py
    from _layout_rules import ROOT_EXPLAINED, HIDDEN_OK, HIDDEN_NOTES  # noqa: E402
except ImportError:  # pragma: no cover
    ROOT_EXPLAINED, HIDDEN_OK, HIDDEN_NOTES = {}, set(), []


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


def _is_empty_dir(path: Path) -> bool:
    try:
        return not any(p for p in path.iterdir() if p.name != ".DS_Store")
    except OSError:
        return False


def scan_root(repo_root: Path) -> dict:
    """Full inventory of the repo root (report only, never moves anything).

    Every top-level item lands in exactly one bucket:

      * ``in_place``  - a known folder or an allowed file (with what it's for)
      * ``misplaced`` - matches a rule in _layout_rules.RULES (has a home)
      * ``look_at``   - not part of the layout and no rule knows it; William
                        decides (empty folders say they're safe to delete)
      * ``notes``     - hidden items worth knowing about (key backups,
                        Google Drive temp folders); never counted as problems
    Ordinary hidden tool files (.git, .venv, caches, .env) are counted but
    not listed.
    """
    if not repo_root.is_dir():
        raise NotADirectoryError(f"repo root not found: {repo_root}")
    misplaced = find_misplaced(repo_root)
    misplaced_names = {f["file"] for f in misplaced}
    in_place: List[dict] = []
    look_at: List[dict] = []
    notes: List[dict] = []
    hidden_ok = 0
    for entry in sorted(repo_root.iterdir(), key=lambda p: p.name.lower()):
        name = entry.name
        kind = "folder" if entry.is_dir() else "file"
        if name.startswith("."):
            if name in HIDDEN_OK:
                hidden_ok += 1
                continue
            for pattern, note, fix in HIDDEN_NOTES:
                if fnmatch.fnmatch(name, pattern):
                    notes.append({"name": name, "kind": kind, "note": note, "fix": fix})
                    break
            else:
                hidden_ok += 1  # other dotfiles: tool state, not William's mess
            continue
        if name in misplaced_names:
            continue
        if (kind == "folder" and name in KNOWN_TOP_LEVEL_DIRS) or (
            kind == "file" and is_root_allowed(name)
        ):
            in_place.append({"name": name, "kind": kind,
                             "what": ROOT_EXPLAINED.get(name, "Part of the normal layout.")})
            continue
        if kind == "folder" and _is_empty_dir(entry):
            look_at.append({"name": name, "kind": kind,
                            "why": "Empty folder that isn't part of Bolt's layout.",
                            "fix": f"Safe to delete: move '{name}' to the Trash."})
        elif kind == "folder":
            look_at.append({"name": name, "kind": kind,
                            "why": "Folder that isn't part of Bolt's layout.",
                            "fix": "If Bolt needs it, add it to KNOWN_TOP_LEVEL_DIRS in scripts/_layout_rules.py; "
                                   "otherwise move it under Data/, Docs/ or 3rd_Party/."})
        else:
            look_at.append({"name": name, "kind": kind,
                            "why": "Loose file that isn't part of Bolt's layout.",
                            "fix": "Move it to the folder it belongs in (code Core/, data Data/, notes Docs/), "
                                   "or add it to ROOT_ALLOWED in scripts/_layout_rules.py if it must stay."})
    return {
        "repo_root": str(repo_root),
        "clean": not misplaced and not look_at,
        "counts": {
            "in_place": len(in_place), "misplaced": len(misplaced),
            "look_at": len(look_at), "notes": len(notes), "hidden_ok": hidden_ok,
        },
        "in_place": in_place,
        "misplaced": misplaced,
        "look_at": look_at,
        "notes": notes,
    }


def format_inventory(scan: dict, show_all: bool = False) -> str:
    """Plain-words report of scan_root()."""
    c = scan["counts"]
    L: List[str] = []
    if scan["clean"]:
        L.append(f"[OK] Top folder is tidy ({scan['repo_root']}).")
    else:
        L.append(f"[WARN] Top folder needs a look ({scan['repo_root']}).")
    L.append(
        f"  {c['in_place']} in place · {c['misplaced']} in the wrong spot · "
        f"{c['look_at']} to look at · {c['notes']} note(s) · {c['hidden_ok']} normal hidden tool files"
    )
    if scan["misplaced"]:
        L.append("")
        L.append("In the wrong spot (each has a home):")
        for f in scan["misplaced"]:
            L.append(f"  - {f['file']}  ->  {f['expected']}")
            L.append(f"      why: {f['reason']}")
        L.append("  Fix: `bolt migrate-layout run` shows the moves; add `--apply` to do them.")
    if scan["look_at"]:
        L.append("")
        L.append("To look at (not part of Bolt's layout):")
        for f in scan["look_at"]:
            L.append(f"  - {f['name']}{'/' if f['kind'] == 'folder' else ''}  {f['why']}")
            L.append(f"      fix: {f['fix']}")
    if scan["notes"]:
        L.append("")
        L.append("Good to know (not problems):")
        for f in scan["notes"]:
            L.append(f"  - {f['name']}  {f['note']}")
            L.append(f"      {f['fix']}")
    if show_all and scan["in_place"]:
        L.append("")
        L.append("In place:")
        for f in scan["in_place"]:
            L.append(f"  - {f['name']}{'/' if f['kind'] == 'folder' else ''}  {f['what']}")
    L.append("")
    L.append("Report only. Nothing was moved or deleted." + ("" if show_all else " Add --all to see what every item is for."))
    return "\n".join(L)


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
    parser.add_argument(
        "--all",
        action="store_true",
        dest="show_all",
        help="Also list every item that is in place, with what it's for.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.root).resolve()
    try:
        scan = scan_root(repo_root)
    except NotADirectoryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    findings = scan["misplaced"]

    if args.as_json:
        payload = {
            "repo_root": str(repo_root),
            "ok": not findings,
            "count": len(findings),
            "findings": findings,
            "clean": scan["clean"],
            "counts": scan["counts"],
            "look_at": scan["look_at"],
            "notes": scan["notes"],
            "in_place": scan["in_place"],
        }
        print(json.dumps(payload, indent=2))
        return 0 if not findings else 1

    if args.quiet:
        status = "OK" if not findings else "WARN"
        print(
            f"[{status}] {len(findings)} misplaced file(s), "
            f"{scan['counts']['look_at']} to look at, at {repo_root}"
        )
        return 0 if not findings else 1

    print(format_inventory(scan, show_all=args.show_all))
    return 0 if not findings else 1


if __name__ == "__main__":
    sys.exit(main())
