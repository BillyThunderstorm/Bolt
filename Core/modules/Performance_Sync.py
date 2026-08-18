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
CONFIG_CANDIDATES = (
    PROJECT_ROOT / "Core" / "config.json",
    PROJECT_ROOT / "Data" / "config.json",
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
    r"(?:"
    + r"|".join(re.escape(t) for t in sorted(KNOWN_TRIGGERS, key=len, reverse=True))
    + r")",
    re.IGNORECASE,
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
        trigger = "unknown"
        game = game_default
        note = "synced from TikTok API (unmatched to queue)"

        if match:
            clip_path = str(match.get("clip_path") or "")
            trigger = infer_trigger_from_path(clip_path)
            if trigger == "unknown":
                # Fall back to any trigger field on the queue item
                trigger = str(match.get("trigger") or "unknown")
            game = str(match.get("game") or game_default)
            note = f"synced from TikTok API (matched queue id={match.get('id', '?')})"

        # Infer trigger from video title when still unknown
        if trigger == "unknown":
            title_hit = _TRIGGER_IN_NAME.search(video.title or video.video_description or "")
            if title_hit:
                trigger = title_hit.group(0).lower()

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
        trigger = "unknown"
        game = game_default
        note = "synced from YouTube API (unmatched to queue)"

        if match:
            clip_path = str(match.get("clip_path") or "")
            trigger = infer_trigger_from_path(clip_path)
            if trigger == "unknown":
                trigger = str(match.get("trigger") or "unknown")
            game = str(match.get("game") or game_default)
            note = (
                f"synced from YouTube API (matched queue id={match.get('id', '?')})"
            )

        if trigger == "unknown":
            title_hit = _TRIGGER_IN_NAME.search(
                video.title or video.description or ""
            )
            if title_hit:
                trigger = title_hit.group(0).lower()

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
