#!/usr/bin/env python3
"""
Memory_Search.py — Phase 4 search over Bolt's local memory (READY)
====================================================================
Wraps ``Memory_Index.retrieve_memory`` / ``format_retrieved_context`` (hybrid
vector+keyword over ``Data/memory_index.json``). Soft-fail prefix:
``Memory search unavailable:``.

CLI (via ``bolt memsearch``):
  status [--json] [--probe]
  list   [--json]
  run|search|query <words…> [--limit N] [--refresh|--no-refresh] [--dry-run] [--json]

``run`` auto-rebuilds ``Data/memory_index.json`` when it is missing or older
than any memory source (Data/memory + Data/content markdown, Data/MEMORY.md,
unified_memory.jsonl, clip/recording history, performance outcomes, decision
audit) — a rebuild is ~0.2 s. Results must share at least one real word with
the query (the hashed-vector score alone matched filenames by collision), and
are ranked by how many query words they contain, then by hybrid score.

Aliases: ``memsearch``, ``memory-search``, ``mem-search``, ``search-memory``,
``memory_search``, ``memsearch-status``.

READY (18 Oct 2026): local, no API keys or models; works on any checkout with
a ``Data/`` folder (index builds itself on first run).

**Distinct from:**
  - READY ``bolt search`` (``Bolt_Search`` — live web / DuckDuckGo)
  - PARTIAL ``bolt memory`` (``Bolt_Memory`` — LLM recall / remember)
  - READY ``bolt refresh-memory`` (index rebuild only; memsearch now
    rebuilds automatically when stale)

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
_DATA = _REPO / "Data"
_SOURCE_FILES = [
    _DATA / "MEMORY.md",
    _DATA / "unified_memory.jsonl",
    _DATA / "clip_history.json",
    _DATA / "seen_clips.json",
    _DATA / "processed_recordings.json",
    _DATA / "performance_outcomes.jsonl",
    _REPO / "logs" / "decision_audit.log",
]
_SOURCE_DIRS = [_DATA / "memory", _DATA / "content"]
_SCAN_LIMIT = 100000  # retrieve everything, then filter/rank here


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


def _parse_generated(value: str) -> Optional[float]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _freshness(idx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Compare index generated_at against the newest memory source. Never raises."""
    idx = idx if idx is not None else _index_meta()
    newest_path = ""
    newest = 0.0
    try:
        candidates: List[Path] = [f for f in _SOURCE_FILES if f.is_file()]
        for d in _SOURCE_DIRS:
            if d.is_dir():
                candidates.extend(d.rglob("*.md"))
        for f in candidates:
            try:
                m = f.stat().st_mtime
            except OSError:
                continue
            if m > newest:
                newest, newest_path = m, str(f)
    except Exception:
        pass
    gen = _parse_generated(str(idx.get("generated_at") or ""))
    if not idx.get("present"):
        stale, reason = True, "index missing"
    elif gen is None:
        stale, reason = True, "index has no generated_at"
    elif newest and newest > gen + 1:
        stale = True
        reason = f"newer source: {Path(newest_path).name}"
    else:
        stale, reason = False, "up to date"
    return {
        "stale": stale,
        "reason": reason,
        "newest_source": newest_path,
        "newest_source_at": (
            datetime.fromtimestamp(newest).isoformat(timespec="seconds")
            if newest
            else ""
        ),
    }


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Never raises. readiness READY; report index freshness + retrieve API."""
    idx = _index_meta()
    fresh = _freshness(idx)
    info: Dict[str, Any] = {
        "checked_at": _iso(),
        "ready": False,
        "partial": False,
        "readiness": "READY",
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
        "index_stale": fresh["stale"],
        "index_stale_reason": fresh["reason"],
        "newest_source": fresh["newest_source"],
        "newest_source_at": fresh["newest_source_at"],
        "memory_index_import_ok": False,
        "retrieve_api_ok": False,
        "format_api_ok": False,
        "api_note": "",
        "probe": bool(probe),
        "probe_ok": None,
        "error": "",
        "hint": (
            'bolt memsearch "words" searches Bolt\'s local memory (auto-rebuilds '
            "the index when stale) · distinct from READY bolt search (web) + "
            "READY bolt memory (LLM recall)"
        ),
        "is_stranger_ready": True,
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
        # Not a blocker: run builds it automatically (~0.2 s).
        info["hint"] = (
            "index not built yet — the first bolt memsearch run \"…\" builds it"
        )
    elif fresh["stale"]:
        info["hint"] = (
            f"index is behind ({fresh['reason']}) — the next bolt memsearch run "
            "rebuilds it automatically"
        )

    # Ready when engine importable + retrieve API present. Index may be
    # absent/stale — run rebuilds it before searching.
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
            "id": "index_fresh",
            "ok": not bool(st.get("index_stale")),
            "detail": (
                f"stale={st.get('index_stale')} ({st.get('index_stale_reason')}); "
                f"newest source {st.get('newest_source_at') or '-'} · run auto-rebuilds"
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
                f"prefix {_SOFT!r}; READY; distinct from READY bolt search "
                "(web) + READY bolt memory (LLM) + READY bolt refresh-memory"
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
    auto_refresh: bool = True,
) -> Dict[str, Any]:
    """Search memory: rebuild if stale, keep word-matched hits, rank. Never raises."""
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
        "refresh_reason": "",
        "refresh_entry_count": None,
        "auto_refresh": bool(auto_refresh),
        "unmatched_dropped": 0,
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
        reason = ""
        if refresh:
            reason = "--refresh"
        elif auto_refresh:
            fresh = _freshness()
            if fresh["stale"]:
                reason = fresh["reason"]
        if reason:
            payload = mi.refresh_memory_index(project_root=_REPO, out_file=_INDEX)
            out["refreshed"] = True
            out["refresh_reason"] = reason
            out["refresh_entry_count"] = int(payload.get("entry_count") or 0)

        raw = mi.retrieve_memory(
            q, limit=_SCAN_LIMIT, index_file=_INDEX, auto_refresh=False
        )
        if not isinstance(raw, list):
            out["error"] = _soft("retrieve_memory returned non-list")
            return out

        # Drop hash-collision noise: a hit must contain a real query word.
        matched = [h for h in raw if h.get("matched_terms")]
        out["unmatched_dropped"] = len(raw) - len(matched)
        matched.sort(
            key=lambda h: (len(h.get("matched_terms") or []), h.get("score") or 0.0),
            reverse=True,
        )
        hits = matched[: max(1, out["limit"])]

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
                    "updated_at": h.get("updated_at"),
                    "matched_terms": h.get("matched_terms") or [],
                    "signal": h.get("signal"),
                    "summary": (h.get("summary") or "")[:240],
                }
            )
        out["hits"] = slim
        if not hits:
            out["hint"] = (
                f"no memory entries contain any of the words in {q!r} — "
                "try a game, clip, product, or decision word"
            )

        if dry_run:
            out["ok"] = True
            out["context"] = ""
            out["hint"] = out.get("hint") or (
                f"dry-run: {out['hit_count']} hit(s) for {q!r} "
                f"(skipped format_retrieved_context print)"
            )
            return out

        ctx = mi.format_retrieved_context(hits)
        ctx = ctx if isinstance(ctx, str) else str(ctx)
        # Add when + matched words under each heading (shared formatter stays
        # unchanged for briefings).
        for h in hits:
            head = f"### {h.get('title', 'Memory')}\n"
            when = str(h.get("updated_at") or "")[:16].replace("T", " ")
            extra = f"- when: {when or '-'}  matched: {', '.join(h.get('matched_terms') or [])}\n"
            ctx = ctx.replace(head, head + extra, 1)
        out["context"] = ctx
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
            f"  fresh:   stale={info.get('index_stale')} "
            f"({info.get('index_stale_reason')})"
        )
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
            "Search Bolt's local memory (READY; auto-rebuilds a stale index). "
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
        help="run/search/query: force an index rebuild before searching",
    )
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="run/search/query: skip the automatic rebuild when the index is stale",
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
            q,
            limit=args.limit,
            refresh=args.refresh,
            dry_run=args.dry_run,
            auto_refresh=not args.no_refresh,
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
                    f"  rebuilt index ({result.get('refresh_reason')}): "
                    f"entries={result.get('refresh_entry_count')}"
                )
            if result.get("dry_run"):
                for h in result.get("hits") or []:
                    print(
                        f"  [{h.get('score')}] {h.get('title')} "
                        f"({h.get('kind')}/{h.get('source')}) "
                        f"matched={','.join(h.get('matched_terms') or [])}"
                    )
                if result.get("hint"):
                    print(f"  hint: {result['hint']}")
            else:
                ctx = result.get("context") or ""
                if not result.get("hit_count"):
                    print("  (no relevant memory found)")
                    if result.get("hint"):
                        print(f"  hint: {result['hint']}")
                    ctx = ""
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
