"""
Learning_Notes.py — local LLM study-note browser (PARTIAL)
==========================================================
Browse ``Data/learning/`` chapter markdown (textbook / study log).

This is **not** Bolt product architecture — just a soft-fail CLI so the
notes are findable. Soft-fail prefix: ``Learning unavailable:``.

  bolt learning                 # status (default)
  bolt learning status [--json] [--probe]
  bolt learning list [--json]
  bolt learning show <slug|stem> [--json]
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO = Path(__file__).resolve().parents[2]
_LEARNING = _REPO / "Data" / "learning"
_TEMPLATE_NAMES = {"_TEMPLATE.md", "_template.md"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def learning_dir() -> Path:
    return _LEARNING


def _chapter_files(root: Optional[Path] = None) -> List[Path]:
    base = root or _LEARNING
    if not base.is_dir():
        return []
    files = [
        p
        for p in sorted(base.glob("*.md"))
        if p.is_file() and p.name not in _TEMPLATE_NAMES
    ]
    return files


def _stem_key(path: Path) -> str:
    return path.stem.lower()


def _title_from_text(text: str, fallback: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            return re.sub(r"^#+\s*", "", s).strip() or fallback
    return fallback


def _meta_line(text: str) -> Optional[str]:
    for line in text.splitlines()[:8]:
        s = line.strip()
        if s.startswith("*") and ("Captured:" in s or "Source:" in s):
            return s.strip("*").strip()
    return None


def describe_note(path: Path) -> Dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {
            "stem": path.stem,
            "path": str(path),
            "ok": False,
            "error": f"Learning unavailable: cannot read {path.name} ({exc})",
        }
    title = _title_from_text(text, path.stem)
    meta = _meta_line(text)
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime).isoformat(
            timespec="seconds"
        )
    except OSError:
        mtime = None
    return {
        "stem": path.stem,
        "path": str(path),
        "title": title,
        "meta": meta,
        "bytes": path.stat().st_size if path.exists() else 0,
        "mtime": mtime,
        "ok": True,
    }


def resolve_note(query: str) -> Optional[Path]:
    q = (query or "").strip()
    if not q:
        return None
    files = _chapter_files()
    if not files:
        return None
    # Exact stem / filename
    lower = q.lower()
    if lower.endswith(".md"):
        lower = lower[:-3]
    for p in files:
        if _stem_key(p) == lower or p.name.lower() == q.lower():
            return p
    # Unique substring match on stem or title
    hits: List[Path] = []
    for p in files:
        info = describe_note(p)
        blob = f"{p.stem} {info.get('title') or ''}".lower()
        if lower in blob:
            hits.append(p)
    if len(hits) == 1:
        return hits[0]
    return None


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Learning notes readiness. Never raises."""
    try:
        exists = _LEARNING.is_dir()
        files = _chapter_files() if exists else []
        template = (_LEARNING / "_TEMPLATE.md").is_file() if exists else False
        notes = [describe_note(p) for p in files]
        ready = exists and len(files) > 0
        hints: List[str] = []
        if not exists:
            hints.append(
                f"Learning unavailable: missing folder {_LEARNING}"
            )
        elif not files:
            hints.append(
                "Learning unavailable: no chapter .md files in Data/learning/ "
                "(study log only — not product architecture)"
            )
        if ready:
            hint = (
                f"{len(files)} chapter note(s) under Data/learning/. "
                "Try: bolt learning list / bolt learning show ch01"
            )
        else:
            hint = " | ".join(hints) if hints else "Try: bolt learning status --json"

        info: Dict[str, Any] = {
            "ready": ready,
            "is_study_log": True,
            "is_product_architecture": False,
            "path": str(_LEARNING),
            "exists": exists,
            "template_present": template,
            "chapter_count": len(files),
            "chapters": [
                {
                    "stem": n.get("stem"),
                    "title": n.get("title"),
                    "mtime": n.get("mtime"),
                }
                for n in notes
                if n.get("ok")
            ],
            "hint": hint,
            "checked_at": _utc_now(),
        }
        if probe:
            info["probe_ok"] = False
            info["probe_detail"] = ""
            if not ready:
                info["probe_detail"] = hint
            else:
                sample = files[0]
                try:
                    text = sample.read_text(encoding="utf-8", errors="replace")
                    ok = len(text.strip()) > 0
                    info["probe_ok"] = ok
                    info["probe_detail"] = (
                        f"ok — read {sample.name} ({len(text)} chars)"
                        if ok
                        else f"Learning unavailable: empty {sample.name}"
                    )
                    if not ok:
                        info["hint"] = info["probe_detail"]
                except OSError as exc:
                    info["probe_detail"] = (
                        f"Learning unavailable: probe read failed ({exc})"
                    )
                    info["hint"] = info["probe_detail"]
        return info
    except Exception as exc:
        return {
            "ready": False,
            "is_study_log": True,
            "is_product_architecture": False,
            "path": str(_LEARNING),
            "exists": False,
            "template_present": False,
            "chapter_count": 0,
            "chapters": [],
            "hint": f"Learning unavailable: status failed ({exc})",
            "error": str(exc),
            "checked_at": _utc_now(),
        }


def list_notes(*, as_json: bool = False) -> int:
    info = status()
    if not info.get("ready"):
        msg = info.get("hint") or "Learning unavailable: no notes"
        if as_json:
            print(json.dumps({"ok": False, "error": msg, **info}, indent=2, default=str))
        else:
            print(msg, file=sys.stderr)
        return 0

    notes = [describe_note(p) for p in _chapter_files()]
    if as_json:
        print(json.dumps({"ok": True, "notes": notes}, indent=2, default=str))
        return 0

    print("\n  Learning notes (study log — not product architecture)")
    print("  " + "─" * 40)
    for n in notes:
        if not n.get("ok"):
            print(f"  ○  {n.get('stem')}: {n.get('error')}")
            continue
        print(f"  •  {n['stem']}")
        print(f"      {n.get('title')}")
        if n.get("meta"):
            print(f"      {n['meta']}")
    print()
    print("  Try: bolt learning show ch01-what-are-llms")
    print()
    return 0


def show_note(query: str, *, as_json: bool = False) -> int:
    if not (query or "").strip():
        msg = "Learning unavailable: show needs a chapter slug (e.g. ch01)"
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0

    info = status()
    if not info.get("ready"):
        msg = info.get("hint") or "Learning unavailable: no notes"
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2, default=str))
        else:
            print(msg, file=sys.stderr)
        return 0

    path = resolve_note(query)
    if path is None:
        # Ambiguous or missing
        stems = [p.stem for p in _chapter_files()]
        lower = query.strip().lower()
        amb = [s for s in stems if lower in s.lower()]
        if len(amb) > 1:
            msg = (
                "Learning unavailable: ambiguous chapter "
                f"{query!r} — matches: " + ", ".join(amb)
            )
        else:
            msg = (
                f"Learning unavailable: no chapter matching {query!r}. "
                "Try: bolt learning list"
            )
        if as_json:
            print(
                json.dumps(
                    {"ok": False, "error": msg, "chapters": stems},
                    indent=2,
                    default=str,
                )
            )
        else:
            print(msg, file=sys.stderr)
        return 0

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        msg = f"Learning unavailable: cannot read {path.name} ({exc})"
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0

    meta = describe_note(path)
    if as_json:
        print(
            json.dumps(
                {"ok": True, "note": meta, "body": text},
                indent=2,
                default=str,
            )
        )
        return 0

    print()
    print(text.rstrip())
    print()
    return 0


def print_status(*, as_json: bool = False, probe: bool = False) -> int:
    info = status(probe=probe)
    if as_json:
        print(json.dumps(info, indent=2, default=str))
        return 0

    print("\n  Learning notes readiness (study log)")
    print("  " + "─" * 40)
    flag = "✓" if info.get("ready") else "○"
    print(f"  {flag}  overall ready: {bool(info.get('ready'))}")
    print(f"      is_study_log: {bool(info.get('is_study_log'))}")
    print(
        f"      is_product_architecture: "
        f"{bool(info.get('is_product_architecture'))}"
    )
    print(f"      path: {info.get('path')}")
    print(f"      exists: {bool(info.get('exists'))}")
    print(f"      template_present: {bool(info.get('template_present'))}")
    print(f"      chapter_count: {info.get('chapter_count')}")
    if info.get("hint"):
        print(f"      → {info['hint']}")
    if probe:
        pok = info.get("probe_ok")
        pflag = "✓" if pok else "○"
        print(f"  {pflag}  probe: {info.get('probe_detail') or '(none)'}")
    chapters = info.get("chapters") or []
    if chapters:
        print()
        for ch in chapters[:12]:
            print(f"  •  {ch.get('stem')} — {ch.get('title')}")
        if len(chapters) > 12:
            print(f"  …  +{len(chapters) - 12} more (bolt learning list)")
    print()
    print("  Try:")
    print("    bolt learning list")
    print("    bolt learning show ch01")
    print("    bolt learning status --json")
    print("  Note: study log only — not clip/queue product architecture.")
    print()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help", "help"):
        print(
            """bolt learning — browse local LLM study notes (PARTIAL)

  bolt learning                      # readiness (default)
  bolt learning status [--json] [--probe]
  bolt learning list [--json]
  bolt learning show <slug> [--json]

Soft-fail: "Learning unavailable:". Study log under Data/learning/ —
not product architecture. Template _TEMPLATE.md is ignored in counts.
"""
        )
        return 0

    json_out = "--json" in args
    probe = "--probe" in args
    positionals = [a for a in args if not a.startswith("-")]
    if not positionals:
        return print_status(as_json=json_out, probe=probe)

    cmd = positionals[0].lower()
    if cmd in ("status", "check", "ready"):
        return print_status(as_json=json_out, probe=probe)
    if cmd in ("list", "ls", "chapters", "notes"):
        return list_notes(as_json=json_out)
    if cmd in ("show", "read", "cat", "view", "open"):
        q = " ".join(positionals[1:]).strip()
        return show_note(q, as_json=json_out)
    # Bare slug → show (bolt learning ch01)
    if cmd.startswith("ch") or cmd.endswith(".md"):
        return show_note(" ".join(positionals), as_json=json_out)

    print(f"unknown learning action: {cmd}", file=sys.stderr)
    print(
        "  try: bolt learning status|list|show <slug> [--json]",
        file=sys.stderr,
    )
    return 0  # soft-fail informational


if __name__ == "__main__":
    raise SystemExit(main())
