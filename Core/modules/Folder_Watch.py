#!/usr/bin/env python3
"""
Folder_Watch.py — ``bolt watch``: watch the recordings folder and clip new recordings
====================================================================================
READY (19 Oct 2026). Watches ``media/Recordings`` (or ``RECORDINGS_FOLDER`` /
``--folder``) and runs every new, finished recording through the same clip
pipeline as ``bolt recordings`` / live mode (``bot.process_recording``:
highlights → clips → titles → captions → rank → vertical + post queue).

Before this, ``bolt watch run`` only printed paths, and the Watcher marked each
one processed — so a recording "seen" by ``bolt watch`` was never clipped.

Soft-fail prefix: ``Watch unavailable:`` (missing ffmpeg / engine / folder).

CLI (via ``bolt watch``):
  status [--json] [--probe]
  list   [--json] [--limit N]
  run    [--folder PATH] [--once] [--max N] [--dry-run] [--json]
           (default)  keep watching; clip each new recording as it lands
           --once     clip what is pending now, then exit
           --dry-run  show what would be clipped; touches nothing

Files still being written (size changing) are skipped and picked up later.
Processed names live in ``Data/processed_recordings.json``; reprocess with
``bolt recordings latest --force``. Distinct from ``bolt launch`` (which also
starts Twitch chat / OBS) and ``bolt recordings`` (one-shot, newest only).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_SOFT = "Watch unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_CORE = _REPO / "Core"
_ENGINE = _REPO / "Core" / "modules" / "Watcher.py"
_BOT = _REPO / "Core" / "bot.py"
_SCRIPT_SHIM = _REPO / "scripts" / "Watcher.py"
_PATHS = _REPO / "scripts" / "_paths.py"
_PROCESSED = _REPO / "Data" / "processed_recordings.json"
_FFMPEG_HINT = (
    "no working ffmpeg (FFmpeg_Bin) — brew install ffmpeg-full "
    "or set BOLT_FFMPEG=/path/to/ffmpeg"
)


def _soft(msg: str) -> str:
    if msg.startswith(_SOFT):
        return msg
    return f"{_SOFT} {msg}"


def _iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_core_path() -> None:
    for p in (str(_REPO / "scripts"), str(_CORE)):
        if p not in sys.path:
            sys.path.insert(0, p)


def _load_watcher():
    _ensure_core_path()
    if not _ENGINE.is_file():
        raise FileNotFoundError(f"missing engine {_ENGINE}")
    from modules import Watcher as w  # noqa: WPS433

    return w


def _ffmpeg_path() -> Optional[str]:
    """Working ffmpeg only (ffmpeg_bin() returns "ffmpeg" even when absent)."""
    _ensure_core_path()
    try:
        from modules.FFmpeg_Bin import working_ffmpeg

        return working_ffmpeg()
    except Exception:
        from shutil import which

        return which("ffmpeg")


def _processed_count() -> int:
    if not _PROCESSED.is_file():
        return 0
    try:
        raw = json.loads(_PROCESSED.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return len(raw)
        if isinstance(raw, dict):
            items = raw.get("processed", raw.get("files", []))
            return len(items) if isinstance(items, list) else 0
    except Exception:
        return 0
    return 0


def status(*, probe: bool = False) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "checked_at": _iso(),
        "ready": False,
        "partial": False,
        "readiness": "READY",
        "soft_fail_prefix": _SOFT,
        "cli": "bolt watch",
        "engine": str(_ENGINE),
        "engine_present": _ENGINE.is_file(),
        "pipeline": str(_BOT),
        "pipeline_present": _BOT.is_file(),
        "paths_helper": str(_PATHS),
        "paths_present": _PATHS.is_file(),
        "processed_log": str(_PROCESSED),
        "processed_present": _PROCESSED.is_file(),
        "processed_count": _processed_count(),
        "ffmpeg_path": None,
        "ffmpeg_present": False,
        "recordings_folder": "",
        "recordings_exists": False,
        "video_count": None,
        "pending_count": None,
        "watch_interval": None,
        "probe": bool(probe),
        "probe_ok": None,
        "error": "",
        "hint": (
            "bolt watch run = keep watching and clip new recordings · "
            "--once = clip what's pending then exit · --dry-run = preview"
        ),
        "is_stranger_ready": False,
    }
    missing = []
    if not info["engine_present"]:
        missing.append("Core/modules/Watcher.py")
    if not info["pipeline_present"]:
        missing.append("Core/bot.py")
    if not info["paths_present"]:
        missing.append("scripts/_paths.py")
    if missing:
        info["readiness"] = "PARTIAL"
        info["error"] = _soft("missing " + ", ".join(missing))
        return info

    ff = _ffmpeg_path()
    info["ffmpeg_path"] = ff
    info["ffmpeg_present"] = bool(ff)

    try:
        w = _load_watcher()
        folder = Path(getattr(w, "RECORDINGS_FOLDER", "") or "")
        info["recordings_folder"] = str(folder)
        info["recordings_exists"] = folder.is_dir() if str(folder) else False
        info["watch_interval"] = getattr(w, "WATCH_INTERVAL", None)
        if info["recordings_exists"]:
            info["video_count"] = len(w.video_files(folder))
            info["pending_count"] = len(w.list_pending_recordings(folder))
        if probe:
            info["probe_ok"] = True
    except Exception as exc:
        info["readiness"] = "PARTIAL"
        info["error"] = _soft(str(exc) or type(exc).__name__)
        if probe:
            info["probe_ok"] = False
        return info

    if not ff:
        info["readiness"] = "PARTIAL"
        info["error"] = _soft(_FFMPEG_HINT)
        return info
    info["ready"] = True
    if not info["recordings_exists"]:
        info["hint"] = (
            f"recordings folder missing (created on run): {info['recordings_folder']}"
            " · point OBS recordings there or set RECORDINGS_FOLDER in .env"
        )
    return info


def list_items(*, limit: int = 20) -> List[Dict[str, Any]]:
    st = status(probe=False)
    rows: List[Dict[str, Any]] = [
        {"id": "engine", "ok": st["engine_present"], "detail": st["engine"]},
        {"id": "pipeline", "ok": st["pipeline_present"], "detail": st["pipeline"]},
        {
            "id": "ffmpeg",
            "ok": st["ffmpeg_present"],
            "detail": st.get("ffmpeg_path") or _FFMPEG_HINT,
        },
        {
            "id": "processed_log",
            "ok": True,
            "detail": (
                f"{st['processed_log']} present={st['processed_present']} "
                f"count={st['processed_count']}"
            ),
        },
        {
            "id": "recordings_folder",
            "ok": bool(st.get("recordings_exists")),
            "detail": (
                f"{st.get('recordings_folder') or '(unknown)'} "
                f"exists={st.get('recordings_exists')} videos={st.get('video_count')}"
            ),
        },
    ]
    try:
        w = _load_watcher()
        pending = w.list_pending_recordings()
        lim = max(0, int(limit))
        for i, path in enumerate(pending[:lim]):
            rows.append({"id": f"pending:{i+1}", "ok": True, "detail": str(path)})
        if len(pending) > lim:
            rows.append(
                {"id": "pending_more", "ok": True, "detail": f"+{len(pending) - lim} more pending"}
            )
        if not pending:
            rows.append(
                {
                    "id": "pending",
                    "ok": True,
                    "detail": "no pending recordings (all processed or folder empty)",
                }
            )
    except Exception as exc:
        rows.append({"id": "pending", "ok": False, "detail": _soft(str(exc) or type(exc).__name__)})
    return rows


def _default_processor() -> Callable[[str], Any]:
    """Return a function that runs one recording through bot.process_recording."""
    _ensure_core_path()
    import bot  # noqa: WPS433 — Core/bot.py

    config = bot.load_config()
    brain = bot.load_brain()
    intelligence = bot.ThinkLearnDecideEngine(config)

    def _run(path: str):
        return bot.process_recording(
            path, config, brain, chat_bot=None, intelligence=intelligence
        )

    return _run


def _is_stable(path: Path, wait: float) -> bool:
    try:
        before = path.stat().st_size
        if before == 0:
            return False
        if wait > 0:
            time.sleep(wait)
        return path.stat().st_size == before
    except OSError:
        return False


def _process_one(w, path: Path, processor) -> Dict[str, Any]:
    started = time.time()
    row: Dict[str, Any] = {"recording": str(path), "ok": False, "result": None, "error": ""}
    try:
        res = processor(str(path))
        row["result"] = res if isinstance(res, (str, int, float, type(None))) else str(res)
        row["ok"] = True
        if res == "unreadable":
            row["ok"] = False
            row["error"] = "recording won't open — see bolt error-recovery run"
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
        row["traceback"] = traceback.format_exc(limit=4)
    finally:
        # process_recording marks on exit; make sure even a failed import does.
        try:
            w.mark_processed(path.name)
        except Exception:
            pass
    row["seconds"] = round(time.time() - started, 1)
    return row


def try_run(
    *,
    folder: Optional[str] = None,
    once: bool = False,
    dry_run: bool = False,
    max_items: Optional[int] = None,
    processor: Optional[Callable[[str], Any]] = None,
    stable_wait: Optional[float] = None,
) -> Dict[str, Any]:
    """Watch + clip. ``once`` handles what's pending now and returns.

    Soft-fails (``Watch unavailable: …``) instead of raising.
    """
    out: Dict[str, Any] = {
        "ok": False,
        "error": "",
        "exit_code": 0,
        "folder": "",
        "dry_run": bool(dry_run),
        "once": bool(once),
        "pending": [],
        "skipped_writing": [],
        "processed": [],
    }
    st = status(probe=False)
    if not st.get("engine_present") or not st.get("pipeline_present"):
        out["error"] = st.get("error") or _soft("engine missing")
        return out
    if not dry_run and processor is None and not st.get("ffmpeg_present"):
        out["error"] = _soft(_FFMPEG_HINT)
        return out
    try:
        w = _load_watcher()
    except Exception as exc:
        out["error"] = _soft(str(exc) or type(exc).__name__)
        return out

    target = Path(folder or getattr(w, "RECORDINGS_FOLDER", "") or "")
    if not str(target):
        out["error"] = _soft("RECORDINGS_FOLDER unset — set it in .env or pass --folder")
        return out
    target = target.expanduser()
    out["folder"] = str(target)
    if dry_run:
        if not target.is_dir():
            out["error"] = _soft(f"folder not found: {target}")
            return out
    else:
        try:
            target.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            out["error"] = _soft(f"cannot create folder {target}: {exc}")
            return out

    wait = float(getattr(w, "STABLE_WAIT_SEC", 3.0) if stable_wait is None else stable_wait)
    limit = max_items if (max_items is not None and max_items > 0) else None

    def _pending_now() -> List[Path]:
        # Oldest first, so a backlog is clipped in recording order.
        return list(reversed(w.list_pending_recordings(target)))

    if dry_run:
        pending = _pending_now()
        out["pending"] = [str(p) for p in pending]
        out["ok"] = True
        return out

    if processor is None:
        try:
            processor = _default_processor()
        except Exception as exc:
            out["error"] = _soft(f"clip pipeline failed to load: {exc}")
            out["traceback"] = traceback.format_exc(limit=4)
            return out

    def _cycle() -> bool:
        """One pass. Returns False when --max is reached."""
        for path in _pending_now():
            if limit is not None and len(out["processed"]) >= limit:
                return False
            if not _is_stable(path, wait):
                if str(path) not in out["skipped_writing"]:
                    out["skipped_writing"].append(str(path))
                    print(f"[Watcher] still being written, will retry: {path.name}", flush=True)
                continue
            print(f"[Watcher] New recording: {path.name} → clipping…", flush=True)
            row = _process_one(w, path, processor)
            out["processed"].append(row)
            if row["ok"]:
                print(f"[Watcher] done: {path.name} ({row['seconds']} s, result={row['result']})", flush=True)
            else:
                print(f"[Watcher] failed: {path.name}: {row['error']}", flush=True)
            if str(path) in out["skipped_writing"]:
                out["skipped_writing"].remove(str(path))
        return True

    try:
        if once:
            _cycle()
        else:
            interval = float(getattr(w, "WATCH_INTERVAL", 5) or 5)
            print(
                f"[Watcher] watching {target} — new recordings get clipped "
                f"(every {interval:g} s, Ctrl+C to stop)",
                flush=True,
            )
            while _cycle():
                time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[Watcher] stopped (Ctrl+C)", flush=True)

    out["ok"] = all(r["ok"] for r in out["processed"])
    if not out["ok"]:
        out["error"] = _soft(
            "some recordings failed: "
            + ", ".join(Path(r["recording"]).name for r in out["processed"] if not r["ok"])
        )
    return out


def _print_status(info: Dict[str, Any], as_json: bool) -> int:
    if as_json:
        print(json.dumps(info, indent=2))
        return 0
    ready = "yes" if info.get("ready") else "no"
    print(f"watch readiness: {info.get('readiness')}  ready={ready}")
    print(f"  engine:   {_ENGINE}  present={info.get('engine_present')}")
    print(f"  pipeline: {_BOT}  present={info.get('pipeline_present')}")
    print(f"  ffmpeg:   {info.get('ffmpeg_path') or 'missing'}")
    print(
        f"  folder:   {info.get('recordings_folder')}  exists={info.get('recordings_exists')}"
        f"  videos={info.get('video_count')}  pending={info.get('pending_count')}"
    )
    print(
        f"  processed:{_PROCESSED}  present={info.get('processed_present')} "
        f"count={info.get('processed_count')}"
    )
    if info.get("probe"):
        print(f"  probe_ok: {info.get('probe_ok')}")
    if info.get("error"):
        print(f"  {info['error']}")
    else:
        print(f"  hint: {info.get('hint')}")
    return 0


def _print_run(result: Dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, default=str))
        return
    if result.get("dry_run"):
        pend = result.get("pending") or []
        print(f"[Watcher] dry run — {len(pend)} recording(s) would be clipped from {result.get('folder')}")
        for p in pend:
            print(f"  {p}")
        return
    done = result.get("processed") or []
    ok = sum(1 for r in done if r["ok"])
    print(f"[Watcher] clipped {ok}/{len(done)} recording(s) from {result.get('folder')}")
    if not done and not result.get("skipped_writing"):
        print("  nothing pending — drop a recording in the folder (or reprocess: bolt recordings latest --force)")
    for p in result.get("skipped_writing") or []:
        print(f"  still being written (next run): {p}")
    if ok:
        print("  clips → media/clips · verticals → media/vertical_clips · queue → bolt queue")
    if result.get("error"):
        print(f"  {result['error']}")


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="bolt watch",
        description="Watch the recordings folder and clip new recordings.",
    )
    parser.add_argument(
        "action", nargs="?", default="status", choices=["status", "list", "run"],
        help="status (default) | list | run",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--probe", action="store_true", help="status: also load the engine")
    parser.add_argument("--limit", type=int, default=20, help="list: max pending paths (default 20)")
    parser.add_argument("--folder", default=None, help="run: watch this folder instead of RECORDINGS_FOLDER")
    parser.add_argument("--once", action="store_true", help="run: clip what's pending now, then exit")
    parser.add_argument("--max", dest="max_items", type=int, default=None, help="run: stop after N recordings")
    parser.add_argument(
        "--dry-run", "--list-only", dest="dry_run", action="store_true",
        help="run: show what would be clipped; changes nothing",
    )
    args = parser.parse_args(argv)

    if args.action == "status":
        return _print_status(status(probe=args.probe), args.json)

    if args.action == "list":
        rows = list_items(limit=args.limit)
        if args.json:
            print(json.dumps({"items": rows}, indent=2))
        else:
            for r in rows:
                mark = "OK" if r["ok"] else "NO"
                print(f"[{mark}] {r['id']}: {r['detail']}")
        return 0

    result = try_run(
        folder=args.folder, once=args.once, dry_run=args.dry_run, max_items=args.max_items
    )
    if result.get("error") and not result.get("processed") and not result.get("dry_run"):
        print(json.dumps(result, indent=2, default=str) if args.json else result["error"])
        return 0
    _print_run(result, args.json)
    return int(result.get("exit_code") or 0)


if __name__ == "__main__":
    sys.exit(main())
