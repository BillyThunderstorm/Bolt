"""
Learning_Notes.py — local LLM study-note log (READY)
=====================================================
Browse, search and add ``Data/learning/`` chapter markdown (study log).

This is **not** Bolt product architecture — it is William's study log, kept
findable. Soft-fail prefix: ``Learning unavailable:``.

  bolt learning                 # status (default)
  bolt learning status [--json] [--probe]
  bolt learning list [--json]
  bolt learning show <slug|stem|number> [--json]
  bolt learning search "words" [--json]
  bolt learning new "Chapter title" [--source "..."] [--open]
  bolt learning edit <slug>     # open the note in the Mac's default app
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
    # Bare chapter number: "3" / "03" / "ch3" → unique chNN note
    m = re.fullmatch(r"(?:ch)?\s*0*(\d+)", lower)
    if m:
        n = int(m.group(1))
        num_hits = [p for p in files if _chapter_number(p) == n]
        if len(num_hits) == 1:
            return num_hits[0]
        if len(num_hits) > 1:
            return None
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


def _chapter_number(path: Path) -> Optional[int]:
    m = re.match(r"ch(\d+)", path.stem.lower())
    return int(m.group(1)) if m else None


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
    return slug[:60].strip("-") or "note"


def _soft(msg: str, as_json: bool, **extra: Any) -> int:
    if as_json:
        print(json.dumps({"ok": False, "error": msg, **extra}, indent=2, default=str))
    else:
        print(msg, file=sys.stderr)
    return 0


def search_notes(query: str, *, as_json: bool = False, limit: int = 40) -> int:
    """Find study-note lines that contain every word of ``query``."""
    words = [w for w in re.split(r"\s+", (query or "").strip().lower()) if w]
    if not words:
        return _soft(
            'Learning unavailable: search needs words, e.g. bolt learning search "attention"',
            as_json,
        )
    files = _chapter_files()
    if not files:
        return _soft(status().get("hint") or "Learning unavailable: no notes", as_json)

    hits: List[Dict[str, Any]] = []
    notes_hit: Dict[str, int] = {}
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            low = line.lower()
            if all(w in low for w in words):
                notes_hit[path.stem] = notes_hit.get(path.stem, 0) + 1
                hits.append({"stem": path.stem, "line": i, "text": line.strip()})

    if as_json:
        print(json.dumps({"ok": True, "query": query, "matches": hits[:limit],
                          "match_count": len(hits), "notes": notes_hit},
                         indent=2, default=str))
        return 0

    print(f'\n  Study notes matching "{query}"')
    print("  " + "─" * 40)
    if not hits:
        print("  No lines contain all of those words.")
        print("  Try fewer words, or: bolt learning list")
        print()
        return 0
    last = None
    for h in hits[:limit]:
        if h["stem"] != last:
            print(f"  •  {h['stem']}")
            last = h["stem"]
        text = h["text"]
        if len(text) > 110:
            text = text[:107] + "…"
        print(f"      line {h['line']}: {text}")
    if len(hits) > limit:
        print(f"  …  +{len(hits) - limit} more lines")
    print()
    print(f"  {len(hits)} line(s) in {len(notes_hit)} note(s). Read one: bolt learning show <name>")
    print()
    return 0


def _open_file(path: Path) -> Optional[str]:
    """Open with the Mac's default app. Returns an error string or None."""
    import shutil
    import subprocess

    opener = shutil.which("open") or shutil.which("xdg-open")
    if not opener:
        return "no 'open' command on this computer"
    try:
        subprocess.Popen([opener, str(path)], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except OSError as exc:
        return str(exc)
    return None


def new_note(title: str, *, source: str = "", open_after: bool = False,
             as_json: bool = False) -> int:
    """Create the next chapter note from _TEMPLATE.md. Never overwrites."""
    title = (title or "").strip()
    if not title:
        return _soft(
            'Learning unavailable: new needs a title, e.g. bolt learning new "Embeddings"',
            as_json,
        )
    if not _LEARNING.is_dir():
        try:
            _LEARNING.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return _soft(f"Learning unavailable: cannot create {_LEARNING} ({exc})", as_json)

    nums = [n for n in (_chapter_number(p) for p in _chapter_files()) if n is not None]
    num = (max(nums) + 1) if nums else 1
    # Title like "Ch09 — Foo" keeps its own number.
    m = re.match(r"(?i)ch\s*0*(\d+)\s*[-—:–]?\s*(.*)$", title)
    if m and m.group(2).strip():
        num = int(m.group(1))
        title = m.group(2).strip()
    stem = f"ch{num:02d}-{_slugify(title)}"
    path = _LEARNING / f"{stem}.md"
    if path.exists():
        return _soft(
            f"Learning unavailable: {path.name} already exists — nothing overwritten. "
            f"Read it: bolt learning show {stem}",
            as_json, path=str(path),
        )

    today = datetime.now().strftime("%Y-%m-%d")
    src = source.strip() or "[book / video / experiment / conversation]"
    tpl_path = _LEARNING / "_TEMPLATE.md"
    try:
        body = tpl_path.read_text(encoding="utf-8")
    except OSError:
        body = "# Ch0X — [Chapter Title]\n*Captured: YYYY-MM-DD | Source: [book / video / experiment / conversation]*\n\n## The core idea\n\n\n## Why this matters for Bolt\n\n"
    lines = body.splitlines()
    out: List[str] = []
    did_title = did_meta = False
    for line in lines:
        if not did_title and line.strip().startswith("#"):
            out.append(f"# Ch{num:02d} — {title}")
            did_title = True
            continue
        if not did_meta and "Captured:" in line:
            out.append(f"*Captured: {today} | Source: {src}*")
            did_meta = True
            continue
        out.append(line)
    text = "\n".join(out).rstrip() + "\n"
    try:
        with open(path, "x", encoding="utf-8") as fh:  # x = never overwrite
            fh.write(text)
    except FileExistsError:
        return _soft(f"Learning unavailable: {path.name} already exists — nothing overwritten.", as_json)
    except OSError as exc:
        return _soft(f"Learning unavailable: cannot write {path.name} ({exc})", as_json)

    open_err = _open_file(path) if open_after else None
    if as_json:
        print(json.dumps({"ok": True, "path": str(path), "stem": stem,
                          "opened": open_after and not open_err,
                          "open_error": open_err}, indent=2))
        return 0
    print(f"\n  ✓  New study note: Data/learning/{path.name}")
    print(f"      Ch{num:02d} — {title}  (captured {today})")
    if open_after:
        print("      Opened it." if not open_err else f"      Couldn't open it ({open_err}).")
    else:
        print(f"      Fill it in: bolt learning edit {stem}")
    print()
    return 0


def edit_note(query: str, *, as_json: bool = False) -> int:
    path = resolve_note(query) if (query or "").strip() else None
    if path is None:
        return show_note(query, as_json=as_json)  # same clear not-found / ambiguous text
    err = _open_file(path)
    if err:
        return _soft(f"Learning unavailable: couldn't open {path.name} ({err}). "
                     f"File is at {path}", as_json)
    if as_json:
        print(json.dumps({"ok": True, "opened": str(path)}, indent=2))
    else:
        print(f"  Opened Data/learning/{path.name}")
    return 0


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
                "Try: bolt learning list / show 3 / search \"words\" / new \"Title\""
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
        m = re.fullmatch(r"(?:ch)?\s*0*(\d+)", lower)
        if m:
            amb = [p.stem for p in _chapter_files() if _chapter_number(p) == int(m.group(1))]
        else:
            amb = [s for s in stems if lower in s.lower()]
        if len(amb) > 1:
            msg = (
                f"Learning unavailable: more than one note matches {query!r}: "
                + ", ".join(amb)
                + f". Use the full name, e.g. bolt learning show {amb[0]}"
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
    print("    bolt learning show 3")
    print('    bolt learning search "attention"')
    print('    bolt learning new "Embeddings" --open')
    print("  Note: study log only — not clip/queue product architecture.")
    print()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help", "help"):
        print(
            """bolt learning — your LLM study log in Data/learning/

  bolt learning                      # readiness (default)
  bolt learning status [--json] [--probe]
  bolt learning list [--json]
  bolt learning show <slug|number> [--json]   e.g. show 3, show attention
  bolt learning search "words" [--json]       lines containing every word
  bolt learning new "Title" [--source "..."] [--open]
                                     next chapter from _TEMPLATE.md, never overwrites
  bolt learning edit <slug>          open a note in the Mac's default app

Soft-fail: "Learning unavailable:". Study log under Data/learning/ —
not product architecture. Template _TEMPLATE.md is ignored in counts.
"""
        )
        return 0

    json_out = "--json" in args
    probe = "--probe" in args
    open_after = "--open" in args
    source = ""
    cleaned: List[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--source" and i + 1 < len(args):
            source = args[i + 1]
            i += 2
            continue
        if a.startswith("--source="):
            source = a.split("=", 1)[1]
        cleaned.append(a)
        i += 1
    positionals = [a for a in cleaned if not a.startswith("-")]
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
    if cmd in ("search", "find", "grep"):
        return search_notes(" ".join(positionals[1:]), as_json=json_out)
    if cmd in ("new", "add", "create"):
        return new_note(" ".join(positionals[1:]), source=source,
                        open_after=open_after, as_json=json_out)
    if cmd in ("edit",):
        return edit_note(" ".join(positionals[1:]), as_json=json_out)
    # Bare slug → show (bolt learning ch01)
    if cmd.startswith("ch") or cmd.endswith(".md"):
        return show_note(" ".join(positionals), as_json=json_out)

    print(f"unknown learning action: {cmd}", file=sys.stderr)
    print(
        "  try: bolt learning status|list|show|search|new|edit [--json]",
        file=sys.stderr,
    )
    return 0  # soft-fail informational


if __name__ == "__main__":
    raise SystemExit(main())
