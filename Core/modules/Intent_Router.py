#!/usr/bin/env python3
"""
modules/Intent_Router.py — Lightweight natural-language intent router for Bolt
==============================================================================
Maps plain spoken/typed phrases to existing Bolt actions so conversation
feels fluid without requiring exact CLI commands.

Design goals:
  - Fast, local, no extra LLM call for routing
  - Prefer high-value, low-risk actions (status, next, morning, queue)
  - Return a short spoken-friendly string the conversation layer can use
  - Fall through (return None) when the message is just normal chat

Usage from Bolt_Conversation:
  from modules.Intent_Router import try_handle_intent
  handled = try_handle_intent(user_text)
  if handled is not None:
      return handled   # already a ready-to-speak reply
  # else: normal ask_llm path
"""

from __future__ import annotations

import re
from typing import Callable, Optional, Tuple


def _normalize(text: str) -> str:
    t = (text or "").lower().strip()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _match_any(text: str, phrases: Tuple[str, ...]) -> bool:
    return any(p in text for p in phrases)


def _action_morning() -> str:
    try:
        from modules.Content_Manager import morning, is_good_morning_phrase

        # morning() already speaks; we still return the spoken text for history
        result = morning(speak_aloud=True)
        return result.get("spoken") or "Good morning briefing is ready."
    except Exception as exc:
        return f"I tried to run the morning briefing but hit a snag: {exc}"


def _action_next() -> str:
    try:
        from modules.Content_Manager import next_actions

        actions = next_actions(limit=3)
        if not actions:
            return "Nothing urgent is queued right now. Want me to suggest a content item?"
        lines = []
        for a in actions:
            lines.append(f"{a['title']}.")
        return "Here's what I'd focus on next: " + " ".join(lines)
    except Exception as exc:
        return f"I couldn't load next actions: {exc}"


def _action_status() -> str:
    try:
        from modules.Content_Manager import (
            list_items,
            store_summary,
            shipped_summary,
            sponsors_pipeline,
            social_queue,
        )

        items = list_items()
        testing = [i for i in items if i.get("status") == "testing"]
        store = store_summary()
        ship = shipped_summary()
        sp = sponsors_pipeline()
        queue_len = len(social_queue())

        parts = [
            f"You have {len(items)} catalog items, {len(testing)} currently testing.",
            f"Storefront has {store['total']} items ({store['with_asin']} with ASINs).",
            f"Shipped reviews: {ship['total']}.",
            f"Sponsor pipeline: {sp['active']} active of {sp['total']}.",
            f"Social queue entries: {queue_len}.",
        ]
        return " ".join(parts)
    except Exception as exc:
        return f"Status check failed: {exc}"


def _action_queue() -> str:
    try:
        from modules.Bolt_Chat import format_queue_status

        return format_queue_status()
    except Exception:
        try:
            from modules.Content_Manager import social_queue

            q = social_queue()
            if not q:
                return "The social queue is empty right now."
            return f"There are {len(q)} items in the social queue. Top one is {q[0].get('item', 'unknown')}."
        except Exception as exc:
            return f"Couldn't read the queue: {exc}"


def _action_research() -> str:
    try:
        from modules.Researcher import status_summary  # type: ignore

        return status_summary()
    except Exception:
        try:
            # Fallback: read research log lightly if helper missing
            from pathlib import Path
            import json

            log_path = Path("Data/memory/research_log.jsonl")
            if not log_path.exists():
                return "Research log is empty so far. Want to add a candidate?"
            lines = log_path.read_text(encoding="utf-8").strip().splitlines()
            return f"Research log has {len(lines)} entries. Run bolt research status for details."
        except Exception as exc:
            return f"Research status unavailable: {exc}"


def _action_mission() -> str:
    try:
        from modules.Command_Center import mission_status  # type: ignore

        return mission_status()
    except Exception:
        return (
            "Mission system is available via bolt mission status. "
            "Want me to start a new mission for a goal?"
        )


# Order matters: more specific patterns first.
_INTENT_TABLE: Tuple[Tuple[Tuple[str, ...], Callable[[], str]], ...] = (
    (
        (
            "good morning bolt",
            "morning bolt",
            "good morning",
            "hey bolt good morning",
            "bolt good morning",
            "give me the morning briefing",
            "run morning briefing",
            "daily briefing",
        ),
        _action_morning,
    ),
    (
        (
            "what should i do",
            "what should i work on",
            "what's next",
            "whats next",
            "next action",
            "next actions",
            "what do you recommend",
            "give me next steps",
            "what needs attention",
        ),
        _action_next,
    ),
    (
        (
            "how are things",
            "status report",
            "give me a status",
            "manager status",
            "catalog status",
            "how is everything",
            "system status",
        ),
        _action_status,
    ),
    (
        (
            "posting queue",
            "queue status",
            "what's in the queue",
            "whats in the queue",
            "show the queue",
            "social queue",
            "clip queue",
        ),
        _action_queue,
    ),
    (
        (
            "research status",
            "research update",
            "any research",
            "research candidates",
            "pending research",
        ),
        _action_research,
    ),
    (
        (
            "mission status",
            "command center",
            "any missions",
            "current mission",
        ),
        _action_mission,
    ),
)


def try_handle_intent(user_text: str) -> Optional[str]:
    """
    If user_text matches a known intent, run the action and return a
    spoken-friendly reply string. Otherwise return None so the caller
    can fall through to free-form LLM chat.
    """
    text = _normalize(user_text)
    if not text:
        return None

    for phrases, action in _INTENT_TABLE:
        if _match_any(text, phrases):
            try:
                return action()
            except Exception as exc:
                return f"I recognized that request but failed while running it: {exc}"
    return None


if __name__ == "__main__":
    samples = [
        "Good morning Bolt",
        "What should I do next?",
        "How are things looking?",
        "Show me the posting queue",
        "Research status",
        "Just chatting about games",
    ]
    for s in samples:
        result = try_handle_intent(s)
        print(f"IN:  {s}")
        print(f"OUT: {result!r}\n")
