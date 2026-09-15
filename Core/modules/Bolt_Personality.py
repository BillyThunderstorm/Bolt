#!/usr/bin/env python3
"""
Bolt_Personality.py — Gemini persona chat loader (PARTIAL)
==========================================================
Soft-fail CLI for the former SHELL/thin dead-end
``scripts/load_bolt_personality.py`` (wrong ``parents[3]`` → ``/Users/carter``
looking for missing ``/Users/carter/Bolt_Personality.txt``).

Soft-fail prefix: ``Personality unavailable:``.
Stay PARTIAL — distinct from READY ``bolt gemini`` / ``bolt nexus`` /
``bolt chat`` (Twitch IRC personality).

Canonical persona: ``Data/context/bolt-personality.md``.
``ready=True`` when engine present + canonical markdown exists (Gemini key
gates chat/run only).

Public API:
  status() / list_items() / try_run() / print_status() / main()
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SOFT = "Personality unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_ENGINE = _REPO / "scripts" / "load_bolt_personality.py"
_CORE = _REPO / "Core"
_PATHS = _REPO / "scripts" / "_paths.py"
_CANON = _REPO / "Data" / "context" / "bolt-personality.md"
_FALLBACK_TXT = _REPO / "Docs" / "scratch" / "reviews" / "Bolt_Personality.txt"
_FALLBACK_ROOT = _REPO / "Bolt_Personality.txt"
_PAGES = _REPO / "Core" / "Bolt_Personality.pages"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _soft(msg: str) -> str:
    if msg.startswith(_SOFT):
        return msg
    return f"{_SOFT} {msg}"


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(_REPO / ".env", override=False)
        load_dotenv(override=False)
    except Exception:
        pass


def _engine_stale() -> bool:
    """True if engine still assigns project root via parents[3]."""
    if not _ENGINE.is_file():
        return False
    try:
        text = _ENGINE.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    if "from _paths import" in text:
        return False
    return "parents[3]" in text


def _genai_available() -> bool:
    try:
        return importlib.util.find_spec("google.genai") is not None
    except Exception:
        return False


def _gemini_key() -> str:
    _load_dotenv()
    return (os.environ.get("GEMINI_API_KEY") or "").strip()


def _redact_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}…{key[-4:]}"


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Readiness for persona file + Gemini chat loader (PARTIAL)."""
    try:
        engine_ok = _ENGINE.is_file()
        stale = _engine_stale()
        paths_ok = _PATHS.is_file()
        canon_ok = _CANON.is_file()
        fb_txt_ok = _FALLBACK_TXT.is_file()
        fb_root_ok = _FALLBACK_ROOT.is_file()
        pages_ok = _PAGES.is_file()
        genai_ok = _genai_available()
        key = _gemini_key()
        key_ok = bool(key)

        out: Dict[str, Any] = {
            "checked_at": _utc_now(),
            "ready": False,
            "partial": True,
            "readiness": "PARTIAL",
            "soft_fail_prefix": _SOFT,
            "engine_path": str(_ENGINE),
            "engine_present": engine_ok,
            "engine_stale_parents3": stale,
            "paths_helper_present": paths_ok,
            "personality_path": str(_CANON),
            "personality_present": canon_ok,
            "fallback_txt_path": str(_FALLBACK_TXT),
            "fallback_txt_present": fb_txt_ok,
            "fallback_root_path": str(_FALLBACK_ROOT),
            "fallback_root_present": fb_root_ok,
            "pages_path": str(_PAGES),
            "pages_present": pages_ok,
            "google_genai_available": genai_ok,
            "gemini_api_key_present": key_ok,
            "gemini_api_key_redacted": _redact_key(key) if key_ok else "",
            "cli": "bolt personality",
            "note": (
                "Gemini persona chat loader over Data/context/bolt-personality.md. "
                "Distinct from READY bolt gemini / bolt nexus / bolt chat "
                "(Twitch IRC personality). Former SHELL parents[3] wrong root."
            ),
            "is_stranger_ready": False,
            "probe": bool(probe),
            "error": "",
            "hint": "",
        }

        if not engine_ok:
            out["error"] = _soft(f"engine missing ({_ENGINE})")
            out["hint"] = out["error"]
            return out

        if stale:
            out["error"] = _soft(
                "engine still uses parents[3] / missing Bolt_Personality.txt root"
            )
            out["hint"] = out["error"]
            return out

        if not paths_ok:
            out["error"] = _soft("scripts/_paths.py missing")
            out["hint"] = out["error"]
            return out

        if not canon_ok:
            out["error"] = _soft(
                f"canonical personality missing ({_CANON})"
            )
            out["hint"] = out["error"]
            return out

        # ready when engine + canonical md present (key gates chat/run only)
        out["ready"] = True
        hint_bits = ["ok — run: bolt personality run (needs google.genai + GEMINI_API_KEY)"]
        if not genai_ok:
            hint_bits.append("google.genai not installed (chat soft-fails)")
        if not key_ok:
            hint_bits.append("GEMINI_API_KEY missing (chat soft-fails)")
        out["hint"] = "; ".join(hint_bits)

        if probe and engine_ok:
            try:
                code = (
                    "import ast, pathlib; "
                    f"ast.parse(pathlib.Path({str(_ENGINE)!r}).read_text()); "
                    "print('probe_ok')"
                )
                r = subprocess.run(
                    [sys.executable, "-c", code],
                    cwd=str(_REPO),
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                out["probe_engine_parse"] = r.returncode == 0 and "probe_ok" in (
                    r.stdout or ""
                )
                if not out["probe_engine_parse"]:
                    out["hint"] = _soft(
                        f"probe engine parse failed ({(r.stderr or r.stdout or '')[:120]})"
                    )
            except Exception as exc:
                out["probe_engine_parse"] = False
                out["hint"] = _soft(f"probe failed ({exc})")
        return out
    except Exception as exc:
        return {
            "checked_at": _utc_now(),
            "ready": False,
            "partial": True,
            "readiness": "PARTIAL",
            "soft_fail_prefix": _SOFT,
            "error": _soft(f"status failed ({exc})"),
            "hint": _soft(f"status failed ({exc})"),
            "cli": "bolt personality",
            "is_stranger_ready": False,
            "probe": bool(probe),
        }


def list_items(*, as_json: bool = False) -> int:
    """Checklist of personality loader gates."""
    try:
        info = status(probe=False)
        rows = [
            ("engine load_bolt_personality.py", bool(info.get("engine_present"))),
            (
                "engine post-reorg (_paths, not parents[3])",
                not bool(info.get("engine_stale_parents3")),
            ),
            ("scripts/_paths.py", bool(info.get("paths_helper_present"))),
            (
                f"canonical Data/context/bolt-personality.md",
                bool(info.get("personality_present")),
            ),
            (
                f"fallback Docs/scratch/reviews/Bolt_Personality.txt",
                bool(info.get("fallback_txt_present")),
            ),
            (
                f"fallback repo-root Bolt_Personality.txt",
                bool(info.get("fallback_root_present")),
            ),
            ("google.genai available (chat gate)", bool(info.get("google_genai_available"))),
            ("GEMINI_API_KEY present (chat gate)", bool(info.get("gemini_api_key_present"))),
            ("soft-fail CLI (bolt personality)", True),
            ("distinct from READY gemini/nexus/chat", True),
            ("stay PARTIAL (not stranger-ready)", True),
        ]
        if as_json:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "readiness": "PARTIAL",
                        "items": [{"name": n, "ok": ok} for n, ok in rows],
                        "hint": info.get("hint"),
                        "error": info.get("error"),
                    },
                    indent=2,
                )
            )
            return 0
        print(
            "Bolt personality (PARTIAL — Gemini persona file; not Twitch chat)",
            flush=True,
        )
        for name, ok in rows:
            mark = "OK" if ok else "--"
            print(f"  [{mark}] {name}", flush=True)
        if info.get("gemini_api_key_redacted"):
            print(
                f"  key redact: {info.get('gemini_api_key_redacted')}",
                flush=True,
            )
        if info.get("hint"):
            print(f"  → {info['hint']}", flush=True)
        print("  (run: bolt personality run | status | list)", flush=True)
        return 0
    except Exception as exc:
        msg = _soft(f"list failed ({exc})")
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0


def try_run(
    *,
    dry_run: bool = False,
    as_json: bool = False,
    extra: Optional[List[str]] = None,
) -> int:
    """Soft-fail invoke load_bolt_personality.py (never raises; never hangs)."""
    try:
        info = status(probe=False)
        if not info.get("engine_present"):
            msg = info.get("error") or _soft("engine script missing")
            if as_json:
                print(
                    json.dumps(
                        {"ok": False, "error": msg, "readiness": "PARTIAL"},
                        indent=2,
                    )
                )
            else:
                print(msg, file=sys.stderr)
            return 0
        if info.get("engine_stale_parents3"):
            msg = info.get("error") or _soft("engine still uses parents[3]")
            if as_json:
                print(
                    json.dumps(
                        {"ok": False, "error": msg, "readiness": "PARTIAL"},
                        indent=2,
                    )
                )
            else:
                print(msg, file=sys.stderr)
            return 0
        if not info.get("personality_present"):
            msg = info.get("error") or _soft("canonical personality missing")
            if as_json:
                print(
                    json.dumps(
                        {"ok": False, "error": msg, "readiness": "PARTIAL"},
                        indent=2,
                    )
                )
            else:
                print(msg, file=sys.stderr)
            return 0
        if not info.get("google_genai_available"):
            msg = _soft("google.genai not installed (pip/uv: google-genai)")
            if as_json:
                print(
                    json.dumps(
                        {"ok": False, "error": msg, "readiness": "PARTIAL"},
                        indent=2,
                    )
                )
            else:
                print(msg, file=sys.stderr)
            return 0
        if not info.get("gemini_api_key_present"):
            msg = _soft("GEMINI_API_KEY missing (chat gated)")
            if as_json:
                print(
                    json.dumps(
                        {"ok": False, "error": msg, "readiness": "PARTIAL"},
                        indent=2,
                    )
                )
            else:
                print(msg, file=sys.stderr)
            return 0

        argv: List[str] = [sys.executable, str(_ENGINE)]
        if extra:
            argv.extend(extra)

        if dry_run:
            if as_json:
                print(
                    json.dumps(
                        {
                            "ok": True,
                            "dry_run": True,
                            "readiness": "PARTIAL",
                            "cmd": argv[1:],
                            "hint": "dry-run → would exec engine (no chat)",
                        },
                        indent=2,
                    )
                )
            else:
                print(f"[dry-run] would exec: {' '.join(argv[1:])}", flush=True)
            return 0

        # Never hang in non-interactive contexts without a one-shot prompt.
        has_once = any(
            a in ("--once", "--prompt", "-q") for a in (extra or [])
        )
        if not sys.stdin.isatty() and not has_once:
            msg = _soft(
                "non-interactive run would hang — use a TTY or "
                "`bolt personality run --once \"…\"`"
            )
            if as_json:
                print(
                    json.dumps(
                        {"ok": False, "error": msg, "readiness": "PARTIAL"},
                        indent=2,
                    )
                )
            else:
                print(msg, file=sys.stderr)
            return 0

        env = os.environ.copy()
        env["PYTHONPATH"] = f"{_CORE}" + (
            f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else ""
        )
        rc = subprocess.call(argv, cwd=str(_REPO), env=env)
        if as_json:
            print(
                json.dumps(
                    {
                        "ok": rc == 0,
                        "exit_code": rc,
                        "readiness": "PARTIAL",
                        "cmd": argv[1:],
                        "error": "" if rc == 0 else _soft(f"engine exit {rc}"),
                        "hint": (
                            "distinct from READY bolt gemini / nexus / chat"
                        ),
                    },
                    indent=2,
                )
            )
        return 0  # soft-fail: never hard-fail the CLI
    except Exception as exc:
        msg = _soft(f"run failed ({exc})")
        if as_json:
            print(
                json.dumps(
                    {"ok": False, "error": msg, "readiness": "PARTIAL"}, indent=2
                )
            )
        else:
            print(msg, file=sys.stderr)
        return 0


def print_status(*, as_json: bool = False, probe: bool = False) -> int:
    try:
        info = status(probe=probe)
        if as_json:
            print(json.dumps(info, indent=2))
            return 0
        ready = bool(info.get("ready"))
        print("Bolt personality (PARTIAL)")
        print(f"  ready: {ready}")
        print(f"  engine: {info.get('engine_path')}")
        print(f"  stale_parents3: {info.get('engine_stale_parents3')}")
        print(
            f"  personality: {info.get('personality_path')} "
            f"present={info.get('personality_present')}"
        )
        print(
            f"  google.genai: {info.get('google_genai_available')} "
            f"GEMINI_API_KEY: {info.get('gemini_api_key_present')}"
            + (
                f" ({info.get('gemini_api_key_redacted')})"
                if info.get("gemini_api_key_redacted")
                else ""
            )
        )
        print(
            "  readiness: PARTIAL (persona file loader; "
            "not READY gemini/nexus/chat)"
        )
        if info.get("error"):
            print(f"  error: {info['error']}")
        if info.get("hint"):
            print(f"  → {info['hint']}")
        return 0
    except Exception as exc:
        msg = _soft(f"status print failed ({exc})")
        if as_json:
            print(
                json.dumps(
                    {"ready": False, "error": msg, "readiness": "PARTIAL"}, indent=2
                )
            )
        else:
            print(msg, file=sys.stderr)
        return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help", "help"):
        print(
            """bolt personality — Gemini persona chat loader (PARTIAL)

  bolt personality                         # status (default)
  bolt personality status [--json] [--probe]
  bolt personality list [--json]
  bolt personality run [--dry-run] [--json] [--once "…"]

Soft-fail: "Personality unavailable:".
Engine: scripts/load_bolt_personality.py (fixed via scripts/_paths.py).
Canonical: Data/context/bolt-personality.md
Distinct from READY bolt gemini / bolt nexus / bolt chat (Twitch).
Stay PARTIAL (key/genai gated chat; not stranger-ready claim).
Aliases: bolt-personality, personality-status, persona, load-personality, load_personality.
"""
        )
        return 0

    json_out = "--json" in args
    probe = "--probe" in args
    dry_run = "--dry-run" in args or "-n" in args

    extra: List[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--once", "--prompt", "-q") and i + 1 < len(args):
            extra.extend([a, args[i + 1]])
            i += 2
            continue
        i += 1

    cleaned: List[str] = []
    skip_next = False
    for idx, a in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if a.startswith("-"):
            if a in ("--once", "--prompt", "-q") and idx + 1 < len(args):
                skip_next = True
            continue
        cleaned.append(a)

    if not cleaned:
        if extra:
            return try_run(dry_run=dry_run, as_json=json_out, extra=extra)
        return print_status(as_json=json_out, probe=probe)

    cmd = cleaned[0].lower()
    if cmd in ("status", "check", "ready"):
        return print_status(as_json=json_out, probe=probe)
    if cmd in ("list", "ls", "checklist"):
        return list_items(as_json=json_out)
    if cmd in ("run", "go", "exec", "chat", "talk"):
        return try_run(dry_run=dry_run, as_json=json_out, extra=extra)

    print(
        _soft(f"unknown command {cleaned[0]!r} — try status|list|run"),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
