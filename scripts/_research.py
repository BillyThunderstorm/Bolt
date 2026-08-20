"""Web search helper for Bolt sponsor research and researcher-find.

Decoupled so Content Manager, Researcher, and tests can share one contract:
`web_search_results(query, limit=5)` → list of {"url", "title", "description"}.

Tries, in order:
  1. hermes_tools.web_search (agent environments)
  2. DuckDuckGo HTML (no API key; used from `bolt research find`)

Returns [] if both fail so callers never crash.
"""

from __future__ import annotations

import html as html_lib
import re
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import Request, urlopen


def web_search_results(query: str, limit: int = 5) -> List[Dict[str, str]]:
    """Return search results for the given query."""
    if not query or not query.strip():
        return []
    for fetcher in (_hermes_search, _ddg_html_search):
        try:
            items = fetcher(query.strip(), limit)
        except Exception:
            items = []
        if items:
            return items[:limit]
    return []


def _hermes_search(query: str, limit: int) -> List[Dict[str, str]]:
    try:
        from hermes_tools import web_search  # type: ignore
    except Exception:
        return []
    try:
        raw = web_search(query, limit=limit)
    except Exception:
        return []
    return _normalize_results(raw, limit)


def _normalize_results(raw: Any, limit: int) -> List[Dict[str, str]]:
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
        items.append(
            {
                "url": entry.get("url", "") or "",
                "title": entry.get("title", "") or "",
                "description": entry.get("description", "")
                or entry.get("snippet", "")
                or "",
            }
        )
        if len(items) >= limit:
            break
    return items


def _unwrap_ddg_url(href: str) -> str:
    href = html_lib.unescape(href or "")
    if "uddg=" in href:
        qs = parse_qs(urlparse(href).query)
        if qs.get("uddg"):
            return unquote(qs["uddg"][0])
    return href


def _strip_tags(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return html_lib.unescape(re.sub(r"\s+", " ", text)).strip()


def parse_ddg_html(html: str, limit: int = 5) -> List[Dict[str, str]]:
    """Parse DuckDuckGo HTML search results. Exported for tests."""
    titles = re.findall(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        html,
        flags=re.I | re.S,
    )
    snippets = re.findall(
        r'class="result__snippet"[^>]*>(.*?)</(?:a|span|div|td)',
        html,
        flags=re.I | re.S,
    )
    items: List[Dict[str, str]] = []
    seen = set()
    for index, (href, title_html) in enumerate(titles):
        url = _unwrap_ddg_url(href)
        title = _strip_tags(title_html)
        if not url or not title:
            continue
        host = (urlparse(url).netloc or "").lower()
        if "duckduckgo.com" in host:
            continue
        if url in seen:
            continue
        seen.add(url)
        snippet = _strip_tags(snippets[index]) if index < len(snippets) else ""
        items.append({"url": url, "title": title, "description": snippet})
        if len(items) >= limit:
            break
    return items


def _ddg_html_search(query: str, limit: int) -> List[Dict[str, str]]:
    body = urlencode({"q": query}).encode("utf-8")
    req = Request(
        "https://html.duckduckgo.com/html/",
        data=body,
        headers={
            "User-Agent": "BoltResearch/1.0 (+https://github.com/local-bolt)",
            "Accept": "text/html",
        },
        method="POST",
    )
    with urlopen(req, timeout=12) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    return parse_ddg_html(html, limit=limit)
