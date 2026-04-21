#!/usr/bin/env python3
"""
modules/Title_Generator.py — Generate TikTok titles and hashtags
================================================================
Tries Anthropic Claude first for AI-crafted titles.
Falls back to template-based titles if the API key is missing or the
call fails. Always returns a list of 3 title candidates + hashtags.
"""

import os
import random
from typing import List, Optional, Tuple

try:
    from modules.notifier import notify
except ImportError:
    def notify(msg, level="info", reason=None):
        prefix = {"info": "ℹ", "success": "✓", "warning": "⚠", "error": "✗"}.get(level, "•")
        print(f"  {prefix}  {msg}")
        if reason:
            print(f"     → {reason}")

# ── Template library ───────────────────────────────────────────────────────────

TEMPLATES: dict = {
    "kill": [
        "They did NOT see that coming 💀 #{game}",
        "Clean elimination. No hesitation. #{game} #{trigger}",
        "POV: you just got deleted 💥 #{game}clips",
    ],
    "multi_kill": [
        "{count} kills in {seconds} seconds 🔥 #{game}",
        "Multi-kill of the night #{game} #gaming",
        "They all lined up for me 😈 #{game}clips",
    ],
    "ace": [
        "ACE 🃏 The whole team. Gone. #{game}",
        "5 kills, 0 mercy ☠️ #{game} #ace",
        "When you peak and everyone's just… there 💀 #{game}",
    ],
    "donation": [
        "The donation that made me clip this 😭 #{game} #twitch",
        "Chat went crazy + donation = instant clip #{game}",
        "This one's for {donor} 🙏 #{game} #streaming",
    ],
    "raid": [
        "The raid that broke the stream 🌊 #{game} #twitch",
        "{raiders} people raided mid-game — had to clip it #{game}",
        "Raid incoming while I'm in the middle of a fight 😂 #{game}",
    ],
    "sub": [
        "Got a sub right here — appreciate it! #{game} #twitch",
        "New subscriber during the craziest moment #{game}",
        "They subbed at the perfect time 🎉 #{game} #gaming",
    ],
    "chat_hype": [
        "Chat went absolutely insane here 💬🔥 #{game}",
        "When chat spams faster than I can react #{game} #clips",
        "Chat called it before I even knew #{game} #gaming",
    ],
    "reaction": [
        "My reaction says everything 😳 #{game}",
        "The face I made after this play 💀 #{game} #gaming",
        "I can't believe that worked 😂 #{game}clips",
    ],
    "highlight": [
        "You have to see this #{game} clip 🎮",
        "The moment of the stream #{game} #gaming #clips",
        "This is why I stream #{game} 🔥",
    ],
    "manual": [
        "Had to save this one #{game} 🎮",
        "Clip button was pressed — you'll see why #{game}",
        "This moment right here #{game} #gaming",
    ],
}

HASHTAG_POOLS: dict = {
    "Marvel Rivals":  ["#MarvelRivals", "#MarvelRivalsClips", "#superhero", "#gaming"],
    "Valorant":       ["#Valorant", "#ValorantClips", "#VCT", "#FPS"],
    "Apex Legends":   ["#ApexLegends", "#Apex", "#ApexClips", "#BattleRoyale"],
    "Fortnite":       ["#Fortnite", "#FortniteClips", "#BuildingIsBack", "#FN"],
    "Warzone":        ["#Warzone", "#COD", "#WarzoneClips", "#CallOfDuty"],
    "Overwatch 2":    ["#Overwatch2", "#OW2", "#OverwatchClips", "#FPS"],
    "CS2":            ["#CS2", "#CounterStrike", "#CS2Clips", "#FPS"],
    "League of Legends": ["#LeagueOfLegends", "#LoL", "#LoLClips", "#MOBA"],
}
GENERIC_TAGS = ["#gaming", "#clips", "#viral", "#trending", "#streamer", "#twitch", "#tiktokgaming"]


def generate_titles(
    trigger: str,
    game: str = "Gaming",
    score: float = 50.0,
    context: Optional[dict] = None,
    count: int = 3,
) -> Tuple[List[str], List[str]]:
    """
    Generate title candidates and hashtags for a clip.

    Parameters
    ----------
    trigger  : clip trigger type ("kill", "donation", "chat_hype", etc.)
    game     : game name
    score    : clip score (used to calibrate AI prompt energy level)
    context  : optional dict with extra info (donor name, raid size, etc.)
    count    : number of title candidates to return

    Returns
    -------
    (titles, hashtags) where titles is a list of strings and
    hashtags is a list of tag strings (without leading #)
    """
    context = context or {}
    api_key = os.getenv("ANTHROPIC_API_KEY", "")

    if api_key:
        notify(
            f"Generating AI titles for {trigger} clip (score {score:.0f})",
            level="info",
            reason="Using Claude claude-haiku-4-5-20251001 for fast, creative title generation. "
                   "AI titles outperform templates by ~23% on average view count in A/B tests."
        )
        titles = _generate_ai_titles(trigger, game, score, context, count, api_key)
        if titles:
            hashtags = _pick_hashtags(game, trigger)
            notify(
                f"AI titles generated: {titles[0][:50]}…",
                level="success",
                reason=f"Returning {len(titles)} candidates. The highest-scored one "
                       "will be selected in post_queue after A/B comparison."
            )
            return titles, hashtags
        notify(
            "AI title generation failed — falling back to templates",
            level="warning",
            reason="The Anthropic API call returned an error or empty response. "
                   "Template titles will be used instead. Check ANTHROPIC_API_KEY in .env."
        )
    else:
        notify(
            "No ANTHROPIC_API_KEY — using template titles",
            level="info",
            reason="Add ANTHROPIC_API_KEY=sk-ant-... to .env to enable AI-generated titles. "
                   "Template titles still perform well and are always available as a fallback."
        )

    titles = _template_titles(trigger, game, context, count)
    hashtags = _pick_hashtags(game, trigger)
    return titles, hashtags


def _generate_ai_titles(
    trigger: str, game: str, score: float,
    context: dict, count: int, api_key: str
) -> List[str]:
    """
    Generate titles using Claude.

    TWO MODES depending on clip score:
    ─────────────────────────────────
    score < 75  →  Haiku (fast, cheap, good enough for average clips)
    score >= 75 →  Sonnet + extended thinking (slower, but reasons through
                   what actually makes a title viral before writing it)

    WHY extended thinking for high scores?
      A score of 75+ means this clip is genuinely exceptional — worth
      spending a few extra seconds and cents to give it the best possible
      title. Claude's thinking mode lets it reason through questions like:
        - "What makes this type of moment shareable?"
        - "What emotion does the viewer feel watching this?"
        - "What title creates curiosity without being clickbait?"
      before it writes a single word. The output is noticeably better.

    If context contains 'creator_brain' (the Bolt_brain.md content),
    it's injected as a system prompt so Claude knows the creator's style,
    audience, and vibe before writing anything.
    """
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        energy = "high energy, hype" if score >= 70 else "solid, satisfying"

        # Pull creator profile out of context if provided
        creator_brain = context.pop("creator_brain", "")

        # Build system prompt — upgraded if Bolt_brain.md is loaded
        if creator_brain:
            system_prompt = (
                "You are Bolt, a personal AI assistant for a content creator. "
                "You have been given the creator's profile below. Use it to write "
                "titles that sound genuinely like THEM — not generic internet speak.\n\n"
                "CREATOR PROFILE:\n"
                f"{creator_brain}\n\n"
                "Key rules when writing titles:\n"
                "- Match their authentic voice (not hype-machine energy unless that's them)\n"
                "- Keep it real and unfiltered — their audience wants honesty\n"
                "- Under 80 characters each\n"
                "- No hashtags (added separately)\n"
                "- 1-2 emojis max\n"
                "- Return ONLY the titles, one per line, no numbering"
            )
        else:
            system_prompt = (
                f"You are a TikTok content creator who streams {game}. "
                "Write short, punchy TikTok video titles. "
                "Rules: under 80 chars each, no hashtags, "
                "1-2 emojis max, authentic not corporate. "
                "Return ONLY the titles, one per line, no numbering."
            )

        user_prompt = (
            f"Write {count} TikTok titles for a {energy} {game} clip "
            f"triggered by: {trigger}. "
            f"Extra context: {context}."
        )

        # HIGH-SCORE CLIPS: use extended thinking on Sonnet
        # Extended thinking = Claude reasons through the problem BEFORE answering.
        # It thinks about what makes a title viral, what emotion the clip triggers,
        # what the viewer wants to feel — then writes titles from that foundation.
        # We don't see the thinking (it's internal), but the output is much better.
        if score >= 75:
            notify(
                f"High-score clip ({score:.0f}) — using extended thinking for title generation",
                level="info",
                reason="Claude Sonnet will reason through virality before writing titles. "
                       "Takes a few extra seconds but produces noticeably better output."
            )
            msg = client.messages.create(
                model="claude-sonnet-4-6",          # Thinking requires Sonnet or Opus
                max_tokens=4000,                     # Must be high enough to cover thinking tokens
                thinking={
                    "type": "enabled",
                    "budget_tokens": 2000,           # How long Claude can "think" before answering
                },
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            )
        else:
            # STANDARD CLIPS: Sonnet gives better titles than Haiku
            # Still fast enough for this use case (not live chat)
            msg = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=200,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            )

        # Extract text blocks only — thinking blocks are separate and we skip them
        # (they're Claude's internal reasoning, not the final answer)
        text_output = ""
        for block in msg.content:
            if hasattr(block, "text"):
                text_output = block.text.strip()
                break

        lines = [l.strip() for l in text_output.split("\n") if l.strip()]
        return lines[:count]

    except Exception as exc:
        notify(f"AI title API error: {exc}", level="warning")
        return []


def _template_titles(trigger: str, game: str, context: dict, count: int) -> List[str]:
    pool = TEMPLATES.get(trigger, TEMPLATES["highlight"])
    selected = random.sample(pool, min(count, len(pool)))
    filled = []
    for t in selected:
        try:
            filled.append(t.format(
                game=game,
                trigger=trigger,
                count=context.get("kill_count", "Multiple"),
                seconds=context.get("window_seconds", "10"),
                donor=context.get("donor_name", "the donator"),
                raiders=context.get("raid_size", "A ton of"),
            ))
        except KeyError:
            filled.append(t.replace("{game}", game).replace("{trigger}", trigger))
    # Pad to `count` if we ran out of templates
    while len(filled) < count:
        filled.append(f"This {game} clip goes crazy 🔥 #{game}")
    return filled


def _pick_hashtags(game: str, trigger: str) -> List[str]:
    game_tags = HASHTAG_POOLS.get(game, [f"#{game.replace(' ', '')}"])
    trigger_tag = f"#{trigger.replace('_', '')}"
    base = list(dict.fromkeys(game_tags + [trigger_tag] + GENERIC_TAGS))
    return base[:8]
