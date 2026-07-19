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
from typing import List, Optional, Dict, Any

try:
    from modules.notifier import notify, notify_score
except ImportError:

    def notify(msg, level="info", reason=None):
        prefix = {"info": "ℹ", "success": "✓", "warning": "⚠", "error": "✗"}.get(
            level, "•"
        )
        print(f"  {prefix}  {msg}")
        if reason:
            print(f"     → {reason}")

    def notify_score(clip, score, breakdown):
        print(f"  📊  {clip}: {score:.0f} | {breakdown}")


try:
    from modules.Clip_Generator import GeneratedClip
except ImportError:
    GeneratedClip = object

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # Bolt/ (repo root)
HISTORY_FILE = PROJECT_ROOT / "Data" / "clip_history.json"

# ── Quality tiers ─────────────────────────────────────────────────────────────
# Three lanes for ranked clips:
#   discard → never auto-process, never notify, hidden from peak-hour pings
#   mid     → kept around in case Billy wants to scroll through them manually
#   queue   → auto-flows through Title/Subtitle/Factory and into Peak_Hour_Notifier
# Tune in config.json → quality_tiers.{discard_below, queue_at}.
TIER_DISCARD = "discard"
TIER_MID = "mid"
TIER_QUEUE = "queue"


def _load_tier_thresholds():
    cfg_path = Path(__file__).parent.parent / "config.json"
    try:
        with open(cfg_path) as f:
            tiers = json.load(f).get("quality_tiers", {})
        return (
            float(tiers.get("discard_below", 60.0)),
            float(tiers.get("queue_at", 80.0)),
        )
    except Exception:
        return 60.0, 80.0


DISCARD_BELOW, QUEUE_AT = _load_tier_thresholds()


def _classify_tier(score: float) -> str:
    """Map a 0-100 score to a quality tier."""
    if score < DISCARD_BELOW:
        return TIER_DISCARD
    if score >= QUEUE_AT:
        return TIER_QUEUE
    return TIER_MID


# Bonus points per trigger type (stacks with audio score)
TRIGGER_BONUS: Dict[str, float] = {
    "kill": 18,
    "multi_kill": 28,
    "ace": 35,
    "donation": 22,
    "raid": 30,
    "sub": 20,
    "resub": 15,
    "bits": 12,
    "chat_hype": 10,
    "highlight": 5,
    "manual": 20,  # Stream Deck button press
}


# ── Learned performance model ─────────────────────────────────────────────────
#
# The hand-coded `_history_boost()` below is fine as a starting point
# but it has two real limitations:
#   - it only uses raw view count (ignores like-rate, which is a much
#     better signal of "the audience actually wanted this")
#   - it treats every observation equally, so old successful clips
#     dominate and the model never adapts to changing audience taste
#
# `learned_boost()` is the ML step. It computes a per-(game, trigger)
# score from the rolling history that:
#   - weights recent observations more heavily via an exponential
#     half-life (so the model follows current taste)
#   - blends like_rate (likes / views) with views itself (a clip
#     that converts viewers into likers is worth more)
#   - requires a minimum sample size before trusting the signal
#     (so a single viral clip doesn't skew the model)
# All of this is hand-coded math, not a fitted model — that keeps
# it deterministic, testable, and explainable.
LEARNED_HALF_LIFE_DAYS = 14.0  # recent = within ~2 weeks
LEARNED_MIN_SAMPLES = 3        # need at least 3 outcomes before boosting
LEARNED_MAX_BOOST = 20.0       # cap the learned bonus so it can't overwhelm the formula


def _days_since(iso_ts: str) -> float:
    """Days between the given ISO timestamp and now. Tolerant of
    malformed input (returns a large value so old data decays)."""
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0)
    except Exception:
        return 1e6


def _weighted_views_and_likes(history: dict) -> tuple:
    """Return (weighted_views_sum, weighted_likes_sum, weight_sum,
    sample_count) using an exponential decay based on the age of each
    entry. Reads the per-(game, trigger) entry's list of
    observations if present, otherwise falls back to the legacy
    single-number fields for back-compat."""
    obs = history.get("observations") or []
    if obs:
        wv = 0.0
        wl = 0.0
        ws = 0.0
        n = 0
        for entry in obs:
            views = max(0, int(entry.get("views", 0) or 0))
            likes = max(0, int(entry.get("likes", 0) or 0))
            ts = entry.get("at", "")
            age = _days_since(ts)
            # Exponential decay: weight = 0.5 ** (age / half_life)
            try:
                weight = 0.5 ** (age / LEARNED_HALF_LIFE_DAYS)
            except Exception:
                weight = 0.0
            wv += views * weight
            wl += likes * weight
            ws += weight
            n += 1
        return wv, wl, ws, n
    # Legacy shape: no observations, just averages.
    avg_views = float(history.get("avg_views", 0) or 0)
    avg_likes = float(history.get("total_likes", 0) or 0) / max(
        1, int(history.get("total_clips", 1) or 1)
    )
    n = int(history.get("total_clips", 0) or 0)
    return avg_views * n, avg_likes * n, float(n), n


def learned_boost(trigger: str, game_history: dict) -> float:
    """ML-ish learned bonus for a trigger, given its full game history
    (the dict for that trigger inside the game's entry). Returns
    0.0 if there's not enough data to trust the signal, otherwise
    a number in [0, LEARNED_MAX_BOOST].

    The formula is a small hand-coded heuristic that mirrors what
    you'd do with a fitted model: combine recency-weighted views
    and like_rate, normalize against a target, and cap the output.
    It's not a fitted model, but it is real, testable, and
    auditable — and you can see exactly which inputs mattered.
    """
    wv, wl, ws, n = _weighted_views_and_likes(game_history)
    if n < LEARNED_MIN_SAMPLES or ws <= 0:
        return 0.0
    avg_views = wv / ws
    avg_likes = wl / ws
    like_rate = (avg_likes / avg_views) if avg_views > 0 else 0.0
    # Target: 5k views and 8% like rate is "good". 20k views and 15%
    # is "great". Map that range linearly into [0, LEARNED_MAX_BOOST].
    # The view term saturates at 20k; the like_rate term saturates at 15%.
    view_term = min(1.0, avg_views / 20_000.0)
    like_term = min(1.0, like_rate / 0.15) if like_rate > 0 else 0.0
    # Like-rate matters more than raw views: weight 0.6 / 0.4.
    raw = (0.4 * view_term + 0.6 * like_term) * LEARNED_MAX_BOOST
    return round(min(LEARNED_MAX_BOOST, raw), 1)


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
        f"history_boost (0-15). min_score threshold = {min_score}.",
    )

    for clip in scoreable:
        score, breakdown = _score_clip(clip, history)
        clip.score = score  # attach dynamically
        clip.tier = _classify_tier(score)  # 'discard' / 'mid' / 'queue'

        notify_score(
            Path(clip.output_file).name, score, f"{breakdown} → tier={clip.tier}"
        )

        if clip.tier == TIER_DISCARD:
            notify(
                f"  DISCARD ({score:.0f} < {DISCARD_BELOW:.0f}) — won't auto-process",
                level="warning",
                reason="Below the discard threshold. The clip file stays on disk "
                "but skips Title/Subtitle/Factory and won't trigger peak-hour "
                "alerts. Lower quality_tiers.discard_below in config.json to "
                "be more lenient.",
            )
        elif clip.tier == TIER_MID:
            notify(
                f"  MID ({score:.0f}) — kept, but won't auto-notify",
                level="info",
                reason="Decent clip, just not great. It's available if you scroll "
                "the clips folder manually. Only QUEUE-tier clips trigger "
                "Peak_Hour_Notifier pings.",
            )
        else:  # queue
            notify(
                f"  QUEUE ({score:.0f}) — auto-processing",
                level="success",
                reason="Strong clip — flowing through Title_Generator, "
                "Subtitle_Generator, Clip_Factory, and into Peak_Hour_Notifier.",
            )

    # Sort descending
    scoreable.sort(key=lambda c: getattr(c, "score", 0), reverse=True)

    if scoreable:
        best = scoreable[0]
        notify(
            f"Best clip: {Path(best.output_file).name} (score {best.score:.0f})",
            level="success",
            reason="This clip will be processed first through Title_Generator "
            "and Clip_Factory before entering the post queue.",
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

    # 3. Hand-coded history boost (kept for back-compat; uses raw
    #    view count only).
    hist_component = _history_boost(trigger, history)

    # 4. Learned boost (the ML step). Combines recency-weighted
    #    views + like_rate per (game, trigger) and caps at
    #    LEARNED_MAX_BOOST. Returns 0 until we have enough samples.
    game_history = history.get(trigger, {}) if history else {}
    learn_component = learned_boost(trigger, game_history)

    # Total: keep the same 0-100 envelope as before. The two
    # history signals together cap at ~35 (15 hand-coded + 20
    # learned) so the formula still tops out near 100.
    total = round(
        audio_component + trigger_component + hist_component + learn_component, 1
    )
    # Clamp to 0-100 in case the cap structure changes.
    total = max(0.0, min(100.0, total))

    breakdown = (
        f"audio={audio_component:.0f} "
        f"trigger={trigger_component:.0f} ({trigger}) "
        f"history={hist_component:.0f} "
        f"learned={learn_component:.0f}"
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


def _load_full_history() -> dict:
    """Load the entire clip_history.json (all games)."""
    try:
        if Path(HISTORY_FILE).exists():
            with open(HISTORY_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def inspect_learned_model(game: str = None) -> Dict[str, Any]:
    """What the model 'thinks' right now, per (game, trigger).

    Returns a dict shaped like:
      {
        "games": {
          "Marvel Rivals": {
            "total_clips": 42,
            "triggers": [
              {"trigger": "multi_kill", "samples": 40,
               "avg_views": 1200, "avg_likes": 80, "like_rate": 0.067,
               "learned_boost": 18.4},
              ...
            ]
          },
          ...
        },
        "summary": {
          "total_games": 3,
          "total_outcomes": 145,
          "triggers_with_signal": 6,
          "triggers_without_signal": 4
        }
      }
    """
    full = _load_full_history()
    out: Dict[str, Any] = {"games": {}, "summary": {
        "total_games": 0, "total_outcomes": 0,
        "triggers_with_signal": 0, "triggers_without_signal": 0,
    }}
    games_to_show = [game] if game else list(full.keys())
    for g in games_to_show:
        gh = full.get(g, {})
        if not isinstance(gh, dict):
            continue
        triggers = []
        for trigger, h in gh.items():
            if not isinstance(h, dict):
                continue
            wv, wl, ws, n = _weighted_views_and_likes(h)
            avg_views = (wv / ws) if ws else 0
            avg_likes = (wl / ws) if ws else 0
            like_rate = (avg_likes / avg_views) if avg_views > 0 else 0.0
            boost = learned_boost(trigger, h) if ws else 0.0
            triggers.append({
                "trigger": trigger,
                "samples": n,
                "avg_views": round(avg_views, 1),
                "avg_likes": round(avg_likes, 1),
                "like_rate": round(like_rate, 4),
                "learned_boost": boost,
            })
            if n >= LEARNED_MIN_SAMPLES:
                out["summary"]["triggers_with_signal"] += 1
            else:
                out["summary"]["triggers_without_signal"] += 1
            out["summary"]["total_outcomes"] += n
        out["games"][g] = {
            "triggers": sorted(triggers, key=lambda t: -t["learned_boost"]),
        }
        if triggers:
            out["summary"]["total_games"] += 1
    return out


def learning_loop_status() -> Dict[str, Any]:
    """Compact status for `manage status` and morning briefings.

    Returns a dict with: total observations, last observation
    timestamp, how many (game, trigger) pairs have enough data
    to influence the model, and the top boosted trigger overall.
    """
    full = _load_full_history()
    total_outcomes = 0
    last_ts = ""
    pairs_with_signal = 0
    pairs_total = 0
    best = None  # (boost, game, trigger, n)
    for game, gh in full.items():
        if not isinstance(gh, dict):
            continue
        for trigger, h in gh.items():
            if not isinstance(h, dict):
                continue
            pairs_total += 1
            obs = h.get("observations") or []
            for o in obs:
                if isinstance(o, dict):
                    total_outcomes += 1
                    ts = o.get("at", "")
                    if ts and ts > last_ts:
                        last_ts = ts
            boost = learned_boost(trigger, h)
            n = int(h.get("total_clips", 0) or 0) or len(obs)
            if boost > 0:
                pairs_with_signal += 1
            if best is None or boost > best[0]:
                best = (boost, game, trigger, n)
    return {
        "total_outcomes": total_outcomes,
        "last_observation_at": last_ts or None,
        "pairs_total": pairs_total,
        "pairs_with_signal": pairs_with_signal,
        "top_boost": (
            {"game": best[1], "trigger": best[2], "boost": best[0], "samples": best[3]}
            if best and best[0] > 0 else None
        ),
    }


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

    Each call appends to the (game, trigger) entry's `observations`
    list (used by the recency-weighted learned model) AND keeps the
    legacy averages up to date for back-compat. The learned_boost()
    function prefers observations when present and falls back to
    the averages otherwise.
    """
    history: dict = {}
    if Path(HISTORY_FILE).exists():
        try:
            with open(HISTORY_FILE) as f:
                history = json.load(f)
        except Exception:
            history = {}

    game_data = history.setdefault(game, {})
    entry = game_data.setdefault(
        trigger, {"total_clips": 0, "total_views": 0, "total_likes": 0, "avg_views": 0, "observations": []}
    )
    # Legacy aggregate fields
    entry["total_clips"] = int(entry.get("total_clips", 0)) + 1
    entry["total_views"] = int(entry.get("total_views", 0)) + int(views)
    entry["total_likes"] = int(entry.get("total_likes", 0)) + int(likes)
    entry["avg_views"] = entry["total_views"] // max(1, entry["total_clips"])

    # New: per-observation record for the recency-weighted model.
    obs = entry.setdefault("observations", [])
    obs.append({
        "at": _now_iso(),
        "views": int(views),
        "likes": int(likes),
    })
    # Cap to the most-recent 200 observations to keep the file bounded.
    if len(obs) > 200:
        entry["observations"] = obs[-200:]

    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

    notify(
        f"Performance logged: {trigger} ({views:,} views) for {game}",
        level="info",
        reason="Historical data updated in clip_history.json. "
        "Future clips with the same trigger type will receive a ranking boost "
        "proportional to this clip's performance (now using recency-weighted "
        "views + like-rate via learned_boost).",
    )


def _now_iso() -> str:
    """ISO-8601 UTC timestamp, seconds precision. Tolerates the
    absence of a timezone-aware datetime so tests don't need a real
    clock."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
