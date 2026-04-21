#!/usr/bin/env python3
"""
modules/Clip_Ranker.py — Score and rank generated clips
========================================================
Combines audio energy, trigger type, and optional performance history
to produce a final score (0-100) for each clip. Higher = better.
"""

import json
import os
from pathlib import Path
from typing import List, Optional, Dict

try:
    from modules.notifier import notify, notify_score
except ImportError:
    def notify(msg, level="info", reason=None):
        prefix = {"info": "ℹ", "success": "✓", "warning": "⚠", "error": "✗"}.get(level, "•")
        print(f"  {prefix}  {msg}")
        if reason:
            print(f"     → {reason}")
    def notify_score(clip, score, breakdown):
        print(f"  📊  {clip}: {score:.0f} | {breakdown}")

try:
    from modules.Clip_Generator import GeneratedClip
except ImportError:
    GeneratedClip = object

HISTORY_FILE = "clip_history.json"

# Bonus points per trigger type (stacks with audio score)
TRIGGER_BONUS: Dict[str, float] = {
    "kill":         18,
    "multi_kill":   28,
    "ace":          35,
    "donation":     22,
    "raid":         30,
    "sub":          20,
    "resub":        15,
    "bits":         12,
    "chat_hype":    10,
    "highlight":     5,
    "manual":       20,   # Stream Deck button press
}


def rank_clips(
    clips: List,
    min_score: float = 40.0,
    game: str = "Gaming",
) -> List:
    """
    Score each clip and return them sorted best-first.
    Clips below min_score are still included but flagged.

    Parameters
    ----------
    clips     : list of GeneratedClip objects (only .success==True are scored)
    min_score : clips below this threshold are flagged as low-priority
    game      : used to load historical performance data

    Returns
    -------
    Sorted list with .score attribute set on each clip (adds attribute dynamically)
    """
    history = _load_history(game)
    scoreable = [c for c in clips if getattr(c, "success", False)]

    notify(
        f"Ranking {len(scoreable)} clip(s) for {game}",
        level="info",
        reason=f"Scoring formula: audio_energy (0-50) + trigger_bonus (0-35) + "
               f"history_boost (0-15). min_score threshold = {min_score}."
    )

    for clip in scoreable:
        score, breakdown = _score_clip(clip, history)
        clip.score = score  # attach dynamically

        level = "success" if score >= min_score else "warning"
        notify_score(
            Path(clip.output_file).name,
            score,
            breakdown
        )
        if score < min_score:
            notify(
                f"  Low score ({score:.0f} < {min_score}) — will not auto-post",
                level="warning",
                reason="The clip didn't meet the minimum posting threshold. "
                       "You can still post it manually. Lower min_post_score in "
                       "config.json to include more clips automatically."
            )

    # Sort descending
    scoreable.sort(key=lambda c: getattr(c, "score", 0), reverse=True)

    if scoreable:
        best = scoreable[0]
        notify(
            f"Best clip: {Path(best.output_file).name} (score {best.score:.0f})",
            level="success",
            reason="This clip will be processed first through Title_Generator "
                   "and Clip_Factory before entering the post queue."
        )

    return scoreable


def _score_clip(clip, history: dict) -> tuple:
    """Return (final_score, breakdown_string)."""
    # 1. Audio energy component (from highlight score, max 50)
    hl = clip.highlight
    audio_component = min(50.0, getattr(hl, "score", 50.0) * 0.5)

    # 2. Trigger bonus
    trigger = getattr(hl, "trigger", "highlight")
    trigger_component = TRIGGER_BONUS.get(trigger, 5.0)

    # 3. Historical performance boost (max 15)
    hist_component = _history_boost(trigger, history)

    total = round(audio_component + trigger_component + hist_component, 1)

    breakdown = (
        f"audio={audio_component:.0f} "
        f"trigger={trigger_component:.0f} ({trigger}) "
        f"history={hist_component:.0f}"
    )
    return total, breakdown


def _history_boost(trigger: str, history: dict) -> float:
    """
    Give a small boost to trigger types that have historically performed well
    (high average view count). Max +15 points.
    """
    if not history:
        return 0.0
    data = history.get(trigger, {})
    avg_views = data.get("avg_views", 0)
    # Scale: 0 views → 0 boost, 10k views → +15 boost (capped)
    boost = min(15.0, (avg_views / 10_000) * 15.0)
    return round(boost, 1)


def _load_history(game: str) -> dict:
    """Load historical performance data from clip_history.json."""
    try:
        if Path(HISTORY_FILE).exists():
            with open(HISTORY_FILE) as f:
                data = json.load(f)
                return data.get(game, {})
    except Exception:
        pass
    return {}


def update_historical_performance(
    game: str,
    trigger: str,
    views: int,
    likes: int = 0,
) -> None:
    """
    Call this after a clip has been live for 24h+ to feed performance
    data back into the ranking model.

    Parameters
    ----------
    game    : game name matching config.json
    trigger : the clip's trigger type (e.g. "kill", "donation")
    views   : view count after 24 hours
    likes   : like count after 24 hours (optional)
    """
    history: dict = {}
    if Path(HISTORY_FILE).exists():
        try:
            with open(HISTORY_FILE) as f:
                history = json.load(f)
        except Exception:
            history = {}

    game_data = history.setdefault(game, {})
    entry = game_data.setdefault(trigger, {"total_clips": 0, "total_views": 0,
                                            "total_likes": 0, "avg_views": 0})
    entry["total_clips"] += 1
    entry["total_views"] += views
    entry["total_likes"] += likes
    entry["avg_views"] = entry["total_views"] // entry["total_clips"]

    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

    notify(
        f"Performance logged: {trigger} ({views:,} views) for {game}",
        level="info",
        reason="Historical data updated in clip_history.json. "
               "Future clips with the same trigger type will receive a ranking boost "
               "proportional to this clip's performance."
    )
