#!/usr/bin/env python3
"""
Filter_Backlog.py — Clip backlog score filter (PARTIAL)
=======================================================
Wraps ``scripts/Filter_Backlog.py`` with a soft-fail CLI:
``bolt filter-backlog`` (alias ``bolt filter_backlog``).

Soft-fail prefix: ``Backlog unavailable:``. Moves low-scoring clips under
``media/clips/_low_score/`` using Clip_Ranker (sidecar / logs / audio).
Stay PARTIAL — score quality and media layout are William-specific; not a
stranger-ready product surface. Distinct from READY ``bolt recordings`` /
``bolt queue``.

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

_SOFT = "Backlog unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "Filter_Backlog.py"
_CLIPS = _REPO / "media" / "clips"
_LEGACY_CLIPS = _REPO / "clips"
_LOW = "_low_score"


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


def _count_low(clips: Path) -> int:
    low = clips / _LOW
    try:
        if not low.is_dir():
            return 0
        return sum(1 for p in low.glob("*.mp4") if p.is_file())
    except Exception:
        return 0


def _ranker_ok() -> tuple[bool, str]:
    try:
        if str(_REPO / "Core") not in sys.path:
            sys.path.insert(0, str(_REPO / "Core"))
        from modules.Clip_Ranker import (  # noqa: F401
            DISCARD_BELOW,
            clip_from_path,
            rank_clips,
        )

        return True, f"Clip_Ranker importable (DISCARD_BELOW={DISCARD_BELOW})"
    except Exception as exc:
        return False, f"Clip_Ranker import failed ({exc})"


def _threshold_default() -> Optional[float]:
    try:
        if str(_REPO / "Core") not in sys.path:
            sys.path.insert(0, str(_REPO / "Core"))
        from modules.Config_Loader import load_config
        from modules.Clip_Ranker import DISCARD_BELOW

        cfg = load_config() or {}
        return float(cfg.get("min_clip_score", DISCARD_BELOW))
    except Exception:
        return None


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Readiness for clip backlog score filter (PARTIAL)."""
    try:
        script_ok = _SCRIPT.is_file()
        clips = _clips_dir()
        clips_ok = clips.is_dir()
        mp4_count = _count_mp4(clips) if clips_ok else 0
        low_count = _count_low(clips) if clips_ok else 0
        ranker_ok, ranker_detail = _ranker_ok()
        threshold = _threshold_default() if (probe or ranker_ok) else None

        out: Dict[str, Any] = {
            "checked_at": _utc_now(),
            "ready": False,
            "partial": True,
            "readiness": "PARTIAL",
            "soft_fail_prefix": _SOFT,
            "script_path": str(_SCRIPT),
            "script_present": script_ok,
            "clips_dir": str(clips),
            "clips_present": clips_ok,
            "mp4_count": mp4_count,
            "low_score_dir": str(clips / _LOW),
            "low_score_count": low_count,
            "ranker_ok": ranker_ok,
            "ranker_detail": ranker_detail,
            "threshold_default": threshold,
            "cli": "bolt filter-backlog",
            "note": (
                "Scores clips in media/clips and moves low scores to "
                "media/clips/_low_score/ (sidecar + logs + audio via Clip_Ranker)"
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

        if not ranker_ok:
            out["error"] = _soft(ranker_detail)
            out["hint"] = out["error"]
            return out

        out["ready"] = True
        thr = f", keep ≥ {threshold:g}" if threshold is not None else ""
        out["hint"] = (
            f"ok — {mp4_count} mp4 in {clips.name}, "
            f"{low_count} already in {_LOW}{thr}; "
            "run: bolt filter-backlog run [--dry-run]"
        )
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
            "cli": "bolt filter-backlog",
            "is_stranger_ready": False,
            "probe": bool(probe),
        }


def list_items(*, as_json: bool = False) -> int:
    """Checklist of backlog filter pieces (no moves)."""
    try:
        info = status(probe=False)
        rows = [
            ("script Filter_Backlog.py", bool(info.get("script_present"))),
            ("Clip_Ranker importable", bool(info.get("ranker_ok"))),
            (f"clips dir ({info.get('clips_dir')})", bool(info.get("clips_present"))),
            (f"mp4 count ({info.get('mp4_count')})", True),
            (f"_low_score count ({info.get('low_score_count')})", True),
            ("soft-fail CLI (bolt filter-backlog)", True),
            ("score/move gated (stay PARTIAL)", True),
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
                        "threshold_default": info.get("threshold_default"),
                    },
                    indent=2,
                )
            )
            return 0
        print("Filter backlog (PARTIAL — Clip_Ranker / media gated)")
        for name, ok in rows:
            mark = "OK" if ok else "--"
            print(f"  [{mark}] {name}")
        if info.get("threshold_default") is not None:
            print(f"  threshold default: {info['threshold_default']}")
        if info.get("hint"):
            print(f"  → {info['hint']}")
        print("  (run: bolt filter-backlog run [--dry-run] [--threshold N])")
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
    threshold: Optional[float] = None,
    game: Optional[str] = None,
) -> int:
    """Soft-fail invoke scripts/Filter_Backlog.py (never raises)."""
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
        if not info.get("ranker_ok"):
            msg = info.get("error") or _soft("Clip_Ranker unavailable")
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

        cmd = [sys.executable, str(_SCRIPT)]
        if dry_run:
            cmd.append("--dry-run")
        if threshold is not None:
            cmd.extend(["--threshold", str(threshold)])
        if game:
            cmd.extend(["--game", str(game)])

        env = os.environ.copy()
        env["PYTHONPATH"] = f"{_REPO / 'Core'}" + (
            f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else ""
        )
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(_REPO),
                env=env,
                capture_output=True,
                text=True,
                timeout=600,
            )
        except subprocess.TimeoutExpired:
            msg = _soft("filter timed out after 600s")
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
            msg = _soft(f"filter failed to start ({exc})")
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

        out_tail = ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()
        tail = out_tail[-40:] if out_tail else []
        payload: Dict[str, Any] = {
            "ok": proc.returncode == 0,
            "readiness": "PARTIAL",
            "returncode": proc.returncode,
            "dry_run": bool(dry_run),
            "clips_dir": info.get("clips_dir"),
            "mp4_count_before": info.get("mp4_count"),
            "threshold": threshold,
            "game": game,
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
        print("Filter backlog readiness (PARTIAL)")
        print(f"  ready: {info.get('ready')}")
        print(f"  readiness: {info.get('readiness')}")
        print(
            f"  script: {info.get('script_present')} · "
            f"ranker: {info.get('ranker_ok')} · "
            f"clips: {info.get('clips_present')}"
        )
        print(
            f"  clips: {info.get('clips_dir')} "
            f"({info.get('mp4_count')} mp4, "
            f"{info.get('low_score_count')} in {_LOW})"
        )
        if info.get("threshold_default") is not None:
            print(f"  threshold_default: {info.get('threshold_default')}")
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
            """bolt filter-backlog — clip backlog score filter (PARTIAL)

  bolt filter-backlog                         # status (default)
  bolt filter-backlog status [--json] [--probe]
  bolt filter-backlog list [--json]
  bolt filter-backlog run [--dry-run] [--threshold N] [--game NAME] [--json]

Soft-fail: "Backlog unavailable:".
Moves low-scoring media/clips → media/clips/_low_score/ via Clip_Ranker.
Stay PARTIAL (score/media gated). Aliases: filter_backlog, backlog-filter.
Engine: scripts/Filter_Backlog.py
"""
        )
        return 0

    json_out = "--json" in args
    probe = "--probe" in args
    dry_run = "--dry-run" in args or "-n" in args
    threshold: Optional[float] = None
    game: Optional[str] = None
    cleaned: List[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--threshold",) and i + 1 < len(args):
            try:
                threshold = float(args[i + 1])
            except ValueError:
                print(_soft(f"bad --threshold {args[i + 1]!r}"), file=sys.stderr)
                return 0
            i += 2
            continue
        if a in ("--game",) and i + 1 < len(args):
            game = args[i + 1]
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
    if cmd in ("run", "filter", "go", "exec"):
        return try_run(
            dry_run=dry_run, as_json=json_out, threshold=threshold, game=game
        )

    print(_soft(f"unknown command {cleaned[0]!r} — try status|list|run"), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
