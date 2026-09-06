"""Web search helper for Bolt sponsor research and researcher-find.

Decoupled so Content Manager, Researcher, Bolt_Search, and tests can share one
contract: `web_search_results(query, limit=5)` → list of
{"url", "title", "description"}.

Tries, in order:
  1. hermes_tools.web_search (agent environments)
  2. ddgs package (robust DuckDuckGo client)
  3. DuckDuckGo HTML (html.duckduckgo.com)
  4. DuckDuckGo Lite (lite.duckduckgo.com) — when HTML is bot-blocked
  5. DuckDuckGo Instant Answer API (abstract + related topics)

Returns [] if all fail so callers never crash.
"""

from __future__ import annotations

import html as html_lib
import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import Request, urlopen

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def web_search_results(query: str, limit: int = 5) -> List[Dict[str, str]]:
    """Return search results for the given query."""
    if not query or not query.strip():
        return []
    for fetcher in (
        _hermes_search,
        _ddgs_search,
        _ddg_html_search,
        _ddg_lite_search,
        _ddg_instant_answer,
    ):
        try:
            items = fetcher(query.strip(), limit)
        except Exception:
            items = []
        if items:
            return items[:limit]
    return []


def _ddgs_search(query: str, limit: int) -> List[Dict[str, str]]:
    """Primary HTML-free DuckDuckGo client (dependency: ddgs)."""
    try:
        from ddgs import DDGS  # type: ignore
    except Exception:
        return []
    items: List[Dict[str, str]] = []
    try:
        with DDGS() as client:
            raw = list(client.text(query, max_results=limit))
    except Exception:
        return []
    for entry in raw or []:
        if not isinstance(entry, dict):
            continue
        items.append(
            {
                "url": entry.get("href") or entry.get("url") or "",
                "title": entry.get("title") or "",
                "description": entry.get("body")
                or entry.get("description")
                or entry.get("snippet")
                or "",
            }
        )
        if len(items) >= limit:
            break
    return items


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
            "User-Agent": _UA,
            "Accept": "text/html",
        },
        method="POST",
    )
    with urlopen(req, timeout=12) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    return parse_ddg_html(html, limit=limit)


def parse_ddg_lite(html: str, limit: int = 5) -> List[Dict[str, str]]:
    """Parse DuckDuckGo Lite results page."""
    # Lite uses simple result-link anchors; snippets often follow in nearby <td>.
    link_pat = re.compile(
        r'class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        flags=re.I | re.S,
    )
    snippet_pat = re.compile(
        r'class="result-snippet"[^>]*>(.*?)</(?:td|div|span|a)',
        flags=re.I | re.S,
    )
    titles = link_pat.findall(html)
    snippets = snippet_pat.findall(html)
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


def _ddg_lite_search(query: str, limit: int) -> List[Dict[str, str]]:
    body = urlencode({"q": query}).encode("utf-8")
    req = Request(
        "https://lite.duckduckgo.com/lite/",
        data=body,
        headers={
            "User-Agent": _UA,
            "Accept": "text/html",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urlopen(req, timeout=12) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    return parse_ddg_lite(html, limit=limit)


def _ddg_instant_answer(query: str, limit: int) -> List[Dict[str, str]]:
    """Fallback: Instant Answer API (Abstract + RelatedTopics)."""
    url = "https://api.duckduckgo.com/?" + urlencode(
        {
            "q": query,
            "format": "json",
            "no_redirect": "1",
            "no_html": "1",
            "skip_disambig": "1",
        }
    )
    req = Request(url, headers={"User-Agent": "BoltSearch/1.0"})
    with urlopen(req, timeout=12) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))

    items: List[Dict[str, str]] = []
    abstract = (data.get("AbstractText") or "").strip()
    heading = (data.get("Heading") or query).strip()
    abs_url = (data.get("AbstractURL") or data.get("AbstractSource") or "").strip()
    if abstract:
        items.append(
            {
                "url": abs_url if abs_url.startswith("http") else "",
                "title": heading or query,
                "description": abstract,
            }
        )

    def _walk_topics(topics: Any) -> None:
        for entry in topics or []:
            if len(items) >= limit:
                return
            if not isinstance(entry, dict):
                continue
            if "Topics" in entry:
                _walk_topics(entry.get("Topics"))
                continue
            text = (entry.get("Text") or "").strip()
            first_url = ""
            for link in entry.get("FirstURL"), entry.get("url"):
                if link:
                    first_url = str(link)
                    break
            if not text:
                continue
            title = text.split(" - ", 1)[0][:120]
            items.append(
                {
                    "url": first_url,
                    "title": title,
                    "description": text,
                }
            )

    _walk_topics(data.get("RelatedTopics"))
    return items[:limit]
