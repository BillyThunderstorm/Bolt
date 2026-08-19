#!/usr/bin/env python3
"""
modules/Performance_Sync.py — Pull social stats → learning loop
================================================================
Connects TikTok + YouTube analytics to Bolt's performance_outcomes.jsonl
and clip_history.json learning path.

Flow:
  1. Fetch recent videos with view/like counts (platform API)
  2. Match each video to a ready_to_post / posted clip when possible
     (title + post time; else infer trigger from clip filename)
  3. Upsert one outcome row per platform video id (no double-count)
  4. On first log for a video, feed Clip_Ranker / Think_Learn_Decide

State files:
  Data/tiktok_stats_state.json
  Data/youtube_stats_state.json
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "Data"
PERFORMANCE_OUTCOMES_FILE = DATA_DIR / "performance_outcomes.jsonl"
STATE_FILE = DATA_DIR / "tiktok_stats_state.json"  # TikTok default (back-compat)
YOUTUBE_STATE_FILE = DATA_DIR / "youtube_stats_state.json"
READY_TO_POST_FILE = DATA_DIR / "ready_to_post.json"
# Core/config.json is canonical. Data/config.json is a leftover and must
# not override the live game (it still says Marvel Rivals).
CONFIG_CANDIDATES = (
    PROJECT_ROOT / "Core" / "config.json",
    PROJECT_ROOT / "config.json",
)

# Triggers we recognize in filenames / captions.
KNOWN_TRIGGERS = (
    "multi_kill",
    "audio_spike",
    "chat_hype",
    "highlight",
    "donation",
    "manual",
    "resub",
    "bits",
    "raid",
    "kill",
    "ace",
    "sub",
)

_TRIGGER_IN_NAME = re.compile(
    r"(?<![a-z0-9])(?:"
    + r"|".join(re.escape(t) for t in sorted(KNOWN_TRIGGERS, key=len, reverse=True))
    + r")(?![a-z0-9])",
    re.IGNORECASE,
)

# (canonical name, lowercase needles). Longer / more specific first.
# Used when a synced video is not matched to a queue row — never assume
# "whatever game is in config.json right now".
GAME_ALIASES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        "007 First Light",
        (
            "007 first light",
            "007firstlight",
            "first light",
            "bondgames",
            "bond game",
        ),
    ),
    (
        "Split Fiction",
        ("split fiction", "splitfiction", "hazelight"),
    ),
    (
        "Hades 2",
        (
            "hades 2",
            "hades2",
            "hades2game",
            "hadesgame",
            "hades game",
            "#hades",
            " hades ",
            "scylla",
        ),
    ),
    (
        "Dead by Daylight",
        (
            "dead by daylight",
            "deadbydaylight",
            "#dbd",
            " dbd ",
        ),
    ),
    (
        "Marvel Rivals",
        (
            "marvel rivals",
            "marvelrivals",
            "marvelrival",
            "marvel rival",
            "rivals gaming",
            "rivals with",
            "deadpool",
            "ironman",
            "iron man",
            " rivals",
        ),
    ),
)


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _load_config_game() -> str:
    for path in CONFIG_CANDIDATES:
        if not path.exists():
            continue
        try:
            with open(path, encoding="utf-8") as f:
                game = json.load(f).get("game")
            if game:
                return str(game)
        except Exception:
            continue
    return "Unknown"


def _is_success(views: int, likes: int) -> bool:
    if views >= 1000:
        return True
    if views > 0 and likes > 0:
        return (likes / views) >= 0.05
    return False


def infer_trigger_from_path(clip_path: str) -> str:
    """Pull a trigger name out of a Bolt clip filename when possible."""
    name = Path(clip_path or "").name
    match = _TRIGGER_IN_NAME.search(name)
    if match:
        return match.group(0).lower()
    return "unknown"


def infer_game_from_text(*parts: Optional[str]) -> Optional[str]:
    """Guess a game from title / description / hashtags.

    Returns None when nothing matches — callers should store "Unknown"
    rather than today's config game.
    """
    blob = " ".join(p for p in parts if p).lower()
    if not blob:
        return None
    # Pad so needles like " hades " can match a title that starts/ends
    # with the word.
    padded = f" {blob} "
    hits: List[Tuple[int, str]] = []
    for canonical, needles in GAME_ALIASES:
        for needle in needles:
            if needle in padded or needle in blob:
                hits.append((len(needle), canonical))
                break
    if not hits:
        return None
    hits.sort(reverse=True)
    return hits[0][1]


def infer_trigger_from_text(*parts: Optional[str]) -> str:
    blob = " ".join(p for p in parts if p)
    if not blob:
        return "unknown"
    hit = _TRIGGER_IN_NAME.search(blob)
    return hit.group(0).lower() if hit else "unknown"


def resolve_video_metadata(
    *,
    title: str = "",
    description: str = "",
    clip_path: str = "",
    match: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    """Return (game, trigger) for a synced video.

    Matched queue rows can carry a game. Unmatched rows are inferred
    from the title — never from config.json.
    """
    trigger = infer_trigger_from_path(clip_path)
    if trigger == "unknown" and match:
        trigger = str(match.get("trigger") or "unknown")
    if trigger == "unknown":
        trigger = infer_trigger_from_text(title, description, clip_path)

    game = None
    if match:
        game = match.get("game") or None
    if not game:
        game = infer_game_from_text(title, description, clip_path)
    return (str(game) if game else "Unknown", trigger)


def _normalize_title(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[#@]\w+", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def _title_similarity(a: str, b: str) -> float:
    """Jaccard token overlap in [0, 1]."""
    ta = set(_normalize_title(a).split())
    tb = set(_normalize_title(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        # Handle trailing Z and naive strings
        cleaned = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def load_posted_clips(path: Path = READY_TO_POST_FILE) -> List[Dict[str, Any]]:
    """Load posted (or ready) queue items for matching against TikTok videos."""
    raw = _load_json(path, {})
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = raw.get("items") or raw.get("clips") or raw.get("queue") or []
    else:
        items = []

    posted: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").lower()
        platforms = item.get("platform_plan") or []
        tiktok_posted = any(
            isinstance(p, dict)
            and str(p.get("platform", "")).lower() == "tiktok"
            and str(p.get("status", "")).lower() in ("posted", "published")
            for p in platforms
        )
        if status in ("posted", "published") or tiktok_posted or item.get("posted_at"):
            posted.append(item)
    return posted


def match_video_to_clip(
    video: Any,
    posted_clips: List[Dict[str, Any]],
    max_hours_delta: float = 48.0,
    platform_preference: str = "tiktok",
) -> Optional[Dict[str, Any]]:
    """Best-effort match of a platform video to a Bolt queue item.

    Scoring:
      - title token overlap (primary)
      - create_time vs posted_at proximity (bonus / filter)
    """
    v_title = (
        getattr(video, "title", None)
        or getattr(video, "video_description", None)
        or getattr(video, "description", None)
        or ""
    )
    v_create = int(getattr(video, "create_time", 0) or 0)
    v_dt = (
        datetime.fromtimestamp(v_create, tz=timezone.utc) if v_create > 0 else None
    )
    pref = (platform_preference or "tiktok").lower()
    # Accept alternate names used in multi_platform_queue
    aliases = {
        "tiktok": ("tiktok",),
        "youtube": ("youtube", "youtube_shorts"),
        "youtube_shorts": ("youtube", "youtube_shorts"),
    }
    platform_names = aliases.get(pref, (pref,))

    best: Optional[Dict[str, Any]] = None
    best_score = 0.0

    for item in posted_clips:
        caption = item.get("title") or ""
        posted_at = _parse_iso(item.get("posted_at"))
        for p in item.get("platform_plan") or []:
            if not isinstance(p, dict):
                continue
            pname = str(p.get("platform", "")).lower()
            if pname in platform_names:
                caption = (
                    p.get("caption")
                    or p.get("title")
                    or p.get("description")
                    or caption
                )
                if posted_at is None:
                    posted_at = _parse_iso(p.get("posted_at"))

        sim = _title_similarity(v_title, caption)
        if sim < 0.25 and _normalize_title(v_title) != _normalize_title(caption):
            # Still allow exact-empty skips; weak titles need time proximity
            if sim < 0.15:
                continue

        score = sim
        if v_dt and posted_at:
            delta_h = abs((v_dt - posted_at).total_seconds()) / 3600.0
            if delta_h > max_hours_delta:
                continue
            # Closer in time → higher score
            score += max(0.0, 0.4 * (1.0 - delta_h / max_hours_delta))

        if score > best_score:
            best_score = score
            best = item

    return best if best_score >= 0.25 else None


def _load_outcomes(path: Path = PERFORMANCE_OUTCOMES_FILE) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _write_outcomes(rows: List[Dict[str, Any]], path: Path = PERFORMANCE_OUTCOMES_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _build_outcome_entry(
    *,
    video_id: str,
    views: int,
    likes: int,
    comments: int,
    shares: int,
    game: str,
    trigger: str,
    clip_path: str,
    share_url: str,
    title: str,
    note: str = "",
    platform: str = "TikTok",
    source: str = "tiktok_api",
    id_field: str = "tiktok_video_id",
) -> Dict[str, Any]:
    like_rate = round((likes / views) * 100, 2) if views > 0 else 0.0
    entry = {
        "timestamp": datetime.now().isoformat(),
        "game": game,
        "trigger": trigger,
        "views": int(views),
        "likes": int(likes),
        "like_rate": like_rate,
        "success": _is_success(views, likes),
        "clip_path": clip_path,
        "platform": platform,
        "note": note or f"synced from {platform} API",
        "share_url": share_url,
        "title": title,
        "comments": int(comments),
        "shares": int(shares),
        "source": source,
    }
    entry[id_field] = str(video_id)
    return entry


def _outcome_identity_keys(entry: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Return (field, value) pairs that uniquely identify a platform video."""
    keys: List[Tuple[str, str]] = []
    for field in ("tiktok_video_id", "youtube_video_id", "x_post_id"):
        val = str(entry.get(field) or "").strip()
        if val:
            keys.append((field, val))
    return keys


def upsert_outcome(
    entry: Dict[str, Any],
    path: Path = PERFORMANCE_OUTCOMES_FILE,
) -> Tuple[Dict[str, Any], bool]:
    """Insert or update an outcome keyed by platform video id fields.

    Matches on tiktok_video_id / youtube_video_id / x_post_id when present.
    Returns (saved_entry, is_new).
    """
    id_keys = _outcome_identity_keys(entry)
    rows = _load_outcomes(path)
    is_new = True
    if id_keys:
        for i, row in enumerate(rows):
            for field, val in id_keys:
                if str(row.get(field) or "") == val:
                    preserved_ts = row.get("timestamp") or entry["timestamp"]
                    merged = {**row, **entry, "timestamp": entry["timestamp"]}
                    merged["first_logged_at"] = (
                        row.get("first_logged_at") or preserved_ts
                    )
                    rows[i] = merged
                    entry = merged
                    is_new = False
                    break
            if not is_new:
                break
    if is_new:
        entry = {**entry, "first_logged_at": entry.get("timestamp")}
        rows.append(entry)
    _write_outcomes(rows, path)
    return entry, is_new


def _feed_learning(entry: Dict[str, Any], is_new: bool) -> None:
    """Push a *new* video outcome into Clip_Ranker + decision engine once."""
    if not is_new:
        return

    game = entry.get("game") or "Unknown"
    trigger = entry.get("trigger") or "unknown"
    views = int(entry.get("views") or 0)
    likes = int(entry.get("likes") or 0)

    try:
        from modules.Clip_Ranker import update_historical_performance

        update_historical_performance(game, trigger, views, likes)
    except Exception as exc:
        print(f"  [sync] clip history update skipped: {exc}")

    try:
        from modules.Think_Learn_Decide import ThinkLearnDecideEngine

        engine = ThinkLearnDecideEngine({})
        engine.learn_from_outcome(
            "clip_performance",
            bool(entry.get("success")),
            {
                "game": game,
                "trigger": trigger,
                "views": views,
                "likes": likes,
                "like_rate": entry.get("like_rate"),
                "platform": entry.get("platform") or "TikTok",
                "note": entry.get("note", ""),
                "tiktok_video_id": entry.get("tiktok_video_id"),
                "youtube_video_id": entry.get("youtube_video_id"),
            },
        )
    except Exception as exc:
        print(f"  [sync] learning loop skipped: {exc}")


def sync_tiktok_stats(
    *,
    limit: int = 50,
    min_age_hours: float = 0.0,
    dry_run: bool = False,
    access_token: Optional[str] = None,
    outcomes_path: Path = PERFORMANCE_OUTCOMES_FILE,
    state_path: Path = STATE_FILE,
    queue_path: Path = READY_TO_POST_FILE,
    default_game: Optional[str] = None,
    feed_learning: bool = True,
    refresh_memory: bool = True,
) -> Dict[str, Any]:
    """Fetch TikTok stats and upsert performance outcomes.

    Parameters
    ----------
    min_age_hours:
        Skip videos younger than this (e.g. 24 to wait for early metrics).
        0 = include everything.
    dry_run:
        Fetch + match only; do not write files or call learning.
    """
    from modules.TikTok_Analytics import TikTokAnalytics, TikTokAnalyticsError

    game_default = default_game or _load_config_game()
    posted = load_posted_clips(queue_path)
    state = _load_json(state_path, {"videos": {}, "last_sync_at": None})
    if not isinstance(state.get("videos"), dict):
        state["videos"] = {}

    try:
        client = TikTokAnalytics(access_token=access_token)
        videos = client.list_videos(limit=limit)
    except TikTokAnalyticsError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "platform": "TikTok",
            "fetched": 0,
            "logged_new": 0,
            "updated": 0,
            "skipped": 0,
            "videos": [],
        }

    now = datetime.now(timezone.utc)
    logged_new = 0
    updated = 0
    skipped = 0
    details: List[Dict[str, Any]] = []

    for video in videos:
        age_h = None
        if video.create_time:
            created = datetime.fromtimestamp(video.create_time, tz=timezone.utc)
            age_h = (now - created).total_seconds() / 3600.0
            if min_age_hours > 0 and age_h < min_age_hours:
                skipped += 1
                details.append(
                    {
                        "id": video.id,
                        "action": "skipped_young",
                        "age_hours": round(age_h, 1),
                        "views": video.view_count,
                    }
                )
                continue

        match = match_video_to_clip(video, posted, platform_preference="tiktok")
        clip_path = ""
        note = "synced from TikTok API (unmatched to queue)"

        if match:
            clip_path = str(match.get("clip_path") or "")
            note = f"synced from TikTok API (matched queue id={match.get('id', '?')})"

        game, trigger = resolve_video_metadata(
            title=video.title or "",
            description=getattr(video, "video_description", "") or "",
            clip_path=clip_path,
            match=match,
        )
        if game == "Unknown" and match and game_default:
            game = str(game_default)

        entry = _build_outcome_entry(
            video_id=video.id,
            views=video.view_count,
            likes=video.like_count,
            comments=video.comment_count,
            shares=video.share_count,
            game=game,
            trigger=trigger,
            clip_path=clip_path,
            share_url=video.share_url,
            title=video.title or video.video_description or "",
            note=note,
            platform="TikTok",
            source="tiktok_api",
            id_field="tiktok_video_id",
        )

        prev = state["videos"].get(video.id) or {}
        prev_views = int(prev.get("views") or -1)
        already_logged = bool(prev.get("logged_outcome"))

        action = "would_log" if dry_run else "logged"
        is_new = not already_logged
        # Also treat missing video_id in outcomes as new even if state is stale
        if not dry_run:
            saved, is_new = upsert_outcome(entry, path=outcomes_path)
            if feed_learning:
                _feed_learning(saved, is_new=is_new and not already_logged)
            state["videos"][video.id] = {
                "views": video.view_count,
                "likes": video.like_count,
                "comments": video.comment_count,
                "shares": video.share_count,
                "title": entry["title"],
                "clip_path": clip_path,
                "trigger": trigger,
                "game": game,
                "share_url": video.share_url,
                "logged_outcome": True,
                "last_synced_at": now.isoformat(),
                "create_time": video.create_time,
                "matched_queue_id": (match or {}).get("id"),
            }
            if is_new:
                logged_new += 1
                action = "logged_new"
            else:
                updated += 1
                action = "updated" if video.view_count != prev_views else "refreshed"
        else:
            if is_new:
                logged_new += 1
            else:
                updated += 1

        details.append(
            {
                "id": video.id,
                "action": action,
                "views": video.view_count,
                "likes": video.like_count,
                "trigger": trigger,
                "game": game,
                "clip_path": Path(clip_path).name if clip_path else "",
                "title": (entry["title"] or "")[:60],
                "matched": bool(match),
                "age_hours": round(age_h, 1) if age_h is not None else None,
            }
        )

    if not dry_run:
        state["last_sync_at"] = now.isoformat()
        _save_json(state_path, state)
        if refresh_memory and (logged_new or updated):
            try:
                from modules.Memory_Index import refresh_memory_index

                refresh_memory_index()
            except Exception as exc:
                print(f"  [sync] memory refresh skipped: {exc}")
        # Refresh dashboard totals
        try:
            from modules.Checkup_Writer import update_checkup

            update_checkup()
        except Exception as exc:
            print(f"  [sync] checkup update skipped: {exc}")

    return {
        "ok": True,
        "error": None,
        "platform": "TikTok",
        "fetched": len(videos),
        "logged_new": logged_new,
        "updated": updated,
        "skipped": skipped,
        "dry_run": dry_run,
        "outcomes_file": str(outcomes_path),
        "state_file": str(state_path),
        "videos": details,
    }


def sync_youtube_stats(
    *,
    limit: int = 50,
    min_age_hours: float = 0.0,
    dry_run: bool = False,
    access_token: Optional[str] = None,
    outcomes_path: Path = PERFORMANCE_OUTCOMES_FILE,
    state_path: Path = YOUTUBE_STATE_FILE,
    queue_path: Path = READY_TO_POST_FILE,
    default_game: Optional[str] = None,
    feed_learning: bool = True,
    refresh_memory: bool = True,
    shorts_only: bool = False,
) -> Dict[str, Any]:
    """Fetch YouTube / Shorts stats and upsert performance outcomes."""
    from modules.YouTube_Analytics import YouTubeAnalytics, YouTubeAnalyticsError

    game_default = default_game or _load_config_game()
    posted = load_posted_clips(queue_path)
    state = _load_json(state_path, {"videos": {}, "last_sync_at": None})
    if not isinstance(state.get("videos"), dict):
        state["videos"] = {}

    try:
        client = YouTubeAnalytics(access_token=access_token)
        videos = client.list_videos(limit=limit, shorts_only=shorts_only)
    except YouTubeAnalyticsError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "platform": "YouTube",
            "fetched": 0,
            "logged_new": 0,
            "updated": 0,
            "skipped": 0,
            "videos": [],
        }

    now = datetime.now(timezone.utc)
    logged_new = 0
    updated = 0
    skipped = 0
    details: List[Dict[str, Any]] = []

    for video in videos:
        age_h = None
        if video.create_time:
            created = datetime.fromtimestamp(video.create_time, tz=timezone.utc)
            age_h = (now - created).total_seconds() / 3600.0
            if min_age_hours > 0 and age_h < min_age_hours:
                skipped += 1
                details.append(
                    {
                        "id": video.id,
                        "action": "skipped_young",
                        "age_hours": round(age_h, 1),
                        "views": video.view_count,
                    }
                )
                continue

        match = match_video_to_clip(
            video, posted, platform_preference="youtube"
        )
        clip_path = ""
        note = "synced from YouTube API (unmatched to queue)"

        if match:
            clip_path = str(match.get("clip_path") or "")
            note = (
                f"synced from YouTube API (matched queue id={match.get('id', '?')})"
            )

        game, trigger = resolve_video_metadata(
            title=video.title or "",
            description=getattr(video, "description", "") or "",
            clip_path=clip_path,
            match=match,
        )
        if game == "Unknown" and match and game_default:
            game = str(game_default)

        entry = _build_outcome_entry(
            video_id=video.id,
            views=video.view_count,
            likes=video.like_count,
            comments=video.comment_count,
            shares=0,
            game=game,
            trigger=trigger,
            clip_path=clip_path,
            share_url=video.share_url,
            title=video.title or "",
            note=note,
            platform="YouTube",
            source="youtube_api",
            id_field="youtube_video_id",
        )
        if video.is_short:
            entry["format"] = "short"

        prev = state["videos"].get(video.id) or {}
        prev_views = int(prev.get("views") or -1)
        already_logged = bool(prev.get("logged_outcome"))

        action = "would_log" if dry_run else "logged"
        is_new = not already_logged
        if not dry_run:
            saved, is_new = upsert_outcome(entry, path=outcomes_path)
            if feed_learning:
                _feed_learning(saved, is_new=is_new and not already_logged)
            state["videos"][video.id] = {
                "views": video.view_count,
                "likes": video.like_count,
                "comments": video.comment_count,
                "title": entry["title"],
                "clip_path": clip_path,
                "trigger": trigger,
                "game": game,
                "share_url": video.share_url,
                "logged_outcome": True,
                "last_synced_at": now.isoformat(),
                "create_time": video.create_time,
                "is_short": video.is_short,
                "matched_queue_id": (match or {}).get("id"),
            }
            if is_new:
                logged_new += 1
                action = "logged_new"
            else:
                updated += 1
                action = "updated" if video.view_count != prev_views else "refreshed"
        else:
            if is_new:
                logged_new += 1
            else:
                updated += 1

        details.append(
            {
                "id": video.id,
                "action": action,
                "views": video.view_count,
                "likes": video.like_count,
                "trigger": trigger,
                "game": game,
                "clip_path": Path(clip_path).name if clip_path else "",
                "title": (entry["title"] or "")[:60],
                "matched": bool(match),
                "is_short": video.is_short,
                "age_hours": round(age_h, 1) if age_h is not None else None,
            }
        )

    if not dry_run:
        state["last_sync_at"] = now.isoformat()
        _save_json(state_path, state)
        if refresh_memory and (logged_new or updated):
            try:
                from modules.Memory_Index import refresh_memory_index

                refresh_memory_index()
            except Exception as exc:
                print(f"  [sync] memory refresh skipped: {exc}")
        try:
            from modules.Checkup_Writer import update_checkup

            update_checkup()
        except Exception as exc:
            print(f"  [sync] checkup update skipped: {exc}")

    return {
        "ok": True,
        "error": None,
        "platform": "YouTube",
        "fetched": len(videos),
        "logged_new": logged_new,
        "updated": updated,
        "skipped": skipped,
        "dry_run": dry_run,
        "outcomes_file": str(outcomes_path),
        "state_file": str(state_path),
        "videos": details,
    }


def print_sync_report(result: Dict[str, Any]) -> None:
    """Human-readable summary of a sync run."""
    platform = result.get("platform") or "Social"
    if not result.get("ok"):
        print(f"\n  ✗ {platform} stats sync failed: {result.get('error')}\n")
        return

    mode = "DRY RUN" if result.get("dry_run") else "SYNC"
    print(f"\n  {platform} stats {mode}")
    print(f"  {'-' * 56}")
    print(f"  Fetched:     {result['fetched']}")
    print(f"  New logs:    {result['logged_new']}")
    print(f"  Updated:     {result['updated']}")
    print(f"  Skipped:     {result['skipped']} (too young)")
    if result.get("outcomes_file"):
        print(f"  Outcomes:    {result['outcomes_file']}")
    print()

    rows = result.get("videos") or []
    if not rows:
        print("  (no videos)\n")
        return

    print(f"  {'Action':<14} {'Views':>8} {'Likes':>6}  {'Trigger':<12} Title")
    print(f"  {'-' * 56}")
    for r in rows[:30]:
        title = (r.get("title") or "")[:28]
        print(
            f"  {str(r.get('action')):<14} "
            f"{int(r.get('views') or 0):>8,} "
            f"{int(r.get('likes') or 0):>6,}  "
            f"{str(r.get('trigger') or '?'):<12} "
            f"{title}"
        )
    if len(rows) > 30:
        print(f"  … and {len(rows) - 30} more")
    print()


def retag_outcomes_from_titles(
    outcomes_path: Path = PERFORMANCE_OUTCOMES_FILE,
    youtube_state_path: Path = YOUTUBE_STATE_FILE,
    tiktok_state_path: Path = STATE_FILE,
) -> Dict[str, int]:
    """Rewrite stored game/trigger from titles instead of the current config game."""
    rows = _load_outcomes(outcomes_path)
    changed = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        match = None
        if row.get("clip_path") and "unmatched" not in str(row.get("note") or ""):
            match = {
                "game": row.get("game"),
                "trigger": row.get("trigger"),
                "clip_path": row.get("clip_path"),
            }
        # Unmatched rows must be re-inferred from the title, ignoring
        # whatever config game was stamped on them at sync time.
        if "unmatched" in str(row.get("note") or ""):
            match = None
        game, trigger = resolve_video_metadata(
            title=str(row.get("title") or ""),
            description="",
            clip_path=str(row.get("clip_path") or ""),
            match=match,
        )
        if row.get("game") != game or row.get("trigger") != trigger:
            row["game"] = game
            row["trigger"] = trigger
            row["game_source"] = "title" if game != "Unknown" else "unknown"
            changed += 1

    if changed:
        _write_outcomes(rows, outcomes_path)

    state_changed = 0
    for state_path in (youtube_state_path, tiktok_state_path):
        state = _load_json(state_path, {})
        videos = state.get("videos")
        if not isinstance(videos, dict):
            continue
        file_changed = 0
        for rec in videos.values():
            if not isinstance(rec, dict):
                continue
            game, trigger = resolve_video_metadata(
                title=str(rec.get("title") or ""),
                description="",
                clip_path=str(rec.get("clip_path") or ""),
                match=None,
            )
            if rec.get("game") != game or rec.get("trigger") != trigger:
                rec["game"] = game
                rec["trigger"] = trigger
                file_changed += 1
        if file_changed:
            _save_json(state_path, state)
            state_changed += file_changed

    return {"outcomes_updated": changed, "state_updated": state_changed}


def rebuild_clip_history_from_outcomes(
    outcomes_path: Path = PERFORMANCE_OUTCOMES_FILE,
    history_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Rebuild clip_history.json from current outcome rows.

    Drops synthetic seed observations (identical 1200/80 copies) and
    malformed trigger keys by not copying them forward.
    """
    if history_path is None:
        history_path = DATA_DIR / "clip_history.json"

    buckets: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in _load_outcomes(outcomes_path):
        if not isinstance(row, dict):
            continue
        game = str(row.get("game") or "Unknown")
        trigger = str(row.get("trigger") or "unknown")
        if "," in trigger:
            continue
        views = int(row.get("views") or 0)
        likes = int(row.get("likes") or 0)
        bucket = buckets.setdefault(
            (game, trigger),
            {"observations": [], "total_views": 0, "total_likes": 0},
        )
        bucket["observations"].append(
            {
                "at": str(row.get("first_logged_at") or row.get("timestamp") or "")[:19],
                "views": views,
                "likes": likes,
            }
        )
        bucket["total_views"] += views
        bucket["total_likes"] += likes

    history: Dict[str, Any] = {}
    for (game, trigger), data in sorted(buckets.items()):
        n = len(data["observations"])
        history.setdefault(game, {})[trigger] = {
            "total_clips": n,
            "total_views": data["total_views"],
            "total_likes": data["total_likes"],
            "avg_views": round(data["total_views"] / n, 1) if n else 0,
            "observations": data["observations"],
        }

    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        json.dumps(history, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return history
