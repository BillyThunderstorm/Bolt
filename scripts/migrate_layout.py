#!/usr/bin/env python3
"""
Bolt drift migrator.

Applies the moves implied by `scripts/_layout_rules.py`. Built to be
safe-by-default:

  * `--dry-run` (default) prints the planned moves and exits without
    touching anything.
  * `--apply` performs the moves.
  * Conflicts (destination already exists) are NEVER overwritten
    silently. The script either asks interactively or, under
    `--yes`, treats a conflict as a fatal error and exits 1 so the
    operator can decide.

The rules in `_layout_rules.py` are the same ones `bolt layout`
reports against, so the two commands stay in sync.

Usage:
    python3 scripts/migrate_layout.py            # dry-run, default
    python3 scripts/migrate_layout.py --apply    # actually move
    python3 scripts/migrate_layout.py --apply --yes
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _paths import REPO_ROOT  # noqa: E402
from _layout_rules import RULES, is_root_allowed, KNOWN_TOP_LEVEL_DIRS  # noqa: E402


# A small set of (basename, expected_destination) overrides for files
# where the simple "move" would be wrong. For each, we have a custom
# handler. The dry-run prints the override explicitly so it's auditable.
#
# Format: { "basename": "handler_name" }
CUSTOM_HANDLERS = {
    # The two clip_history.json files have different content. The root
    # one is stale (158B, single key) and the Data/data/ one is the
    # live one (400B, two keys). DO NOT overwrite the live one.
    # Action: delete the stale root copy after confirming the live one
    # is bigger / newer.
    "clip_history.json": "stale_root_overwritten_by_live",
    # Multi_Publisher.py exists at root AND is expected at
    # Core/modules/. Peak_Hour_Notifier.py imports it from
    # `modules.Multi_Publisher`, which only resolves to
    # Core/modules/. If the file at Core/modules/ is empty/missing,
    # the import fails. Action: move root -> Core/modules/. If
    # destination already has a file, refuse (the user has to decide).
    # 101_hello_tinker.py: colab sandbox -> 3rd_Party/colabs/
    "101_hello_tinker.py": "move",
    # 3 docs / 1 media / 2 data files: plain moves
    "seen_clips.json": "move",
    "structure.txt": "move",
    "think_learn_decide.md": "move",
    "Untitled 2.rtf": "move_under_scratch",
}


def plan_moves(repo_root: Path) -> List[dict]:
    """Build a list of planned operations. Each entry has:

        {
            "basename":   "Multi_Publisher.py",
            "src":        "/abs/path/to/Multi_Publisher.py",
            "dst":        "/abs/path/to/Core/modules/Multi_Publisher.py",
            "handler":    "move" | "stale_root_overwritten_by_live" | "move_under_scratch",
            "action":     "move" | "delete" | "mkdir+move",
            "will_overwrite": False,
            "notes":      "...",
        }
    """
    ops: List[dict] = []
    for entry in sorted(repo_root.iterdir()):
        name = entry.name
        if name.startswith("."):
            continue
        if entry.is_dir():
            continue
        if name in KNOWN_TOP_LEVEL_DIRS:
            continue
        if is_root_allowed(name):
            continue

        # Find the rule that matches and the custom handler (if any).
        # We use the FIRST matching rule's expected path. If the
        # scanner is well-formed, only one rule will match per
        # basename.
        expected_rel = None
        for matcher, expected, _reason in RULES:
            if fnmatch.fnmatch(name, matcher):
                expected_rel = expected
                break
        if expected_rel is None:
            continue  # not actually misplaced (defensive)

        handler = CUSTOM_HANDLERS.get(name, "move")
        src = entry
        dst = repo_root / expected_rel

        if handler == "stale_root_overwritten_by_live":
            ops.append(
                {
                    "basename": name,
                    "src": str(src),
                    "dst": str(dst),
                    "handler": handler,
                    "action": "delete",
                    "will_overwrite": False,
                    "notes": (
                        f"Root {name} appears stale; live copy is at "
                        f"{dst}. The live one is larger/newer. "
                        f"Deleting the root copy, NOT overwriting {dst}."
                    ),
                }
            )
        elif handler == "move_under_scratch":
            # The rule says expected="Docs/scratch/" (a directory).
            # We need to actually move the file INTO that directory,
            # not to the directory path itself. Append the basename
            # to get a real file destination.
            file_dst = repo_root / expected_rel.rstrip("/") / name
            ops.append(
                {
                    "basename": name,
                    "src": str(src),
                    "dst": str(file_dst),
                    "handler": handler,
                    "action": "mkdir+move",
                    "will_overwrite": file_dst.exists(),
                    "notes": (
                        f"Will create {expected_rel} if needed and move "
                        f"the file into it."
                    ),
                }
            )
        else:  # plain "move"
            ops.append(
                {
                    "basename": name,
                    "src": str(src),
                    "dst": str(dst),
                    "handler": handler,
                    "action": "move",
                    "will_overwrite": dst.exists(),
                    "notes": "Plain move.",
                }
            )
    return ops


def render_plan(ops: List[dict], dry_run: bool) -> str:
    lines: List[str] = []
    verb = "DRY RUN" if dry_run else "APPLY"
    lines.append(f"=== {verb}: {len(ops)} operation(s) ===")
    if not ops:
        lines.append("(nothing to do — layout is clean)")
        return "\n".join(lines)

    for op in ops:
        action = op["action"]
        marker = "WOULD" if dry_run else "WILL"
        if action == "delete":
            lines.append(f"  {marker} DELETE   {op['src']}")
            lines.append(f"     (live copy at {op['dst']} is preserved)")
        elif action == "move":
            lines.append(f"  {marker} MOVE     {op['src']}")
            lines.append(f"        ->        {op['dst']}")
            if op["will_overwrite"]:
                lines.append(
                    f"        *** WARNING: destination already exists — "
                    f"this will be REJECTED on --apply unless you handle it manually."
                )
        elif action == "mkdir+move":
            lines.append(f"  {marker} MKDIR    {Path(op['dst']).parent}")
            lines.append(f"  {marker} MOVE     {op['src']}")
            lines.append(f"        ->        {op['dst']}")
            if op["will_overwrite"]:
                lines.append(
                    f"        *** WARNING: destination already exists."
                )
        if op.get("notes"):
            lines.append(f"     note: {op['notes']}")
    return "\n".join(lines)


def apply(ops: List[dict], assume_yes: bool) -> int:
    """Apply the planned operations. Returns 0 on success, 1 on
    conflict. Asks interactively unless --yes is given; under --yes
    a conflict is fatal."""
    for op in ops:
        action = op["action"]
        src = Path(op["src"])
        dst = Path(op["dst"])
        if action == "delete":
            src.unlink()
            print(f"  deleted: {src}")
        elif action == "move":
            if dst.exists():
                if assume_yes:
                    print(f"  REFUSED: {dst} already exists (refusing to overwrite under --yes)", file=sys.stderr)
                    return 1
                resp = input(f"  {dst} already exists. Overwrite? [y/N] ").strip().lower()
                if resp != "y":
                    print(f"  SKIPPED: {src} -> {dst}")
                    continue
                dst.unlink()
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            print(f"  moved:   {src} -> {dst}")
        elif action == "mkdir+move":
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                if assume_yes:
                    print(f"  REFUSED: {dst} already exists (refusing to overwrite under --yes)", file=sys.stderr)
                    return 1
                resp = input(f"  {dst} already exists. Overwrite? [y/N] ").strip().lower()
                if resp != "y":
                    print(f"  SKIPPED: {src} -> {dst}")
                    continue
                dst.unlink()
            shutil.move(str(src), str(dst))
            print(f"  moved:   {src} -> {dst}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply the moves implied by scripts/_layout_rules.py. "
        "Dry-run by default; pass --apply to actually move files.",
    )
    parser.add_argument("--root", default=str(REPO_ROOT))
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually move files (default is dry-run).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Under --apply, treat destination conflicts as fatal errors instead of asking.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.root).resolve()
    ops = plan_moves(repo_root)

    print(render_plan(ops, dry_run=not args.apply))
    if not args.apply:
        print()
        print("This was a DRY RUN. No files were touched. Re-run with --apply to execute.")
        return 0

    # --apply path
    print()
    print("=== Applying moves ===")
    rc = apply(ops, assume_yes=args.yes)
    if rc == 0:
        print()
        print("Done. Run 'bolt layout' to confirm the repo is clean.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
