#!/usr/bin/env python3
"""
modules/Bolt_Search.py — optional search routing for Bolt
=========================================================
Claude/Anthropic support has been removed from this module.

Bolt no longer depends on Anthropic web search to function. The public
API stays the same so Bolt_Chat and other modules can still import:

    from modules.Bolt_Search import search_and_answer, needs_search

If a question appears to need current web information, needs_search()
will still return True, but search_and_answer() now returns None so the
caller can fall back safely instead of crashing or calling Claude.
"""

from typing import Optional

try:
    from modules.notifier import notify
except ImportError:
    def notify(msg, level="info", reason=None):
        prefix = {"info": "ℹ", "success": "✓", "warning": "⚠", "error": "✗"}.get(level, "•")
        print(f"  {prefix}  {msg}")
        if reason:
            print(f"     → {reason}")


def search_and_answer(
    question: str,
    context: str = "",
    short: bool = True,
    max_searches: int = 2,
) -> Optional[str]:
    """
    Return None instead of calling Claude web search.

    Keeping this function prevents the rest of Bolt from breaking while
    removing the Anthropic dependency. Later, this can be wired to another
    provider or a local search stack behind the same function name.
    """
    notify(
        "Live web search is disabled",
        level="info",
        reason="Anthropic/Claude search was removed. Bolt will use its local fallback response."
    )
    return None


def needs_search(question: str) -> bool:
    """
    Heuristic to decide whether a question probably needs live/current info.

    This remains useful even while search is disabled because callers can
    decide whether to fall back, defer, or answer locally.
    """
    search_signals = [
        "right now", "currently", "today", "this week", "latest",
        "best", "meta", "patch", "update", "nerf", "buff", "broken",
        "trending", "popular", "new", "season", "ranked",
        "what is", "how do", "how to", "tips", "guide", "loadout",
        "settings", "pro settings", "what happened", "news",
    ]
    q_lower = question.lower()
    return any(signal in q_lower for signal in search_signals)


if __name__ == "__main__":
    import sys

    test_q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "what is the current meta?"
    print("\n  ⚡️  Bolt Search — Claude-free mode")
    print(f"  Question: {test_q}")
    print(f"  Needs search: {needs_search(test_q)}")
    print("  Answer: search disabled; caller should use fallback.\n")
