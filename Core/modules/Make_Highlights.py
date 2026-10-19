#!/usr/bin/env python3
"""
Make_Highlights.py — Local highlight reel stitch (READY)
========================================================
Soft-fail CLI for the former SHELL ``scripts/make_highlights.py`` (invalid
Twitch Helix paste / IndentationError). Engine is the real local stitcher
``scripts/make_twitch_highlights.py`` (same code path as READY
``bolt highlights``).

Soft-fail prefix: ``Highlights unavailable:``.
READY (18 Oct 2026): real stitch of the top media/clips into
media/output/YYYY-MM-DD_highlight_reel.mp4 with the working ffmpeg from
FFmpeg_Bin. Every clip is normalised (1920x1080/30 fps/AAC stereo; silent
track added when a clip has none) so mixed sources concat cleanly. Missing
ffmpeg or zero clips soft-fail with guidance. Helix "create clip from VOD"
from the old paste is NOT implemented. Distinct from READY ``bolt vods`` (Helix
list/download) and from READY thin ``bolt highlights`` compile (same
engine; this surface adds status/list/run soft-fail).

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

_SOFT = "Highlights unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_ENGINE = _REPO / "scripts" / "make_twitch_highlights.py"
_LEGACY_SHELL = _REPO / "scripts" / "make_highlights.py"
_CLIPS = _REPO / "media" / "clips"
_LEGACY_CLIPS = _REPO / "clips"
_VERTICAL = _REPO / "media" / "vertical_clips"
_OUTPUT = _REPO / "media" / "output"


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


def _count_mp4(clips: Path) -> int:
    try:
        return sum(1 for p in clips.glob("*.mp4") if p.is_file())
    except Exception:
        return 0


def _which(name: str) -> Optional[str]:
    return shutil.which(name)


def _ffmpeg_path() -> Optional[str]:
    """Working ffmpeg only (ffmpeg_bin() returns "ffmpeg" even when absent)."""
    try:
        if str(_REPO / "Core") not in sys.path:
            sys.path.insert(0, str(_REPO / "Core"))
        from modules.FFmpeg_Bin import working_ffmpeg

        return working_ffmpeg()
    except Exception:
        return _which("ffmpeg")


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Readiness for local highlight reel stitch (READY)."""
    try:
        engine_ok = _ENGINE.is_file()
        legacy = _LEGACY_SHELL.is_file()
        clips = _clips_dir()
        clips_ok = clips.is_dir()
        mp4_count = _count_mp4(clips) if clips_ok else 0
        ff = _ffmpeg_path()
        vert_ok = _VERTICAL.is_dir()

        out: Dict[str, Any] = {
            "checked_at": _utc_now(),
            "ready": False,
            "partial": False,
            "readiness": "READY",
            "soft_fail_prefix": _SOFT,
            "engine_path": str(_ENGINE),
            "engine_present": engine_ok,
            "legacy_shell_path": str(_LEGACY_SHELL),
            "legacy_shell_present": legacy,
            "legacy_note": (
                "former IndentationError Helix paste — now forwards to "
                "make_twitch_highlights.py"
            ),
            "clips_dir": str(clips),
            "clips_present": clips_ok,
            "mp4_count": mp4_count,
            "vertical_clips_dir": str(_VERTICAL),
            "vertical_clips_present": vert_ok,
            "ffmpeg_path": ff,
            "ffmpeg_present": bool(ff),
            "cli": "bolt make-highlights",
            "ready_alias": "bolt highlights",
            "output_dir": str(_OUTPUT),
            "note": (
                "Local stitch of top media/clips into one reel; "
                "not Twitch Helix create-clip. Prefer bolt highlights to compile; "
                "bolt vods for Helix list/download."
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
            out["error"] = _soft(
                "no working ffmpeg (FFmpeg_Bin) — brew install ffmpeg-full "
                "or set BOLT_FFMPEG=/path/to/ffmpeg"
            )
            out["hint"] = out["error"]
            return out

        if mp4_count < 1:
            out["error"] = _soft(
                f"no mp4 clips in {clips} — run bolt recordings first"
            )
            out["hint"] = out["error"]
            # tooling present; empty library
            out["ready"] = True
            out["hint"] = (
                f"tooling ok but 0 clips in {clips.name}; "
                "run: bolt make-highlights list | bolt highlights --list"
            )
            out["error"] = ""
            return out

        out["ready"] = True
        out["hint"] = (
            f"ok — {mp4_count} mp4 in {clips.name}; "
            "run: bolt make-highlights run [--list][--count N] "
            "or bolt highlights --list"
        )
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
            "cli": "bolt make-highlights",
            "is_stranger_ready": False,
            "probe": bool(probe),
        }


def list_items(*, as_json: bool = False) -> int:
    """Checklist + top clips preview (engine --list)."""
    try:
        info = status(probe=False)
        rows = [
            ("engine make_twitch_highlights.py", bool(info.get("engine_present"))),
            ("legacy make_highlights.py forwarder", bool(info.get("legacy_shell_present"))),
            (f"clips dir ({info.get('clips_dir')})", bool(info.get("clips_present"))),
            (f"mp4 count ({info.get('mp4_count')})", True),
            ("ffmpeg / FFmpeg_Bin", bool(info.get("ffmpeg_present"))),
            ("soft-fail CLI (bolt make-highlights)", True),
            ("READY compile alias (bolt highlights)", True),
            ("distinct from bolt vods (Helix)", True),
            (f"output → {_OUTPUT.relative_to(_REPO)}/YYYY-MM-DD_highlight_reel.mp4", True),
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
        print("Make highlights (READY)", flush=True)
        for name, ok in rows:
            mark = "OK" if ok else "--"
            print(f"  [{mark}] {name}", flush=True)
        if info.get("hint"):
            print(f"  → {info['hint']}", flush=True)
        # Best-effort top-clip preview (after checklist so piped stdout stays ordered)
        if info.get("engine_present") and info.get("ffmpeg_present"):
            print("  --- engine --list ---", flush=True)
            try:
                env = os.environ.copy()
                env["PYTHONPATH"] = f"{_REPO / 'Core'}" + (
                    f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else ""
                )
                subprocess.call(
                    [sys.executable, str(_ENGINE), "--list"],
                    cwd=str(_REPO),
                    env=env,
                )
            except Exception as exc:
                print(f"  ({_soft(f'list preview failed ({exc})')})", flush=True)
        print(
            "  (run: bolt make-highlights run [--count N][--game NAME][--output PATH])",
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
    list_only: bool = False,
    count: Optional[int] = None,
    game: Optional[str] = None,
    output: Optional[str] = None,
) -> int:
    """Soft-fail invoke make_twitch_highlights.py (never raises)."""
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

        if int(info.get("mp4_count") or 0) < 1:
            msg = _soft(
                f"no mp4 clips in {info.get('clips_dir')} — run bolt wrap "
                "<vod> or bolt recordings first, then bolt make-highlights run"
            )
            if as_json:
                print(json.dumps({"ok": False, "error": msg, "readiness": "READY"}, indent=2))
            else:
                print(msg, file=sys.stderr)
            return 0

        argv: List[str] = [sys.executable, str(_ENGINE)]
        if list_only or dry_run:
            argv.append("--list")
        if count is not None:
            argv.extend(["--count", str(count)])
        if game:
            argv.extend(["--game", game])
        if output and not (list_only or dry_run):
            argv.extend(["--output", output])

        if dry_run and as_json:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "dry_run": True,
                        "readiness": "READY",
                        "cmd": argv[1:],
                        "mp4_count": info.get("mp4_count"),
                        "hint": "dry-run → engine --list only",
                    },
                    indent=2,
                )
            )
            # still show list
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{_REPO / 'Core'}" + (
            f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else ""
        )
        rc = subprocess.call(argv, cwd=str(_REPO), env=env)
        if rc != 0 and not as_json:
            print(
                _soft(f"engine exit {rc} — see the message above"),
                file=sys.stderr,
            )
        if as_json and not dry_run:
            print(
                json.dumps(
                    {
                        "ok": rc == 0,
                        "exit_code": rc,
                        "readiness": "READY",
                        "cmd": argv[1:],
                        "error": "" if rc == 0 else _soft(f"engine exit {rc}"),
                    },
                    indent=2,
                )
            )
        return 0 if rc == 0 else 0  # soft-fail: never hard-fail the CLI
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
        print("Make highlights (READY)")
        print(f"  ready: {ready}")
        print(f"  engine: {info.get('engine_path')}")
        print(f"  clips: {info.get('clips_dir')} ({info.get('mp4_count')} mp4)")
        print(f"  ffmpeg: {info.get('ffmpeg_path') or '(missing)'}")
        print(f"  output: {info.get('output_dir')}")
        print(f"  READY alias: bolt highlights")
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
            """bolt make-highlights — local highlight reel stitch (READY)

  bolt make-highlights                              # status (default)
  bolt make-highlights status [--json] [--probe]
  bolt make-highlights list [--json]
  bolt make-highlights run [--list] [--count N] [--game NAME] [--output PATH] [--dry-run] [--json]

Soft-fail: "Highlights unavailable:".
Engine: scripts/make_twitch_highlights.py (same as READY bolt highlights).
Former SHELL scripts/make_highlights.py (broken Helix paste) now forwards here.
Output: media/output/YYYY-MM-DD_highlight_reel.mp4 (--output NAME|ABS_PATH).
Distinct from READY bolt vods (Helix).
Aliases: make_highlights, make-highlights-status, stitch-highlights.
"""
        )
        return 0

    json_out = "--json" in args
    probe = "--probe" in args
    dry_run = "--dry-run" in args or "-n" in args
    list_flag = "--list" in args
    count: Optional[int] = None
    game: Optional[str] = None
    output: Optional[str] = None
    cleaned: List[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--count",) and i + 1 < len(args):
            try:
                count = int(args[i + 1])
            except ValueError:
                print(_soft(f"bad --count {args[i + 1]!r}"), file=sys.stderr)
                return 0
            i += 2
            continue
        if a in ("--game",) and i + 1 < len(args):
            game = args[i + 1]
            i += 2
            continue
        if a in ("--output", "-o") and i + 1 < len(args):
            output = args[i + 1]
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        cleaned.append(a)
        i += 1

    if not cleaned:
        return print_status(as_json=json_out, probe=probe)

    cmd = cleaned[0].lower()
    if cmd in ("status", "check", "ready"):
        return print_status(as_json=json_out, probe=probe)
    if cmd in ("list", "ls", "checklist"):
        return list_items(as_json=json_out)
    if cmd in ("run", "compile", "go", "exec", "stitch"):
        return try_run(
            dry_run=dry_run,
            as_json=json_out,
            list_only=list_flag,
            count=count,
            game=game,
            output=output,
        )

    print(
        _soft(f"unknown command {cleaned[0]!r} — try status|list|run"),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
