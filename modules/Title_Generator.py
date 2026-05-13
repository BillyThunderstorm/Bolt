#!/usr/bin/env python3
"""
modules/Title_Generator.py — Generate TikTok titles and hashtags
================================================================
Claude/Anthropic support has been removed from this module.

Bolt now uses local template-based titles only. That keeps the clip
pipeline free, predictable, and independent from cloud API keys.
Always returns a list of title candidates plus hashtags.
"""

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
        "When you peek and everyone's just… there 💀 #{game}",
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
    Generate title candidates and hashtags for a clip using local templates.

    This function intentionally does not call any cloud AI provider.
    """
    context = context or {}
    notify(
        f"Generating local template titles for {trigger} clip (score {score:.0f})",
        level="info",
        reason="Claude/Anthropic title generation has been removed. Using free local templates."
    )

    titles = _template_titles(trigger, game, context, count)
    hashtags = _pick_hashtags(game, trigger)
    return titles, hashtags


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

    while len(filled) < count:
        filled.append(f"This {game} clip goes crazy 🔥 #{game}")
    return filled


def _pick_hashtags(game: str, trigger: str) -> List[str]:
    game_tags = HASHTAG_POOLS.get(game, [f"#{game.replace(' ', '')}"])
    trigger_tag = f"#{trigger.replace('_', '')}"
    base = list(dict.fromkeys(game_tags + [trigger_tag] + GENERIC_TAGS))
    return base[:8]
