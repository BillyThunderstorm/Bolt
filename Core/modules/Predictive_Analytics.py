#!/usr/bin/env python3
"""
modules/Predictive_Analytics.py — Tier 4.4 view-count forecasting
==================================================================
Predicts the likely 24-hour view count for a new clip, based on the
historical performance of similar clips.

Approach
--------
We don't need a neural net. The Tier 4.4 spec asks for "predict likely
view count" and "alert if prediction is unusually high." A simple
per-(game, trigger) rolling average with a confidence interval does
both — and it's *explainable*, so the alert reason reads like a sentence
("this is 2σ above the average Marvel Rivals kill clip") instead of a
black box.

Pipeline
--------
1. load_outcomes()         — read performance_outcomes.jsonl
2. group_by_key(rows, key) — per-(game, trigger) or per-(game, trigger,
                             platform) buckets
3. predict(clip_features)  — given a new clip's features, return a
                             Prediction dataclass with:
                               - median_views (the central estimate)
                               - low_views, high_views (IQR or 1σ)
                               - confidence (0..1: how much data we have)
                               - percentile (0..1: how this clip ranks
                                 against historical peers)
                               - is_potential_viral (True if upper
                                 bound exceeds the "viral" threshold)

The "viral" threshold is the 90th percentile of all historical view
counts. Anything predicted to clear it gets flagged with a reason.

Wired to Bolt via the post-queue: any clip in the queue that scores
>= viral_threshold gets a notify() with the prediction reasoning, so
Billy can choose to prioritize it (or pull it forward in the review
window).

No external ML framework. No API calls. The same JSONL the existing
performance logging writes is what this reads.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Repo-root-relative data location. Same convention as Analytics_Tracker.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "Data"
PERFORMANCE_OUTCOMES_FILE = DATA_DIR / "performance_outcomes.jsonl"

# Default viral threshold: 90th percentile of historical view counts.
# This is a relative bar, so it adapts as the channel grows — what was
# viral 6 months ago gets reclassified as "normal" once the channel
# reaches a new baseline.
DEFAULT_VIRAL_PERCENTILE = 0.90

# Minimum sample size for a confident per-(game, trigger) prediction.
# Below this, we fall back to a per-game prediction (or per-trigger,
# or global) so the caller never gets an empty answer.
MIN_SAMPLES_FOR_GROUP = 3

# Minimum total samples needed for the viral threshold itself to be
# meaningful. Below this we just say "not enough data" and skip the
# viral flag.
MIN_SAMPLES_FOR_VIRAL_THRESHOLD = 10


# ── Data loading ─────────────────────────────────────────────────────────────


def _load_outcomes(
    path: Path = PERFORMANCE_OUTCOMES_FILE,
    days: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Load performance outcomes, optionally filtered to the last N days."""
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    cutoff = None
    if days is not None:
        cutoff = datetime.now().timestamp() - (days * 86400)
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if cutoff is not None:
                ts_str = rec.get("timestamp", "")
                try:
                    if datetime.fromisoformat(ts_str).timestamp() < cutoff:
                        continue
                except (ValueError, TypeError):
                    continue
            rows.append(rec)
    return rows


def _group_key(rec: Dict[str, Any], dims: Tuple[str, ...]) -> Tuple[str, ...]:
    return tuple(str(rec.get(d, "unknown")) for d in dims)


def _group_views(
    rows: List[Dict[str, Any]],
    dims: Tuple[str, ...],
) -> Dict[Tuple[str, ...], List[int]]:
    """
    Group rows by a tuple of dimensions and return view-count lists
    per group. Also includes shorter tuples representing less-specific
    groupings so the predictor can fall back when a key is sparse.

    Example: dims=("game", "trigger") generates keys of length 2
    (the full grouping) and length 1 (the (game,) fallback). The
    predictor can then look up (game, trigger) and gracefully fall
    back to (game,) when the full grouping is too small.
    """
    out: Dict[Tuple[str, ...], List[int]] = {}
    for r in rows:
        full_key = _group_key(r, dims)
        views = r.get("views", 0) or 0
        out.setdefault(full_key, []).append(views)
        # Less-specific keys: drop one dim at a time.
        for i in range(1, len(dims)):
            short_key = full_key[:i]
            out.setdefault(short_key, []).append(views)
    return out


def _pick_group(
    groups: Dict[Tuple[str, ...], List[int]],
    row_key: Tuple[str, ...],
) -> Tuple[Tuple[str, ...], List[int]]:
    """Find the most-specific group that has enough data, falling back
    to less-specific groups when the exact one is empty or too small.

    `row_key` is a tuple whose length determines the granularity
    the caller wants (e.g. (game, trigger) means "I want a per-trigger
    estimate; if too small, fall back to per-game"). The function
    only ever returns a key of the same length as `row_key` or
    shorter — never drops a dimension that the caller asked for.
    """
    # Most-specific: the full row_key.
    if row_key in groups and len(groups[row_key]) >= MIN_SAMPLES_FOR_GROUP:
        return row_key, groups[row_key]

    # Fall back by dropping one dim at a time (i.e. shortening the key).
    for i in range(1, len(row_key)):
        shorter = row_key[:i]
        if shorter in groups and len(groups[shorter]) >= MIN_SAMPLES_FOR_GROUP:
            return shorter, groups[shorter]

    # Nothing big enough — return whatever we found (possibly empty).
    if row_key in groups:
        return row_key, groups[row_key]
    for i in range(1, len(row_key)):
        shorter = row_key[:i]
        if shorter in groups:
            return shorter, groups[shorter]
    return row_key, []


def _percentile(values: List[int], p: float) -> float:
    """Linear-interpolated percentile. p in [0, 1]."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return float(s[0])
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return float(s[f])
    return s[f] + (s[c] - s[f]) * (k - f)


# ── Prediction dataclass ─────────────────────────────────────────────────────


@dataclass
class Prediction:
    """Result of predicting the 24-hour view count for a clip."""
    game: str
    trigger: str
    platform: Optional[str]
    median_views: float
    low_views: float         # 25th percentile
    high_views: float        # 75th percentile
    confidence: float        # 0..1: how reliable this estimate is
    percentile: float        # 0..1: where this clip ranks vs history
    is_potential_viral: bool
    viral_threshold: float   # the 90th-percentile bar
    sample_size: int
    group_used: Tuple[str, ...]  # which (game, trigger, platform) combo we used
    summary: str = ""
    insufficient_data: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── The predictor ────────────────────────────────────────────────────────────


def predict(
    clip: Dict[str, Any],
    rows: Optional[List[Dict[str, Any]]] = None,
    viral_percentile: float = DEFAULT_VIRAL_PERCENTILE,
) -> Prediction:
    """
    Predict the 24-hour view count for a clip.

    `clip` is a dict with at least `game` and `trigger`, optionally
    `platform` and any other feature keys (these are ignored for now
    but reserved for future scoring features).

    `rows` is the historical performance data; if None, it's loaded
    from the default JSONL file.

    Returns a Prediction dataclass. The `summary` field is a
    human-readable sentence ready to drop into a notify() message.
    """
    game = str(clip.get("game", "unknown"))
    trigger = str(clip.get("trigger", "unknown"))
    platform = clip.get("platform")

    if rows is None:
        rows = _load_outcomes()

    if not rows:
        return Prediction(
            game=game, trigger=trigger, platform=platform,
            median_views=0.0, low_views=0.0, high_views=0.0,
            confidence=0.0, percentile=0.0,
            is_potential_viral=False, viral_threshold=0.0,
            sample_size=0, group_used=(game, trigger),
            insufficient_data=True,
            summary=(
                "No performance history yet — log a few clips with "
                "scripts/log_clip_performance.py to enable predictions."
            ),
        )

    # Most specific grouping is (game, trigger, platform).
    dims: Tuple[str, ...] = ("game", "trigger", "platform")
    # Build the lookup key. The platform dim is dropped when not specified
    # so the most-specific (game, trigger) group is checked first.
    if platform:
        row_key: Tuple[str, ...] = (game, trigger, str(platform))
    else:
        row_key = (game, trigger)
    groups = _group_views(rows, dims)
    used_key, view_list = _pick_group(groups, row_key)

    if not view_list or len(view_list) < MIN_SAMPLES_FOR_GROUP:
        return Prediction(
            game=game, trigger=trigger, platform=platform,
            median_views=0.0, low_views=0.0, high_views=0.0,
            confidence=0.0, percentile=0.0,
            is_potential_viral=False, viral_threshold=0.0,
            sample_size=len(view_list), group_used=used_key,
            insufficient_data=True,
            summary=(
                f"Need {MIN_SAMPLES_FOR_GROUP} samples for {game} + {trigger}; "
                f"have {len(view_list)}."
            ),
        )

    median_views = float(statistics.median(view_list))
    low_views = float(_percentile(view_list, 0.25))
    high_views = float(_percentile(view_list, 0.75))

    # Confidence: more samples = more confident. Caps at 1.0 around 20 samples.
    confidence = min(1.0, len(view_list) / 20.0)

    # Viral threshold: 90th percentile of all historical view counts.
    all_views = [r.get("views", 0) or 0 for r in rows]
    if len(all_views) >= MIN_SAMPLES_FOR_VIRAL_THRESHOLD:
        viral_threshold = float(_percentile(all_views, viral_percentile))
    else:
        viral_threshold = 0.0  # not enough data to define "viral"

    # Where would this clip rank? Use the high end of the predicted
    # range (75th percentile) — that's our optimistic-but-not-crazy
    # point estimate for ranking.
    percentile = (
        sum(1 for v in view_list if v <= high_views) / len(view_list)
    )
    is_viral = viral_threshold > 0 and high_views >= viral_threshold

    summary = _summarize(
        game=game,
        trigger=trigger,
        platform=platform,
        used_key=used_key,
        n=len(view_list),
        median=median_views,
        high=high_views,
        viral_threshold=viral_threshold,
        is_viral=is_viral,
        confidence=confidence,
    )

    return Prediction(
        game=game, trigger=trigger, platform=platform,
        median_views=round(median_views, 0),
        low_views=round(low_views, 0),
        high_views=round(high_views, 0),
        confidence=round(confidence, 2),
        percentile=round(percentile, 2),
        is_potential_viral=is_viral,
        viral_threshold=round(viral_threshold, 0),
        sample_size=len(view_list),
        group_used=used_key,
        summary=summary,
    )


def _summarize(
    game: str,
    trigger: str,
    platform: Optional[str],
    used_key: Tuple[str, ...],
    n: int,
    median: float,
    high: float,
    viral_threshold: float,
    is_viral: bool,
    confidence: float,
) -> str:
    base = (
        f"Predicted {int(median):,} views (range {int(median):,}–{int(high):,}) "
        f"for {game} {trigger} clip"
    )
    if platform:
        base += f" on {platform}"
    base += f" — based on {n} historical clip"
    if n != 1:
        base += "s"
    # Note when we fell back to a less-specific group
    if len(used_key) < 3:
        base += f" (matched at {', '.join(used_key)} level)"
    base += "."

    if is_viral:
        base += (
            f" 🌟 POTENTIALLY VIRAL — high end ({int(high):,}) clears the "
            f"channel's 90th-percentile viral bar ({int(viral_threshold):,}). "
            f"Confidence: {int(confidence * 100)}%."
        )
    return base


# ── Convenience: predict a batch of clips from the post queue ────────────────


def predict_queue(
    clips: List[Dict[str, Any]],
    days: Optional[int] = None,
) -> List[Prediction]:
    """Predict for each clip in a queue. Returns one Prediction per clip
    in the same order."""
    rows = _load_outcomes(days=days)
    return [predict(clip, rows=rows) for clip in clips]


# ── CLI ──────────────────────────────────────────────────────────────────────


def _main() -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Predict 24-hour view count for a clip."
    )
    parser.add_argument("--game", required=True, help="Game name (e.g. 'Marvel Rivals')")
    parser.add_argument("--trigger", required=True, help="Trigger type (e.g. 'kill', 'multi_kill', 'donation')")
    parser.add_argument("--platform", default=None, help="Platform (e.g. 'tiktok', 'youtube')")
    parser.add_argument(
        "--days", type=int, default=None,
        help="Only use historical data from the last N days",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output JSON instead of a human summary",
    )
    args = parser.parse_args()

    rows = _load_outcomes(days=args.days)
    p = predict(
        {"game": args.game, "trigger": args.trigger, "platform": args.platform},
        rows=rows,
    )

    if args.json:
        json.dump(p.to_dict(), sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        print("=" * 60)
        print(f"  PREDICTED VIEWS: {args.game} {args.trigger} clip")
        if args.platform:
            print(f"  Platform: {args.platform}")
        print("=" * 60)
        if p.insufficient_data:
            print(f"  {p.summary}")
        else:
            print(f"  Median (50th pct):  {int(p.median_views):>10,}")
            print(f"  Range (25-75 pct):  {int(p.low_views):>5,} – {int(p.high_views):>10,}")
            print(f"  Confidence:         {int(p.confidence * 100)}%  ({p.sample_size} sample(s))")
            print(f"  Percentile rank:    {int(p.percentile * 100)}%")
            print(f"  Viral threshold:    {int(p.viral_threshold):>10,} (90th pct of all clips)")
            print(f"  Viral pick:         {'YES 🌟' if p.is_potential_viral else 'no'}")
            print()
            print(f"  {p.summary}")
        print("=" * 60)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_main())
