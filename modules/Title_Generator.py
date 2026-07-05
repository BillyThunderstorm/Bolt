#!/usr/bin/env python3
"""Generate TikTok titles and hashtags.

The default path stays local and free. When config enables AI titles and an
OpenAI key is present, Bolt asks the LLM for Billy-styled options, caches the
answer, and falls back to templates if anything goes sideways.
"""

import hashlib
import json
import os
import random
import re
from pathlib import Path
from typing import List, Optional, Tuple

# ── LLM Backend: Gemini (via Nexus) or OpenAI fallback ───────────────────────
# Bolt now uses Gemini by default for title generation since it's free.
# Set USE_GEMINI_TITLES=false in .env to fall back to OpenAI.
USE_GEMINI = os.getenv("USE_GEMINI_TITLES", "true").lower() not in ("false", "0", "no")

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


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TITLE_CACHE = PROJECT_ROOT / "data" / "title_cache.json"
BRAIN_FILES = (PROJECT_ROOT / "bolt_brain.md", PROJECT_ROOT / "Bolt_brain.md")
AI_MODEL = "gpt-4o-mini"  # OpenAI fallback (requires credits)
GEMINI_MODEL = "gemini-2.5-flash"  # Free tier

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
    "Marvel Rivals": ["#MarvelRivals", "#MarvelRivalsClips", "#superhero", "#gaming"],
    "Valorant": ["#Valorant", "#ValorantClips", "#VCT", "#FPS"],
    "Apex Legends": ["#ApexLegends", "#Apex", "#ApexClips", "#BattleRoyale"],
    "Fortnite": ["#Fortnite", "#FortniteClips", "#BuildingIsBack", "#FN"],
    "Warzone": ["#Warzone", "#COD", "#WarzoneClips", "#CallOfDuty"],
    "Overwatch 2": ["#Overwatch2", "#OW2", "#OverwatchClips", "#FPS"],
    "CS2": ["#CS2", "#CounterStrike", "#CS2Clips", "#FPS"],
    "League of Legends": ["#LeagueOfLegends", "#LoL", "#LoLClips", "#MOBA"],
}
GENERIC_TAGS = [
    "#gaming",
    "#clips",
    "#viral",
    "#trending",
    "#streamer",
    "#twitch",
    "#tiktokgaming",
]


def generate_titles(
    trigger: str,
    game: str = "Gaming",
    score: float = 50.0,
    context: Optional[dict] = None,
    count: int = 3,
) -> Tuple[List[str], List[str]]:
    """
    Generate title candidates and hashtags for a clip.

    AI generation is opt-in via config (`use_ai_titles` or
    `quality_tiers.use_ai_titles`) and always falls back to local templates.
    """
    context = context or {}
    if _ai_titles_enabled(context):
        titles_and_tags = _llm_titles(trigger, game, score, context, count)
        if titles_and_tags:
            return titles_and_tags

    notify(
        f"Generating local template titles for {trigger} clip (score {score:.0f})",
        level="info",
        reason="AI titles are disabled or unavailable. Using free local templates.",
    )

    titles = _template_titles(trigger, game, context, count)
    hashtags = _pick_hashtags(game, trigger)
    return titles, hashtags


def _ai_titles_enabled(context: dict) -> bool:
    explicit = context.get("use_ai_titles")
    if explicit is not None:
        return bool(explicit)

    config = context.get("config")
    if config is None:
        try:
            from modules.Config_Loader import load_config

            config = load_config()
        except Exception:
            config = {}

    title_config = (
        config.get("title_generation", {}) if isinstance(config, dict) else {}
    )
    if title_config.get("enabled") is not None:
        return bool(title_config.get("enabled"))

    if isinstance(config, dict) and config.get("use_ai_titles") is not None:
        return bool(config.get("use_ai_titles"))

    quality_tiers = config.get("quality_tiers", {}) if isinstance(config, dict) else {}
    return bool(quality_tiers.get("use_ai_titles", False))


def _llm_titles(
    trigger: str,
    game: str,
    score: float,
    context: dict,
    count: int,
) -> Optional[Tuple[List[str], List[str]]]:
    cache = _load_title_cache()
    cache_key = _cache_key(trigger, game, score, context, count)
    cached = cache.get(cache_key)
    if cached:
        notify(
            f"Using cached AI titles for {trigger} clip",
            level="info",
            reason="Title cache avoids paying for the same prompt twice.",
        )
        return cached.get("titles", []), cached.get("hashtags", [])

    prompt = _build_title_prompt(trigger, game, score, context, count)
    notify(
        f"Generating AI titles for {trigger} clip (score {score:.0f})",
        level="info",
        reason="Using Billy's creator profile plus clip context, with template fallback.",
    )

    # ── Try Gemini first (free), fall back to OpenAI ──────────────────────
    raw = None
    try:
        if USE_GEMINI and _has_gemini_key():
            raw = _ask_gemini(prompt)
        elif _has_openai_key():
            from modules.LLM_Handler import ask_llm
            raw = ask_llm(prompt, model=AI_MODEL)
        else:
            notify(
                "AI titles enabled, but no API key configured (GEMINI_API_KEY or OPENAI_API_KEY)",
                level="warning",
                reason="Bolt will keep working with local template titles.",
            )
            return None

        if not raw or raw.startswith("Nexus unavailable") or raw.startswith("LLM unavailable"):
            raise ValueError("LLM returned empty or error response")
        result = _parse_title_response(raw)
        titles = _clean_titles(result.get("titles", []), count)
        hashtags = _clean_hashtags(result.get("hashtags", []), game, trigger)
        if not titles:
            raise ValueError("LLM response did not include usable titles")

        cache[cache_key] = {"titles": titles, "hashtags": hashtags}
        _save_title_cache(cache)
        notify(
            f"AI title ready: {titles[0]}",
            level="success",
            reason="Saved to data/title_cache.json for reuse.",
        )
        return titles, hashtags
    except Exception as exc:
        notify(
            f"AI title generation failed: {exc}",
            level="warning",
            reason="Falling back to local templates so the clip pipeline can continue.",
        )
        return None


def _build_title_prompt(
    trigger: str, game: str, score: float, context: dict, count: int
) -> str:
    brain = str(context.get("creator_brain") or _load_creator_brain())
    transcript = str(context.get("transcript") or "").strip()
    memory = str(context.get("memory") or context.get("retrieved_memory") or "").strip()
    details = {
        "trigger": trigger,
        "game": game,
        "score": round(score, 1),
        "kill_count": context.get("kill_count"),
        "window_seconds": context.get("window_seconds"),
    }
    return f"""You write short-form gaming captions for Billy.

Creator profile:
{brain[:2500]}

Clip details:
{json.dumps(details, indent=2)}

Transcript:
{transcript[:1200] or "No transcript available."}

Relevant memory:
{memory[:1200] or "No retrieved memory."}

Generate {count} title options and 8 hashtags.
Rules:
- Titles should be 1 short sentence each.
- Sound like Billy, not generic marketing copy.
- Avoid overpromising what is not in the clip.
- Return only JSON with this shape:
{{"titles": ["..."], "hashtags": ["#MarvelRivals", "..."]}}
"""


def _load_creator_brain() -> str:
    for path in BRAIN_FILES:
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
    return ""


def _load_title_cache() -> dict:
    if not TITLE_CACHE.exists():
        return {}
    try:
        return json.loads(TITLE_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_title_cache(cache: dict) -> None:
    TITLE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    TITLE_CACHE.write_text(
        json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8"
    )


def _cache_key(trigger: str, game: str, score: float, context: dict, count: int) -> str:
    transcript = str(context.get("transcript") or "")
    creator_brain = str(context.get("creator_brain") or "")
    parts = {
        "trigger": trigger,
        "game": game,
        "score_bucket": int(score // 5) * 5,
        "count": count,
        "context": {
            "kill_count": context.get("kill_count"),
            "window_seconds": context.get("window_seconds"),
            "transcript": transcript[:500],
            "creator_brain": creator_brain[:500],
        },
    }
    encoded = json.dumps(parts, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _has_openai_key() -> bool:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    return bool(key and key != "sk_your_key_here")


def _has_gemini_key() -> bool:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    return bool(key)


def _ask_gemini(prompt: str) -> str:
    """Ask Gemini for titles using the google-genai SDK directly."""
    try:
        from google import genai
        import os as _os

        client = genai.Client(api_key=_os.getenv("GEMINI_API_KEY"))
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        return response.text or ""
    except Exception as e:
        return f"LLM unavailable: {str(e)[:120]}"


def _parse_title_response(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _clean_titles(titles: list, count: int) -> List[str]:
    cleaned = []
    for title in titles:
        text = str(title).strip()
        if text and text not in cleaned:
            cleaned.append(text[:140])
    return cleaned[:count]


def _clean_hashtags(hashtags: list, game: str, trigger: str) -> List[str]:
    cleaned = []
    for tag in hashtags:
        text = str(tag).strip()
        if not text:
            continue
        if not text.startswith("#"):
            text = f"#{text}"
        text = re.sub(r"\s+", "", text)
        if text not in cleaned:
            cleaned.append(text[:40])
    for tag in _pick_hashtags(game, trigger):
        if tag not in cleaned:
            cleaned.append(tag)
    return cleaned[:8]


def _template_titles(trigger: str, game: str, context: dict, count: int) -> List[str]:
    pool = TEMPLATES.get(trigger, TEMPLATES["highlight"])
    selected = random.sample(pool, min(count, len(pool)))
    filled = []
    for t in selected:
        try:
            filled.append(
                t.format(
                    game=game,
                    trigger=trigger,
                    count=context.get("kill_count", "Multiple"),
                    seconds=context.get("window_seconds", "10"),
                    donor=context.get("donor_name", "the donator"),
                    raiders=context.get("raid_size", "A ton of"),
                )
            )
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
