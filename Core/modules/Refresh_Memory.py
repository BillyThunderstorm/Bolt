#!/usr/bin/env python3
"""
Refresh_Memory.py — soft-fail CLI for memory index rebuild (PARTIAL)
===================================================================
Soft-fail wrapper around ``scripts/refresh_memory_index.py`` /
``modules.Memory_Index.refresh_memory_index`` (writes
``Data/memory_index.json``). Soft-fail prefix: ``Memory refresh unavailable:``.

CLI (via ``bolt refresh-memory`` / ``bolt refresh_memory``):
  status [--json] [--probe]
  list   [--json]
  run    [--dry-run]   # rebuild index (or report counts without write)

Stay PARTIAL — rebuild is local/data-gated and not a stranger-ready product
surface by itself. **Distinct from READY briefing retrieve** via
``Memory_Index.retrieve_memory`` (used in-process by briefings). Former thin
SCRIPT_MAP ``refresh_memory`` → ``scripts/refresh_memory_index.py`` (no
soft-fail status/list/run).
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

_SOFT = "Memory refresh unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_CORE = _REPO / "Core"
_ENGINE = _REPO / "scripts" / "refresh_memory_index.py"
_PATHS = _REPO / "scripts" / "_paths.py"
_MEMORY_MOD = _REPO / "Core" / "modules" / "Memory_Index.py"
_INDEX = _REPO / "Data" / "memory_index.json"
_MEMORY_DIR = _REPO / "Data" / "memory"
_CONTENT_DIR = _REPO / "Data" / "content"
_HOT = _REPO / "Data" / "MEMORY.md"
_UNIFIED = _REPO / "Data" / "unified_memory.jsonl"
_HISTORY = _REPO / "Data" / "clip_history.json"
_DECISIONS = _REPO / "logs" / "decision_audit.log"
_OUTCOMES = _REPO / "Data" / "performance_outcomes.jsonl"


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


def _load_memory_mod():
    _ensure_core_path()
    if not _MEMORY_MOD.is_file():
        raise FileNotFoundError(f"missing {_MEMORY_MOD}")
    from modules import Memory_Index as mi  # noqa: WPS433

    return mi


def _index_meta() -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "present": _INDEX.is_file(),
        "entry_count": 0,
        "generated_at": "",
        "version": None,
        "size_bytes": 0,
    }
    if not meta["present"]:
        return meta
    try:
        meta["size_bytes"] = int(_INDEX.stat().st_size)
        raw = json.loads(_INDEX.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            meta["entry_count"] = int(raw.get("entry_count") or len(raw.get("entries") or []))
            meta["generated_at"] = str(raw.get("generated_at") or "")
            meta["version"] = raw.get("version")
    except Exception:
        pass
    return meta


def _source_flags() -> Dict[str, bool]:
    return {
        "memory_dir": _MEMORY_DIR.is_dir(),
        "content_dir": _CONTENT_DIR.is_dir(),
        "hot_cache": _HOT.is_file(),
        "unified_memory": _UNIFIED.is_file(),
        "clip_history": _HISTORY.is_file(),
        "decision_audit": _DECISIONS.is_file(),
        "performance_outcomes": _OUTCOMES.is_file(),
    }


def status(*, probe: bool = False) -> Dict[str, Any]:
    idx = _index_meta()
    sources = _source_flags()
    any_source = any(sources.values())
    info: Dict[str, Any] = {
        "checked_at": _iso(),
        "ready": False,
        "partial": True,
        "readiness": "PARTIAL",
        "soft_fail_prefix": _SOFT,
        "cli": "bolt refresh-memory",
        "engine": str(_ENGINE),
        "engine_present": _ENGINE.is_file(),
        "paths_helper": str(_PATHS),
        "paths_present": _PATHS.is_file(),
        "memory_module": str(_MEMORY_MOD),
        "memory_module_present": _MEMORY_MOD.is_file(),
        "index_path": str(_INDEX),
        "index_present": idx["present"],
        "index_entry_count": idx["entry_count"],
        "index_generated_at": idx["generated_at"],
        "index_version": idx["version"],
        "index_size_bytes": idx["size_bytes"],
        "sources": sources,
        "any_source": any_source,
        "probe": bool(probe),
        "probe_ok": None,
        "error": "",
        "hint": (
            "rebuild Data/memory_index.json · distinct from READY briefing "
            "retrieve (Memory_Index.retrieve_memory) · stay PARTIAL"
        ),
        "is_stranger_ready": False,
    }
    missing = []
    if not info["engine_present"]:
        missing.append("scripts/refresh_memory_index.py")
    if not info["paths_present"]:
        missing.append("scripts/_paths.py")
    if not info["memory_module_present"]:
        missing.append("Core/modules/Memory_Index.py")
    if missing:
        info["error"] = _soft("missing " + ", ".join(missing))
        return info

    if not any_source:
        info["hint"] = _soft(
            "no memory sources yet under Data/memory|content|MEMORY.md / "
            "unified_memory / clip_history / decision_audit / outcomes — "
            "rebuild still runs (may write empty index)"
        )

    info["ready"] = True
    if probe:
        try:
            mi = _load_memory_mod()
            info["probe_ok"] = True
            info["has_refresh"] = callable(getattr(mi, "refresh_memory_index", None))
            info["has_retrieve"] = callable(getattr(mi, "retrieve_memory", None))
            info["memory_index_file"] = str(
                getattr(mi, "MEMORY_INDEX_FILE", _INDEX)
            )
            if not info["has_refresh"]:
                info["probe_ok"] = False
                info["ready"] = False
                info["error"] = _soft("Memory_Index.refresh_memory_index missing")
        except Exception as exc:
            info["probe_ok"] = False
            info["ready"] = False
            info["error"] = _soft(str(exc) or type(exc).__name__)
    return info


def list_items() -> List[Dict[str, Any]]:
    st = status(probe=False)
    sources = st.get("sources") or {}
    rows: List[Dict[str, Any]] = [
        {"id": "engine", "ok": st["engine_present"], "detail": st["engine"]},
        {"id": "paths", "ok": st["paths_present"], "detail": st["paths_helper"]},
        {
            "id": "memory_module",
            "ok": st["memory_module_present"],
            "detail": st["memory_module"],
        },
        {
            "id": "index",
            "ok": True,
            "detail": (
                f"{st['index_path']} present={st['index_present']} "
                f"entries={st['index_entry_count']} "
                f"generated_at={st.get('index_generated_at') or '-'}"
            ),
        },
    ]
    for key, ok in sources.items():
        rows.append({"id": f"source:{key}", "ok": bool(ok), "detail": key})
    rows.append(
        {
            "id": "soft_fail",
            "ok": True,
            "detail": (
                f"prefix {_SOFT!r}; stay PARTIAL; distinct from READY "
                "briefing retrieve"
            ),
        }
    )
    return rows


def try_run(argv: Optional[List[str]] = None) -> Dict[str, Any]:
    """Rebuild the index (or dry-run counts). Soft-fails instead of raising."""
    out: Dict[str, Any] = {
        "ok": False,
        "error": "",
        "exit_code": 0,
        "report": "",
        "entry_count": None,
        "index_path": str(_INDEX),
        "dry_run": False,
    }
    st = status(probe=False)
    if not st.get("ready") and st.get("error"):
        out["error"] = st["error"]
        return out

    argv = list(argv or [])
    dry = "--dry-run" in argv or "-n" in argv
    out["dry_run"] = dry

    try:
        mi = _load_memory_mod()
        if dry:
            entries = mi.build_memory_entries(_REPO)
            count = len(entries)
            out["entry_count"] = count
            out["ok"] = True
            out["report"] = (
                f"[dry-run] would index {count} memory entries -> {_INDEX}\n"
            )
            return out

        payload = mi.refresh_memory_index(project_root=_REPO, out_file=_INDEX)
        count = int(payload.get("entry_count") or 0)
        out["entry_count"] = count
        out["ok"] = True
        out["report"] = f"Indexed {count} memory entries -> {_INDEX}\n"
        return out
    except Exception as exc:
        out["ok"] = False
        out["error"] = _soft(str(exc) or type(exc).__name__)
        out["report"] = traceback.format_exc()
        out["exit_code"] = 0  # soft-fail
        return out


def _print_status(info: Dict[str, Any], as_json: bool) -> int:
    if as_json:
        print(json.dumps(info, indent=2))
    else:
        ready = "yes" if info.get("ready") else "no"
        print(f"refresh-memory readiness: {info.get('readiness')}  ready={ready}")
        print(f"  engine:  {_ENGINE}  present={info.get('engine_present')}")
        print(f"  module:  {_MEMORY_MOD}  present={info.get('memory_module_present')}")
        print(
            f"  index:   {_INDEX}  present={info.get('index_present')} "
            f"entries={info.get('index_entry_count')}"
        )
        if info.get("index_generated_at"):
            print(f"  generated_at: {info.get('index_generated_at')}")
        src = info.get("sources") or {}
        on = [k for k, v in src.items() if v]
        print(f"  sources: {', '.join(on) if on else '(none yet)'}")
        if info.get("probe"):
            print(f"  probe_ok: {info.get('probe_ok')}")
        if info.get("error"):
            print(f"  {info['error']}")
        else:
            print(f"  hint: {info.get('hint')}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Back-compat: bare flags → run
    if argv and argv[0] not in ("status", "list", "run", "-h", "--help"):
        if argv[0].startswith("-"):
            argv = ["run"] + argv

    parser = argparse.ArgumentParser(
        prog="bolt refresh-memory",
        description="Rebuild clip/memory index (PARTIAL; soft-fail).",
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
        help="status only: import Memory_Index and verify refresh API",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="run only: count entries without writing index",
    )
    args, rest = parser.parse_known_args(argv)

    if args.action == "status":
        return _print_status(status(probe=args.probe), args.json)

    if args.action == "list":
        rows = list_items()
        if args.json:
            print(json.dumps({"items": rows}, indent=2))
        else:
            for r in rows:
                mark = "OK" if r["ok"] else "NO"
                print(f"[{mark}] {r['id']}: {r['detail']}")
        return 0

    if args.action == "run":
        engine_argv = list(rest)
        if args.dry_run and "--dry-run" not in engine_argv and "-n" not in engine_argv:
            engine_argv.append("--dry-run")
        result = try_run(engine_argv)
        if result.get("error") and not result.get("ok"):
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(result["error"])
            return 0
        if args.json:
            print(
                json.dumps(
                    {
                        "ok": result.get("ok"),
                        "exit_code": result.get("exit_code"),
                        "entry_count": result.get("entry_count"),
                        "dry_run": result.get("dry_run"),
                        "index_path": result.get("index_path"),
                        "report": result.get("report"),
                    },
                    indent=2,
                )
            )
        else:
            sys.stdout.write(result.get("report") or "")
        return int(result.get("exit_code") or 0)

    print(_soft(f"unknown action {args.action!r}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
