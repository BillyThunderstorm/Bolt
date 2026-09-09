"""
Creator_Domains.py — creator-domain requirements / instructions browser (PARTIAL)
================================================================================
Browse ``Docs/requirements/creator-domains-requirements.md`` and
``.github/instructions/creator-domains.instructions.md``.

This is **not** a multi-domain runtime engine — just a soft-fail CLI so the
spec docs are findable. Soft-fail prefix: ``Domains unavailable:``.

  bolt domains                    # status (default)
  bolt domains status [--json] [--probe]
  bolt domains list [--json]
  bolt domains show <slug|number|substring> [--json]
  bolt domains show instructions  # or: bolt domains instructions
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO = Path(__file__).resolve().parents[2]
_REQUIREMENTS = (
    _REPO / "Docs" / "requirements" / "creator-domains-requirements.md"
)
_INSTRUCTIONS = (
    _REPO / ".github" / "instructions" / "creator-domains.instructions.md"
)

_DOMAIN_HEADING_RE = re.compile(
    r"^##\s+(\d+)\.\s+(.+?)\s*$", re.MULTILINE
)
_NEXT_BOUNDARY_RE = re.compile(
    r"^##\s+(?:\d+\.|Cross-Domain)\b", re.MULTILINE
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slugify(title: str) -> str:
    s = (title or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "domain"


def requirements_path() -> Path:
    return _REQUIREMENTS


def instructions_path() -> Path:
    return _INSTRUCTIONS


def _readable_with_content(path: Path) -> Tuple[bool, str]:
    """Return (ok, detail). ok means exists, readable, non-empty strip."""
    if not path.is_file():
        return False, f"missing {path}"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return False, f"cannot read {path.name} ({exc})"
    if not text.strip():
        return False, f"empty {path.name}"
    return True, f"ok — {path.name} ({len(text)} chars)"


def parse_domains(text: Optional[str] = None) -> List[Dict[str, Any]]:
    """Parse numbered ``## N. Title`` headings from requirements markdown."""
    if text is None:
        try:
            text = _REQUIREMENTS.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
    domains: List[Dict[str, Any]] = []
    for m in _DOMAIN_HEADING_RE.finditer(text or ""):
        did = int(m.group(1))
        title = m.group(2).strip()
        domains.append(
            {
                "id": did,
                "title": title,
                "slug": _slugify(title),
            }
        )
    return domains


def _domain_section(text: str, domain_id: int) -> Optional[str]:
    """Extract section body from ``## N.`` until next numbered/Cross-Domain heading."""
    pattern = re.compile(
        rf"^##\s+{domain_id}\.\s+.+$", re.MULTILINE
    )
    m = pattern.search(text)
    if not m:
        return None
    start = m.start()
    rest = text[m.end() :]
    nxt = _NEXT_BOUNDARY_RE.search(rest)
    if nxt:
        end = m.end() + nxt.start()
        return text[start:end].rstrip() + "\n"
    return text[start:].rstrip() + "\n"


def resolve_domain(query: str, domains: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """Resolve by id, exact slug, or unique substring on title/slug."""
    q = (query or "").strip()
    if not q:
        return None
    doms = domains if domains is not None else parse_domains()
    if not doms:
        return None
    lower = q.lower()
    # Numeric id
    if q.isdigit():
        want = int(q)
        for d in doms:
            if d["id"] == want:
                return d
        return None
    # Exact slug
    for d in doms:
        if d["slug"] == lower:
            return d
    # Unique substring on slug or title
    hits: List[Dict[str, Any]] = []
    for d in doms:
        blob = f"{d['slug']} {d['title']}".lower()
        if lower in blob:
            hits.append(d)
    if len(hits) == 1:
        return hits[0]
    return None


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Creator-domains spec readiness. Never raises."""
    try:
        req_ok, req_detail = _readable_with_content(_REQUIREMENTS)
        ins_ok, ins_detail = _readable_with_content(_INSTRUCTIONS)
        domains: List[Dict[str, Any]] = []
        if req_ok:
            try:
                text = _REQUIREMENTS.read_text(encoding="utf-8", errors="replace")
                domains = parse_domains(text)
            except OSError:
                domains = []
                req_ok = False
                req_detail = "Domains unavailable: cannot re-read requirements"

        ready = req_ok and ins_ok and len(domains) > 0
        hints: List[str] = []
        if not req_ok:
            hints.append(f"Domains unavailable: requirements — {req_detail}")
        if not ins_ok:
            hints.append(f"Domains unavailable: instructions — {ins_detail}")
        if req_ok and not domains:
            hints.append(
                "Domains unavailable: no numbered ## N. domain headings in requirements"
            )

        if ready:
            hint = (
                f"{len(domains)} domain(s) in requirements + instructions present. "
                "Try: bolt domains list / bolt domains show 1"
            )
        else:
            hint = (
                " | ".join(hints)
                if hints
                else "Try: bolt domains status --json"
            )

        req_size = (
            _REQUIREMENTS.stat().st_size if _REQUIREMENTS.is_file() else 0
        )
        ins_size = (
            _INSTRUCTIONS.stat().st_size if _INSTRUCTIONS.is_file() else 0
        )

        info: Dict[str, Any] = {
            "ready": ready,
            "is_spec_browser": True,
            "is_runtime_system": False,
            "requirements_path": str(_REQUIREMENTS),
            "instructions_path": str(_INSTRUCTIONS),
            "requirements_exists": _REQUIREMENTS.is_file(),
            "instructions_exists": _INSTRUCTIONS.is_file(),
            "requirements_bytes": req_size,
            "instructions_bytes": ins_size,
            "domain_count": len(domains),
            "domains": domains,
            "hint": hint,
            "checked_at": _utc_now(),
        }
        if probe:
            info["probe_ok"] = False
            info["probe_detail"] = ""
            if not ready:
                info["probe_detail"] = hint
            else:
                try:
                    text = _REQUIREMENTS.read_text(
                        encoding="utf-8", errors="replace"
                    )
                    ok = len(text.strip()) > 0 and len(domains) >= 7
                    info["probe_ok"] = ok
                    info["probe_detail"] = (
                        f"ok — read requirements ({len(text)} chars, "
                        f"{len(domains)} domains); instructions "
                        f"{ins_size} bytes"
                        if ok
                        else (
                            "Domains unavailable: probe expected ≥7 domains "
                            f"with content (got {len(domains)})"
                        )
                    )
                    if not ok:
                        info["hint"] = info["probe_detail"]
                except OSError as exc:
                    info["probe_detail"] = (
                        f"Domains unavailable: probe read failed ({exc})"
                    )
                    info["hint"] = info["probe_detail"]
        return info
    except Exception as exc:
        return {
            "ready": False,
            "is_spec_browser": True,
            "is_runtime_system": False,
            "requirements_path": str(_REQUIREMENTS),
            "instructions_path": str(_INSTRUCTIONS),
            "requirements_exists": False,
            "instructions_exists": False,
            "requirements_bytes": 0,
            "instructions_bytes": 0,
            "domain_count": 0,
            "domains": [],
            "hint": f"Domains unavailable: status failed ({exc})",
            "error": str(exc),
            "checked_at": _utc_now(),
        }


def list_domains(*, as_json: bool = False) -> int:
    info = status()
    if not info.get("ready") and not info.get("domains"):
        msg = info.get("hint") or "Domains unavailable: no domains"
        if as_json:
            print(
                json.dumps(
                    {"ok": False, "error": msg, **info}, indent=2, default=str
                )
            )
        else:
            print(msg, file=sys.stderr)
        return 0

    domains = info.get("domains") or []
    if as_json:
        print(
            json.dumps(
                {"ok": True, "domain_count": len(domains), "domains": domains},
                indent=2,
                default=str,
            )
        )
        return 0

    print("\n  Creator domains (spec browser — not a runtime engine)")
    print("  " + "─" * 40)
    for d in domains:
        print(f"  {d['id']}.  {d['title']}")
        print(f"      slug: {d['slug']}")
    print()
    print("  Try: bolt domains show 1")
    print("       bolt domains show content-creation")
    print()
    return 0


def show_instructions(*, as_json: bool = False, max_lines: int = 80) -> int:
    path = _INSTRUCTIONS
    if not path.is_file():
        msg = f"Domains unavailable: missing instructions at {path}"
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        msg = f"Domains unavailable: cannot read instructions ({exc})"
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0

    lines = text.splitlines()
    preview = "\n".join(lines[:max_lines])
    truncated = len(lines) > max_lines
    if as_json:
        print(
            json.dumps(
                {
                    "ok": True,
                    "path": str(path),
                    "bytes": path.stat().st_size,
                    "line_count": len(lines),
                    "preview_lines": max_lines,
                    "truncated": truncated,
                    "body": preview,
                },
                indent=2,
                default=str,
            )
        )
        return 0

    print()
    print(f"  Instructions: {path}")
    print(f"  ({path.stat().st_size} bytes, {len(lines)} lines)")
    print("  " + "─" * 40)
    print(preview.rstrip())
    if truncated:
        print()
        print(f"  … truncated after {max_lines} lines — full file: {path}")
    print()
    return 0


def show_domain(query: str, *, as_json: bool = False) -> int:
    q = (query or "").strip()
    if not q:
        msg = (
            "Domains unavailable: show needs a domain "
            "(number, slug, or substring); or: show instructions"
        )
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0

    if q.lower() in ("instructions", "instruction", "instr", "behavior"):
        return show_instructions(as_json=as_json)

    info = status()
    domains = info.get("domains") or []
    if not domains:
        msg = info.get("hint") or "Domains unavailable: no domains"
        if as_json:
            print(
                json.dumps(
                    {"ok": False, "error": msg}, indent=2, default=str
                )
            )
        else:
            print(msg, file=sys.stderr)
        return 0

    # Ambiguity check before resolve
    lower = q.lower()
    if not q.isdigit():
        hits = [
            d
            for d in domains
            if lower in f"{d['slug']} {d['title']}".lower()
            or d["slug"] == lower
        ]
        exact = [d for d in domains if d["slug"] == lower]
        if exact:
            hits = exact
        elif len(hits) > 1:
            msg = (
                "Domains unavailable: ambiguous domain "
                f"{q!r} — matches: "
                + ", ".join(f"{d['id']}:{d['slug']}" for d in hits)
            )
            if as_json:
                print(
                    json.dumps(
                        {
                            "ok": False,
                            "error": msg,
                            "domains": domains,
                        },
                        indent=2,
                        default=str,
                    )
                )
            else:
                print(msg, file=sys.stderr)
            return 0

    dom = resolve_domain(q, domains)
    if dom is None:
        msg = (
            f"Domains unavailable: no domain matching {q!r}. "
            "Try: bolt domains list"
        )
        if as_json:
            print(
                json.dumps(
                    {"ok": False, "error": msg, "domains": domains},
                    indent=2,
                    default=str,
                )
            )
        else:
            print(msg, file=sys.stderr)
        return 0

    try:
        text = _REQUIREMENTS.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        msg = f"Domains unavailable: cannot read requirements ({exc})"
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0

    section = _domain_section(text, int(dom["id"]))
    if section is None:
        msg = (
            f"Domains unavailable: heading for domain {dom['id']} not found"
        )
        if as_json:
            print(json.dumps({"ok": False, "error": msg, "domain": dom}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0

    if as_json:
        print(
            json.dumps(
                {"ok": True, "domain": dom, "body": section},
                indent=2,
                default=str,
            )
        )
        return 0

    print()
    print(section.rstrip())
    print()
    return 0


def print_status(*, as_json: bool = False, probe: bool = False) -> int:
    info = status(probe=probe)
    if as_json:
        print(json.dumps(info, indent=2, default=str))
        return 0

    print("\n  Creator domains readiness (spec browser)")
    print("  " + "─" * 40)
    flag = "✓" if info.get("ready") else "○"
    print(f"  {flag}  overall ready: {bool(info.get('ready'))}")
    print(f"      is_spec_browser: {bool(info.get('is_spec_browser'))}")
    print(f"      is_runtime_system: {bool(info.get('is_runtime_system'))}")
    print(f"      requirements: {info.get('requirements_path')}")
    print(
        f"        exists={bool(info.get('requirements_exists'))} "
        f"bytes={info.get('requirements_bytes')}"
    )
    print(f"      instructions: {info.get('instructions_path')}")
    print(
        f"        exists={bool(info.get('instructions_exists'))} "
        f"bytes={info.get('instructions_bytes')}"
    )
    print(f"      domain_count: {info.get('domain_count')}")
    if info.get("hint"):
        print(f"      → {info['hint']}")
    if probe:
        pok = info.get("probe_ok")
        pflag = "✓" if pok else "○"
        print(f"  {pflag}  probe: {info.get('probe_detail') or '(none)'}")
    domains = info.get("domains") or []
    if domains:
        print()
        for d in domains:
            print(f"  {d.get('id')}.  {d.get('title')}  ({d.get('slug')})")
    print()
    print("  Try:")
    print("    bolt domains list")
    print("    bolt domains show 1")
    print("    bolt domains show instructions")
    print("    bolt domains status --json")
    print("  Note: spec browser only — not a multi-domain runtime.")
    print()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help", "help"):
        print(
            """bolt domains — browse creator-domain requirements (PARTIAL)

  bolt domains                         # readiness (default)
  bolt domains status [--json] [--probe]
  bolt domains list [--json]
  bolt domains show <slug|number|substring> [--json]
  bolt domains show instructions       # or: bolt domains instructions

Soft-fail: "Domains unavailable:". Spec docs only — not a runtime
domain engine. Sources:
  Docs/requirements/creator-domains-requirements.md
  .github/instructions/creator-domains.instructions.md
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
    if cmd in ("list", "ls", "domains"):
        return list_domains(as_json=json_out)
    if cmd in ("show", "read", "cat", "view", "open"):
        q = " ".join(positionals[1:]).strip()
        return show_domain(q, as_json=json_out)
    if cmd in ("instructions", "instruction", "instr"):
        return show_instructions(as_json=json_out)
    # Bare number / slug → show
    if cmd.isdigit() or "-" in cmd:
        return show_domain(" ".join(positionals), as_json=json_out)

    print(f"unknown domains action: {cmd}", file=sys.stderr)
    print(
        "  try: bolt domains status|list|show <slug|N> [--json]",
        file=sys.stderr,
    )
    return 0  # soft-fail informational


if __name__ == "__main__":
    raise SystemExit(main())
