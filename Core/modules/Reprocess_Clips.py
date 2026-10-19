#!/usr/bin/env python3
"""
Reprocess_Clips.py — Vertical rebuild + multi-platform queue (READY)
===================================================================
CLI for ``scripts/reprocess_clips.py``: rebuild 9:16 verticals of
``media/clips/*.mp4`` into ``media/vertical_clips/`` (verified portrait
output) and MERGE manual-upload plans into ``Data/multi_platform_queue.json``
(other queue items kept; no duplicates). READY 18 Oct 2026.

Soft-fail prefix: ``Reprocess unavailable:``. Needs a working ffmpeg
(FFmpeg_Bin) + Clip_Factory; does NOT auto-upload to TikTok. Distinct from READY ``bolt recordings`` / live clip pipeline,
READY ``bolt enhance`` (Smart_Trim + Text_Overlay), READY ``bolt multi``
(manual platform plans), and the thin vertical path inside Clip_Factory
during ``process_recording``.

Public API:
  status() / list_items() / try_run() / print_status() / main()
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SOFT = "Reprocess unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_ENGINE = _REPO / "scripts" / "reprocess_clips.py"
_CLIPS = _REPO / "media" / "clips"
_LEGACY_CLIPS = _REPO / "clips"
_VERTICAL = _REPO / "media" / "vertical_clips"
_LEGACY_VERTICAL = _REPO / "vertical_clips"
_QUEUE = _REPO / "Data" / "multi_platform_queue.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _soft(msg: str) -> str:
    if msg.startswith(_SOFT):
        return msg
    return f"{_SOFT} {msg}"


def _clips_dir() -> Path:
    if _CLIPS.is_dir():
        return _CLIPS
    if _LEGACY_CLIPS.is_dir():
        return _LEGACY_CLIPS
    return _CLIPS


def _vertical_dir() -> Path:
    if _VERTICAL.is_dir():
        return _VERTICAL
    if _LEGACY_VERTICAL.is_dir():
        return _LEGACY_VERTICAL
    return _VERTICAL


def _count_mp4(clips: Path) -> int:
    try:
        return sum(1 for p in clips.glob("*.mp4") if p.is_file())
    except Exception:
        return 0


def _which(name: str) -> Optional[str]:
    return shutil.which(name)


def _ffmpeg_path() -> Optional[str]:
    try:
        if str(_REPO / "Core") not in sys.path:
            sys.path.insert(0, str(_REPO / "Core"))
        from modules.FFmpeg_Bin import ffmpeg_bin

        p = ffmpeg_bin()
        if p:
            return str(p)
    except Exception:
        pass
    return _which("ffmpeg")


def _clip_factory_importable() -> bool:
    try:
        if str(_REPO / "Core") not in sys.path:
            sys.path.insert(0, str(_REPO / "Core"))
        from modules.Clip_Factory import format_for_tiktok  # noqa: F401

        return True
    except Exception:
        return False


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Readiness for vertical reprocess / queue merge (READY)."""
    try:
        engine_ok = _ENGINE.is_file()
        clips = _clips_dir()
        clips_ok = clips.is_dir()
        mp4_count = _count_mp4(clips) if clips_ok else 0
        vert = _vertical_dir()
        vert_ok = vert.is_dir()
        vert_count = 0
        pending = 0
        if clips_ok:
            for c in clips.glob("*.mp4"):
                if not c.is_file():
                    continue
                v = vert / f"{c.stem}_tiktok.mp4"
                if v.is_file() and v.stat().st_size > 0:
                    vert_count += 1
                else:
                    pending += 1
        ff = _ffmpeg_path()
        cf_ok = _clip_factory_importable()
        queue_parent_ok = _QUEUE.parent.is_dir() or True  # Data/ usually exists

        out: Dict[str, Any] = {
            "checked_at": _utc_now(),
            "ready": False,
            "partial": False,
            "readiness": "READY",
            "soft_fail_prefix": _SOFT,
            "engine_path": str(_ENGINE),
            "engine_present": engine_ok,
            "clips_dir": str(clips),
            "clips_present": clips_ok,
            "mp4_count": mp4_count,
            "vertical_clips_dir": str(vert),
            "vertical_clips_present": vert_ok,
            "queue_path": str(_QUEUE),
            "queue_present": _QUEUE.is_file(),
            "queue_parent_present": _QUEUE.parent.is_dir(),
            "ffmpeg_path": ff,
            "ffmpeg_present": bool(ff),
            "clip_factory_importable": cf_ok,
            "cli": "bolt reprocess",
            "vertical_count": vert_count,
            "pending_count": pending,
            "note": (
                "Rebuild vertical (9:16) versions of existing media/clips and "
                "merge manual-upload plans into Data/multi_platform_queue.json. "
                "Does NOT auto-upload to TikTok. Distinct from bolt recordings / "
                "enhance / multi / Clip_Factory process_recording vertical path."
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

        if not clips_ok:
            out["error"] = _soft(f"clips dir missing ({clips})")
            out["hint"] = out["error"]
            return out

        if not ff:
            out["error"] = _soft("ffmpeg not on PATH / FFmpeg_Bin")
            out["hint"] = out["error"]
            return out

        if not cf_ok:
            out["error"] = _soft("Clip_Factory not importable")
            out["hint"] = out["error"]
            return out

        if mp4_count < 1:
            out["ready"] = True
            out["hint"] = (
                f"tooling ok but 0 clips in {clips.name}; "
                "run: bolt reprocess list | bolt recordings first"
            )
            out["error"] = ""
            return out

        out["ready"] = True
        out["hint"] = (
            f"ok — {mp4_count} mp4 in {clips.name}, {vert_count} already vertical, "
            f"{pending} to build; run: bolt reprocess run [--dry-run]"
        )
        return out
    except Exception as exc:
        return {
            "checked_at": _utc_now(),
            "ready": False,
            "partial": True,
            "readiness": "READY",
            "soft_fail_prefix": _SOFT,
            "error": _soft(f"status failed ({exc})"),
            "hint": _soft(f"status failed ({exc})"),
            "cli": "bolt reprocess",
            "is_stranger_ready": False,
            "probe": bool(probe),
        }


def list_items(*, as_json: bool = False) -> int:
    """Checklist of reprocess gates."""
    try:
        info = status(probe=False)
        rows = [
            ("engine reprocess_clips.py", bool(info.get("engine_present"))),
            (f"clips dir ({info.get('clips_dir')})", bool(info.get("clips_present"))),
            (f"mp4 count ({info.get('mp4_count')})", True),
            (
                f"vertical dir ({info.get('vertical_clips_dir')})",
                bool(info.get("vertical_clips_present")),
            ),
            (f"queue path ({info.get('queue_path')})", True),
            ("ffmpeg / FFmpeg_Bin", bool(info.get("ffmpeg_present"))),
            ("Clip_Factory importable", bool(info.get("clip_factory_importable"))),
            ("soft-fail CLI (bolt reprocess)", True),
            (f"verticals built ({info.get('vertical_count')}) / to build ({info.get('pending_count')})", True),
            ("queue merge (keeps other items, no duplicates)", True),
            ("no TikTok auto-upload (manual queue)", True),
            ("distinct from bolt recordings / enhance / multi", True),
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
        print("Reprocess clips (READY)", flush=True)
        for name, ok in rows:
            mark = "OK" if ok else "--"
            print(f"  [{mark}] {name}", flush=True)
        if info.get("hint"):
            print(f"  → {info['hint']}", flush=True)
        print(
            "  (run: bolt reprocess run [--dry-run])",
            flush=True,
        )
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
    force: bool = False,
    limit: Optional[int] = None,
    names: Optional[List[str]] = None,
) -> int:
    """Soft-fail invoke reprocess_clips.py (never raises)."""
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
        if not info.get("ffmpeg_present"):
            msg = info.get("error") or _soft("ffmpeg not on PATH")
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
        if not info.get("clips_present"):
            msg = info.get("error") or _soft("clips dir missing")
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
        if not info.get("clip_factory_importable") and not dry_run:
            msg = info.get("error") or _soft("Clip_Factory not importable")
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
        if dry_run:
            argv.append("--dry-run")
        if force:
            argv.append("--force")
        if limit is not None:
            argv += ["--limit", str(limit)]
        if as_json:
            argv.append("--json")
        argv += list(names or [])
        if (info.get("mp4_count") or 0) < 1:
            msg = _soft(
                f"no mp4 clips in {info.get('clips_dir')} — run bolt wrap <vod> "
                "or bolt recordings first"
            )
            if as_json:
                print(json.dumps({"ok": False, "error": msg, "readiness": "READY"}, indent=2))
            else:
                print(msg, file=sys.stderr)
            return 0

        env = os.environ.copy()
        env["PYTHONPATH"] = f"{_REPO / 'Core'}" + (
            f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else ""
        )
        rc = subprocess.call(argv, cwd=str(_REPO), env=env)
        if rc == 1:
            print(_soft("engine setup error (see above)"), file=sys.stderr)
        elif rc == 2:
            print(_soft("some clips failed to convert (see above)"), file=sys.stderr)
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
        print("Reprocess clips (READY)")
        print(f"  ready: {ready}")
        print(f"  engine: {info.get('engine_path')}")
        print(f"  clips: {info.get('clips_dir')} ({info.get('mp4_count')} mp4)")
        print(
            f"  vertical: {info.get('vertical_clips_dir')} "
            f"({info.get('vertical_count')} built, {info.get('pending_count')} to build)"
        )
        print(f"  queue: {info.get('queue_path')}")
        print(f"  ffmpeg: {info.get('ffmpeg_path') or '(missing)'}")
        print(f"  Clip_Factory: {info.get('clip_factory_importable')}")
        print("  readiness: READY (manual upload queue; no TikTok auto-upload)")
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
            """bolt reprocess — vertical rebuild + multi-platform queue (READY)

  bolt reprocess                              # status (default)
  bolt reprocess status [--json] [--probe]
  bolt reprocess list [--json]
  bolt reprocess run [NAME ...] [--dry-run] [--force] [--limit N] [--json]

run: media/clips/*.mp4 → media/vertical_clips/<stem>_tiktok.mp4 (config
tiktok_style; output checked to be a real portrait video) → merged into
Data/multi_platform_queue.json (other items kept, no duplicates; .bak
written first). NAME filters clips by substring; --force rebuilds
existing verticals. Source clips are never moved or deleted.
Soft-fail: "Reprocess unavailable:".
Does NOT auto-upload to TikTok (manual_upload_ready plans only).
Distinct from bolt recordings / enhance / multi / Clip_Factory process_recording.
Aliases: reprocess_clips, reprocess-clips, reprocess-status, vertical-reprocess, tiktok-reprocess.
"""
        )
        return 0

    json_out = "--json" in args
    probe = "--probe" in args
    dry_run = "--dry-run" in args or "-n" in args
    force = "--force" in args
    limit: Optional[int] = None
    cleaned: List[str] = []
    skip = False
    for i, a in enumerate(args):
        if skip:
            skip = False
            continue
        if a == "--limit" and i + 1 < len(args):
            try:
                limit = int(args[i + 1])
            except ValueError:
                print(_soft(f"--limit needs a number, got {args[i + 1]!r}"), file=sys.stderr)
                return 0
            skip = True
            continue
        if a.startswith("--limit="):
            try:
                limit = int(a.split("=", 1)[1])
            except ValueError:
                print(_soft(f"bad {a}"), file=sys.stderr)
                return 0
            continue
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
    if cmd in ("run", "go", "exec", "reprocess"):
        return try_run(
            dry_run=dry_run,
            as_json=json_out,
            force=force,
            limit=limit,
            names=cleaned[1:],
        )

    print(
        _soft(f"unknown command {cleaned[0]!r} — try status|list|run"),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
