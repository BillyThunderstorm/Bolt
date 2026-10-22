#!/usr/bin/env python3
"""
Bolt drift migrator (engine for ``bolt migrate-layout``).

Puts stray files at the top of the Bolt folder back where
``scripts/_layout_rules.py`` says they belong (the same rules
``bolt layout`` reports against).

Safe by default:

  * Dry run unless ``--apply``: prints the plan and touches nothing.
  * Never overwrites. If the destination already exists:
      - same bytes  -> the top-folder copy is an exact duplicate and goes
                       to the Trash (the real copy stays put);
      - different   -> skipped and listed with the fix (William decides).
  * Never prompts (works from cron / the menu bar / a background shell).
  * Nothing is deleted outright: duplicates and stale copies go to the
    macOS Trash (``/usr/bin/trash``, then ~/.Trash).
  * Every applied step is logged to ``Data/layout_moves.jsonl`` with a
    run id, and ``--undo`` puts the last run's moves back.
  * ``--tidy-empty`` also sends empty folders that aren't part of Bolt's
    layout to the Trash (the "safe to delete" items from ``bolt layout``).

Usage:
    python3 scripts/migrate_layout.py                 # dry run
    python3 scripts/migrate_layout.py --apply         # do it
    python3 scripts/migrate_layout.py --apply --tidy-empty
    python3 scripts/migrate_layout.py --undo          # put the last run back
"""

from __future__ import annotations

import argparse
import filecmp
import fnmatch
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _paths import REPO_ROOT  # noqa: E402
from _layout_rules import RULES, is_root_allowed, KNOWN_TOP_LEVEL_DIRS  # noqa: E402

LOG_REL = Path("Data") / "layout_moves.jsonl"

# Files whose top-folder copy is a known stale leftover of a live file.
# If the live copy exists, the top-folder copy goes to the Trash instead
# of overwriting the live one. If the live copy is missing, it is moved.
STALE_IF_LIVE_EXISTS = {"clip_history.json", "seen_clips.json"}


def _is_empty_dir(path: Path) -> bool:
    try:
        return not any(p for p in path.iterdir() if p.name != ".DS_Store")
    except OSError:
        return False


def _rule_for(name: str):
    for matcher, expected, reason in RULES:
        if fnmatch.fnmatch(name, matcher):
            return expected, reason
    return None, None


def _same_bytes(a: Path, b: Path) -> bool:
    try:
        return a.is_file() and b.is_file() and filecmp.cmp(str(a), str(b), shallow=False)
    except OSError:
        return False


def plan_moves(repo_root: Path, tidy_empty: bool = False) -> List[dict]:
    """Plan every step. Each op is a dict with keys:

    name, src, dst, action ('move' | 'trash' | 'skip' | 'trash-folder'),
    reason (why it belongs elsewhere), notes (plain words), fix (for skips).
    """
    repo_root = Path(repo_root)
    ops: List[dict] = []
    for entry in sorted(repo_root.iterdir(), key=lambda p: p.name.lower()):
        name = entry.name
        if name.startswith("."):
            continue
        if entry.is_dir():
            if (tidy_empty and name not in KNOWN_TOP_LEVEL_DIRS
                    and not entry.is_symlink() and _is_empty_dir(entry)):
                ops.append({
                    "name": name, "src": str(entry), "dst": "", "action": "trash-folder",
                    "reason": "Empty folder that isn't part of Bolt's layout.",
                    "notes": "Empty, so nothing is lost; it goes to the Trash.", "fix": "",
                })
            continue
        if is_root_allowed(name):
            continue
        expected, reason = _rule_for(name)
        if expected is None:
            continue  # unknown loose file: bolt layout lists it under "to look at"
        dst = repo_root / expected
        if expected.endswith("/"):
            dst = dst / name  # folder rule: file goes INTO the folder
        op = {"name": name, "src": str(entry), "dst": str(dst), "reason": reason, "fix": ""}
        if dst.exists():
            if _same_bytes(entry, dst):
                op.update(action="trash", notes=f"Exact duplicate of {expected.rstrip('/')}"
                          f"{'/' + name if expected.endswith('/') else ''}; the top-folder copy goes to the Trash.")
            elif name in STALE_IF_LIVE_EXISTS:
                op.update(action="trash", notes=f"Old leftover; the live copy at {dst.relative_to(repo_root)} "
                          "is kept untouched and the top-folder copy goes to the Trash.")
            else:
                op.update(action="skip", notes="A different file with that name is already there, so nothing is moved.",
                          fix=f"Compare the two, keep the right one, then run again: '{entry}' vs '{dst}'.")
        else:
            op.update(action="move", notes="Moved; nothing is overwritten.")
        ops.append(op)
    return ops


def render_plan(ops: List[dict], dry_run: bool) -> str:
    head = "Dry run (nothing touched)" if dry_run else "Applying"
    todo = [o for o in ops if o["action"] != "skip"]
    skips = [o for o in ops if o["action"] == "skip"]
    lines = [f"=== {head}: {len(todo)} step(s), {len(skips)} skipped ==="]
    if not ops:
        lines.append("(nothing to do — the top of the Bolt folder is tidy)")
        return "\n".join(lines)
    w = "Would" if dry_run else "Will"
    for o in ops:
        a = o["action"]
        if a == "move":
            lines.append(f"  {w} move   {o['name']}  ->  {o['dst']}")
        elif a == "trash":
            lines.append(f"  {w} trash  {o['name']}  (copy at {o['dst']} kept)")
        elif a == "trash-folder":
            lines.append(f"  {w} trash  {o['name']}/  (empty folder)")
        else:
            lines.append(f"  Skip     {o['name']}  ->  {o['dst']}")
        if o.get("reason"):
            lines.append(f"     why:  {o['reason']}")
        lines.append(f"     note: {o['notes']}")
        if o.get("fix"):
            lines.append(f"     fix:  {o['fix']}")
    return "\n".join(lines)


def trash(path: Path) -> str:
    """Send a file/folder to the Trash. Never unlinks. Returns the method."""
    p = Path(path)
    test_dir = os.environ.get("BOLT_LAYOUT_TRASH_DIR")
    if test_dir:
        td = Path(test_dir)
        td.mkdir(parents=True, exist_ok=True)
        shutil.move(str(p), str(_unique(td / p.name)))
        return "test-trash"
    if sys.platform == "darwin" and Path("/usr/bin/trash").exists():
        try:
            subprocess.run(["/usr/bin/trash", str(p)], capture_output=True, timeout=60)
        except Exception:
            pass
        if not p.exists():
            return "trash"
    home_trash = Path.home() / ".Trash"
    home_trash.mkdir(exist_ok=True)
    shutil.move(str(p), str(_unique(home_trash / p.name)))
    return "~/.Trash"


def _unique(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stamp = datetime.now().strftime("%H%M%S")
    i = 0
    while True:
        cand = dest.with_name(f"{dest.stem} {stamp}{'-' + str(i) if i else ''}{dest.suffix}")
        if not cand.exists():
            return cand
        i += 1


def _log(repo_root: Path, row: dict) -> None:
    log = Path(repo_root) / LOG_REL
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def read_log(repo_root: Path) -> List[dict]:
    log = Path(repo_root) / LOG_REL
    rows: List[dict] = []
    if not log.is_file():
        return rows
    for line in log.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def apply(ops: List[dict], assume_yes: bool = True, repo_root: Optional[Path] = None) -> Dict:
    """Do the planned steps. Never prompts, never overwrites.

    Returns {'run_id', 'done': [...], 'skipped': [...], 'failed': [...], 'rc'}.
    rc is 0 when nothing failed or was skipped, 1 otherwise.
    """
    repo_root = Path(repo_root or REPO_ROOT)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    done, skipped, failed = [], [], []
    for o in ops:
        src, a = Path(o["src"]), o["action"]
        row = {"run_id": run_id, "at": datetime.now().isoformat(timespec="seconds"),
               "action": a, "name": o["name"], "src": o["src"], "dst": o.get("dst", "")}
        try:
            if a == "skip":
                skipped.append(o)
                continue
            if not src.exists():
                failed.append({**o, "error": "gone before it could be moved"})
                continue
            if a == "move":
                dst = Path(o["dst"])
                if dst.exists():  # appeared since planning: never overwrite
                    skipped.append({**o, "fix": f"{dst} appeared meanwhile; run again."})
                    continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                print(f"  moved:   {o['name']} -> {dst}")
            elif a in ("trash", "trash-folder"):
                row["trash_method"] = trash(src)
                print(f"  trashed: {o['name']}{'/' if a == 'trash-folder' else ''}")
            _log(repo_root, row)
            done.append(o)
        except Exception as exc:  # keep going; report at the end
            failed.append({**o, "error": str(exc) or type(exc).__name__})
    for o in skipped:
        print(f"  skipped: {o['name']} — {o.get('fix', '')}")
    for o in failed:
        print(f"  FAILED:  {o['name']} — {o['error']}", file=sys.stderr)
    rc = 0 if not skipped and not failed else 1
    return {"run_id": run_id, "done": done, "skipped": skipped, "failed": failed, "rc": rc}


def undo_last(repo_root: Optional[Path] = None) -> Dict:
    """Put the last applied run back. Moves are reversed (never overwriting);
    empty folders are recreated; trashed duplicates stay in the Trash
    (use Finder > Put Back) because an exact copy is still in place."""
    repo_root = Path(repo_root or REPO_ROOT)
    rows = [r for r in read_log(repo_root) if not r.get("undone") and r.get("action") != "undo"]
    undone = {r.get("of") for r in read_log(repo_root) if r.get("action") == "undo"}
    runs = [r["run_id"] for r in rows if r["run_id"] not in undone]
    if not runs:
        return {"run_id": None, "restored": [], "left": [], "rc": 0, "message": "Nothing to undo."}
    last = runs[-1]
    restored, left = [], []
    for r in reversed([r for r in rows if r["run_id"] == last]):
        src, dst = Path(r["src"]), Path(r["dst"]) if r.get("dst") else None
        if r["action"] == "move":
            if dst and dst.exists() and not src.exists():
                shutil.move(str(dst), str(src))
                restored.append(r["name"])
            else:
                left.append({"name": r["name"], "why": "already back, or something is in the way"})
        elif r["action"] == "trash-folder":
            if not src.exists():
                src.mkdir(parents=True)
            restored.append(r["name"] + "/")
        elif r["action"] == "trash":
            left.append({"name": r["name"], "why": "exact/old copy is in the Trash (Finder > Put Back if you want it)"})
    _log(repo_root, {"run_id": datetime.now().strftime("%Y%m%d-%H%M%S"), "action": "undo", "of": last,
                     "at": datetime.now().isoformat(timespec="seconds"), "name": "", "src": "", "dst": ""})
    return {"run_id": last, "restored": restored, "left": left, "rc": 0,
            "message": f"Undid run {last}: {len(restored)} put back, {len(left)} left as is."}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Put stray top-folder files where scripts/_layout_rules.py says. "
        "Dry run by default; --apply to do it; --undo puts the last run back.")
    parser.add_argument("--root", default=str(REPO_ROOT))
    parser.add_argument("--apply", action="store_true", help="Actually do it (default is a dry run).")
    parser.add_argument("--yes", action="store_true", help="Accepted for old scripts; never prompts anyway.")
    parser.add_argument("--tidy-empty", action="store_true",
                        help="Also send empty folders that aren't part of the layout to the Trash.")
    parser.add_argument("--undo", action="store_true", help="Put the last applied run back.")
    args = parser.parse_args(argv)
    repo_root = Path(args.root).resolve()
    if args.undo:
        res = undo_last(repo_root)
        print(res["message"])
        for x in res["left"]:
            print(f"  left: {x['name']} — {x['why']}")
        return 0
    ops = plan_moves(repo_root, tidy_empty=args.tidy_empty)
    print(render_plan(ops, dry_run=not args.apply))
    if not args.apply:
        print("\nThis was a DRY RUN. No files were touched. Re-run with --apply to do it.")
        return 0
    res = apply(ops, repo_root=repo_root)
    print(f"\nDone: {len(res['done'])} step(s), {len(res['skipped'])} skipped, {len(res['failed'])} failed "
          f"(run {res['run_id']}; undo with --undo). Run 'bolt layout' to confirm.")
    return res["rc"]


if __name__ == "__main__":
    sys.exit(main())
