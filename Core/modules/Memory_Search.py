#!/usr/bin/env python3
"""
Memory_Search.py — soft-fail CLI for Phase 4 semantic search over memory (PARTIAL)
=================================================================================
Wraps ``Memory_Index.retrieve_memory`` / ``format_retrieved_context`` (hybrid
vector+keyword over ``Data/memory_index.json``). Soft-fail prefix:
``Memory search unavailable:``.

CLI (via ``bolt memsearch``):
  status [--json] [--probe]
  list   [--json]
  run|search|query <words…> [--limit N] [--refresh] [--dry-run] [--json]

Aliases: ``memsearch``, ``memory-search``, ``mem-search``, ``search-memory``,
``memory_search``, ``memsearch-status``.

Stay PARTIAL — index/data gated; not stranger-ready as a full Phase 4 product.
``is_stranger_ready=False``.

**Distinct from:**
  - READY ``bolt search`` (``Bolt_Search`` — live web / DuckDuckGo)
  - PARTIAL ``bolt memory`` (``Bolt_Memory`` — LLM recall / remember)
  - PARTIAL ``bolt refresh-memory`` (index rebuild only)

Owns the Phase 4 memory-search IDEA formerly mis-labeled on ``Bolt_Search.py``
in Docs/AI_Guide.md (filename was reused for READY web search).
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SOFT = "Memory search unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_CORE = _REPO / "Core"
_MEMORY_MOD = _REPO / "Core" / "modules" / "Memory_Index.py"
_INDEX = _REPO / "Data" / "memory_index.json"


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
            meta["entry_count"] = int(
                raw.get("entry_count") or len(raw.get("entries") or [])
            )
            meta["generated_at"] = str(raw.get("generated_at") or "")
            meta["version"] = raw.get("version")
    except Exception:
        pass
    return meta


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Never raises. readiness PARTIAL; report index + Memory_Index retrieve API."""
    idx = _index_meta()
    info: Dict[str, Any] = {
        "checked_at": _iso(),
        "ready": False,
        "partial": True,
        "readiness": "PARTIAL",
        "soft_fail_prefix": _SOFT,
        "cli": "bolt memsearch",
        "module": str(Path(__file__).resolve()),
        "module_present": Path(__file__).is_file(),
        "memory_module": str(_MEMORY_MOD),
        "memory_module_present": _MEMORY_MOD.is_file(),
        "index_path": str(_INDEX),
        "index_present": idx["present"],
        "index_entry_count": idx["entry_count"],
        "index_generated_at": idx["generated_at"],
        "index_version": idx["version"],
        "index_size_bytes": idx["size_bytes"],
        "memory_index_import_ok": False,
        "retrieve_api_ok": False,
        "format_api_ok": False,
        "api_note": "",
        "probe": bool(probe),
        "probe_ok": None,
        "error": "",
        "hint": (
            "Phase 4 semantic search over Data/memory_index.json · distinct from "
            "READY bolt search (web) + PARTIAL bolt memory (LLM) + PARTIAL "
            "bolt refresh-memory (rebuild) · stay PARTIAL"
        ),
        "is_stranger_ready": False,
        "missing": [],
    }
    missing: List[str] = []
    if not info["module_present"]:
        missing.append("Core/modules/Memory_Search.py")
    if not info["memory_module_present"]:
        missing.append("Core/modules/Memory_Index.py")

    if missing:
        info["missing"] = missing
        info["error"] = _soft("missing " + ", ".join(missing))
        return info

    try:
        mi = _load_memory_mod()
        info["memory_index_import_ok"] = True
        retrieve_ok = callable(getattr(mi, "retrieve_memory", None))
        format_ok = callable(getattr(mi, "format_retrieved_context", None))
        info["retrieve_api_ok"] = retrieve_ok
        info["format_api_ok"] = format_ok
        if retrieve_ok and format_ok:
            info["api_note"] = "retrieve_memory + format_retrieved_context importable"
        else:
            bits = []
            if not retrieve_ok:
                bits.append("retrieve_memory missing")
            if not format_ok:
                bits.append("format_retrieved_context missing")
            info["api_note"] = "; ".join(bits)
            missing.append(info["api_note"])
    except Exception as exc:
        info["memory_index_import_ok"] = False
        info["api_note"] = str(exc) or type(exc).__name__
        missing.append(f"Memory_Index import failed: {info['api_note']}")
        info["error"] = _soft(info["api_note"])
        info["missing"] = missing
        return info

    if not idx["present"]:
        missing.append(
            "Data/memory_index.json missing (run bolt refresh-memory run)"
        )
        info["hint"] = _soft(
            "index missing — bolt refresh-memory run then bolt memsearch run \"…\""
        )

    # Ready for PARTIAL use when engine importable + retrieve API present.
    # Index may be empty/absent (retrieve can auto_refresh) — still PARTIAL.
    info["ready"] = bool(
        info["memory_index_import_ok"]
        and info["retrieve_api_ok"]
        and info["format_api_ok"]
    )
    info["missing"] = missing
    if not info["ready"] and not info["error"]:
        info["error"] = _soft(info["api_note"] or "retrieve API not ready")

    if probe:
        try:
            hits = mi.retrieve_memory("bolt", limit=1, auto_refresh=False)
            ctx = mi.format_retrieved_context(hits if isinstance(hits, list) else [])
            info["probe_ok"] = isinstance(hits, list) and isinstance(ctx, str)
            info["probe_hit_count"] = len(hits) if isinstance(hits, list) else 0
            if not info["probe_ok"]:
                info["error"] = _soft("probe retrieve/format returned unexpected types")
        except Exception as exc:
            info["probe_ok"] = False
            info["error"] = _soft(str(exc) or type(exc).__name__)
    return info


def list_items() -> List[Dict[str, Any]]:
    st = status(probe=False)
    rows: List[Dict[str, Any]] = [
        {
            "id": "module",
            "ok": bool(st.get("module_present")),
            "detail": st.get("module") or str(Path(__file__).resolve()),
        },
        {
            "id": "memory_index_import",
            "ok": bool(st.get("memory_index_import_ok")),
            "detail": st.get("api_note") or st.get("memory_module") or "",
        },
        {
            "id": "index_file",
            "ok": bool(st.get("index_present")),
            "detail": (
                f"{st.get('index_path')} present={st.get('index_present')} "
                f"size={st.get('index_size_bytes')}"
            ),
        },
        {
            "id": "entry_count",
            "ok": True,
            "detail": (
                f"entries={st.get('index_entry_count')} "
                f"generated_at={st.get('index_generated_at') or '-'}"
            ),
        },
        {
            "id": "retrieve_api",
            "ok": bool(st.get("retrieve_api_ok")) and bool(st.get("format_api_ok")),
            "detail": (
                f"retrieve={st.get('retrieve_api_ok')} "
                f"format={st.get('format_api_ok')} ({st.get('api_note')})"
            ),
        },
        {
            "id": "soft_fail",
            "ok": True,
            "detail": (
                f"prefix {_SOFT!r}; stay PARTIAL; distinct from READY bolt search "
                "(web) + PARTIAL bolt memory (LLM) + PARTIAL bolt refresh-memory"
            ),
        },
    ]
    return rows


def try_run(
    query: str = "",
    *,
    limit: int = 5,
    refresh: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Call retrieve_memory + format_retrieved_context. Never raises."""
    out: Dict[str, Any] = {
        "ok": False,
        "error": "",
        "query": (query or "").strip(),
        "limit": int(limit) if limit else 5,
        "refresh": bool(refresh),
        "dry_run": bool(dry_run),
        "hit_count": 0,
        "hits": [],
        "context": "",
        "index_path": str(_INDEX),
        "refreshed": False,
        "refresh_entry_count": None,
    }
    q = out["query"]
    if not q:
        out["error"] = _soft("empty query — pass words after run/search/query")
        return out

    try:
        mi = _load_memory_mod()
    except Exception as exc:
        out["error"] = _soft(str(exc) or type(exc).__name__)
        return out

    try:
        if refresh:
            payload = mi.refresh_memory_index(project_root=_REPO, out_file=_INDEX)
            out["refreshed"] = True
            out["refresh_entry_count"] = int(payload.get("entry_count") or 0)

        hits = mi.retrieve_memory(q, limit=out["limit"], auto_refresh=not refresh)
        if not isinstance(hits, list):
            out["error"] = _soft("retrieve_memory returned non-list")
            return out

        out["hit_count"] = len(hits)
        # Slim hit rows for JSON (no huge text blobs unless needed)
        slim: List[Dict[str, Any]] = []
        for h in hits:
            slim.append(
                {
                    "title": h.get("title"),
                    "source": h.get("source"),
                    "kind": h.get("kind"),
                    "score": h.get("score"),
                    "summary": (h.get("summary") or "")[:240],
                }
            )
        out["hits"] = slim

        if dry_run:
            out["ok"] = True
            out["context"] = ""
            out["hint"] = (
                f"dry-run: {out['hit_count']} hit(s) for {q!r} "
                f"(skipped format_retrieved_context print)"
            )
            return out

        ctx = mi.format_retrieved_context(hits)
        out["context"] = ctx if isinstance(ctx, str) else str(ctx)
        out["ok"] = True
        return out
    except Exception as exc:
        out["ok"] = False
        out["error"] = _soft(str(exc) or type(exc).__name__)
        out["traceback"] = traceback.format_exc()
        return out


def _print_status(info: Dict[str, Any], as_json: bool) -> int:
    if as_json:
        print(json.dumps(info, indent=2))
    else:
        ready = "yes" if info.get("ready") else "no"
        print(f"memsearch readiness: {info.get('readiness')}  ready={ready}")
        print(f"  module: present={info.get('module_present')}")
        print(
            f"  Memory_Index: present={info.get('memory_module_present')}  "
            f"import_ok={info.get('memory_index_import_ok')}"
        )
        print(
            f"  index:   {_INDEX}  present={info.get('index_present')} "
            f"entries={info.get('index_entry_count')}"
        )
        if info.get("index_generated_at"):
            print(f"  generated_at: {info.get('index_generated_at')}")
        print(
            f"  API: retrieve={info.get('retrieve_api_ok')}  "
            f"format={info.get('format_api_ok')}  ({info.get('api_note')})"
        )
        print(f"  stranger_ready: {info.get('is_stranger_ready')}")
        if info.get("probe"):
            print(
                f"  probe_ok: {info.get('probe_ok')}  "
                f"hits={info.get('probe_hit_count')}"
            )
        if info.get("error"):
            print(f"  {info['error']}")
        else:
            print(f"  hint: {info.get('hint')}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Bare flags without action → status (except query-like bare words → run)
    if argv and argv[0] not in (
        "status",
        "list",
        "run",
        "search",
        "query",
        "-h",
        "--help",
    ):
        if argv[0].startswith("-"):
            argv = ["status"] + argv
        else:
            # Convenience: bolt memsearch "pop culture" → run
            argv = ["run"] + argv

    parser = argparse.ArgumentParser(
        prog="bolt memsearch",
        description=(
            "Phase 4 semantic search over memory index (PARTIAL; soft-fail). "
            "Distinct from READY bolt search (web)."
        ),
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["status", "list", "run", "search", "query"],
        help="status (default) | list | run | search | query",
    )
    parser.add_argument(
        "query",
        nargs="*",
        help="search words (for run/search/query)",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="status: smoke-test retrieve_memory + format_retrieved_context",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="run/search/query: max hits (default 5)",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="run/search/query: rebuild index before retrieve",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="run/search/query: count hits without printing full context",
    )
    args = parser.parse_args(argv)

    action = args.action
    if action in ("search", "query"):
        action = "run"

    if action == "status":
        return _print_status(status(probe=args.probe), args.json)

    if action == "list":
        rows = list_items()
        if args.json:
            print(json.dumps({"items": rows, "soft_fail_note": _SOFT}, indent=2))
        else:
            for r in rows:
                mark = "OK" if r["ok"] else "NO"
                print(f"[{mark}] {r['id']}: {r['detail']}")
            print(f"(soft-fail prefix: {_SOFT!r})")
        return 0

    if action == "run":
        q = " ".join(args.query).strip()
        result = try_run(
            q, limit=args.limit, refresh=args.refresh, dry_run=args.dry_run
        )
        if args.json:
            # Drop traceback from default JSON unless failure
            payload = {k: v for k, v in result.items() if k != "traceback"}
            if result.get("error") and result.get("traceback"):
                payload["traceback"] = result["traceback"]
            print(json.dumps(payload, indent=2))
        else:
            if result.get("error") and not result.get("ok"):
                print(result["error"])
                return 0
            mode = "dry-run" if result.get("dry_run") else "live"
            print(
                f"memsearch run ({mode}): ok={result.get('ok')}  "
                f"hits={result.get('hit_count')}  query={result.get('query')!r}"
            )
            if result.get("refreshed"):
                print(
                    f"  refreshed index: entries={result.get('refresh_entry_count')}"
                )
            if result.get("dry_run"):
                for h in result.get("hits") or []:
                    print(
                        f"  [{h.get('score')}] {h.get('title')} "
                        f"({h.get('kind')}/{h.get('source')})"
                    )
                if result.get("hint"):
                    print(f"  hint: {result['hint']}")
            else:
                ctx = result.get("context") or ""
                if ctx:
                    sys.stdout.write(ctx)
                    if not ctx.endswith("\n"):
                        sys.stdout.write("\n")
            if result.get("error"):
                print(f"  {result['error']}")
        return 0

    print(_soft(f"unknown action {action!r}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
