# modules/AI_Title_Generator.py
# Generates viral titles for your clips using context from the video.
# The notifier will explain every title decision so you can learn the logic.

import json
import random
import os
from pathlib import Path
from modules.notifier import notify, notify_title, notify_error

VIRAL_MODEL_FILE = "viral_titles_model.json"

# Six title categories — each has a different psychological hook.
# Understanding WHY each works helps you write better titles manually too.
TITLE_TEMPLATES = {
    "reaction": [
        "I can't believe this happened in {game}",
        "This {game} moment broke my brain",
        "Nobody saw this coming in {game}",
        "My reaction to this {game} clip says everything",
    ],
    "achievement": [
        "Finally hit {achievement} in {game}",
        "The {game} play I've been grinding for",
        "How I pulled off the impossible in {game}",
        "{achievement} after 100 hours of {game}",
    ],
    "funny": [
        "The funniest thing that happened in {game} today",
        "This {game} bug is actually hilarious",
        "I don't even know what happened here ({game})",
        "This {game} moment lives rent free in my head",
    ],
    "hype": [
        "The most insane {game} clip you'll see today",
        "This {game} play is UNREAL",
        "POV: you just went off in {game}",
        "No way this actually worked in {game}",
    ],
    "challenge": [
        "Can this {game} strategy actually work?",
        "What happens when you try this in {game}",
        "Testing the most broken thing in {game}",
        "This should not be possible in {game}",
    ],
    "informative": [
        "How to pull this off in {game}",
        "The {game} technique nobody talks about",
        "This is why {game} pros do it this way",
        "Learn this {game} trick in 30 seconds",
    ],
}

# Keywords in the transcription steer the category choice.
# Recognizing these patterns is a core NLP concept called "intent detection".
CATEGORY_KEYWORDS = {
    "reaction":    ["insane", "crazy", "no way", "what", "omg", "bro", "wait"],
    "achievement": ["finally", "clutch", "first time", "win", "victory", "ranked"],
    "funny":       ["lol", "lmao", "bug", "glitch", "wtf", "accident", "oops"],
    "hype":        ["go off", "cracked", "nasty", "goated", "diff", "aim"],
    "challenge":   ["try", "test", "see if", "attempt", "challenge", "strategy"],
    "informative": ["how", "tip", "trick", "tutorial", "learn", "guide"],
}


def generate_title(clip_path: str, game: str, transcription: str = "",
                   visual_intensity: float = 0.5) -> str:
    """
    Generate the best title for a clip.

    How it works:
    1. Scan the transcription for keywords that hint at the category
    2. Use visual intensity to lean toward hype vs informative
    3. Pick the best-performing template from that category
    4. Substitute the game name and any detected achievements
    5. Notify you of the choice and the reasoning
    """
    notify(f"Generating title for: {Path(clip_path).name}", level="info",
           reason="Title generation analyzes your transcript + video energy to pick the most viral framing.")

    # Step 1: Score each category based on keyword matches in the transcript
    category_scores = {cat: 0 for cat in TITLE_TEMPLATES}
    transcript_lower = transcription.lower()

    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in transcript_lower:
                category_scores[category] += 1

    notify(
        f"Category scores: {category_scores}",
        level="learn",
        reason=(
            "Each point means a keyword from that category appeared in your speech. "
            "More keyword matches = stronger signal that this framing fits the clip."
        )
    )

    # Step 2: Adjust scores based on visual intensity
    # High intensity clips benefit from hype framing
    # Low intensity clips suit informative or achievement framing
    if visual_intensity >= 0.7:
        category_scores["hype"] += 2
        category_scores["reaction"] += 1
    elif visual_intensity <= 0.3:
        category_scores["informative"] += 2
        category_scores["achievement"] += 1

    notify(
        f"Visual intensity: {visual_intensity:.0%} — adjusted category scores",
        level="learn",
        reason=(
            f"Visual intensity {visual_intensity:.0%} means the frame had "
            f"{'a lot of fast movement — boosted hype/reaction categories' if visual_intensity >= 0.7 else 'calm/steady footage — boosted informative/achievement categories'}."
        )
    )

    # Step 3: Pick the winning category
    # Load historical performance to break ties
    best_category = max(category_scores, key=lambda c: (
        category_scores[c],
        _get_category_performance(c)
    ))

    # Step 4: Pick the best template from the category
    templates = TITLE_TEMPLATES[best_category]
    best_template = _pick_best_template(templates, best_category)
    runner_up_template = templates[1] if len(templates) > 1 and templates[1] != best_template else None

    # Step 5: Fill in placeholders
    achievement = _detect_achievement(transcription)
    title = best_template.format(
        game=game,
        achievement=achievement or "this moment"
    )
    runner_up = runner_up_template.format(game=game, achievement=achievement or "this moment") if runner_up_template else None

    # Notify with full explanation
    notify_title(Path(clip_path).name, title, best_category, runner_up)

    # Save to model for future learning
    _record_title(title, best_category, clip_path)

    return title


def train_on_titles(titles_file: str):
    """
    Feed the system examples of titles that performed well.
    This is supervised learning in its simplest form —
    you're providing labeled examples to improve future output.
    """
    notify(f"Training on titles from: {titles_file}", level="info",
           reason="Training means we're learning which title patterns perform best so future clips get better titles automatically.")

    try:
        with open(titles_file) as f:
            examples = json.load(f)  # expects [{"title": "...", "views": 1000}, ...]
    except Exception as e:
        notify_error("train_on_titles", e, recoverable=False)
        return

    model = _load_model()
    for example in examples:
        title = example.get("title", "")
        views = example.get("views", 0)
        category = _classify_title(title)
        model["category_performance"][category] = model["category_performance"].get(category, [])
        model["category_performance"][category].append(views)

    _save_model(model)
    notify(f"Trained on {len(examples)} title examples", level="success",
           reason="The model now has real performance data — it will prefer categories that historically got more views.")


# ── Internal helpers ──────────────────────────────────────────────────────────

def _detect_achievement(transcription: str) -> str:
    """Look for achievement-like phrases in the transcript."""
    achievement_phrases = ["kill streak", "ace", "clutch", "MVP", "win", "ranked up", "headshot"]
    tl = transcription.lower()
    for phrase in achievement_phrases:
        if phrase.lower() in tl:
            return phrase
    return None


def _pick_best_template(templates: list, category: str) -> str:
    """Return the template with the best historical performance, or random if no data."""
    model = _load_model()
    performance = model.get("template_performance", {})
    scored = [(t, performance.get(t, 0)) for t in templates]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[0][0]


def _get_category_performance(category: str) -> float:
    """Average views for this category from historical data."""
    model = _load_model()
    views = model.get("category_performance", {}).get(category, [])
    return sum(views) / len(views) if views else 0


def _classify_title(title: str) -> str:
    """Best-guess category for an existing title (used in training)."""
    title_lower = title.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in title_lower for kw in keywords):
            return category
    return "hype"


def _record_title(title: str, category: str, clip_path: str):
    model = _load_model()
    model.setdefault("history", []).append({
        "title": title,
        "category": category,
        "clip": str(clip_path),
        "views": None  # updated later when metrics come in
    })
    _save_model(model)


def _load_model() -> dict:
    if Path(VIRAL_MODEL_FILE).exists():
        try:
            with open(VIRAL_MODEL_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"category_performance": {}, "template_performance": {}, "history": []}


def _save_model(model: dict):
    with open(VIRAL_MODEL_FILE, "w") as f:
        json.dump(model, f, indent=2)

    if not config.get("use_ai_titles", True):
    titles = [f"Clip from {game}"]
    hashtags = []
else:
    # existing Claude call
