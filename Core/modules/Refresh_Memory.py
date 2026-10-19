#!/usr/bin/env python3
"""
Refresh_Memory.py — memory index rebuild CLI (READY, 18 Oct 2026)
==================================================================
Soft-fail wrapper around ``scripts/refresh_memory_index.py`` /
``modules.Memory_Index.refresh_memory_index`` (writes
``Data/memory_index.json``). Soft-fail prefix: ``Memory refresh unavailable:``.

CLI (via ``bolt refresh-memory`` / ``bolt refresh_memory``):
  status [--json] [--probe]
  list   [--json]
  run    [--dry-run] [--if-stale]   # rebuild index (or count / skip when fresh)

READY: local only, no keys/models. ``status`` shows whether the index is
stale vs the newest memory source (same check ``bolt memsearch`` uses);
``run`` rebuilds atomically, re-reads the written file to verify it, and
reports before/after entry counts + time. A source-less repo still writes a
valid empty index. **Distinct from READY briefing retrieve** via
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


def _freshness(idx: Dict[str, Any]) -> Dict[str, Any]:
    """Same stale check as READY ``bolt memsearch``. Never raises."""
    try:
        _ensure_core_path()
        from modules import Memory_Search as ms  # noqa: WPS433

        return ms._freshness(dict(idx))
    except Exception as exc:  # pragma: no cover - defensive
        return {
            "stale": None,
            "reason": f"freshness unknown ({type(exc).__name__})",
            "newest_source": "",
            "newest_source_at": "",
        }


def _verify_index(path: Path, expected: int) -> Optional[str]:
    """Re-read the written index. Returns an error string, or None when OK."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"index written but unreadable ({type(exc).__name__}: {exc})"
    if not isinstance(raw, dict):
        return "index written but is not a JSON object"
    entries = raw.get("entries")
    if not isinstance(entries, list):
        return "index written without an entries list"
    if len(entries) != expected or int(raw.get("entry_count") or 0) != expected:
        return (
            f"index entry count mismatch (wrote {expected}, file has "
            f"{len(entries)} / entry_count={raw.get('entry_count')})"
        )
    return None


def status(*, probe: bool = False) -> Dict[str, Any]:
    idx = _index_meta()
    fresh = _freshness(idx)
    sources = _source_flags()
    any_source = any(sources.values())
    info: Dict[str, Any] = {
        "checked_at": _iso(),
        "ready": False,
        "partial": False,
        "readiness": "READY",
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
        "index_stale": fresh.get("stale"),
        "index_stale_reason": fresh.get("reason"),
        "newest_source": fresh.get("newest_source"),
        "newest_source_at": fresh.get("newest_source_at"),
        "sources": sources,
        "any_source": any_source,
        "probe": bool(probe),
        "probe_ok": None,
        "error": "",
        "hint": (
            "bolt refresh-memory run rebuilds Data/memory_index.json "
            "(--if-stale skips when up to date; bolt memsearch also rebuilds "
            "a stale index itself) · distinct from READY briefing retrieve"
        ),
        "is_stranger_ready": True,
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
            "rebuild still runs (writes a valid empty index)"
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
        {
            "id": "fresh",
            "ok": st.get("index_stale") is False,
            "detail": (
                f"stale={st.get('index_stale')} ({st.get('index_stale_reason')}); "
                f"newest source {st.get('newest_source_at') or '-'}"
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
                f"prefix {_SOFT!r}; READY; distinct from READY "
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
        "skipped": False,
        "before_count": None,
        "elapsed_s": None,
    }
    st = status(probe=False)
    if not st.get("ready") and st.get("error"):
        out["error"] = st["error"]
        return out

    argv = list(argv or [])
    dry = "--dry-run" in argv or "-n" in argv
    if_stale = "--if-stale" in argv
    out["dry_run"] = dry
    out["before_count"] = st.get("index_entry_count") if st.get("index_present") else None

    if if_stale and not dry and st.get("index_stale") is False:
        out["ok"] = True
        out["skipped"] = True
        out["entry_count"] = st.get("index_entry_count")
        out["report"] = (
            f"Index already up to date ({st.get('index_entry_count')} entries, "
            f"generated {st.get('index_generated_at') or '-'}) -> {_INDEX}\n"
            "  (drop --if-stale to rebuild anyway)\n"
        )
        return out

    import time as _time

    t0 = _time.monotonic()
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
        out["elapsed_s"] = round(_time.monotonic() - t0, 2)
        problem = _verify_index(_INDEX, count)
        if problem:
            out["error"] = _soft(problem)
            return out
        out["ok"] = True
        before = out["before_count"]
        was = f" (was {before})" if before is not None else " (new index)"
        out["report"] = (
            f"Indexed {count} memory entries{was} in {out['elapsed_s']} s -> {_INDEX}\n"
        )
        if count == 0:
            out["report"] += (
                "  note: no memory sources found yet (Data/memory, Data/content, "
                "Data/MEMORY.md, unified_memory, clip_history, outcomes) — "
                "wrote a valid empty index\n"
            )
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
        print(
            f"  fresh:   stale={info.get('index_stale')} "
            f"({info.get('index_stale_reason')})"
            + (
                f"  newest source {info.get('newest_source_at')}"
                if info.get("newest_source_at")
                else ""
            )
        )
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
        description=(
            "Rebuild Bolt's local memory index Data/memory_index.json "
            "(READY; local, no keys)."
        ),
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
    parser.add_argument(
        "--if-stale",
        action="store_true",
        help="run only: skip the rebuild when the index is already up to date",
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
        if args.if_stale and "--if-stale" not in engine_argv:
            engine_argv.append("--if-stale")
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
                        "skipped": result.get("skipped"),
                        "before_count": result.get("before_count"),
                        "elapsed_s": result.get("elapsed_s"),
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
