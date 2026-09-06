#!/usr/bin/env python3
"""
modules/Bolt_Search.py — live web search for Bolt
=================================================
Public API used by Bolt_Chat (!Bolt) and the CLI:

    from modules.Bolt_Search import search_and_answer, needs_search

Flow:
  1. DuckDuckGo HTML (shared with Researcher via scripts/_research.py)
  2. Optional LLM summary (Ollama / light stack) into a short chat answer
  3. If LLM is down, return a compact snippet digest

Missing network / empty results → return None so callers fall back to local LLM.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

try:
    from modules.notifier import notify
except ImportError:

    def notify(msg, level="info", reason=None):
        prefix = {"info": "ℹ", "success": "✓", "warning": "⚠", "error": "✗"}.get(
            level, "•"
        )
        print(f"  {prefix}  {msg}")
        if reason:
            print(f"     → {reason}")


def _web_search(query: str, limit: int) -> List[dict]:
    """Fetch search hits via the shared research helper (DDG HTML, no API key)."""
    # Prefer package import when PYTHONPATH includes Core + scripts parent.
    try:
        from scripts._research import web_search_results  # type: ignore
    except Exception:
        try:
            # Core/modules → repo root/scripts
            repo_root = Path(__file__).resolve().parents[2]
            scripts_dir = repo_root / "scripts"
            if str(scripts_dir) not in sys.path:
                sys.path.insert(0, str(scripts_dir))
            if str(repo_root) not in sys.path:
                sys.path.insert(0, str(repo_root))
            from _research import web_search_results  # type: ignore
        except Exception as exc:
            notify(
                "Web search helper unavailable",
                level="warning",
                reason=str(exc),
            )
            return []
    try:
        return list(web_search_results(query, limit=limit) or [])
    except Exception as exc:
        notify("Web search failed", level="warning", reason=str(exc))
        return []


def _format_digest(results: List[dict], short: bool = True) -> str:
    """Build a no-LLM answer from titles + snippets."""
    lines: List[str] = []
    cap = 2 if short else 5
    for hit in results[:cap]:
        title = (hit.get("title") or "").strip()
        desc = (hit.get("description") or "").strip()
        url = (hit.get("url") or "").strip()
        if not title and not desc:
            continue
        bit = title
        if desc:
            bit = f"{title}: {desc}" if title else desc
        if url and not short:
            bit = f"{bit} ({url})"
        lines.append(bit)
    if not lines:
        return ""
    joined = " | ".join(lines) if short else "\n".join(f"- {x}" for x in lines)
    if short and len(joined) > 280:
        joined = joined[:277] + "…"
    return joined


def _summarize_with_llm(
    question: str,
    results: List[dict],
    context: str = "",
    short: bool = True,
) -> Optional[str]:
    """Ask the local/light LLM to turn search hits into a chat reply."""
    try:
        from modules.LLM_Handler import ask_llm
    except Exception:
        return None

    bullets = []
    for hit in results[:5]:
        title = (hit.get("title") or "").strip()
        desc = (hit.get("description") or "").strip()
        url = (hit.get("url") or "").strip()
        bullets.append(f"- {title}: {desc} [{url}]".strip())
    evidence = "\n".join(bullets)
    system = (
        "You answer briefly using only the search snippets provided. "
        "If snippets are thin or conflicting, say what is known and what is unclear. "
        "No markdown, no bullet lists in the reply — plain sentences for chat."
    )
    if short:
        system += " Keep the whole reply under 220 characters."
    prompt_parts = [f"Question: {question}"]
    if context:
        prompt_parts.append(f"Context: {context}")
    prompt_parts.append("Search results:\n" + evidence)
    prompt_parts.append("Answer the question for a live stream chat.")
    try:
        answer = ask_llm(
            "\n\n".join(prompt_parts),
            system=system,
            max_tokens=120 if short else 350,
            temperature=0.4,
            task_type="chat",
            complexity="low",
        )
    except Exception as exc:
        notify("Search LLM summary failed", level="warning", reason=str(exc))
        return None
    text = (answer or "").strip()
    if not text:
        return None
    if short and len(text) > 280:
        text = text[:277] + "…"
    return text


def search_and_answer(
    question: str,
    context: str = "",
    short: bool = True,
    max_searches: int = 2,
    limit: Optional[int] = None,
) -> Optional[str]:
    """
    Search the web and return a short answer string, or None on failure.

    ``max_searches`` is kept for API compatibility (maps to ~3 hits each).
    Prefer ``limit`` when the caller knows the exact result count.
    """
    q = (question or "").strip()
    if not q:
        return None

    if limit is None:
        limit = max(1, min(int(max_searches or 2) * 3, 8))
    else:
        limit = max(1, min(int(limit), 10))
    results = _web_search(q, limit=limit)
    if not results:
        notify(
            "No web results",
            level="info",
            reason="DuckDuckGo returned nothing — caller should use local fallback.",
        )
        return None

    notify(
        f"Web search: {len(results)} hit(s)",
        level="success",
        reason=q[:80],
    )

    summarized = _summarize_with_llm(q, results, context=context, short=short)
    if summarized:
        return summarized

    digest = _format_digest(results, short=short)
    return digest or None


def needs_search(question: str) -> bool:
    """
    Heuristic: does this question probably need live/current info?
    """
    search_signals = [
        "right now",
        "currently",
        "today",
        "this week",
        "latest",
        "best",
        "meta",
        "patch",
        "update",
        "nerf",
        "buff",
        "broken",
        "trending",
        "popular",
        "new",
        "season",
        "ranked",
        "what is",
        "how do",
        "how to",
        "tips",
        "guide",
        "loadout",
        "settings",
        "pro settings",
        "what happened",
        "news",
    ]
    q_lower = (question or "").lower()
    return any(signal in q_lower for signal in search_signals)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI: ``bolt search "question"`` / ``python -m modules.Bolt_Search``."""
    parser = argparse.ArgumentParser(
        prog="bolt search",
        description="Live web search (DuckDuckGo) with optional LLM summary.",
    )
    parser.add_argument(
        "question",
        nargs="+",
        help="Question to search (quote multi-word questions)",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print search hits only (skip LLM summary)",
    )
    parser.add_argument(
        "--long",
        action="store_true",
        help="Allow a longer answer (default is short chat style)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Max search hits to fetch (default 5)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw hits as JSON and exit",
    )
    args = parser.parse_args(argv)
    question = " ".join(args.question).strip()
    if not question:
        print("bolt search: need a question", file=sys.stderr)
        return 1

    results = _web_search(question, limit=max(1, args.limit))
    if args.json:
        import json

        print(json.dumps(results, indent=2))
        return 0 if results else 1

    if args.raw:
        if not results:
            print("No results.", file=sys.stderr)
            return 1
        for hit in results:
            title = (hit.get("title") or "").strip()
            desc = (hit.get("description") or "").strip()
            url = (hit.get("url") or "").strip()
            print(f"- {title}")
            if desc:
                print(f"  {desc}")
            if url:
                print(f"  {url}")
        return 0

    answer = search_and_answer(
        question,
        short=not args.long,
        limit=max(1, args.limit),
    )
    if not answer:
        print("No answer (search empty or failed).", file=sys.stderr)
        return 1
    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
