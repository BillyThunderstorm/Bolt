#!/usr/bin/env python3
"""Finish merge_py SHELL→READY on Goddess: module + bin/bolt + Docs."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path("/Users/carter/developer/Bolt")
WIP = REPO / "Data" / "_shells_wip"


def find_src(name: str) -> Path | None:
    for cand in (
        WIP / name,
        Path(__file__).resolve().parent / name,
        Path.cwd() / name,
    ):
        if cand.exists() and cand.stat().st_size > 100:
            return cand
    return None


def patch_bin_bolt(bolt: Path) -> None:
    text = bolt.read_text(encoding="utf-8")
    handler = '''
    # Built-in: merge local .py sources into one dump (Core/merge_py.py; soft-fail)
    if subcommand in (
        "merge-py",
        "merge_py",
        "mergepy",
        "merge-sources",
        "merge_sources",
    ):
        env = os.environ.copy()
        merge_script = CORE_DIR / "merge_py.py"
        if not merge_script.exists():
            print(f"Merge unavailable: missing {merge_script}", file=sys.stderr)
            return 0
        # Bare `bolt merge-py` → status (safe; write needs explicit run)
        if not rest:
            rest = ["status"]
        cmd = [py, str(merge_script)] + rest
        os.chdir(REPO_ROOT)
        return subprocess.call(cmd, cwd=str(REPO_ROOT), env=env)

'''
    marker = "    # Script passthrough\n"
    if '"merge-py",' in text or "'merge-py'," in text:
        print("bin/bolt: handler already present")
    elif marker not in text:
        raise SystemExit("bin/bolt: script passthrough marker not found")
    else:
        text = text.replace(marker, handler + marker, 1)
        print("bin/bolt: handler inserted")

    old_help = "  layout [--quiet|--json] Report any files misplaced at the repo root (no moves)\n"
    new_help = old_help + (
        "  merge-py [status|run|--dry-run|--list] [-o PATH]\n"
        "                          Concatenate local .py sources → Data/merged_bot.py\n"
        "                          (aliases: merge_py, merge-sources). Soft-fail.\n"
        "                          Bare `bolt merge-py` = status; write: bolt merge-py run\n"
    )
    if "merge-py [status" in text:
        print("bin/bolt: help already present")
    elif old_help not in text:
        raise SystemExit("bin/bolt: help anchor not found")
    else:
        text = text.replace(old_help, new_help, 1)
        print("bin/bolt: help updated")

    bolt.write_text(text, encoding="utf-8")


def main() -> int:
    if not REPO.is_dir():
        print(f"REPO missing: {REPO}", file=sys.stderr)
        return 1

    WIP.mkdir(parents=True, exist_ok=True)
    merge_src = find_src("merge_py.py")
    dest_merge = REPO / "Core" / "merge_py.py"
    if merge_src:
        shutil.copy2(merge_src, dest_merge)
        print(f"copied {merge_src} → {dest_merge}")
    else:
        print("WARN: merge_py.py source missing; patching in place if present")

    patch_bin_bolt(REPO / "bin" / "bolt")

    for name, dest in (
        ("READINESS.md", REPO / "Docs" / "READINESS.md"),
        ("BOLT_COMMANDS.md", REPO / "Core" / "modules" / "BOLT_COMMANDS.md"),
    ):
        src = find_src(name)
        if not src:
            print(f"SKIP docs (missing {name})")
            continue
        bak = dest.with_suffix(dest.suffix + ".bak-shells-20260908-eve")
        if dest.exists() and not bak.exists():
            shutil.copy2(dest, bak)
        shutil.copy2(src, dest)
        print(f"copied {src.name} → {dest}")

    py = REPO / ".venv" / "bin" / "python3"
    if not py.exists():
        py = Path(sys.executable)
    subprocess.check_call([str(py), "-m", "py_compile", str(dest_merge)])
    print("compile ok")

    r = subprocess.run(
        [str(py), str(dest_merge), "status", "--json"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=120,
    )
    print(r.stdout)
    if r.stderr:
        print(r.stderr, file=sys.stderr)
    if r.returncode != 0:
        return 1

    # Prefer bolt CLI if handler wired
    bolt = REPO / ".venv" / "bin" / "bolt"
    if bolt.exists():
        r2 = subprocess.run(
            [str(bolt), "merge-py", "status", "--json"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=120,
        )
        print("bolt merge-py status exit", r2.returncode)
        print(r2.stdout[:2000])
        if r2.stderr:
            print(r2.stderr, file=sys.stderr)
        return 0 if r2.returncode == 0 else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
