"""
Creator_Domains.py — creator-domain spec browser (READY as a spec browser)
=========================================================================
Find and read Bolt's two creator-domain docs:

  Docs/requirements/creator-domains-requirements.md      (what Bolt must do)
  .github/instructions/creator-domains.instructions.md   (how Bolt should act)

This is **not** a multi-domain runtime engine. It makes the specs easy to
find, read, and search, and checks the two docs still agree with each other.
Soft-fail prefix: ``Domains unavailable:``. Read-only except ``open``, which
only opens a doc in its default Mac app.

  bolt domains                        # status (default)
  bolt domains status [--json] [--probe]
  bolt domains list [--json]
  bolt domains show <N|word>          # requirements + how Bolt should act
        [--req | --behavior] [--json]
  bolt domains show <heading word>    # any other section, e.g. priorities,
                                      # metrics, burnout, identity
  bolt domains show instructions      # whole instructions file
  bolt domains show requirements      # whole requirements file
  bolt domains search "words" [--json]
  bolt domains open [requirements|instructions] [--print]
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO = Path(__file__).resolve().parents[2]
_REQUIREMENTS = _REPO / "Docs" / "requirements" / "creator-domains-requirements.md"
_INSTRUCTIONS = _REPO / ".github" / "instructions" / "creator-domains.instructions.md"

_DOMAIN_HEADING_RE = re.compile(r"^##\s+(\d+)\.\s+(.+?)\s*$", re.MULTILINE)
_BEHAVIOR_HEADING_RE = re.compile(r"^###\s+(\d+)\.\s+(.+?)\s*$", re.MULTILINE)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
# Repo-relative paths mentioned in the docs, e.g. Data/context/x.md
_PATH_REF_RE = re.compile(
    r"(?<![\w/.-])((?:Data|Docs|Core|memory|modules|scripts|App|bin)/[\w./-]+\.(?:md|json|py|txt|yml|yaml))"
)
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (title or "").strip().lower())
    return s.strip("-") or "domain"


def requirements_path() -> Path:
    return _REQUIREMENTS


def instructions_path() -> Path:
    return _INSTRUCTIONS


def _read(path: Path) -> Tuple[Optional[str], str]:
    """Return (text or None, plain-words detail)."""
    if not path.is_file():
        return None, f"missing {path} (restore it from git: git checkout -- {path.relative_to(_REPO)})"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return None, f"cannot read {path.name} ({exc})"
    if not text.strip():
        return None, f"{path.name} is empty"
    return text, f"ok — {path.name} ({len(text.splitlines())} lines)"


def _readable_with_content(path: Path) -> Tuple[bool, str]:  # kept for callers
    text, detail = _read(path)
    return text is not None, detail


# ---------------------------------------------------------------- parsing


def parse_domains(text: Optional[str] = None) -> List[Dict[str, Any]]:
    """Numbered ``## N. Title`` headings from the requirements doc."""
    if text is None:
        text, _ = _read(_REQUIREMENTS)
    out: List[Dict[str, Any]] = []
    for m in _DOMAIN_HEADING_RE.finditer(text or ""):
        title = m.group(2).strip()
        out.append({"id": int(m.group(1)), "title": title, "slug": _slugify(title)})
    return out


def parse_behaviors(text: Optional[str] = None) -> List[Dict[str, Any]]:
    """Numbered ``### N. Title`` headings from the instructions doc."""
    if text is None:
        text, _ = _read(_INSTRUCTIONS)
    out: List[Dict[str, Any]] = []
    for m in _BEHAVIOR_HEADING_RE.finditer(text or ""):
        title = m.group(2).strip()
        out.append({"id": int(m.group(1)), "title": title, "slug": _slugify(title)})
    return out


def sections(text: str) -> List[Dict[str, Any]]:
    """Every markdown heading (outside code fences) with its body.

    A section runs until the next heading of the same or higher level.
    """
    lines = text.splitlines()
    heads: List[Tuple[int, int, str]] = []  # (line index, level, title)
    in_fence = False
    for i, line in enumerate(lines):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _HEADING_RE.match(line)
        if m:
            heads.append((i, len(m.group(1)), m.group(2).strip()))
    out: List[Dict[str, Any]] = []
    for n, (i, level, title) in enumerate(heads):
        end = len(lines)
        for j, lvl2, _t in heads[n + 1 :]:
            if lvl2 <= level:
                end = j
                break
        body = "\n".join(lines[i:end]).rstrip()
        body = re.sub(r"\n-{3,}\s*$", "", body).rstrip()  # drop trailing ---
        out.append(
            {
                "title": title,
                "level": level,
                "line": i + 1,
                "slug": _slugify(re.sub(r"^\d+\.\s*", "", title)),
                "body": body + "\n",
            }
        )
    return out


def _domain_section(text: str, domain_id: int) -> Optional[str]:
    for s in sections(text):
        if s["level"] == 2 and re.match(rf"^{domain_id}\.\s", s["title"]):
            return s["body"]
    return None


def _behavior_section(text: str, domain_id: int) -> Optional[str]:
    for s in sections(text):
        if s["level"] == 3 and re.match(rf"^{domain_id}\.\s", s["title"]):
            return s["body"]
    return None


def resolve_domain(query: str, domains: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """By number, exact slug, or a unique word/substring of the title."""
    q = (query or "").strip().lower()
    doms = domains if domains is not None else parse_domains()
    if not q or not doms:
        return None
    if q.isdigit():
        return next((d for d in doms if d["id"] == int(q)), None)
    exact = [d for d in doms if d["slug"] == q or d["title"].lower() == q]
    if exact:
        return exact[0]
    hits = _domain_hits(q, doms)
    return hits[0] if len(hits) == 1 else None


def _domain_hits(q: str, doms: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    q = q.strip().lower()
    words = [w for w in re.split(r"[\s\-_]+", q) if w]
    hits = []
    for d in doms:
        blob = f"{d['slug']} {d['title']}".lower()
        if q in blob or (words and all(w in blob for w in words)):
            hits.append(d)
    return hits


def _stale_path_refs(text: str) -> List[str]:
    """Repo paths a doc mentions that don't exist (``modules/`` = Core/modules)."""
    refs = sorted(set(_PATH_REF_RE.findall(text or "")))
    missing = []
    for r in refs:
        base = _REPO / "Core" if r.startswith("modules/") else _REPO
        if not (base / r).exists():
            missing.append(r)
    return missing


# ---------------------------------------------------------------- status


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Spec browser readiness + doc agreement check. Never raises."""
    try:
        req_text, req_detail = _read(_REQUIREMENTS)
        ins_text, ins_detail = _read(_INSTRUCTIONS)
        domains = parse_domains(req_text) if req_text else []
        behaviors = parse_behaviors(ins_text) if ins_text else []

        problems: List[str] = []
        if req_text is None:
            problems.append(f"Domains unavailable: requirements — {req_detail}")
        if ins_text is None:
            problems.append(f"Domains unavailable: instructions — {ins_detail}")
        if req_text is not None and not domains:
            problems.append(
                "Domains unavailable: no '## 1. Title' domain headings in the requirements doc"
            )

        # Do the two docs still list the same domains?
        mismatches: List[str] = []
        if domains and ins_text is not None:
            beh_by_id = {b["id"]: b for b in behaviors}
            for d in domains:
                b = beh_by_id.get(d["id"])
                if b is None:
                    mismatches.append(
                        f"domain {d['id']} ({d['title']}) has no '### {d['id']}. {d['title']}' "
                        "section in the instructions doc"
                    )
                elif b["slug"] != d["slug"]:
                    mismatches.append(
                        f"domain {d['id']} is '{d['title']}' in requirements but "
                        f"'{b['title']}' in instructions — rename one so they match"
                    )
            req_ids = {d["id"] for d in domains}
            for b in behaviors:
                if b["id"] not in req_ids:
                    mismatches.append(
                        f"instructions has '### {b['id']}. {b['title']}' but requirements has no domain {b['id']}"
                    )

        stale: List[str] = []
        for label, text in (("requirements", req_text), ("instructions", ins_text)):
            for ref in _stale_path_refs(text or ""):
                stale.append(f"{label} mentions {ref}, which doesn't exist")

        ready = not problems
        if ready:
            hint = (
                f"{len(domains)} domains; both docs present"
                + ("; docs agree" if not mismatches else f"; {len(mismatches)} mismatch(es)")
                + ". Try: bolt domains show 1 / bolt domains search \"burnout\""
            )
        else:
            hint = " | ".join(problems)

        info: Dict[str, Any] = {
            "ready": ready,
            "is_spec_browser": True,
            "is_runtime_system": False,
            "requirements_path": str(_REQUIREMENTS),
            "instructions_path": str(_INSTRUCTIONS),
            "requirements_exists": _REQUIREMENTS.is_file(),
            "instructions_exists": _INSTRUCTIONS.is_file(),
            "requirements_bytes": _REQUIREMENTS.stat().st_size if _REQUIREMENTS.is_file() else 0,
            "instructions_bytes": _INSTRUCTIONS.stat().st_size if _INSTRUCTIONS.is_file() else 0,
            "domain_count": len(domains),
            "behavior_count": len(behaviors),
            "domains": domains,
            "docs_agree": ready and not mismatches,
            "mismatches": mismatches,
            "stale_refs": stale,
            "problems": problems,
            "hint": hint,
            "checked_at": _utc_now(),
        }
        if probe:
            ok = ready and not mismatches and len(domains) >= 1
            info["probe_ok"] = ok
            if ok:
                info["probe_detail"] = (
                    f"ok — {len(domains)} domains in requirements, "
                    f"{len(behaviors)} matching behavior sections in instructions"
                )
            elif not ready:
                info["probe_detail"] = hint
            else:
                info["probe_detail"] = "Domains unavailable: docs disagree — " + "; ".join(mismatches)
        return info
    except Exception as exc:  # pragma: no cover - last resort
        return {
            "ready": False,
            "is_spec_browser": True,
            "is_runtime_system": False,
            "requirements_path": str(_REQUIREMENTS),
            "instructions_path": str(_INSTRUCTIONS),
            "domain_count": 0,
            "domains": [],
            "docs_agree": False,
            "mismatches": [],
            "stale_refs": [],
            "problems": [f"Domains unavailable: status failed ({exc})"],
            "hint": f"Domains unavailable: status failed ({exc})",
            "error": str(exc),
            "checked_at": _utc_now(),
        }


def _emit(obj: Dict[str, Any], as_json: bool, text: Optional[str] = None, err: bool = False) -> int:
    if as_json:
        print(json.dumps(obj, indent=2, default=str))
    elif text is not None:
        print(text, file=sys.stderr if err else sys.stdout)
    return 0


def _fail(msg: str, as_json: bool, **extra: Any) -> int:
    return _emit({"ok": False, "error": msg, **extra}, as_json, msg, err=True)


def print_status(*, as_json: bool = False, probe: bool = False) -> int:
    info = status(probe=probe)
    if as_json:
        print(json.dumps(info, indent=2, default=str))
        return 0
    print("\n  Creator domains (spec browser — not a runtime engine)")
    print("  " + "─" * 48)
    if info["ready"]:
        print(f"  ✓  READY — {info['domain_count']} domains, both docs found")
    else:
        print("  ○  not ready")
    print(f"      requirements: {info['requirements_path']}")
    print(f"      instructions: {info['instructions_path']}")
    for p in info.get("problems") or []:
        print(f"  ✗  {p}")
    if info["ready"]:
        if info.get("mismatches"):
            print("  !  the two docs disagree:")
            for m in info["mismatches"]:
                print(f"       - {m}")
        else:
            print("  ✓  both docs list the same domains")
    for s in info.get("stale_refs") or []:
        print(f"  !  {s}")
    if probe:
        flag = "✓" if info.get("probe_ok") else "○"
        print(f"  {flag}  probe: {info.get('probe_detail')}")
    if info.get("domains"):
        print()
        for d in info["domains"]:
            print(f"  {d['id']}.  {d['title']}")
    print()
    print("  Try:")
    print("    bolt domains show 5               # what Bolt must do + how it should act")
    print("    bolt domains show priorities      # any other section by name")
    print('    bolt domains search "burnout"')
    print("    bolt domains open instructions")
    print()
    return 0


def list_domains(*, as_json: bool = False) -> int:
    info = status()
    domains = info.get("domains") or []
    if not domains:
        return _fail(info.get("hint") or "Domains unavailable: no domains", as_json)
    if as_json:
        return _emit({"ok": True, "domain_count": len(domains), "domains": domains}, True)
    print("\n  Creator domains")
    print("  " + "─" * 40)
    for d in domains:
        print(f"  {d['id']}.  {d['title']}   ({d['slug']})")
    print()
    print("  Other sections: bolt domains show priorities | metrics | identity | burnout …")
    print("  Try: bolt domains show 1")
    print()
    return 0


def _show_whole(path: Path, as_json: bool) -> int:
    text, detail = _read(path)
    if text is None:
        return _fail(f"Domains unavailable: {detail}", as_json)
    if as_json:
        return _emit({"ok": True, "path": str(path), "line_count": len(text.splitlines()), "body": text}, True)
    print(f"\n  {path}\n  " + "─" * 40)
    print(text.rstrip())
    print()
    return 0


def show_instructions(*, as_json: bool = False, max_lines: Optional[int] = None) -> int:
    # max_lines kept for old callers; the whole file is shown now.
    return _show_whole(_INSTRUCTIONS, as_json)


def _find_sections(q: str, req_text: str, ins_text: str) -> List[Dict[str, Any]]:
    """Non-domain headings whose title matches every word of q."""
    words = [w for w in re.split(r"[\s\-_]+", q.lower()) if w]
    hits: List[Dict[str, Any]] = []
    for doc, text in (("requirements", req_text), ("instructions", ins_text)):
        for s in sections(text or ""):
            if s["level"] == 1:
                continue
            t = s["title"].lower()
            if words and all(w in t for w in words):
                hits.append({**s, "doc": doc})
    # Prefer exact title / slug matches
    exact = [h for h in hits if h["title"].lower() == q.lower() or h["slug"] == _slugify(q)]
    return exact or hits


def show_domain(query: str, *, as_json: bool = False, part: str = "both") -> int:
    q = (query or "").strip()
    if not q:
        return _fail(
            "Domains unavailable: show needs a domain number or word "
            "(e.g. bolt domains show 5, show streaming, show priorities)",
            as_json,
        )
    low = q.lower()
    if low in ("instructions", "instruction", "instr", "behavior", "behaviour"):
        return _show_whole(_INSTRUCTIONS, as_json)
    if low in ("requirements", "requirement", "reqs", "req", "spec"):
        return _show_whole(_REQUIREMENTS, as_json)

    req_text, req_detail = _read(_REQUIREMENTS)
    ins_text, _ = _read(_INSTRUCTIONS)
    if req_text is None:
        return _fail(f"Domains unavailable: {req_detail}", as_json)
    domains = parse_domains(req_text)

    dom: Optional[Dict[str, Any]] = None
    if low.isdigit():
        dom = next((d for d in domains if d["id"] == int(low)), None)
        if dom is None:
            ids = ", ".join(str(d["id"]) for d in domains)
            return _fail(f"Domains unavailable: there is no domain {q} (domains are {ids})", as_json)
    else:
        exact = [d for d in domains if d["slug"] == _slugify(q) or d["title"].lower() == low]
        hits = exact or _domain_hits(low, domains)
        if len(hits) > 1:
            names = "; ".join(f"{d['id']}. {d['title']}" for d in hits)
            return _fail(
                f"Domains unavailable: '{q}' matches more than one domain — {names}. "
                f"Use the number, e.g. bolt domains show {hits[0]['id']}",
                as_json,
                matches=hits,
            )
        if hits:
            dom = hits[0]

    if dom is not None:
        req_body = _domain_section(req_text, dom["id"])
        beh_body = _behavior_section(ins_text or "", dom["id"])
        if as_json:
            return _emit(
                {
                    "ok": True,
                    "domain": dom,
                    "body": req_body,  # old key
                    "requirements": req_body,
                    "behavior": beh_body,
                },
                True,
            )
        print()
        if part in ("both", "req"):
            print(f"  WHAT BOLT MUST DO — {_REQUIREMENTS.name}")
            print("  " + "─" * 48)
            print((req_body or "(section not found)").rstrip())
            print()
        if part in ("both", "behavior"):
            print(f"  HOW BOLT SHOULD ACT — {_INSTRUCTIONS.name}")
            print("  " + "─" * 48)
            if beh_body:
                print(beh_body.rstrip())
            else:
                print(
                    f"  (no '### {dom['id']}. {dom['title']}' section in the instructions doc — "
                    "run bolt domains status)"
                )
            print()
        return 0

    # Not a domain: try any other heading in either doc.
    secs = _find_sections(q, req_text, ins_text or "")
    if not secs:
        return _fail(
            f"Domains unavailable: nothing called '{q}'. Try bolt domains list, "
            f'or bolt domains search "{q}" to look inside the text',
            as_json,
        )
    if len(secs) > 1:
        names = "; ".join(f"{s['title']} ({s['doc']})" for s in secs[:12])
        return _fail(
            f"Domains unavailable: '{q}' matches {len(secs)} sections — {names}. Use more words.",
            as_json,
            matches=[{k: s[k] for k in ("title", "doc", "line")} for s in secs],
        )
    s = secs[0]
    if as_json:
        return _emit({"ok": True, "section": {k: s[k] for k in ("title", "doc", "line")}, "body": s["body"]}, True)
    path = _REQUIREMENTS if s["doc"] == "requirements" else _INSTRUCTIONS
    print(f"\n  {path.name}, line {s['line']}\n  " + "─" * 48)
    print(s["body"].rstrip())
    print()
    return 0


def search(query: str, *, as_json: bool = False, limit: int = 40) -> int:
    q = (query or "").strip()
    words = [w for w in q.lower().split() if w]
    if not words:
        return _fail('Domains unavailable: search needs words, e.g. bolt domains search "burnout"', as_json)
    results: List[Dict[str, Any]] = []
    for doc, path in (("requirements", _REQUIREMENTS), ("instructions", _INSTRUCTIONS)):
        text, _ = _read(path)
        if text is None:
            continue
        current = ""
        in_fence = False
        for i, line in enumerate(text.splitlines(), 1):
            if _FENCE_RE.match(line):
                in_fence = not in_fence
            m = None if in_fence else _HEADING_RE.match(line)
            if m:
                current = m.group(2).strip()
            if all(w in line.lower() for w in words):
                results.append({"doc": doc, "line": i, "section": current, "text": line.strip()})
    total = len(results)
    shown = results[:limit]
    if as_json:
        return _emit({"ok": True, "query": q, "count": total, "results": shown}, True)
    if not results:
        print(f"\n  Nothing in the creator-domain docs mentions all of: {q}\n")
        return 0
    print(f"\n  {total} line(s) mention {q!r}" + (f" (first {limit} shown)" if total > limit else ""))
    print("  " + "─" * 48)
    last = None
    for r in shown:
        key = (r["doc"], r["section"])
        if key != last:
            print(f"\n  [{r['doc']}] {r['section'] or '(top)'}")
            last = key
        print(f"    line {r['line']}: {r['text'][:160]}")
    print("\n  Read a whole section: bolt domains show <section name>\n")
    return 0


def open_doc(which: str = "requirements", *, print_only: bool = False, as_json: bool = False) -> int:
    w = (which or "requirements").lower()
    path = _INSTRUCTIONS if w.startswith(("instr", "behav")) else _REQUIREMENTS
    if not path.is_file():
        return _fail(f"Domains unavailable: missing {path}", as_json)
    opener = shutil.which("open")
    if print_only or not opener:
        return _emit({"ok": True, "path": str(path), "opened": False}, as_json, str(path))
    try:
        rc = subprocess.run([opener, str(path)], timeout=10, capture_output=True, text=True)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _fail(f"Domains unavailable: could not open {path.name} ({exc}); the file is at {path}", as_json)
    if rc.returncode != 0:
        return _fail(
            f"Domains unavailable: open failed ({(rc.stderr or '').strip()}); the file is at {path}", as_json
        )
    return _emit({"ok": True, "path": str(path), "opened": True}, as_json, f"Opened {path}")


_HELP = """bolt domains — browse Bolt's creator-domain specs (spec browser, not a runtime)

  bolt domains                          # status (default)
  bolt domains status [--json] [--probe]
  bolt domains list [--json]
  bolt domains show <N|word> [--req|--behavior] [--json]
                                        # what Bolt must do + how it should act
  bolt domains show priorities          # any other section by name
  bolt domains show instructions|requirements   # a whole doc
  bolt domains search "words" [--json]
  bolt domains open [requirements|instructions] [--print]

Docs:
  Docs/requirements/creator-domains-requirements.md
  .github/instructions/creator-domains.instructions.md
Soft-fail prefix: "Domains unavailable:". Read-only (open just opens the file).
"""


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help", "help"):
        print(_HELP)
        return 0
    as_json = "--json" in args
    probe = "--probe" in args
    part = "req" if "--req" in args else "behavior" if ("--behavior" in args or "--behaviour" in args) else "both"
    print_only = "--print" in args
    pos = [a for a in args if not a.startswith("--")]
    if not pos:
        return print_status(as_json=as_json, probe=probe)
    cmd = pos[0].lower()
    rest = " ".join(pos[1:]).strip()
    if cmd in ("status", "check", "ready"):
        return print_status(as_json=as_json, probe=probe)
    if cmd in ("list", "ls", "domains"):
        return list_domains(as_json=as_json)
    if cmd in ("show", "read", "cat", "view"):
        return show_domain(rest, as_json=as_json, part=part)
    if cmd in ("search", "find", "grep"):
        return search(rest, as_json=as_json)
    if cmd in ("open", "edit"):
        return open_doc(rest or "requirements", print_only=print_only, as_json=as_json)
    if cmd in ("instructions", "instruction", "instr"):
        return _show_whole(_INSTRUCTIONS, as_json)
    if cmd in ("requirements", "requirement", "reqs"):
        return _show_whole(_REQUIREMENTS, as_json)
    # Bare number / word → show
    return show_domain(" ".join(pos), as_json=as_json, part=part)


if __name__ == "__main__":
    raise SystemExit(main())
