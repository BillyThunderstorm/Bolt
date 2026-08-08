#!/usr/bin/env python3
"""Generate TikTok titles and hashtags.

Preference order (Google sparingly):
  1. Grok (xAI) or ChatGPT (OpenAI) via ``BOLT_LLM_PROVIDER``
  2. Local templates (free, always available)
  3. Gemini only if ``USE_GEMINI_TITLES=true`` (off by default)
"""

import hashlib
import json
import os
import random
import re
from pathlib import Path
from typing import List, Optional, Tuple

# Gemini is last-resort and off unless explicitly enabled.
USE_GEMINI = os.getenv("USE_GEMINI_TITLES", "false").lower() in (
    "true",
    "1",
    "yes",
)

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
OPENAI_TITLE_MODEL = os.getenv("BOLT_OPENAI_MODEL", "gpt-4o-mini")
XAI_TITLE_MODEL = os.getenv("BOLT_XAI_MODEL") or os.getenv("GROK_MODEL", "grok-4.5")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
# Back-compat alias used in older tests/docs
AI_MODEL = OPENAI_TITLE_MODEL

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

    # ── Grok/ChatGPT first → optional Gemini → templates ──────────────────
    raw = None
    try:
        raw, used = _ask_preferred_title_llm(prompt)
        if raw and not str(raw).startswith("LLM unavailable"):
            notify(
                f"Using {used} for AI titles",
                level="info",
                reason="Prefers Grok/ChatGPT over Gemini. Templates if this fails.",
            )
        else:
            raw = None

        # Gemini only when explicitly enabled — last resort before templates.
        if not raw and USE_GEMINI and _has_gemini_key():
            raw = _ask_gemini(prompt)
            if raw and not raw.startswith("LLM unavailable"):
                notify(
                    "Using Gemini for AI titles (explicit opt-in)",
                    level="info",
                    reason=f"USE_GEMINI_TITLES=true · model {GEMINI_MODEL}",
                )
            else:
                raw = None

        if not raw:
            notify(
                "AI titles enabled, but Grok/ChatGPT unavailable "
                "(check XAI_API_KEY / OPENAI_API_KEY / BOLT_LLM_PROVIDER)",
                level="warning",
                reason="Bolt will keep working with local template titles.",
            )
            return None

        if (
            not raw
            or raw.startswith("Nexus unavailable")
            or raw.startswith("LLM unavailable")
        ):
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


def _has_xai_key() -> bool:
    return bool(os.getenv("XAI_API_KEY", "").strip())


def _has_gemini_key() -> bool:
    try:
        from modules.Gemini_Client import has_gemini_key

        return has_gemini_key()
    except Exception:
        return bool(os.getenv("GEMINI_API_KEY", "").strip())


def _ask_preferred_title_llm(prompt: str) -> Tuple[Optional[str], str]:
    """
    Call Grok or ChatGPT based on BOLT_LLM_PROVIDER.

    Returns (response_text_or_None, provider_label).
    Never sends an OpenAI model name to the xAI endpoint (or vice versa).
    """
    preferred = os.getenv("BOLT_LLM_PROVIDER", "openai").lower().strip()
    fallback = os.getenv("BOLT_LLM_FALLBACK", "openai").lower().strip()

    order: List[str] = []
    for name in (preferred, fallback):
        if name and name != "none" and name not in order:
            order.append(name)
    # If preferred is unset/odd, still try whichever keys exist.
    if not order:
        order = ["xai", "openai"]
    for name in ("xai", "openai"):
        if name not in order:
            order.append(name)

    try:
        from modules.LLM_Handler import ask_llm
    except Exception as exc:
        return f"LLM unavailable: {exc}", "none"

    last = None
    for prov in order:
        if prov == "xai" and not _has_xai_key():
            continue
        if prov == "openai" and not _has_openai_key():
            continue
        if prov not in ("xai", "openai"):
            continue
        model = XAI_TITLE_MODEL if prov == "xai" else OPENAI_TITLE_MODEL
        label = f"Grok/{model}" if prov == "xai" else f"ChatGPT/{model}"
        raw = ask_llm(
            prompt,
            provider=prov,
            model=model,
            max_tokens=600,
            temperature=0.7,
        )
        last = raw
        if raw and not str(raw).startswith("LLM unavailable"):
            return raw, label
    return last, preferred or "none"


def _ask_gemini(prompt: str) -> str:
    """Ask Gemini for titles only when USE_GEMINI_TITLES is enabled."""
    try:
        from modules.Gemini_Client import ask_gemini

        return ask_gemini(
            prompt,
            model=GEMINI_MODEL,
            temperature=0.7,
            max_output_tokens=600,
            json_mode=True,
            timeout=30.0,
        )
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

    # If Video_Intelligence surfaced on-screen stats, prepend the strongest
    # one to each title. The result: "15 KILL STREAK — Billy just erased
    # the lobby" instead of just the template alone. This is the Tier 2.1
    # "data-driven titles" piece of the spec.
    on_screen = context.get("on_screen_stats") or []
    if on_screen:
        headline = on_screen[0]
        filled = [f"{headline} — {t}" for t in filled]

    while len(filled) < count:
        filled.append(f"This {game} clip goes crazy 🔥 #{game}")
    return filled


def _pick_hashtags(game: str, trigger: str) -> List[str]:
    game_tags = HASHTAG_POOLS.get(game, [f"#{game.replace(' ', '')}"])
    trigger_tag = f"#{trigger.replace('_', '')}"
    base = list(dict.fromkeys(game_tags + [trigger_tag] + GENERIC_TAGS))
    return base[:8]
