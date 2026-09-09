#!/usr/bin/env python3
"""
merge_py.py — concatenate local Bolt .py sources into one dump file
=================================================================
Maintenance / audit helper (not part of the clip pipeline).

Walks the repo, skips vendor / cache / media trees, and writes a single
concatenated dump for LLM context, audits, or offline review.

Soft-fail prefixes:
  - ``Merge unavailable: …`` — cannot walk / write

CLI:
  bolt merge-py status [--json]
  bolt merge-py [--dry-run] [--list] [--output PATH]
  python3 Core/merge_py.py …

Default output: Data/merged_bot.py (repo-root merged_bot.py was a dead-end).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = PROJECT_ROOT / "Data" / "merged_bot.py"

# Directory name segments to skip anywhere in the relative path.
EXCLUDE_DIR_NAMES = {
    ".venv",
    ".git",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    "3rd_Party",
    "archive",
    "dist",
    "logs",
    "media",
    "vod_samples",
    "vector_db",
    "LLMs-from-scratch",
    "New Folder With Items",
    "legacy",
}

# Exact relative path prefixes (posix) to skip.
EXCLUDE_PREFIXES = (
    "Data/vector_db",
    "Data/learning",  # textbook notes, not product code
    "scripts/legacy",
    "Core/data",  # legacy nested data if present
)

# Never re-ingest the dump output.
EXCLUDE_FILE_NAMES = {
    "merged_bot.py",
}


def _rel(path: Path) -> Path:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return path


def _dir_name_excluded(name: str) -> bool:
    """True if a single path segment should be treated as excluded."""
    if not name:
        return True
    # Accidental dirs like ".venv<newline>" from bad writes.
    if any(ord(ch) < 32 for ch in name):
        return True
    if name in EXCLUDE_DIR_NAMES:
        return True
    # Prefix match so ".venv\n" / ".venv-backup" style junk is skipped.
    if name.startswith(".venv") or name.startswith(".git"):
        return True
    return False


def should_exclude(path: Path) -> bool:
    """True if this path should be skipped during the walk."""
    try:
        rel = path.resolve().relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return True
    parts = rel.parts
    if any(_dir_name_excluded(p) for p in parts):
        return True
    rel_posix = rel.as_posix()
    for prefix in EXCLUDE_PREFIXES:
        if rel_posix == prefix or rel_posix.startswith(prefix + "/"):
            return True
    if path.is_file() and path.name in EXCLUDE_FILE_NAMES:
        return True
    return False


def get_py_files(*, root: Optional[Path] = None) -> List[Path]:
    """Return sorted list of local .py files under the project root."""
    base = (root or PROJECT_ROOT).resolve()
    py_files: List[Path] = []
    for walk_root, dirs, files in os.walk(base):
        walk_path = Path(walk_root)
        # Prune excluded dirs in-place so os.walk does not descend.
        dirs[:] = sorted(
            d for d in dirs if not should_exclude(walk_path / d)
        )
        for name in files:
            if not name.endswith(".py"):
                continue
            full = walk_path / name
            if should_exclude(full):
                continue
            py_files.append(full)
    return sorted(py_files)


def status() -> Dict[str, Any]:
    """Readiness dict — never raises."""
    info: Dict[str, Any] = {
        "ready": False,
        "surface": "merge-py",
        "module": "Core/merge_py.py",
        "project_root": str(PROJECT_ROOT),
        "default_output": str(DEFAULT_OUTPUT),
        "file_count": 0,
        "total_bytes": 0,
        "sample": [],
        "hint": "",
        "error": None,
    }
    try:
        if not PROJECT_ROOT.is_dir():
            info["error"] = f"Merge unavailable: project root missing ({PROJECT_ROOT})"
            info["hint"] = "Check Bolt install path."
            return info
        files = get_py_files()
        info["file_count"] = len(files)
        info["total_bytes"] = sum(f.stat().st_size for f in files if f.is_file())
        info["sample"] = [str(_rel(f)) for f in files[:8]]
        info["ready"] = info["file_count"] > 0
        if not info["ready"]:
            info["error"] = "Merge unavailable: no .py files found after excludes"
            info["hint"] = "Check EXCLUDE_DIR_NAMES / project root."
        else:
            info["hint"] = (
                "bolt merge-py status; bolt merge-py --dry-run; "
                "bolt merge-py run  # write Data/merged_bot.py"
            )
    except Exception as exc:  # noqa: BLE001 — soft-fail surface
        info["error"] = f"Merge unavailable: {exc}"
        info["hint"] = "bolt merge-py status --json"
    return info


def print_status(*, as_json: bool = False) -> int:
    info = status()
    if as_json:
        print(json.dumps(info, indent=2, default=str))
        return 0
    print("\n  Merge-py readiness")
    print("  " + "─" * 40)
    flag = "✓" if info.get("ready") else "○"
    print(f"  {flag}  overall ready: {bool(info.get('ready'))}")
    if info.get("error"):
        print(f"      error: {info['error']}")
    if info.get("hint"):
        print(f"      → {info['hint']}")
    print(f"  files: {info.get('file_count')}  (~{info.get('total_bytes', 0):,} bytes)")
    print(f"  default output: {info.get('default_output')}")
    sample = info.get("sample") or []
    if sample:
        print("  sample:")
        for s in sample:
            print(f"      • {s}")
    print()
    print("  Try:")
    print("    bolt merge-py status --json")
    print("    bolt merge-py --dry-run")
    print("    bolt merge-py --list")
    print("    bolt merge-py run             # write Data/merged_bot.py")
    print("    bolt merge-py run -o /tmp/bolt_dump.py")
    print()
    return 0


def merge(
    *,
    output: Optional[Path] = None,
    dry_run: bool = False,
    list_only: bool = False,
) -> Dict[str, Any]:
    """
    Collect .py files and optionally write the dump.
    Never raises — returns a result dict with ok / error.
    """
    out_path = (output or DEFAULT_OUTPUT).expanduser()
    if not out_path.is_absolute():
        out_path = (PROJECT_ROOT / out_path).resolve()
    else:
        out_path = out_path.resolve()

    result: Dict[str, Any] = {
        "ok": False,
        "dry_run": dry_run,
        "list_only": list_only,
        "output": str(out_path),
        "file_count": 0,
        "bytes_written": 0,
        "files": [],
        "error": None,
    }
    try:
        files = get_py_files()
        # Do not include the destination if it somehow slipped through.
        files = [f for f in files if f.resolve() != out_path]
        result["file_count"] = len(files)
        result["files"] = [str(_rel(f)) for f in files]
        if list_only:
            result["ok"] = True
            return result
        if dry_run:
            result["ok"] = True
            result["bytes_written"] = sum(f.stat().st_size for f in files)
            return result
        if not files:
            result["error"] = "Merge unavailable: no .py files to merge"
            return result

        out_path.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with open(out_path, "w", encoding="utf-8") as outfile:
            header = (
                "# Merged Bolt Python files\n"
                "# Concatenation of local .py sources "
                "(excludes vendor, cache, media, learning notes).\n"
                "# Generated by Core/merge_py.py — not an executable bot.\n"
                f"# Files: {len(files)}\n\n"
            )
            outfile.write(header)
            written += len(header.encode("utf-8"))

            for py_file in files:
                rel_path = _rel(py_file)
                banner = (
                    "# =============================================================================\n"
                    f"# File: {rel_path}\n"
                    "# =============================================================================\n"
                )
                outfile.write(banner)
                written += len(banner.encode("utf-8"))
                try:
                    content = py_file.read_text(encoding="utf-8")
                except Exception as exc:  # noqa: BLE001
                    err_line = f"# ERROR reading {rel_path}: {exc}\n\n"
                    outfile.write(err_line)
                    written += len(err_line.encode("utf-8"))
                    continue
                outfile.write(content)
                written += len(content.encode("utf-8"))
                if not content.endswith("\n"):
                    outfile.write("\n")
                    written += 1
                outfile.write("\n\n")
                written += 2

        result["bytes_written"] = written
        result["ok"] = True
        return result
    except Exception as exc:  # noqa: BLE001 — soft-fail
        result["error"] = f"Merge unavailable: {exc}"
        return result


def _print_merge_result(result: Dict[str, Any], *, as_json: bool) -> int:
    if as_json:
        # Drop huge file list in JSON unless list_only / dry_run asked for it
        payload = dict(result)
        if not result.get("list_only") and len(payload.get("files") or []) > 40:
            payload["files"] = (payload["files"] or [])[:40]
            payload["files_truncated"] = True
        print(json.dumps(payload, indent=2, default=str))
        return 0 if result.get("ok") else 1

    if result.get("list_only"):
        for rel in result.get("files") or []:
            print(rel)
        print(f"\n{result.get('file_count', 0)} files", file=sys.stderr)
        return 0 if result.get("ok") else 1

    if result.get("error"):
        print(result["error"], file=sys.stderr)
        return 1

    n = result.get("file_count", 0)
    if result.get("dry_run"):
        print(f"Dry-run: would merge {n} .py files → {result.get('output')}")
        print(f"  (~{result.get('bytes_written', 0):,} source bytes)")
        return 0

    print(f"Merged {n} .py files → {result.get('output')}")
    print(f"  ({result.get('bytes_written', 0):,} bytes written)")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bolt merge-py",
        description=(
            "Concatenate local Bolt .py sources into one dump "
            "(Data/merged_bot.py by default). Soft-fails with "
            "'Merge unavailable:'."
        ),
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="run",
        help="status | run (default) | list",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Machine-readable output",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count files / bytes without writing",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_files",
        help="Print relative paths only (no write)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Output path (default: Data/merged_bot.py)",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Alias for status (readiness only; no write)",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)
    action = (args.action or "run").lower()

    if action in ("status", "check", "ready") or args.probe:
        return print_status(as_json=args.json)

    if action in ("help",):
        parser.print_help()
        return 0

    if action == "list" or args.list_files:
        result = merge(list_only=True)
        return _print_merge_result(result, as_json=args.json)

    if action not in ("run", "merge", "write", "dump"):
        print(f"unknown merge-py action: {action}", file=sys.stderr)
        print("  try: bolt merge-py status | bolt merge-py [--dry-run]", file=sys.stderr)
        return 0  # soft-fail informational

    out = Path(args.output) if args.output else None
    result = merge(output=out, dry_run=args.dry_run)
    return _print_merge_result(result, as_json=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
