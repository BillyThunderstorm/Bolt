#!/usr/bin/env python3
"""
Folder_Watch.py — soft-fail CLI for Core/modules/Watcher.py (PARTIAL)
=====================================================================
Folder-watch readiness + pending list + soft-fail run loop around the
canonical Watcher (processed log, newest-pending, mark-after-yield).
Soft-fail prefix: ``Watch unavailable:``.

CLI (via ``bolt watch``):
  status [--json] [--probe]
  list   [--json] [--limit N]
  run    [--folder PATH] [--once]   # long watch; --once yields pending once

Stay PARTIAL — long-running / media-gated; not stranger-ready as a product
surface. Prefer READY ``bolt launch`` for live mode and ``bolt recordings``
for one-shot process. Distinct from READY pipeline Watcher import used by
bot/launch (this is the soft-fail CLI wrapper over the same engine).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SOFT = "Watch unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_CORE = _REPO / "Core"
_ENGINE = _REPO / "Core" / "modules" / "Watcher.py"
_SCRIPT_SHIM = _REPO / "scripts" / "Watcher.py"
_PATHS = _REPO / "scripts" / "_paths.py"
_PROCESSED = _REPO / "Data" / "processed_recordings.json"


def _soft(msg: str) -> str:
    if msg.startswith(_SOFT):
        return msg
    return f"{_SOFT} {msg}"


def _iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_core_path() -> None:
    if str(_CORE) not in sys.path:
        sys.path.insert(0, str(_CORE))
    scripts = str(_REPO / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)


def _load_watcher():
    _ensure_core_path()
    if not _ENGINE.is_file():
        raise FileNotFoundError(f"missing engine {_ENGINE}")
    from modules import Watcher as w  # noqa: WPS433

    return w


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
        "partial": True,
        "readiness": "PARTIAL",
        "soft_fail_prefix": _SOFT,
        "cli": "bolt watch",
        "engine": str(_ENGINE),
        "engine_present": _ENGINE.is_file(),
        "script_shim": str(_SCRIPT_SHIM),
        "shim_present": _SCRIPT_SHIM.is_file(),
        "paths_helper": str(_PATHS),
        "paths_present": _PATHS.is_file(),
        "processed_log": str(_PROCESSED),
        "processed_present": _PROCESSED.is_file(),
        "processed_count": _processed_count(),
        "recordings_folder": "",
        "recordings_exists": False,
        "pending_count": None,
        "watch_interval": None,
        "probe": bool(probe),
        "probe_ok": None,
        "error": "",
        "hint": (
            "folder watch CLI · prefer bolt launch for live mode · "
            "bolt recordings for one-shot · bare bolt watch = status; "
            "bolt watch run starts the loop"
        ),
        "is_stranger_ready": False,
    }
    missing = []
    if not info["engine_present"]:
        missing.append("Core/modules/Watcher.py")
    if not info["paths_present"]:
        missing.append("scripts/_paths.py")
    if missing:
        info["error"] = _soft("missing " + ", ".join(missing))
        return info

    try:
        w = _load_watcher()
        folder = Path(getattr(w, "RECORDINGS_FOLDER", "") or "")
        info["recordings_folder"] = str(folder)
        info["recordings_exists"] = folder.is_dir() if folder else False
        info["watch_interval"] = getattr(w, "WATCH_INTERVAL", None)
        # ready when engine + paths load; folder may be creatable on run
        info["ready"] = True
        if probe:
            pending = w.list_pending_recordings()
            info["pending_count"] = len(pending)
            info["probe_ok"] = True
            if not info["recordings_exists"]:
                # informational — run can mkdir; do not clear ready
                info["hint"] = _soft(
                    f"recordings folder missing (will create on run): {folder}"
                )
    except Exception as exc:
        info["ready"] = False
        info["error"] = _soft(str(exc) or type(exc).__name__)
        if probe:
            info["probe_ok"] = False
    return info


def list_items(*, limit: int = 20) -> List[Dict[str, Any]]:
    st = status(probe=False)
    rows: List[Dict[str, Any]] = [
        {"id": "engine", "ok": st["engine_present"], "detail": st["engine"]},
        {"id": "paths", "ok": st["paths_present"], "detail": st["paths_helper"]},
        {
            "id": "shim",
            "ok": st["shim_present"],
            "detail": st["script_shim"] + " (thin SCRIPT_MAP leftover OK)",
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
                f"exists={st.get('recordings_exists')}"
            ),
        },
        {
            "id": "soft_fail",
            "ok": True,
            "detail": f"prefix {_SOFT!r}; stay PARTIAL; prefer bolt launch",
        },
        {
            "id": "distinct",
            "ok": True,
            "detail": "distinct from READY bolt launch / bolt recordings",
        },
    ]
    try:
        w = _load_watcher()
        pending = w.list_pending_recordings()
        lim = max(0, int(limit))
        for i, path in enumerate(pending[:lim]):
            rows.append(
                {
                    "id": f"pending:{i+1}",
                    "ok": True,
                    "detail": str(path),
                }
            )
        if len(pending) > lim:
            rows.append(
                {
                    "id": "pending_more",
                    "ok": True,
                    "detail": f"+{len(pending) - lim} more pending",
                }
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
        rows.append(
            {
                "id": "pending",
                "ok": False,
                "detail": _soft(str(exc) or type(exc).__name__),
            }
        )
    return rows


def try_run(
    *,
    folder: Optional[str] = None,
    once: bool = False,
) -> Dict[str, Any]:
    """Start folder watch (or list pending once). Soft-fails instead of raising."""
    out: Dict[str, Any] = {
        "ok": False,
        "error": "",
        "exit_code": 0,
        "report": "",
        "yielded": [],
    }
    st = status(probe=False)
    if not st.get("ready"):
        out["error"] = st.get("error") or _soft("not ready")
        return out
    try:
        w = _load_watcher()
        target = folder or getattr(w, "RECORDINGS_FOLDER", None)
        if not target:
            out["error"] = _soft("RECORDINGS_FOLDER unset")
            return out
        target_path = Path(target)
        try:
            target_path.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            out["error"] = _soft(f"cannot create folder {target_path}: {exc}")
            return out

        if once:
            pending = w.list_pending_recordings(target_path)
            lines = [str(p) for p in pending]
            out["yielded"] = lines
            out["ok"] = True
            out["report"] = (
                f"[Watcher] pending={len(lines)} folder={target_path}\n"
                + ("\n".join(lines) + ("\n" if lines else ""))
            )
            return out

        # Long-running loop — print paths as Watcher yields (legacy bolt watch).
        out["ok"] = True
        out["report"] = f"[Watcher] starting watch on {target_path} (Ctrl+C to stop)\n"
        sys.stdout.write(out["report"])
        sys.stdout.flush()
        try:
            for path in w.watch_folder(str(target_path)):
                print(path)
                out["yielded"].append(str(path))
        except KeyboardInterrupt:
            msg = "\n[Watcher] stopped (KeyboardInterrupt)\n"
            sys.stdout.write(msg)
            out["report"] += msg
            out["ok"] = True
        return out
    except Exception as exc:
        out["ok"] = False
        out["error"] = _soft(str(exc) or type(exc).__name__)
        out["traceback"] = traceback.format_exc(limit=3)
        out["exit_code"] = 0
        return out


def _print_status(info: Dict[str, Any], as_json: bool) -> int:
    if as_json:
        print(json.dumps(info, indent=2))
    else:
        ready = "yes" if info.get("ready") else "no"
        print(f"watch readiness: {info.get('readiness')}  ready={ready}")
        print(f"  engine:   {_ENGINE}  present={info.get('engine_present')}")
        print(
            f"  folder:   {info.get('recordings_folder')}  "
            f"exists={info.get('recordings_exists')}"
        )
        print(
            f"  processed:{_PROCESSED}  present={info.get('processed_present')} "
            f"count={info.get('processed_count')}"
        )
        if info.get("probe"):
            print(
                f"  probe_ok: {info.get('probe_ok')}  "
                f"pending={info.get('pending_count')}"
            )
        if info.get("error"):
            print(f"  {info['error']}")
        else:
            print(f"  hint: {info.get('hint')}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="bolt watch",
        description="Folder watch readiness / pending list / run (PARTIAL; soft-fail).",
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["status", "list", "run"],
        help="status (default) | list | run",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="status only: count pending recordings",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="list: max pending paths to show (default 20)",
    )
    parser.add_argument(
        "--folder",
        default=None,
        help="run: override RECORDINGS_FOLDER",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="run: print pending once (no infinite loop)",
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

    if args.action == "run":
        result = try_run(folder=args.folder, once=args.once)
        if result.get("error") and not result.get("ok"):
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(result["error"])
            return 0
        if args.json:
            # Avoid dumping infinite yielded history; summarize
            print(
                json.dumps(
                    {
                        "ok": result.get("ok"),
                        "error": result.get("error"),
                        "yielded_count": len(result.get("yielded") or []),
                        "yielded": (result.get("yielded") or [])[:50],
                        "once": bool(args.once),
                    },
                    indent=2,
                )
            )
        elif args.once:
            sys.stdout.write(result.get("report") or "")
        # long run already printed live
        return int(result.get("exit_code") or 0)

    print(_soft(f"unknown action {args.action!r}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
