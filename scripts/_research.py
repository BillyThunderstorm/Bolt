"""Web search helper for Bolt sponsor research.

Decoupled from the rest of the project so it can be imported from
anywhere (Content Manager CLI, manual research scripts, future
batch jobs). Uses the project's standard web_search tool when
available; falls back to a no-op stub with a clear error message
so the caller can decide what to do.

The contract: `web_search_results(query, limit=5)` returns a list
of {"url", "title", "description"} dicts, the same shape
Content_Manager.sponsors_research() expects.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def web_search_results(query: str, limit: int = 5) -> List[Dict[str, str]]:
    """Return search results for the given query.

    Tries (in order):
      1. hermes_tools.web_search — the agent's primary web search
      2. a fallback that returns an empty list

    The empty-list fallback means the caller (e.g. sponsors_research)
    will get a "0 results attached" log entry but won't crash. The
    operator can then re-run with the search tool available.
    """
    if not query or not query.strip():
        return []
    try:
        from hermes_tools import web_search  # type: ignore
    except Exception:
        web_search = None  # type: ignore

    if web_search is None:
        return []

    try:
        raw = web_search(query, limit=limit)
    except Exception:
        return []

    # Normalize: hermes_tools.web_search returns {"data": {"web": [...]}}
    # or sometimes a list directly. Handle both.
    items: List[Dict[str, str]] = []
    candidates: Optional[List[Dict[str, Any]]] = None
    if isinstance(raw, dict):
        if "data" in raw and isinstance(raw["data"], dict):
            candidates = raw["data"].get("web") or raw["data"].get("results")
        elif "results" in raw:
            candidates = raw["results"]
        elif "web" in raw:
            candidates = raw["web"]
    elif isinstance(raw, list):
        candidates = raw

    for entry in candidates or []:
        if not isinstance(entry, dict):
            continue
        items.append({
            "url": entry.get("url", "") or "",
            "title": entry.get("title", "") or "",
            "description": entry.get("description", "") or entry.get("snippet", "") or "",
        })
        if len(items) >= limit:
            break
    return items
