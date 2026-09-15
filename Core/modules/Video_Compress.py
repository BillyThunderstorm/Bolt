#!/usr/bin/env python3
"""
Video_Compress.py — HandBrake clip compression (PARTIAL)
========================================================
Wraps ``scripts/compress_videos.sh`` (cron + storage optimize path) with a
soft-fail CLI: ``bolt compress``.

Soft-fail prefix: ``Compress unavailable:``. HandBrakeCLI / ffmpeg gated —
stay PARTIAL (not stranger-ready). Distinct from READY ``bolt storage``
size/cron health (optimize may skip compress).

Public API:
  status() / list_items() / try_run() / print_status() / main()
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SOFT = "Compress unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "compress_videos.sh"
_CLIPS = _REPO / "media" / "clips"
_LEGACY_CLIPS = _REPO / "clips"
_LOG = _REPO / "logs" / "video_compression.log"
_OPTIMIZE = _REPO / "scripts" / "storage_optimization.sh"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _soft(msg: str) -> str:
    if msg.startswith(_SOFT):
        return msg
    return f"{_SOFT} {msg}"


def _which(name: str) -> Optional[str]:
    path = shutil.which(name)
    if path:
        return path
    brew = Path("/opt/homebrew/bin") / name
    if brew.is_file() and os.access(brew, os.X_OK):
        return str(brew)
    return None


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


def _crontab_mentions_compress() -> Optional[bool]:
    """True/False if crontab readable; None if crontab unavailable."""
    try:
        proc = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode != 0:
            return None
        body = (proc.stdout or "").lower()
        return "compress" in body or "handbrake" in body
    except Exception:
        return None


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Readiness for HandBrake clip compression (PARTIAL)."""
    try:
        darwin = platform.system() == "Darwin"
        script_ok = _SCRIPT.is_file() and os.access(_SCRIPT, os.X_OK)
        hb = _which("HandBrakeCLI")
        ff = _which("ffmpeg")
        clips = _clips_dir()
        clips_ok = clips.is_dir()
        mp4_count = _count_mp4(clips) if clips_ok else 0
        backup = clips / "originals_backup"
        cron_hit = _crontab_mentions_compress() if (probe or darwin) else None
        optimize_ok = _OPTIMIZE.is_file()

        out: Dict[str, Any] = {
            "checked_at": _utc_now(),
            "ready": False,
            "partial": True,
            "readiness": "PARTIAL",
            "soft_fail_prefix": _SOFT,
            "darwin": darwin,
            "script_path": str(_SCRIPT),
            "script_present": script_ok,
            "handbrake_path": hb,
            "handbrake_present": bool(hb),
            "ffmpeg_path": ff,
            "ffmpeg_present": bool(ff),
            "clips_dir": str(clips),
            "clips_present": clips_ok,
            "mp4_count": mp4_count,
            "backup_dir": str(backup),
            "backup_present": backup.is_dir(),
            "log_path": str(_LOG),
            "log_present": _LOG.is_file(),
            "crontab_mentions_compress": cron_hit,
            "storage_optimize_script": str(_OPTIMIZE) if optimize_ok else None,
            "cli": "bolt compress",
            "note": (
                "HandBrake clip compress for media/clips; "
                "also reachable via bolt storage optimize (may --skip-compress)"
            ),
            "is_stranger_ready": False,
            "probe": bool(probe),
            "error": "",
            "hint": "",
        }

        if not script_ok:
            out["error"] = _soft(f"engine missing ({_SCRIPT})")
            out["hint"] = out["error"]
            return out

        if not clips_ok:
            out["error"] = _soft(f"clips dir missing ({clips})")
            out["hint"] = out["error"]
            return out

        if not hb and not ff:
            out["error"] = _soft(
                "HandBrakeCLI and ffmpeg not on PATH (brew install handbrake)"
            )
            out["hint"] = out["error"]
            return out

        # Soft ready: script + clips + HandBrake (preferred) or ffmpeg fallback
        # noted in storage_optimization; cron script itself needs HandBrake.
        if not hb:
            out["error"] = _soft(
                "HandBrakeCLI not on PATH — cron script needs it "
                "(ffmpeg only helps bolt storage optimize)"
            )
            out["hint"] = out["error"]
            # still partial tooling present via ffmpeg for optimize path
            out["ready"] = False
            return out

        out["ready"] = True
        out["hint"] = (
            f"ok — {mp4_count} mp4 in {clips.name}; "
            "run: bolt compress run [--dry-run]"
        )
        if cron_hit is False:
            out["hint"] += " (no compress line in crontab — optional)"
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
            "cli": "bolt compress",
            "is_stranger_ready": False,
            "probe": bool(probe),
        }


def list_items(*, as_json: bool = False) -> int:
    """Checklist of compression pieces (no HandBrake run)."""
    try:
        info = status(probe=False)
        rows = [
            ("script compress_videos.sh", bool(info.get("script_present"))),
            ("HandBrakeCLI on PATH", bool(info.get("handbrake_present"))),
            ("ffmpeg on PATH (optimize fallback)", bool(info.get("ffmpeg_present"))),
            (f"clips dir ({info.get('clips_dir')})", bool(info.get("clips_present"))),
            (f"mp4 count ({info.get('mp4_count')})", True),
            ("backup originals_backup/", bool(info.get("backup_present"))),
            ("soft-fail CLI (bolt compress)", True),
            ("HandBrake gated (stay PARTIAL)", True),
            (
                "crontab mentions compress",
                info.get("crontab_mentions_compress") is not False,
            ),
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
        print("Video compress (PARTIAL — HandBrake gated)")
        for name, ok in rows:
            mark = "OK" if ok else "--"
            print(f"  [{mark}] {name}")
        if info.get("hint"):
            print(f"  → {info['hint']}")
        print("  (run: bolt compress run [--dry-run])")
        return 0
    except Exception as exc:
        msg = _soft(f"list failed ({exc})")
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0


def try_run(*, dry_run: bool = False, as_json: bool = False) -> int:
    """Soft-fail invoke compress_videos.sh (never raises)."""
    try:
        info = status(probe=False)
        if not info.get("script_present"):
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
        if not info.get("handbrake_present"):
            msg = info.get("error") or _soft("HandBrakeCLI not on PATH")
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
        if not info.get("clips_present"):
            msg = info.get("error") or _soft("clips dir missing")
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

        clips = Path(str(info.get("clips_dir")))
        backup = clips / "originals_backup"
        candidates: List[str] = []
        try:
            import time

            now = time.time()
            for p in sorted(clips.glob("*.mp4")):
                if not p.is_file():
                    continue
                if (backup / p.name).is_file():
                    continue
                # Match shell: only files older than 5 minutes
                age_min = (now - p.stat().st_mtime) / 60.0
                if age_min > 5:
                    candidates.append(str(p))
        except Exception:
            candidates = []

        if dry_run:
            payload = {
                "ok": True,
                "readiness": "PARTIAL",
                "dry_run": True,
                "candidates": candidates,
                "candidate_count": len(candidates),
                "clips_dir": str(clips),
                "handbrake": info.get("handbrake_path"),
            }
            if as_json:
                print(json.dumps(payload, indent=2))
            else:
                print(
                    f"Would compress {len(candidates)} mp4 "
                    f"(>5 min old, not in originals_backup) under {clips}"
                )
                for c in candidates[:20]:
                    print(f"  {c}")
                if len(candidates) > 20:
                    print(f"  … +{len(candidates) - 20} more")
            return 0

        env = os.environ.copy()
        env["PATH"] = "/opt/homebrew/bin:/opt/homebrew/sbin:" + env.get("PATH", "")
        env["CLIPS_DIR"] = str(clips)
        try:
            proc = subprocess.run(
                ["bash", str(_SCRIPT)],
                cwd=str(_REPO),
                env=env,
                capture_output=True,
                text=True,
                timeout=3600,
            )
        except subprocess.TimeoutExpired:
            msg = _soft("compress timed out after 3600s")
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
        except Exception as exc:
            msg = _soft(f"compress failed to start ({exc})")
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

        # Soft-fail: script exits 0 even on tool miss; report output
        out_tail = ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()
        tail = out_tail[-12:] if out_tail else []
        payload = {
            "ok": proc.returncode == 0,
            "readiness": "PARTIAL",
            "returncode": proc.returncode,
            "clips_dir": str(clips),
            "candidate_count_before": len(candidates),
            "log_path": str(_LOG),
            "tail": tail,
        }
        if proc.returncode != 0:
            payload["error"] = _soft(f"script exit {proc.returncode}")
        if as_json:
            print(json.dumps(payload, indent=2))
        else:
            if payload.get("error"):
                print(payload["error"], file=sys.stderr)
            for line in tail:
                print(line)
            print(f"  log: {_LOG}")
        return 0
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
            print(json.dumps(info, indent=2, default=str))
            return 0
        print("Video compress readiness (PARTIAL)")
        print(f"  ready: {info.get('ready')}")
        print(f"  readiness: {info.get('readiness')}")
        print(
            f"  HandBrake: {bool(info.get('handbrake_present'))} · "
            f"ffmpeg: {bool(info.get('ffmpeg_present'))} · "
            f"script: {info.get('script_present')}"
        )
        print(
            f"  clips: {info.get('clips_dir')} "
            f"({info.get('mp4_count')} mp4)"
        )
        print(f"  crontab_compress: {info.get('crontab_mentions_compress')}")
        print(f"  note: {info.get('note')}")
        print(f"  soft_fail_prefix: {info.get('soft_fail_prefix')}")
        if info.get("error"):
            print(f"  → {info['error']}")
        elif info.get("hint"):
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
            """bolt compress — HandBrake clip compression (PARTIAL)

  bolt compress                              # status (default)
  bolt compress status [--json] [--probe]
  bolt compress list [--json]
  bolt compress run [--dry-run] [--json]

Soft-fail: "Compress unavailable:".
HandBrakeCLI gated — stay PARTIAL.
Engine: scripts/compress_videos.sh (media/clips).
Also: bolt storage optimize [--skip-compress]
"""
        )
        return 0

    json_out = "--json" in args
    probe = "--probe" in args
    dry_run = "--dry-run" in args or "-n" in args
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
    if cmd in ("run", "compress", "scan", "go"):
        return try_run(dry_run=dry_run, as_json=json_out)

    print(
        _soft(f"unknown command '{cmd}' — try status|list|run"),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
