#!/usr/bin/env python3
"""
Filter_Backlog.py — Clip backlog score filter (READY)
=====================================================
Wraps ``scripts/Filter_Backlog.py`` with a soft-fail CLI:
``bolt filter-backlog`` (alias ``bolt filter_backlog``).

Soft-fail prefix: ``Backlog unavailable:``. Moves low-scoring clips (mp4 +
same-name sidecar/thumbnail/captions) under ``media/clips/_low_score/`` using
Clip_Ranker scores (sidecar / logs / audio) and the game profile's
``min_clip_score`` (Game_Config). Keeps clips still in the post queue and
clips that could not be scored; never overwrites; every move is logged to
``_low_score/_moves.jsonl`` and ``bolt filter-backlog restore`` undoes it.
READY since 19 Oct 2026 (Shells). Distinct from READY ``bolt recordings`` /
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


_THR_SRC: Dict[str, str] = {}


def _threshold_default() -> Optional[float]:
    """Same threshold the engine uses: game profile min_clip_score."""
    try:
        if str(_REPO / "Core") not in sys.path:
            sys.path.insert(0, str(_REPO / "Core"))
        from modules.Config_Loader import load_config
        from modules.Clip_Ranker import DISCARD_BELOW

        cfg = load_config() or {}
        try:
            from modules.Game_Config import effective_config

            eff = effective_config(None, cfg)
            val = (eff.get("values") or {}).get("min_clip_score")
            if val is not None:
                _THR_SRC["src"] = (
                    f"game profile {eff.get('game')!r} "
                    f"({(eff.get('sources') or {}).get('min_clip_score', 'default')})"
                )
                return float(val)
        except Exception:
            pass
        _THR_SRC["src"] = "config"
        return float(cfg.get("min_clip_score", DISCARD_BELOW))
    except Exception:
        return None


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Readiness for clip backlog score filter (READY)."""
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
            "partial": False,
            "readiness": "READY",
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
                "Scores clips in media/clips (Clip_Ranker) against the game "
                "profile min_clip_score and moves low ones + companions to "
                "media/clips/_low_score/; queued/unscored clips kept; restore undoes"
            ),
            "is_stranger_ready": False,
            "threshold_source": _THR_SRC.get("src", ""),
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
        if low_count:
            thr += f"; undo: bolt filter-backlog restore"
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
            "partial": False,
            "readiness": "READY",
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
            ("game-profile threshold + queue/unscored protection", True),
            ("companions moved together + restore (undo)", True),
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
                        "threshold_default": info.get("threshold_default"),
                    },
                    indent=2,
                )
            )
            return 0
        print("Filter backlog (READY)")
        for name, ok in rows:
            mark = "OK" if ok else "--"
            print(f"  [{mark}] {name}")
        if info.get("threshold_default") is not None:
            print(
                f"  threshold default: {info['threshold_default']:g}"
                + (f" · {info.get('threshold_source')}" if info.get("threshold_source") else "")
            )
        if info.get("hint"):
            print(f"  → {info['hint']}")
        print("  (run: bolt filter-backlog run [--dry-run] [--threshold N] · restore [NAME|--all])")
        return 0
    except Exception as exc:
        msg = _soft(f"list failed ({exc})")
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0


def _emit_fail(msg: str, as_json: bool) -> int:
    if as_json:
        print(json.dumps({"ok": False, "error": msg, "readiness": "READY"}, indent=2))
    else:
        print(msg, file=sys.stderr)
    return 0


def _run_engine(extra: List[str], *, as_json: bool, meta: Dict[str, Any]) -> int:
    """Soft-fail invoke scripts/Filter_Backlog.py with ``extra`` args."""
    info = status(probe=False)
    for key, fallback in (
        ("script_present", "engine script missing"),
        ("clips_present", "clips dir missing"),
        ("ranker_ok", "Clip_Ranker unavailable"),
    ):
        if not info.get(key):
            return _emit_fail(info.get("error") or _soft(fallback), as_json)

    cmd = [sys.executable, str(_SCRIPT)] + list(extra)
    if as_json:
        cmd.append("--json")
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{_REPO / 'Core'}" + (
        f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else ""
    )
    try:
        proc = subprocess.run(
            cmd, cwd=str(_REPO), env=env, capture_output=True, text=True, timeout=600
        )
    except subprocess.TimeoutExpired:
        return _emit_fail(_soft("filter timed out after 600s"), as_json)
    except Exception as exc:
        return _emit_fail(_soft(f"filter failed to start ({exc})"), as_json)

    stdout = proc.stdout or ""
    if as_json:
        payload: Dict[str, Any] = {"readiness": "READY", "returncode": proc.returncode}
        payload.update(meta)
        try:
            payload["result"] = json.loads(stdout)
            payload["ok"] = bool(payload["result"].get("ok", proc.returncode == 0))
        except Exception:
            payload["ok"] = False
            payload["tail"] = (stdout + (proc.stderr or "")).strip().splitlines()[-40:]
        if proc.returncode != 0 and not payload.get("error"):
            payload["error"] = _soft(f"script exit {proc.returncode}")
        print(json.dumps(payload, indent=2, default=str))
        return 0

    lines = (stdout + (proc.stderr or "")).strip().splitlines()
    # Drop Clip_Ranker/notifier log chatter; the engine prints its own summary.
    lines = [ln for ln in lines if ln.strip()]
    if proc.returncode != 0:
        print(_soft(f"script exit {proc.returncode}"), file=sys.stderr)
    for line in lines[-80:]:
        print(line)
    return 0


def try_run(
    *,
    dry_run: bool = False,
    as_json: bool = False,
    threshold: Optional[float] = None,
    game: Optional[str] = None,
    include_queued: bool = False,
) -> int:
    """Soft-fail score + move low clips (never raises)."""
    try:
        extra: List[str] = []
        if dry_run:
            extra.append("--dry-run")
        if threshold is not None:
            extra.extend(["--threshold", str(threshold)])
        if game:
            extra.extend(["--game", str(game)])
        if include_queued:
            extra.append("--include-queued")
        return _run_engine(
            extra,
            as_json=as_json,
            meta={"action": "run", "dry_run": bool(dry_run), "threshold": threshold, "game": game},
        )
    except Exception as exc:
        return _emit_fail(_soft(f"run failed ({exc})"), as_json)


def try_restore(
    names: Optional[List[str]] = None,
    *,
    restore_all: bool = False,
    dry_run: bool = False,
    as_json: bool = False,
) -> int:
    """Soft-fail move clips back from _low_score (no names = list them)."""
    try:
        extra: List[str] = ["--restore"] + list(names or [])
        if restore_all:
            extra.append("--all")
        if dry_run:
            extra.append("--dry-run")
        return _run_engine(
            extra,
            as_json=as_json,
            meta={"action": "restore", "dry_run": bool(dry_run), "names": list(names or [])},
        )
    except Exception as exc:
        return _emit_fail(_soft(f"restore failed ({exc})"), as_json)


def print_status(*, as_json: bool = False, probe: bool = False) -> int:
    try:
        info = status(probe=probe)
        if as_json:
            print(json.dumps(info, indent=2, default=str))
            return 0
        print("Filter backlog readiness (READY)")
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
            """bolt filter-backlog — clip backlog score filter (READY)

  bolt filter-backlog                         # status (default)
  bolt filter-backlog status [--json] [--probe]
  bolt filter-backlog list [--json]
  bolt filter-backlog run [--dry-run] [--threshold N] [--game NAME] [--include-queued] [--json]
  bolt filter-backlog restore [NAME ...] [--all] [--dry-run] [--json]

Soft-fail: "Backlog unavailable:".
Moves low-scoring media/clips → media/clips/_low_score/ via Clip_Ranker.
Threshold = game profile min_clip_score (bolt game-config show) unless --threshold.
Moves the mp4 plus its same-name .json/.jpg/.srt; keeps clips still in the post
queue and clips that could not be scored; never overwrites. Every move is logged
to media/clips/_low_score/_moves.jsonl; restore with no names lists what's there.
Aliases: filter_backlog, backlog-filter, filter-clips.
Engine: scripts/Filter_Backlog.py
"""
        )
        return 0

    json_out = "--json" in args
    probe = "--probe" in args
    dry_run = "--dry-run" in args or "-n" in args
    include_queued = "--include-queued" in args
    restore_all = "--all" in args
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
            dry_run=dry_run,
            as_json=json_out,
            threshold=threshold,
            game=game,
            include_queued=include_queued,
        )
    if cmd in ("restore", "undo", "unfilter"):
        return try_restore(
            cleaned[1:], restore_all=restore_all, dry_run=dry_run, as_json=json_out
        )

    print(_soft(f"unknown command {cleaned[0]!r} — try status|list|run|restore"), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
