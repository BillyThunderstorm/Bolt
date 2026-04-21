#!/usr/bin/env python3
"""
modules/Bolt_Search.py — Bolt's real-time web search capability
================================================================
Lets Bolt look things up instead of guessing.

WHY this exists:
  Without search, Bolt can only answer from what Claude already knows
  from its training data (which has a cutoff date). Game metas change,
  patch notes drop, trending audio shifts — Bolt needs to be current.

  With search, a viewer can ask "what's the best loadout right now?"
  and Bolt will actually look it up instead of making something up.

HOW it works:
  We give Claude a built-in web_search tool. When it decides the question
  needs a live answer, it searches automatically, reads the results, and
  gives back a real answer. We don't manage the search ourselves — Claude
  decides when and what to search.

WHEN to use it:
  - !Bolt questions that need current info (metas, patch notes, trending)
  - Content planning (what hashtags are trending? what game is blowing up?)
  - Anything that changes week to week

WHEN NOT to use it:
  - Live chat reactions (too slow — use templates or base Claude calls)
  - Simple questions Claude already knows well

Usage:
  from modules.Bolt_Search import search_and_answer

  answer = search_and_answer("what's the warzone meta right now?")
  answer = search_and_answer("best hashtags for apex legends clips", short=False)
"""

import os
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import anthropic
    ANTHROPIC_OK = True
except ImportError:
    ANTHROPIC_OK = False

try:
    from modules.notifier import notify
except ImportError:
    def notify(msg, level="info", reason=None):
        prefix = {"info": "ℹ", "success": "✓", "warning": "⚠", "error": "✗"}.get(level, "•")
        print(f"  {prefix}  {msg}")
        if reason:
            print(f"     → {reason}")

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# We use Haiku for search — it's fast and the web results do the heavy lifting.
# The model doesn't need to "know" the answer, it just needs to read and summarize.
SEARCH_MODEL = "claude-haiku-4-5-20251001"


def search_and_answer(
    question: str,
    context: str = "",
    short: bool = True,
    max_searches: int = 2,
) -> Optional[str]:
    """
    Search the web and return an answer.

    Parameters
    ----------
    question     : what to look up
    context      : extra info to help Claude answer (e.g. game name, streamer name)
    short        : True = 1-2 sentence answer (Twitch chat), False = fuller answer
    max_searches : how many web searches Claude can do (more = slower but deeper)

    Returns
    -------
    Answer string, or None if search failed or isn't available.

    WHY short=True by default:
      Twitch chat moves fast. A paragraph answer will get buried before
      anyone reads it. 1-2 sentences is the sweet spot — enough to be
      useful, short enough to actually land.
    """
    if not ANTHROPIC_OK:
        notify(
            "Search unavailable — anthropic package not installed",
            level="warning",
            reason="Run: pip3 install anthropic --break-system-packages"
        )
        return None

    if not ANTHROPIC_KEY:
        notify(
            "Search unavailable — ANTHROPIC_API_KEY not set in .env",
            level="warning"
        )
        return None

    # Build the system prompt based on where the answer is going
    if short:
        length_rule = (
            "Answer in 1-2 sentences MAX. This is going straight to Twitch chat "
            "where long messages get ignored. Be direct, be accurate, be brief."
        )
    else:
        length_rule = (
            "Give a thorough answer. Use 2-4 sentences. Include specifics. "
            "This is for content planning, not live chat."
        )

    system = (
        "You are Bolt — an AI assistant for a Twitch streamer and content creator. "
        "You have access to web search. Use it when the question needs current information "
        "(game metas, patch notes, trending content, recent news). "
        "Be accurate — if you're not sure, say so rather than guessing. "
        "Keep Bolt's tone: calm, confident, precise. No hype.\n\n"
        f"{length_rule}"
    )

    if context:
        system += f"\n\nExtra context: {context}"

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

        notify(
            f"Bolt searching: {question[:60]}…",
            level="info",
            reason="Using Claude with web search tool. May take a few seconds."
        )

        response = client.messages.create(
            model=SEARCH_MODEL,
            max_tokens=300 if short else 600,
            tools=[{
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": max_searches,
            }],
            system=system,
            messages=[{"role": "user", "content": question}]
        )

        # The response may contain tool use blocks (the search itself) followed
        # by a text block (the answer). We want the final text block.
        answer = None
        for block in response.content:
            if hasattr(block, "text") and block.text.strip():
                answer = block.text.strip()

        if answer:
            notify(
                "Search complete ✓",
                level="success",
                reason=f"Answer: {answer[:80]}…" if len(answer) > 80 else f"Answer: {answer}"
            )
            return answer

        notify("Search returned no text answer", level="warning")
        return None

    except anthropic.BadRequestError as e:
        # Web search tool not available on this API tier
        notify(
            "Web search not available on your current API plan",
            level="warning",
            reason=str(e)
        )
        return None
    except Exception as exc:
        notify(
            f"Search failed: {exc}",
            level="warning",
            reason="Falling back to non-search response."
        )
        return None


def needs_search(question: str) -> bool:
    """
    Heuristic to decide if a question probably needs a web search.

    We don't want to search for everything — searches take longer and cost
    slightly more. Simple questions ("how long has Billy been streaming?")
    don't need the internet. Current-info questions do.

    This is a simple keyword check. Claude will still decide on its own
    whether to actually trigger a search, but this lets us avoid the overhead
    entirely for questions that clearly don't need it.
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


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    """
    Test search directly from terminal.

    Usage:
      python3 -m modules.Bolt_Search
      python3 -m modules.Bolt_Search "best warzone loadout right now"
    """
    import sys

    print("\n  ⚡️  Bolt Search — Direct Test")
    print(f"  API key: {'set ✓' if ANTHROPIC_KEY else 'MISSING — add to .env'}")
    print()

    if not ANTHROPIC_KEY:
        sys.exit(1)

    # Use a test question or the one passed as argument
    test_q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "what is the current meta in Warzone?"

    print(f"  Question: {test_q}")
    print(f"  Needs search: {needs_search(test_q)}")
    print()

    answer = search_and_answer(test_q, context="Twitch stream for BillyandRandy")

    print()
    if answer:
        print(f"  Answer: {answer}")
    else:
        print("  No answer returned — check logs above for details.")
    print()
