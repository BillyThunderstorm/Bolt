#!/usr/bin/env python3
"""
Bolt_Personality.py — Bolt persona loader
=========================================
Loads William's system prompt (``Data/context/bolt-personality.md``) and
talks through ``LLM_Handler`` (Ollama first). Not a Gemini chat.

The old wrapper gated ``bolt personality run`` on ``google.genai`` and
``GEMINI_API_KEY``. That was the wrong brain. The prompt was never a
Gemini feature.

Soft-fail prefix: ``Personality unavailable:``.

Public API:
  status() / list_items() / try_run() / print_status() / main()
"""

from __future__ import annotations

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


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _soft(msg: str) -> str:
    if msg.startswith(_SOFT):
        return msg
    return f"{_SOFT} {msg}"


def _engine_text() -> str:
    if not _ENGINE.is_file():
        return ""
    try:
        return _ENGINE.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _engine_stale() -> bool:
    """True if engine still assigns project root via parents[3]."""
    text = _engine_text()
    if not text:
        return False
    if "from _paths import" in text:
        return False
    return "parents[3]" in text


def _engine_uses_llm_handler() -> bool:
    text = _engine_text()
    if "ask_llm" not in text:
        return False
    if "google.genai" in text or "GEMINI_API_KEY" in text:
        return False
    return True


def _loaded_prompt() -> str:
    scripts = str(_REPO / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    try:
        from load_bolt_personality import load_bolt_personality

        return load_bolt_personality() or ""
    except Exception:
        return ""


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Readiness for the persona file wired into LLM_Handler."""
    try:
        engine_ok = _ENGINE.is_file()
        stale = _engine_stale()
        paths_ok = _PATHS.is_file()
        canon_ok = _CANON.is_file()
        fb_txt_ok = _FALLBACK_TXT.is_file()
        fb_root_ok = _FALLBACK_ROOT.is_file()
        uses_llm = _engine_uses_llm_handler()
        prompt = _loaded_prompt() if engine_ok and not stale else ""
        prompt_ok = bool(prompt) and "client.chat.completions.create" not in prompt

        out: Dict[str, Any] = {
            "checked_at": _utc_now(),
            "ready": False,
            "partial": False,
            "readiness": "READY",
            "soft_fail_prefix": _SOFT,
            "engine_path": str(_ENGINE),
            "engine_present": engine_ok,
            "engine_stale_parents3": stale,
            "engine_uses_llm_handler": uses_llm,
            "paths_helper_present": paths_ok,
            "personality_path": str(_CANON),
            "personality_present": canon_ok,
            "prompt_loaded": prompt_ok,
            "prompt_chars": len(prompt),
            "fallback_txt_path": str(_FALLBACK_TXT),
            "fallback_txt_present": fb_txt_ok,
            "fallback_root_path": str(_FALLBACK_ROOT),
            "fallback_root_present": fb_root_ok,
            "cli": "bolt personality",
            "note": (
                "William's persona in Data/context/bolt-personality.md is the "
                "system prompt for voice, Twitch chat, and `bolt personality run`. "
                "Replies use LLM_Handler (Ollama first). Not Gemini."
            ),
            "is_stranger_ready": True,
            "probe": bool(probe),
            "error": "",
            "hint": "",
        }

        if not engine_ok:
            out["readiness"] = "MISSING"
            out["error"] = _soft(f"engine missing ({_ENGINE})")
            out["hint"] = out["error"]
            return out

        if stale:
            out["readiness"] = "BROKEN"
            out["error"] = _soft(
                "engine still uses parents[3] / missing Bolt_Personality.txt root"
            )
            out["hint"] = out["error"]
            return out

        if not paths_ok:
            out["readiness"] = "BROKEN"
            out["error"] = _soft("scripts/_paths.py missing")
            out["hint"] = out["error"]
            return out

        if not uses_llm:
            out["readiness"] = "BROKEN"
            out["error"] = _soft(
                "personality chat is not on LLM_Handler "
                "(still looks like a Gemini gate)"
            )
            out["hint"] = out["error"]
            return out

        if not canon_ok and not prompt_ok:
            out["readiness"] = "MISSING"
            out["error"] = _soft(f"canonical personality missing ({_CANON})")
            out["hint"] = out["error"]
            return out

        if not prompt_ok:
            out["readiness"] = "BROKEN"
            out["error"] = _soft("personality file loaded empty")
            out["hint"] = out["error"]
            return out

        out["ready"] = True
        out["hint"] = (
            "ok — persona is the system prompt "
            f"({len(prompt)} chars). "
            "bolt personality run uses LLM_Handler, not Gemini."
        )

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
            "partial": False,
            "readiness": "BROKEN",
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
                "canonical Data/context/bolt-personality.md",
                bool(info.get("personality_present")),
            ),
            ("prompt text loads (draft example stripped)", bool(info.get("prompt_loaded"))),
            (
                "chat uses LLM_Handler (not Gemini)",
                bool(info.get("engine_uses_llm_handler")),
            ),
            ("soft-fail CLI (bolt personality)", True),
        ]
        readiness = info.get("readiness") or "BROKEN"
        if as_json:
            print(
                json.dumps(
                    {
                        "ok": bool(info.get("ready")),
                        "readiness": readiness,
                        "items": [{"name": n, "ok": ok} for n, ok in rows],
                        "hint": info.get("hint"),
                        "error": info.get("error"),
                    },
                    indent=2,
                )
            )
            return 0
        print(
            "Bolt personality (system prompt via LLM_Handler; not Gemini)",
            flush=True,
        )
        for name, ok in rows:
            mark = "OK" if ok else "--"
            print(f"  [{mark}] {name}", flush=True)
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
        readiness = info.get("readiness") or "BROKEN"
        if not info.get("ready"):
            msg = info.get("error") or _soft("personality not ready")
            if as_json:
                print(
                    json.dumps(
                        {"ok": False, "error": msg, "readiness": readiness},
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
                            "readiness": readiness,
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
        has_once = any(a in ("--once", "--prompt", "-q") for a in (extra or []))
        if not sys.stdin.isatty() and not has_once:
            msg = _soft(
                "non-interactive run would hang — use a TTY or "
                '`bolt personality run --once "…"`'
            )
            if as_json:
                print(
                    json.dumps(
                        {"ok": False, "error": msg, "readiness": readiness},
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
                        "readiness": readiness,
                        "cmd": argv[1:],
                        "error": "" if rc == 0 else _soft(f"engine exit {rc}"),
                        "hint": "persona chat via LLM_Handler (not Gemini)",
                    },
                    indent=2,
                )
            )
        return 0  # soft-fail: never hard-fail the CLI
    except Exception as exc:
        msg = _soft(f"run failed ({exc})")
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
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
        print("Bolt personality")
        print(f"  ready: {ready}")
        print(f"  engine: {info.get('engine_path')}")
        print(f"  stale_parents3: {info.get('engine_stale_parents3')}")
        print(
            f"  personality: {info.get('personality_path')} "
            f"present={info.get('personality_present')} "
            f"chars={info.get('prompt_chars')}"
        )
        print(f"  llm_handler: {info.get('engine_uses_llm_handler')} (not Gemini)")
        print(f"  readiness: {info.get('readiness')}")
        if info.get("error"):
            print(f"  error: {info['error']}")
        if info.get("hint"):
            print(f"  → {info['hint']}")
        return 0
    except Exception as exc:
        msg = _soft(f"status print failed ({exc})")
        if as_json:
            print(json.dumps({"ready": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help", "help"):
        print(
            """bolt personality — Bolt's system prompt (LLM_Handler, not Gemini)

  bolt personality                         # status (default)
  bolt personality status [--json] [--probe]
  bolt personality list [--json]
  bolt personality run [--dry-run] [--json] [--once "…"]

Soft-fail: "Personality unavailable:".
Engine: scripts/load_bolt_personality.py
Canonical: Data/context/bolt-personality.md
Voice and Twitch chat load the same prompt.
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
