#!/usr/bin/env python3
"""
Health_Check.py — Bolt quick health check (READY, 21 Oct 2026)
===============================================================
``bolt health run`` answers "is Bolt ready to make clips right now?" in about
a second: files, folders, a working ffmpeg/ffprobe, Whisper (venv package or
the Mac's whisper CLI), pipeline packages + modules, Core/config.json, which
AI is available (Grok key / Ollama running / OpenAI key) and free disk. Every
WARN/FAIL line carries the exact fix. Reads .env.local then .env like the
rest of Bolt. Engine: ``scripts/health_check.py``.

Soft-fail prefix: ``Health check unavailable:``.
For the full live/mocked/stale audit of every feature use ``bolt doctor``.

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

_SOFT = "Health check unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_ENGINE = _REPO / "scripts" / "health_check.py"
_CORE = _REPO / "Core"
_CONFIG = _CORE / "config.json"
_BOT = _CORE / "bot.py"
_LAUNCH = _CORE / "launch.py"
_MODULES = _CORE / "modules"
_DATA = _REPO / "Data"
_CLIPS = _REPO / "media" / "clips"
_DOCTOR = _REPO / "scripts" / "doctor.py"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _soft(msg: str) -> str:
    if msg.startswith(_SOFT):
        return msg
    return f"{_SOFT} {msg}"


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Readiness for the quick health check (READY)."""
    try:
        engine_ok = _ENGINE.is_file()
        core_ok = _CORE.is_dir()
        config_ok = _CONFIG.is_file()
        bot_ok = _BOT.is_file()
        launch_ok = _LAUNCH.is_file()
        modules_ok = _MODULES.is_dir()
        data_ok = _DATA.is_dir()
        clips_ok = _CLIPS.is_dir()
        doctor_ok = _DOCTOR.is_file()
        paths_helper = (_REPO / "scripts" / "_paths.py").is_file()

        # Detect if engine still has stale CWD-relative markers (regression)
        stale_markers = False
        if engine_ok:
            try:
                text = _ENGINE.read_text(encoding="utf-8", errors="ignore")
                # Post-fix engine mentions post-reorg; pre-fix had bare "clips"
                # as CWD keys without _paths import.
                stale_markers = (
                    "from _paths import" not in text
                    and '"clips": "Generated clips"' in text
                )
            except Exception:
                stale_markers = False

        out: Dict[str, Any] = {
            "checked_at": _utc_now(),
            "ready": False,
            "partial": False,
            "readiness": "READY",
            "soft_fail_prefix": _SOFT,
            "engine_path": str(_ENGINE),
            "engine_present": engine_ok,
            "engine_stale_cwd_paths": stale_markers,
            "paths_helper_present": paths_helper,
            "core_present": core_ok,
            "config_path": str(_CONFIG),
            "config_present": config_ok,
            "bot_present": bot_ok,
            "launch_present": launch_ok,
            "modules_present": modules_ok,
            "data_present": data_ok,
            "clips_dir": str(_CLIPS),
            "clips_present": clips_ok,
            "doctor_present": doctor_ok,
            "prefer_cli": "bolt doctor",
            "cli": "bolt health",
            "note": (
                "Quick 'ready to make clips?' check with fixes (ffmpeg, "
                "whisper, packages, modules, config, AI, disk). Full audit: "
                "bolt doctor."
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

        if stale_markers:
            out["error"] = _soft(
                "engine still uses pre-reorg CWD paths; prefer bolt doctor"
            )
            out["hint"] = out["error"]
            return out

        if not paths_helper:
            out["error"] = _soft("scripts/_paths.py missing")
            out["hint"] = out["error"]
            return out

        if not (core_ok and config_ok and bot_ok and modules_ok):
            missing = []
            if not core_ok:
                missing.append("Core/")
            if not config_ok:
                missing.append("Core/config.json")
            if not bot_ok:
                missing.append("Core/bot.py")
            if not modules_ok:
                missing.append("Core/modules/")
            out["error"] = _soft("missing " + ", ".join(missing))
            out["hint"] = out["error"]
            return out

        out["ready"] = True
        out["hint"] = (
            "ok — run: bolt health run (full audit: bolt doctor)"
            + ("" if clips_ok else " (media/clips missing — creatable)")
        )
        if probe:
            # Run the real check quietly and summarise it.
            rep = _engine_json()
            if rep is None:
                out["probe_ok"] = False
                out["hint"] = _soft("probe: engine gave no report (run: bolt health run)")
            else:
                out["probe_ok"] = bool(rep.get("ok"))
                out["probe_verdict"] = rep.get("verdict")
                out["probe_counts"] = rep.get("counts")
                out["probe_problems"] = [
                    f"{c.get('state')} {c.get('name')}: {c.get('fix') or c.get('detail')}"
                    for c in rep.get("problems") or []
                ]
        return out
    except Exception as exc:
        return {
            "checked_at": _utc_now(),
            "ready": False,
            "partial": False,
            "readiness": "READY",
            "soft_fail_prefix": _SOFT,
            "error": _soft(f"status failed ({exc})"),
            "hint": _soft(f"status failed ({exc})"),
            "cli": "bolt health",
            "prefer_cli": "bolt doctor",
            "is_stranger_ready": False,
            "probe": bool(probe),
        }


def _engine_json(*, no_network: bool = False, timeout: int = 60) -> Optional[Dict[str, Any]]:
    """Run the engine with --json and return its report (None on failure)."""
    argv = [sys.executable, str(_ENGINE), "--json"]
    if no_network:
        argv.append("--no-network")
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{_CORE}" + (f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else "")
    try:
        res = subprocess.run(argv, cwd=str(_REPO), env=env, capture_output=True,
                             text=True, timeout=timeout)
        text = res.stdout.strip()
        start = text.find("{")
        return json.loads(text[start:]) if start >= 0 else None
    except Exception:
        return None


def list_items(*, as_json: bool = False) -> int:
    """Checklist of health-check gates."""
    try:
        info = status(probe=False)
        rows = [
            ("engine health_check.py", bool(info.get("engine_present"))),
            ("engine post-reorg (_paths)", not bool(info.get("engine_stale_cwd_paths"))),
            ("scripts/_paths.py", bool(info.get("paths_helper_present"))),
            ("Core/ present", bool(info.get("core_present"))),
            ("Core/config.json", bool(info.get("config_present"))),
            ("Core/bot.py", bool(info.get("bot_present"))),
            ("Core/launch.py", bool(info.get("launch_present"))),
            ("Core/modules/", bool(info.get("modules_present"))),
            ("Data/", bool(info.get("data_present"))),
            (f"media/clips ({info.get('clips_dir')})", bool(info.get("clips_present"))),
            ("scripts/doctor.py (prefer bolt doctor)", bool(info.get("doctor_present"))),
            ("soft-fail CLI (bolt health)", True),
            ("full audit lives in bolt doctor / verify", True),
        ]
        if as_json:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "readiness": "READY",
                        "items": [{"name": n, "ok": ok} for n, ok in rows],
                        "hint": info.get("hint"),
                        "error": info.get("error"),
                    },
                    indent=2,
                )
            )
            return 0
        print("Health check (READY) — what `bolt health run` checks needs:", flush=True)
        for name, ok in rows:
            mark = "OK" if ok else "--"
            print(f"  [{mark}] {name}", flush=True)
        if info.get("hint"):
            print(f"  → {info['hint']}", flush=True)
        print("  (run: bolt health run)", flush=True)
        return 0
    except Exception as exc:
        msg = _soft(f"list failed ({exc})")
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0


def try_run(*, dry_run: bool = False, as_json: bool = False, no_network: bool = False) -> int:
    """Soft-fail invoke health_check.py (never raises)."""
    try:
        info = status(probe=False)
        if not info.get("engine_present"):
            msg = info.get("error") or _soft("engine script missing")
            if as_json:
                print(
                    json.dumps(
                        {"ok": False, "error": msg, "readiness": "READY"},
                        indent=2,
                    )
                )
            else:
                print(msg, file=sys.stderr)
            return 0
        if info.get("engine_stale_cwd_paths"):
            msg = info.get("error") or _soft("engine still uses pre-reorg CWD paths")
            if as_json:
                print(
                    json.dumps(
                        {"ok": False, "error": msg, "readiness": "READY"},
                        indent=2,
                    )
                )
            else:
                print(msg, file=sys.stderr)
            return 0

        argv: List[str] = [sys.executable, str(_ENGINE)]
        if no_network:
            argv.append("--no-network")
        if as_json and not dry_run:
            rep = _engine_json(no_network=no_network)
            if rep is None:
                print(json.dumps({"ok": False, "readiness": "READY",
                                  "error": _soft("engine gave no report")}, indent=2))
            else:
                print(json.dumps(rep, indent=2))
            return 0
        if dry_run:
            if as_json:
                print(
                    json.dumps(
                        {
                            "ok": True,
                            "dry_run": True,
                            "readiness": "READY",
                            "cmd": argv[1:],
                            "hint": "dry-run → would exec engine (no run)",
                        },
                        indent=2,
                    )
                )
            else:
                print(f"[dry-run] would exec: {' '.join(argv[1:])}", flush=True)
                print(f"  → {info.get('hint') or 'ok'}", flush=True)
            return 0

        env = os.environ.copy()
        env["PYTHONPATH"] = f"{_CORE}" + (
            f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else ""
        )
        try:
            rc = subprocess.call(argv, cwd=str(_REPO), env=env, timeout=120)
        except subprocess.TimeoutExpired:
            print(_soft("check took over 2 minutes and was stopped — run: bolt doctor"),
                  file=sys.stderr)
            return 0
        if rc not in (0, 1):
            print(_soft(f"engine crashed (exit {rc}) — run: bolt doctor"), file=sys.stderr)
        return 0  # soft-fail: never hard-fail the CLI
    except Exception as exc:
        msg = _soft(f"run failed ({exc})")
        if as_json:
            print(json.dumps({"ok": False, "error": msg, "readiness": "READY"}, indent=2))
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
        print("Health check (READY) — quick 'ready to make clips?' check")
        print(f"  ready: {ready}")
        print(f"  engine: {info.get('engine_path')}")
        print(f"  config: {info.get('config_path')} present={info.get('config_present')}")
        print(f"  clips: {info.get('clips_dir')} present={info.get('clips_present')}")
        if probe and "probe_ok" in info:
            print(f"  probe: {info.get('probe_verdict') or 'no report'}  {info.get('probe_counts') or ''}")
            for line in info.get("probe_problems") or []:
                print(f"    • {line}")
        print("  full audit: bolt doctor")
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
                    {"ready": False, "error": msg, "readiness": "READY"}, indent=2
                )
            )
        else:
            print(msg, file=sys.stderr)
        return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help", "help"):
        print(
            """bolt health — quick "is Bolt ready to make clips?" check (READY)

  bolt health                              # status (default; safe)
  bolt health run [--json] [--no-network]  # the check (~1 s), fixes for every problem
  bolt health status [--json] [--probe]    # --probe runs the check quietly
  bolt health list [--json]

Checks files, folders, ffmpeg/ffprobe, Whisper (venv or Mac CLI), packages,
pipeline modules, Core/config.json, AI (Grok / Ollama / OpenAI) and disk.
Reads .env.local then .env. --no-network skips the 2 s Ollama ping.
Soft-fail: "Health check unavailable:". Full audit: bolt doctor.
Aliases: health-check, health_check, health-status, system-health.
"""
        )
        return 0

    json_out = "--json" in args
    probe = "--probe" in args
    dry_run = "--dry-run" in args or "-n" in args
    no_network = "--no-network" in args
    cleaned: List[str] = []
    for a in args:
        if a.startswith("-"):
            continue
        cleaned.append(a)

    if not cleaned:
        return print_status(as_json=json_out, probe=probe)

    cmd = cleaned[0].lower()
    if cmd in ("status", "check", "ready"):
        return print_status(as_json=json_out, probe=probe)
    if cmd in ("list", "ls", "checklist"):
        return list_items(as_json=json_out)
    if cmd in ("run", "go", "exec", "health"):
        return try_run(dry_run=dry_run, as_json=json_out, no_network=no_network)

    print(
        _soft(f"unknown command {cleaned[0]!r} — try status|list|run"),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
