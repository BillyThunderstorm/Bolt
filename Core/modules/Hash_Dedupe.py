#!/usr/bin/env python3
"""
Hash_Dedupe.py — SHA256 media hash scan (PARTIAL)
=================================================
Soft-fail CLI for the former thin SCRIPT_MAP ``bolt clip_dedupe`` /
``scripts/clip_deduplicator.py`` (wrong ``parents[3]`` → ``/Users/carter``
with legacy bare ``clips/`` / ``recordings/`` — default scans missed
``media/clips`` + ``media/Recordings``).

Soft-fail prefix: ``Hash dedupe unavailable:``.
Stay PARTIAL — distinct from READY pipeline
``Core/modules/Clip_Deduplicator.py`` (pHash during process_recording →
``Data/seen_clips.json``). This surface writes ``Data/media_hash_db.json``.

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

_SOFT = "Hash dedupe unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_ENGINE = _REPO / "scripts" / "clip_deduplicator.py"
_CORE = _REPO / "Core"
_PIPELINE = _CORE / "modules" / "Clip_Deduplicator.py"
_DATA = _REPO / "Data"
_HASH_DB = _DATA / "media_hash_db.json"
_SEEN = _DATA / "seen_clips.json"
_CLIPS = _REPO / "media" / "clips"
_RECORDINGS = _REPO / "media" / "Recordings"
_PATHS = _REPO / "scripts" / "_paths.py"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _soft(msg: str) -> str:
    if msg.startswith(_SOFT):
        return msg
    return f"{_SOFT} {msg}"


def _engine_stale() -> bool:
    """True if engine still assigns PROJECT_ROOT via parents[3]."""
    if not _ENGINE.is_file():
        return False
    try:
        text = _ENGINE.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    # Fixed engine imports _paths; stale had parents[3] assignment.
    if "from _paths import" in text:
        return False
    return "parents[3]" in text and "PROJECT_ROOT" in text


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Readiness for SHA256 hash dedupe scan (PARTIAL)."""
    try:
        engine_ok = _ENGINE.is_file()
        stale = _engine_stale()
        paths_ok = _PATHS.is_file()
        clips_ok = _CLIPS.is_dir()
        rec_ok = _RECORDINGS.is_dir()
        data_ok = _DATA.is_dir()
        pipeline_ok = _PIPELINE.is_file()
        hash_db_ok = _HASH_DB.is_file()
        seen_ok = _SEEN.is_file()

        clips_count = 0
        if clips_ok:
            try:
                clips_count = sum(
                    1
                    for p in _CLIPS.rglob("*")
                    if p.is_file()
                    and p.suffix.lower() in (".mp4", ".mov", ".mkv", ".avi")
                )
            except Exception:
                clips_count = 0

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
            "clips_dir": str(_CLIPS),
            "clips_present": clips_ok,
            "clips_media_count": clips_count,
            "recordings_dir": str(_RECORDINGS),
            "recordings_present": rec_ok,
            "data_present": data_ok,
            "hash_db_path": str(_HASH_DB),
            "hash_db_present": hash_db_ok,
            "pipeline_module": str(_PIPELINE),
            "pipeline_present": pipeline_ok,
            "pipeline_seen_file": str(_SEEN),
            "pipeline_seen_present": seen_ok,
            "cli": "bolt clip-dedupe",
            "prefer_pipeline": "Clip_Deduplicator (process_recording / Data/seen_clips.json)",
            "note": (
                "SHA256 hash scan of media/clips + media/Recordings → "
                "Data/media_hash_db.json. Distinct from READY pipeline "
                "Clip_Deduplicator pHash (Data/seen_clips.json). Former "
                "thin SCRIPT_MAP clip_dedupe with parents[3] wrong root."
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
                "engine still uses parents[3] / legacy clips|recordings paths"
            )
            out["hint"] = out["error"]
            return out

        if not paths_ok:
            out["error"] = _soft("scripts/_paths.py missing")
            out["hint"] = out["error"]
            return out

        if not data_ok:
            out["error"] = _soft("Data/ missing")
            out["hint"] = out["error"]
            return out

        out["ready"] = True
        out["hint"] = (
            "ok — run: bolt clip-dedupe run [--dry-run]"
            + ("" if clips_ok else " (media/clips missing — creatable)")
            + ("" if rec_ok else " (media/Recordings missing — creatable)")
        )
        if probe and engine_ok:
            try:
                # Import path constants without running a full scan
                env = os.environ.copy()
                env["PYTHONPATH"] = f"{_CORE}" + (
                    f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else ""
                )
                # lightweight: confirm engine parses and _paths resolves
                code = (
                    "import ast, pathlib; "
                    f"ast.parse(pathlib.Path({str(_ENGINE)!r}).read_text()); "
                    "print('probe_ok')"
                )
                r = subprocess.run(
                    [sys.executable, "-c", code],
                    cwd=str(_REPO),
                    env=env,
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
            "cli": "bolt clip-dedupe",
            "is_stranger_ready": False,
            "probe": bool(probe),
        }


def list_items(*, as_json: bool = False) -> int:
    """Checklist of hash-dedupe gates."""
    try:
        info = status(probe=False)
        rows = [
            ("engine clip_deduplicator.py", bool(info.get("engine_present"))),
            ("engine post-reorg (_paths, not parents[3])", not bool(info.get("engine_stale_parents3"))),
            ("scripts/_paths.py", bool(info.get("paths_helper_present"))),
            ("Data/", bool(info.get("data_present"))),
            (f"media/clips ({info.get('clips_dir')})", bool(info.get("clips_present"))),
            (
                f"media/Recordings ({info.get('recordings_dir')})",
                bool(info.get("recordings_present")),
            ),
            (
                f"Data/media_hash_db.json present={info.get('hash_db_present')}",
                True,  # optional until first run
            ),
            (
                "pipeline Clip_Deduplicator.py (distinct READY pHash)",
                bool(info.get("pipeline_present")),
            ),
            (
                "Data/seen_clips.json is pipeline store (not this tool)",
                True,
            ),
            ("soft-fail CLI (bolt clip-dedupe)", True),
            ("media gated / stay PARTIAL", True),
        ]
        if as_json:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "readiness": "PARTIAL",
                        "items": [{"name": n, "ok": ok} for n, ok in rows],
                        "clips_media_count": info.get("clips_media_count"),
                        "hint": info.get("hint"),
                        "error": info.get("error"),
                    },
                    indent=2,
                )
            )
            return 0
        print("Hash dedupe (PARTIAL — SHA256 scan; not pipeline pHash)", flush=True)
        for name, ok in rows:
            mark = "OK" if ok else "--"
            print(f"  [{mark}] {name}", flush=True)
        print(
            f"  clips media count: {info.get('clips_media_count', 0)}",
            flush=True,
        )
        if info.get("hint"):
            print(f"  → {info['hint']}", flush=True)
        print("  (run: bolt clip-dedupe run [--dry-run])", flush=True)
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
    """Soft-fail invoke clip_deduplicator.py (never raises)."""
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

        argv: List[str] = [sys.executable, str(_ENGINE)]
        if dry_run:
            argv.append("--dry-run")
        if extra:
            argv.extend(extra)

        env = os.environ.copy()
        env["PYTHONPATH"] = f"{_CORE}" + (
            f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else ""
        )
        # Always exec engine (including --dry-run) so path fix is smoke-tested
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
                            "writes Data/media_hash_db.json; "
                            "pipeline pHash stays Data/seen_clips.json"
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
        print("Hash dedupe (PARTIAL)")
        print(f"  ready: {ready}")
        print(f"  engine: {info.get('engine_path')}")
        print(f"  stale_parents3: {info.get('engine_stale_parents3')}")
        print(f"  clips: {info.get('clips_dir')} present={info.get('clips_present')} count={info.get('clips_media_count')}")
        print(f"  recordings: {info.get('recordings_dir')} present={info.get('recordings_present')}")
        print(f"  hash_db: {info.get('hash_db_path')} present={info.get('hash_db_present')}")
        print(f"  pipeline (distinct): {info.get('prefer_pipeline')}")
        print("  readiness: PARTIAL (SHA256 scan; media gated)")
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
            """bolt clip-dedupe — SHA256 media hash scan (PARTIAL)

  bolt clip-dedupe                         # status (default)
  bolt clip-dedupe status [--json] [--probe]
  bolt clip-dedupe list [--json]
  bolt clip-dedupe run [--dry-run] [--json] [--scan DIR] [--check FILE]

Soft-fail: "Hash dedupe unavailable:".
Engine: scripts/clip_deduplicator.py (fixed via scripts/_paths.py).
Writes: Data/media_hash_db.json
Distinct from READY pipeline Clip_Deduplicator (Data/seen_clips.json).
Stay PARTIAL (media gated; not stranger-ready claim).
Aliases: clip_dedupe, hash-dedupe, dedupe-status, sha-dedupe.
"""
        )
        return 0

    json_out = "--json" in args
    probe = "--probe" in args
    dry_run = "--dry-run" in args or "-n" in args

    # Forward engine flags that need values
    extra: List[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--scan", "--check") and i + 1 < len(args):
            extra.extend([a, args[i + 1]])
            i += 2
            continue
        if a in ("--clear-db", "--clear"):
            extra.append(a)
            i += 1
            continue
        i += 1

    cleaned: List[str] = []
    skip_next = False
    for idx, a in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if a.startswith("-"):
            if a in ("--scan", "--check") and idx + 1 < len(args):
                skip_next = True
            continue
        cleaned.append(a)

    if not cleaned:
        # bare with --scan/--check/--clear → run
        if extra:
            return try_run(dry_run=dry_run, as_json=json_out, extra=extra)
        return print_status(as_json=json_out, probe=probe)

    cmd = cleaned[0].lower()
    if cmd in ("status", "check", "ready"):
        return print_status(as_json=json_out, probe=probe)
    if cmd in ("list", "ls", "checklist"):
        return list_items(as_json=json_out)
    if cmd in ("run", "go", "exec", "scan", "dedupe", "dedup"):
        return try_run(dry_run=dry_run, as_json=json_out, extra=extra)

    print(
        _soft(f"unknown command {cleaned[0]!r} — try status|list|run"),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
