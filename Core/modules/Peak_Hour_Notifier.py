#!/usr/bin/env python3
"""
modules/Peak_Hour_Notifier.py — Queue, review, and safeguarded auto-posting
==========================================================================
Bolt saves ready clips, asks Billy for review before peak time, and can
auto-post at the deadline if a clip was approved or the review window expires.

Peak windows (configurable in config.json):
  - 7:00 – 9:00 AM   (morning scroll)
  - 12:00 – 2:00 PM  (lunch break)
  - 7:00 – 10:00 PM  (prime time)

Why this is safer than blind auto-posting:
  - You stay in control of what goes up
  - You can add context, trending sounds, or tweak the caption before posting
  - Rejections are logged so Bolt learns what to do less often
  - Twitch chat commands can approve, stop, or hold the queue instantly
"""

import os
import json
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

try:
    import requests
except ImportError:
    requests = None  # type: ignore

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

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


# ── Config ─────────────────────────────────────────────────────────────────────

POSTING_TIMEZONE = os.getenv("POSTING_TIMEZONE", "America/New_York")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "")
# Anchor to repo root so the writer doesn't drift back to CWD.
# 3 levels: Peak_Hour_Notifier.py -> modules/ -> Core/ -> <repo root>
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
READY_FILE = _PROJECT_ROOT / "Data" / "ready_to_post.json"
CONFIG_FILE = _PROJECT_ROOT / "Core" / "config.json"
REJECTION_LOG = _PROJECT_ROOT / "Data" / "post_rejections.jsonl"

# Peak posting windows as (start_hour, end_hour) in 24h format
PEAK_WINDOWS = [
    (7, 9),  # 7:00 AM – 9:00 AM   morning scroll
    (12, 14),  # 12:00 PM – 2:00 PM  lunch break
    (19, 22),  # 7:00 PM – 10:00 PM  prime time
]


# ── Helpers ────────────────────────────────────────────────────────────────────


def _load_ready() -> dict:
    """Load the ready-to-post list from disk. Returns empty structure if missing."""
    READY_FILE.parent.mkdir(exist_ok=True)
    if READY_FILE.exists():
        try:
            with open(READY_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"clips": []}


def _save_ready(data: dict):
    """Persist the ready-to-post list to disk."""
    READY_FILE.parent.mkdir(exist_ok=True)
    with open(READY_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


def _load_config() -> dict:
    """Load local config for queue eligibility checks."""
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _auto_posting_config() -> dict:
    config = _load_config()
    auto = config.get("auto_posting", {}) if isinstance(config, dict) else {}
    return {
        "enabled": bool(auto.get("enabled", False)),
        "review_window_minutes": int(auto.get("review_window_minutes", 30)),
        "auto_post_if_deadline_missed": bool(
            auto.get("auto_post_if_deadline_missed", True)
        ),
        "require_rejection_reason": bool(auto.get("require_rejection_reason", True)),
        "privacy": str(auto.get("privacy", "PUBLIC_TO_EVERYONE")),
        # Backoff for failed publishes: after publish_clip returns
        # success=False, the clip stays ready and the queue will retry
        # it on the next process_auto_post_queue run, but not before
        # `min_retry_gap_minutes` have passed since the last attempt.
        # After `max_publish_attempts` failed attempts the clip is
        # auto-held with reason 'publish_failed_after_N_attempts' so
        # Billy can see it without it spinning forever.
        "max_publish_attempts": int(auto.get("max_publish_attempts", 3)),
        "min_retry_gap_minutes": int(auto.get("min_retry_gap_minutes", 5)),
    }


def _score_floor() -> float:
    """Current minimum score required before a clip should wake Billy up."""
    config = _load_config()
    return float(config.get("min_post_score", config.get("min_clip_score", 0)))


def _clip_file_exists(clip: dict) -> bool:
    """Return True when the queued media file exists on this Mac."""
    clip_path = clip.get("clip_path", "")
    return bool(clip_path) and Path(clip_path).exists()


def _score_clears_floor(clip: dict) -> bool:
    """Return True when a queued clip clears the current posting score floor."""
    try:
        return float(clip.get("score", 0)) >= _score_floor()
    except Exception:
        return False


def _is_queue_tier(clip: dict) -> bool:
    """True for tiers that should compete for auto-post / peak alerts."""
    tier = str(clip.get("tier", "queue") or "queue").lower()
    return tier in {"queue", "auto_queue"}


def _is_alertable_clip(clip: dict) -> bool:
    """
    Return True when a queue row is safe to include in peak-hour alerts.

    Old queue rows can survive config changes or iCloud sync without their media
    files. Keep those rows for history, but do not alert Billy to post clips that
    are missing locally or below the current score floor.
    """
    return (
        clip.get("status") == "ready"
        and _is_queue_tier(clip)
        and _clip_file_exists(clip)
        and _score_clears_floor(clip)
    )


def _plan_status(clip: dict) -> str:
    plan = clip.get("auto_post") or {}
    return str(plan.get("status") or "")


def _actionable_clips(clips: list[dict] | None = None) -> list[dict]:
    """
    Ready rows whose video file still exists — the only ones worth reviewing.

    Sorted so the thing Billy should act on first is at index 0:
      1. awaiting_approval
      2. approved (waiting for peak / post-now)
      3. publish_failed (retry)
      4. scheduled / other ready
    Within each bucket, higher score first.
    """
    if clips is None:
        clips = _load_ready().get("clips") or []
    ready_with_file = [
        c
        for c in clips
        if c.get("status") == "ready" and _clip_file_exists(c)
    ]

    priority = {
        "awaiting_approval": 0,
        "approved": 1,
        "publish_failed": 2,
        "publishing": 3,
        "scheduled": 4,
    }

    def sort_key(clip: dict):
        status = _plan_status(clip) or "scheduled"
        return (
            priority.get(status, 9),
            -float(clip.get("score") or 0),
            str(clip.get("queued_at") or ""),
        )

    return sorted(ready_with_file, key=sort_key)


def _find_ready_clip(
    data: dict,
    clip_id: str | None = None,
    *,
    require_file: bool = True,
    allowed_plan_statuses: set[str] | None = None,
) -> dict | None:
    """
    Pick one ready clip for approve / reject / post-now.

    When clip_id is omitted, prefers actionable (file-present) clips in
    review priority order so ghost rows never become "the next clip".
    """
    clips = data.get("clips") or []
    if clip_id:
        for clip in clips:
            if clip.get("id") != clip_id:
                continue
            if clip.get("status") != "ready":
                return None
            if require_file and not _clip_file_exists(clip):
                return None
            if allowed_plan_statuses is not None:
                plan = _ensure_auto_post_plan(clip)
                if plan.get("status") not in allowed_plan_statuses:
                    return None
            return clip
        return None

    candidates = _actionable_clips(clips) if require_file else [
        c for c in clips if c.get("status") == "ready"
    ]
    for clip in candidates:
        if allowed_plan_statuses is not None:
            plan = _ensure_auto_post_plan(clip)
            if plan.get("status") not in allowed_plan_statuses:
                continue
        return clip
    return None


def _clip_display_name(clip: dict) -> str:
    path = clip.get("clip_path") or ""
    return Path(path).name if path else "(no file)"


def _format_clip_card(clip: dict, index: int | None = None, total: int | None = None) -> str:
    """Human-readable card for one queue row (no JSON digging required)."""
    plan = clip.get("auto_post") or {}
    path = clip.get("clip_path") or ""
    header = "── Next clip ──"
    if index is not None and total is not None:
        header = f"── Clip {index} of {total} ──"
    lines = [
        header,
        f"  id:     {clip.get('id', '?')}",
        f"  score:  {clip.get('score', '?')}  tier={clip.get('tier', '?')}",
        f"  title:  {clip.get('title') or '(untitled)'}",
        f"  file:   {_clip_display_name(clip)}",
        f"  path:   {path or '(missing)'}",
        f"  plan:   {plan.get('status') or '—'}  "
        f"peak={plan.get('scheduled_for') or '—'}",
    ]
    if not _clip_file_exists(clip):
        lines.append("  ⚠  video file is MISSING on this Mac (ghost queue row)")
    return "\n".join(lines)


def _open_clip_video(clip: dict) -> bool:
    """Open the clip's video in the OS default player (macOS `open`, else xdg-open)."""
    path = clip.get("clip_path") or ""
    if not path or not Path(path).exists():
        print("  cannot open: video file missing", file=sys.stderr)
        return False
    import subprocess

    try:
        if sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", path], check=False)
        else:
            subprocess.run(["cmd", "/c", "start", "", path], check=False)
        print(f"  opened: {path}")
        return True
    except Exception as exc:
        print(f"  open failed: {exc}", file=sys.stderr)
        return False


def _parse_dt(value: str):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _now() -> datetime:
    return datetime.now(ZoneInfo(POSTING_TIMEZONE))


def _is_peak_now() -> tuple:
    """
    Check if the current time falls inside a peak window.
    Returns (is_peak: bool, window_label: str).

    Example return values:
      (True,  "7:00 AM – 9:00 AM")
      (False, "Next peak: 12:00 PM")
    """
    now = _now()
    hour = now.hour

    for start_h, end_h in PEAK_WINDOWS:
        if start_h <= hour < end_h:
            label = f"{_fmt_hour(start_h)} – {_fmt_hour(end_h)}"
            return True, label

    # Not peak — find next window
    next_window = _next_peak_window()
    return False, f"Next peak: {next_window}"


def _next_peak_window() -> str:
    """Return a human-readable string for the next upcoming peak window."""
    tz = ZoneInfo(POSTING_TIMEZONE)
    now = datetime.now(tz)
    hour = now.hour

    # Check today's remaining windows
    for start_h, end_h in PEAK_WINDOWS:
        if start_h > hour:
            return _fmt_hour(start_h)

    # All today's windows passed — first window tomorrow
    start_h = PEAK_WINDOWS[0][0]
    tomorrow = (now + timedelta(days=1)).strftime("%a")
    return f"{_fmt_hour(start_h)} tomorrow ({tomorrow})"


def _fmt_hour(h: int) -> str:
    """Convert 24h integer to readable 12h string. E.g. 19 → '7:00 PM'"""
    period = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:00 {period}"


def _next_peak_datetime(now: datetime = None) -> datetime:
    """Return the next peak window start as a timezone-aware datetime."""
    tz = ZoneInfo(POSTING_TIMEZONE)
    now = now or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)

    for start_h, _end_h in PEAK_WINDOWS:
        candidate = now.replace(hour=start_h, minute=0, second=0, microsecond=0)
        if candidate > now:
            return candidate

    tomorrow = now + timedelta(days=1)
    return tomorrow.replace(hour=PEAK_WINDOWS[0][0], minute=0, second=0, microsecond=0)


def _ensure_auto_post_plan(clip: dict, now: datetime = None) -> dict:
    """Attach safeguarded auto-post timing metadata to a queue row."""
    auto_cfg = _auto_posting_config()
    now = now or _now()
    plan = clip.get("auto_post") or {}
    status = plan.get("status") or "scheduled"
    scheduled = _parse_dt(plan.get("scheduled_for", ""))
    if not scheduled or (scheduled <= now and status == "scheduled"):
        scheduled = _next_peak_datetime(now)

    review_starts = scheduled - timedelta(minutes=auto_cfg["review_window_minutes"])
    plan.update(
        {
            "enabled": auto_cfg["enabled"],
            "status": status,
            "scheduled_for": scheduled.isoformat(),
            "review_starts_at": review_starts.isoformat(),
            "approval_deadline": scheduled.isoformat(),
            "auto_post_if_deadline_missed": auto_cfg["auto_post_if_deadline_missed"],
        }
    )
    clip["auto_post"] = plan
    return plan


def _send_discord(message: str):
    """
    Fire a Discord webhook notification.
    Does nothing silently if no webhook is configured or requests isn't installed.

    Webhook URLs come from DISCORD_WEBHOOK_URL, CAPTAIN_HOOK_WEBHOOK_URL, and
    optional comma-separated DISCORD_WEBHOOK_URLS in .env.
    """
    webhooks = _discord_webhooks()
    if not webhooks or not requests:
        return
    for webhook in webhooks:
        try:
            requests.post(webhook, json={"content": message}, timeout=10)
        except Exception as exc:
            notify(
                f"Discord notify failed: {exc}",
                level="warning",
                reason="Check Discord webhook values in .env. Clip still saved locally.",
            )


def _discord_webhooks() -> list[str]:
    urls = [
        os.getenv("DISCORD_WEBHOOK_URL", ""),
        os.getenv("CAPTAIN_HOOK_WEBHOOK_URL", ""),
    ]
    extra = os.getenv("DISCORD_WEBHOOK_URLS", "")
    if extra:
        urls.extend(extra.replace("\n", ",").split(","))

    cleaned = []
    for url in urls:
        text = url.strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload) + "\n")


def _record_rejection(clip: dict, reason: str) -> None:
    payload = {
        "timestamp": _now().isoformat(timespec="seconds"),
        "clip_id": clip.get("id"),
        "clip_path": clip.get("clip_path"),
        "title": clip.get("title"),
        "score": clip.get("score"),
        "reason": reason,
    }
    _append_jsonl(REJECTION_LOG, payload)
    try:
        from modules.Think_Learn_Decide import ThinkLearnDecideEngine

        engine = ThinkLearnDecideEngine({"memory_auto_refresh": False})
        engine.learn_from_feedback("queue_clip", accepted=False, feedback_text=reason)
    except Exception:
        pass


# ── Public API ─────────────────────────────────────────────────────────────────


def queue_clip(
    clip_path: str,
    title: str,
    hashtags: list = None,
    score: float = 50,
    tier: str = "queue",
) -> dict:
    """
    Add a clip to the ready-to-post list.

    Called by bot.py after a clip has been processed and scored.
    The clip gets a unique ID so you can mark it posted later.

    Tier semantics (from Clip_Ranker):
      - "queue"  → counted in peak-hour alerts (pings you on Discord)
      - "mid"    → saved to disk, visible in --summary, but NEVER pings you
      - "discard"→ shouldn't reach this function; bot.py is supposed to skip
                   discard-tier clips before calling. We honor it defensively
                   anyway by tagging the item but still saving the row.

    Returns the item dict that was saved.
    """
    data = _load_ready()
    now = _now()

    is_peak, window_info = _is_peak_now()

    item = {
        "id": str(uuid.uuid4())[:8],
        "clip_path": str(clip_path),
        "title": title,
        "hashtags": hashtags or [],
        "score": round(score, 1),
        "tier": tier,
        "status": "ready",
        "queued_at": now.isoformat(),
        "posted_at": None,
    }
    if tier == "queue":
        _ensure_auto_post_plan(item, now)

    try:
        from modules.Multi_Publisher import append_platform_plan, build_platform_plan

        platform_plan = build_platform_plan(
            clip_path=clip_path,
            title=title,
            hashtags=hashtags or [],
            queued_at=now,
            timezone=POSTING_TIMEZONE,
        )
        item["platform_plan"] = platform_plan
        append_platform_plan(item["id"], platform_plan)
    except Exception as exc:
        item["platform_plan"] = []
        notify(
            f"Multi-platform plan skipped: {exc}",
            level="warning",
            reason="The main ready-to-post queue was still saved.",
        )

    data["clips"].append(item)
    _save_ready(data)

    notify(
        f"Clip saved to post queue  [score {score:.0f}, tier {tier}]",
        level="success",
        reason=f"Title: '{title}'\n"
        f"     → File: {Path(clip_path).name}\n"
        f"     → {window_info}\n"
        f"     → Platform packets: {len(item.get('platform_plan', []))}\n"
        f"     → Will trigger peak alert: {'YES' if tier == 'queue' else 'no (mid-tier)'}",
    )

    # Only QUEUE tier triggers an immediate peak-window alert.
    # Mid-tier clips just sit in the queue silently for manual review.
    if is_peak and tier == "queue":
        alert_peak_window()

    return item


def alert_peak_window():
    """
    Check if it's peak time and, if so, send Billy a Discord notification
    listing every unposted clip that's ready to go.

    This is called:
      - Automatically by queue_clip() when a clip arrives during peak hours
      - By Post_Queue's background checker (if running)
      - Any time you want to manually check: python -m modules.Peak_Hour_Notifier
    """
    data = _load_ready()
    # Only QUEUE-tier clips wake Billy up. Mid-tier clips are visible in
    # --summary for manual review, but never trigger a Discord ping.
    # Backward compat: clips queued before tier existed have no 'tier' key
    # — treat those as 'queue' so old data still works.
    ready = [c for c in data["clips"] if _is_alertable_clip(c)]
    mid_count = sum(
        1 for c in data["clips"] if c["status"] == "ready" and c.get("tier") == "mid"
    )
    missing_count = sum(
        1
        for c in data["clips"]
        if c.get("status") == "ready" and not _clip_file_exists(c)
    )
    low_score_count = sum(
        1
        for c in data["clips"]
        if c.get("status") == "ready"
        and _clip_file_exists(c)
        and not _score_clears_floor(c)
    )

    if not ready:
        if missing_count or low_score_count:
            notify(
                "No alertable clips ready",
                level="info",
                reason=f"{missing_count} queued clip(s) are missing files on this Mac; "
                f"{low_score_count} existing clip(s) are below the current score floor. "
                "Queue history was left untouched.",
            )
        elif mid_count:
            notify(
                f"No QUEUE-tier clips ready — but {mid_count} MID-tier clip(s) sitting on disk",
                level="info",
                reason="Mid-tier clips are decent but not great. They live in "
                "data/ready_to_post.json with tier='mid'. Browse them manually "
                "if you want, or lower quality_tiers.queue_at in config.json "
                "to promote more clips into the auto-alert lane.",
            )
        else:
            notify(
                "No clips in post queue",
                level="info",
                reason="Process a recording first, or drop an .mp4 into recordings/",
            )
        return

    is_peak, window_info = _is_peak_now()

    if not is_peak:
        notify(
            f"Not peak hours yet  ({window_info})",
            level="info",
            reason=f"{len(ready)} clip(s) are ready and waiting. "
            "Bolt will alert you when the window opens.",
        )
        return

    # It IS peak time — build the notification
    lines = [
        f"⚡️ **Bolt ALERT — Peak Posting Window: {window_info}**",
        f"You have **{len(ready)} clip(s)** ready to post on TikTok:\n",
    ]
    for i, clip in enumerate(ready, 1):
        tags = " ".join(f"#{t.lstrip('#')}" for t in clip.get("hashtags", []))
        lines.append(
            f"**{i}. {clip['title']}**\n"
            f"   Score: {clip['score']}/100\n"
            f"   File: `{Path(clip['clip_path']).name}`\n"
            f"   Tags: {tags or '(none)'}\n"
        )
    lines.append(
        "✅ Post these manually on TikTok, then run:\n"
        "   `python -m modules.Peak_Hour_Notifier --mark-posted`\n"
        "   to clear them from the queue."
    )

    message = "\n".join(lines)

    # Terminal output
    print("\n" + "─" * 60)
    print(message.replace("**", "").replace("`", ""))
    print("─" * 60 + "\n")

    # Discord notification
    _send_discord(message)

    notify(
        f"Peak hour alert sent! {len(ready)} clip(s) are ready.",
        level="success",
        reason="Check Discord for the full list with titles and file names.",
    )


def alert_review_window(now: datetime = None) -> int:
    """Send the 30-minute pre-peak review alert for ready auto-post clips."""
    data = _load_ready()
    now = now or _now()
    count = 0
    changed = False
    ready = [c for c in data["clips"] if _is_alertable_clip(c)]

    for clip in ready:
        plan = _ensure_auto_post_plan(clip, now)
        if not plan.get("enabled"):
            continue
        status = plan.get("status")
        review_starts = _parse_dt(plan.get("review_starts_at", ""))
        deadline = _parse_dt(plan.get("approval_deadline", ""))
        if not review_starts or not deadline:
            continue
        if status == "scheduled" and review_starts <= now < deadline:
            plan["status"] = "awaiting_approval"
            plan["review_alerted_at"] = now.isoformat()
            count += 1
            changed = True

    if count:
        message = _review_message(
            [
                c
                for c in ready
                if c.get("auto_post", {}).get("status") == "awaiting_approval"
            ],
            ignored_count=int(data.get("consecutive_ignored_reviews", 0)),
        )
        _send_discord(message)
        notify(
            "Post ready and awaiting your approval.",
            level="success",
            reason=f"{count} clip(s) are in the pre-peak review window. Approve with !postnow or hold with !dontpost <reason>.",
        )

    if changed:
        _save_ready(data)
    return count


def _review_message(clips: list[dict], ignored_count: int = 0) -> str:
    lines = []
    # Audit #2: After 3+ consecutive reviews went by without a
    # !postnow or !dontpost, prefix the message with a louder
    # banner. The counter resets to 0 the moment Billy responds
    # (approve_next_clip / reject_next_clip) so the escalation is
    # tied to *consecutive* silence, not lifetime total.
    if ignored_count >= 3:
        lines.append(
            f"🚨 **URGENT: {ignored_count} reviews ignored in a row — please respond.**"
        )
    lines.extend(
        [
            "🔔 **Post ready and awaiting your approval.**",
            "Peak hours are close. Reply in Twitch chat with `!postnow` to approve now or `!dontpost <reason>` to hold.",
            "If the deadline passes with no rejection, Bolt will try to auto-post.",
            "",
        ]
    )
    for clip in clips:
        plan = clip.get("auto_post", {})
        lines.append(
            f"- `{clip.get('id')}` **{clip.get('title')}** | score {clip.get('score')} | deadline {plan.get('approval_deadline')}"
        )
    return "\n".join(lines)


def _increment_ignored_reviews(data: dict) -> int:
    """Bump the consecutive-ignored counter. Returns the new value."""
    data["consecutive_ignored_reviews"] = int(
        data.get("consecutive_ignored_reviews", 0)
    ) + 1
    return data["consecutive_ignored_reviews"]


def _reset_ignored_reviews(data: dict) -> None:
    data["consecutive_ignored_reviews"] = 0


def approve_next_clip(clip_id: str = None) -> dict:
    """Approve one waiting clip, or the next actionable ready clip (file must exist)."""
    data = _load_ready()
    now = _now()
    clip = _find_ready_clip(
        data,
        clip_id,
        require_file=True,
        allowed_plan_statuses={"scheduled", "awaiting_approval", "publish_failed"},
    )
    if not clip:
        # Explicit id may be approved already or missing a plan status match —
        # still allow re-approving a ready clip with file if id was given.
        if clip_id:
            clip = _find_ready_clip(data, clip_id, require_file=True)
            if not clip:
                return {}
            plan = _ensure_auto_post_plan(clip, now)
            if plan.get("status") not in {
                "scheduled",
                "awaiting_approval",
                "publish_failed",
                "approved",
            }:
                return {}
        else:
            return {}

    plan = _ensure_auto_post_plan(clip, now)
    plan["status"] = "approved"
    plan["approved_at"] = now.isoformat()
    # Audit #2: Billy responded, clear the escalation counter.
    _reset_ignored_reviews(data)
    _save_ready(data)
    notify(
        f"Approved clip {clip.get('id')} for auto-post",
        level="success",
        reason="Bolt will post at the scheduled peak time, or you can use !postnow / bolt postnow to publish immediately.",
    )
    return clip


def reject_next_clip(reason: str = "", clip_id: str = None) -> dict:
    """Hold one waiting/ready clip and record why it should not post."""
    data = _load_ready()
    now = _now()
    reason = reason.strip()
    if not reason:
        reason = "No rejection reason provided yet"

    clip = _find_ready_clip(
        data,
        clip_id,
        require_file=True,
        allowed_plan_statuses={
            "scheduled",
            "awaiting_approval",
            "approved",
            "publish_failed",
        },
    )
    # Holding by id should still work for ghost rows (file already gone).
    if not clip and clip_id:
        clip = _find_ready_clip(data, clip_id, require_file=False)

    if not clip:
        return {}

    plan = _ensure_auto_post_plan(clip, now)
    clip["status"] = "held"
    clip["held_at"] = now.isoformat()
    clip["hold_reason"] = reason
    plan["status"] = "rejected"
    plan["rejected_at"] = now.isoformat()
    plan["rejection_reason"] = reason
    _record_rejection(clip, reason)
    # Audit #2: Billy responded, clear the escalation counter.
    _reset_ignored_reviews(data)
    _save_ready(data)
    notify(
        f"Held clip {clip.get('id')}",
        level="warning",
        reason=f"Reason recorded: {reason}",
    )
    if reason == "No rejection reason provided yet":
        _send_discord(
            f"⚠️ Clip `{clip.get('id')}` was held. Please add a reason with `!dontpost {clip.get('id')} <reason>` so Bolt learns."
        )
    return clip


def override_clip_score(score: float, clip_id: str = None) -> dict:
    """Override a ready clip's score and promote/demote alertability."""
    data = _load_ready()
    now = _now()
    score = max(0.0, min(100.0, float(score)))
    config = _load_config()
    queue_at = float(config.get("quality_tiers", {}).get("queue_at", 80))
    min_score = float(config.get("min_post_score", config.get("min_clip_score", 65)))

    for clip in data["clips"]:
        if clip.get("status") != "ready":
            continue
        if clip_id and clip.get("id") != clip_id:
            continue
        clip["score"] = round(score, 1)
        clip["score_overridden_at"] = now.isoformat()
        clip["score_override_source"] = "twitch_chat"
        if score >= queue_at:
            clip["tier"] = "queue"
            _ensure_auto_post_plan(clip, now)
        elif score >= min_score:
            clip["tier"] = "mid"
            if clip.get("auto_post"):
                clip["auto_post"]["status"] = "demoted"
        else:
            clip["tier"] = "discard"
            if clip.get("auto_post"):
                clip["auto_post"]["status"] = "demoted"
        _save_ready(data)
        notify(
            f"Clip {clip.get('id')} score set to {score:.0f}",
            level="success",
            reason=f"Tier is now {clip.get('tier')}.",
        )
        return clip
    return {}


def post_now(clip_id: str = None, force: bool = True) -> dict:
    """Publish one ready clip immediately via the TikTok publisher."""
    data = _load_ready()
    now = _now()
    # Always require a local file — publishing a ghost path cannot succeed.
    if force:
        clip = _find_ready_clip(data, clip_id, require_file=True)
    else:
        # Non-force: only alertable (queue-tier + score floor + file).
        candidates = _actionable_clips(data.get("clips") or [])
        clip = None
        for c in candidates:
            if clip_id and c.get("id") != clip_id:
                continue
            if _is_alertable_clip(c):
                clip = c
                break
            if clip_id:
                break
    if not clip:
        return {
            "clip": None,
            "result": {
                "success": False,
                "error": "No ready clip with a local video file found",
            },
        }
    result = _publish_clip(clip, now, reason="manual override")
    # Audit #2: Billy responded, clear the escalation counter.
    _reset_ignored_reviews(data)
    _save_ready(data)
    return {"clip": clip, "result": result}


def process_auto_post_queue(now: datetime = None) -> dict:
    """Advance review windows and publish approved or expired auto-post items."""
    data = _load_ready()
    now = now or _now()
    stats = {"review_alerted": 0, "posted": 0, "failed": 0, "held": 0}

    for clip in data["clips"]:
        if not _is_alertable_clip(clip):
            continue
        plan = _ensure_auto_post_plan(clip, now)
        if not plan.get("enabled"):
            continue

        review_starts = _parse_dt(plan.get("review_starts_at", ""))
        deadline = _parse_dt(plan.get("approval_deadline", ""))
        if not review_starts or not deadline:
            continue

        status = plan.get("status")
        if status == "scheduled" and review_starts <= now < deadline:
            plan["status"] = "awaiting_approval"
            plan["review_alerted_at"] = now.isoformat()
            stats["review_alerted"] += 1

        status = plan.get("status")
        deadline_missed = (
            status == "awaiting_approval"
            and now >= deadline
            and plan.get("auto_post_if_deadline_missed")
        )
        approved_due = status == "approved" and now >= deadline
        # Backoff retry: a clip that previously failed to publish is
        # eligible to retry once `next_eligible_at` has passed. The
        # attempt counter is bumped in _publish_clip; after
        # max_publish_attempts failures the clip is auto-held, so
        # this branch only fires for clips that still have retries
        # left.
        retry_eligible = False
        if status == "publish_failed":
            next_eligible = _parse_dt(plan.get("next_eligible_at", ""))
            if next_eligible and now >= next_eligible:
                retry_eligible = True
            elif not next_eligible:
                # Failed before backoff was wired in — give it one
                # chance immediately rather than spinning forever.
                retry_eligible = True
        if deadline_missed or approved_due or retry_eligible:
            if deadline_missed:
                publish_reason = "deadline missed"
                # Audit #2: a deadline-driven publish means Billy
                # didn't respond during the review window. Bump the
                # consecutive-ignored counter so the next review
                # message gets the urgent banner.
                _increment_ignored_reviews(data)
            elif approved_due:
                publish_reason = "approved"
            else:
                publish_reason = f"retry attempt {plan.get('attempt_count', 0) + 1}"
            result = _publish_clip(clip, now, reason=publish_reason)
            if result.get("success"):
                stats["posted"] += 1
            else:
                stats["failed"] += 1

    if stats["review_alerted"]:
        waiting = [
            c
            for c in data["clips"]
            if c.get("auto_post", {}).get("status") == "awaiting_approval"
        ]
        _send_discord(_review_message(
            waiting,
            ignored_count=int(data.get("consecutive_ignored_reviews", 0)),
        ))
        notify(
            "Post ready and awaiting your approval.",
            level="success",
            reason=f"{stats['review_alerted']} clip(s) entered the review window.",
        )

    _save_ready(data)
    return stats


def _publish_clip(clip: dict, now: datetime, reason: str) -> dict:
    plan = _ensure_auto_post_plan(clip, now)
    # Audit #3: de-dup lock. If another process is already
    # publishing this clip (e.g. !postnow racing the deadline
    # auto-post), bail out instead of calling publish_clip twice.
    if plan.get("status") == "publishing":
        return {
            "success": False,
            "error": "publish already in progress for this clip",
        }
    plan["status"] = "publishing"
    cfg = _auto_posting_config()
    plan["last_publish_attempt_at"] = now.isoformat()
    plan["last_publish_reason"] = reason
    # Bump the attempt counter before we call the publisher so a crash
    # inside publish_clip still counts as an attempt.
    plan["attempt_count"] = int(plan.get("attempt_count", 0)) + 1
    try:
        from modules.TikTok_Publisher import publish_clip

        result = publish_clip(
            clip.get("clip_path", ""),
            clip.get("title", ""),
            hashtags=clip.get("hashtags", []),
            privacy=cfg["privacy"],
        )
    except Exception as exc:
        result = {"success": False, "error": str(exc)}

    if result.get("success"):
        clip["status"] = "posted"
        clip["posted_at"] = now.isoformat()
        clip["posted_by"] = "auto_post"
        plan["status"] = "posted"
        plan["publish_result"] = result
        notify(
            f"Auto-posted clip {clip.get('id')}",
            level="success",
            reason=f"Published after {reason} (attempt {plan['attempt_count']}).",
        )
        # Audit #4: close the loop with a Discord confirmation.
        # The publisher's result dict usually carries the post URL —
        # surface it so Billy can click through and verify.
        post_url = (result.get("url") or result.get("post_url") or "").strip()
        if post_url:
            _send_discord(
                f"✅ Posted: **{clip.get('title', '(untitled)')}** — {post_url}"
            )
        else:
            _send_discord(
                f"✅ Posted: **{clip.get('title', '(untitled)')}** (no URL returned)"
            )
    else:
        plan["status"] = "publish_failed"
        plan["publish_error"] = result.get("error", "unknown error")
        # Schedule the next eligible attempt `min_retry_gap_minutes`
        # from now, and decide whether to give up entirely.
        next_eligible = now + timedelta(minutes=cfg["min_retry_gap_minutes"])
        plan["next_eligible_at"] = next_eligible.isoformat()
        if plan["attempt_count"] >= cfg["max_publish_attempts"]:
            # Out of retries. Hold the clip so the queue stops touching
            # it and Billy sees it as a known failure in the queue UI.
            clip["status"] = "held"
            clip["held_at"] = now.isoformat()
            hold_reason = (
                f"publish_failed_after_{plan['attempt_count']}_attempts: "
                f"{plan['publish_error']}"
            )
            clip["hold_reason"] = hold_reason
            plan["status"] = "held_after_retries"
            plan["held_at"] = now.isoformat()
            plan["hold_reason"] = hold_reason
            notify(
                f"Auto-post gave up on clip {clip.get('id')}",
                level="warning",
                reason=(
                    f"{plan['attempt_count']} failed attempts. "
                    f"Last error: {plan['publish_error']}. "
                    f"Clip is now held; manual post or `!postnow` will retry."
                ),
            )
        else:
            notify(
                f"Auto-post failed for clip {clip.get('id')} "
                f"(attempt {plan['attempt_count']}/{cfg['max_publish_attempts']})",
                level="warning",
                reason=(
                    f"{plan['publish_error']}. "
                    f"Will retry after {cfg['min_retry_gap_minutes']}m."
                ),
            )
    return result


def mark_posted(clip_id: str = None):
    """
    Mark one or all 'ready' clips as posted.

    clip_id=None  → marks ALL ready clips as posted (use after a posting session)
    clip_id='abc' → marks just that specific clip

    This keeps the queue clean so you don't get duplicate alerts.
    """
    data = _load_ready()
    tz = ZoneInfo(POSTING_TIMEZONE)
    now = datetime.now(tz)
    count = 0

    for clip in data["clips"]:
        if clip["status"] != "ready":
            continue
        if clip_id is None or clip["id"] == clip_id:
            clip["status"] = "posted"
            clip["posted_at"] = now.isoformat()
            count += 1

    _save_ready(data)
    notify(
        f"Marked {count} clip(s) as posted ✓",
        level="success",
        reason="Queue updated. Run again after your next session to clear new clips.",
    )
    return count


def reset_queue() -> Path:
    """
    Archive the current ready-to-post queue and start fresh.

    This only touches data/ready_to_post.json. It does not delete clips,
    vertical exports, captions, logs, or memory.
    """
    READY_FILE.parent.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = READY_FILE.with_name(f"ready_to_post.archive-{timestamp}.json")

    if READY_FILE.exists():
        archive_path.write_text(
            READY_FILE.read_text(encoding="utf-8"), encoding="utf-8"
        )

    _save_ready({"clips": []})
    notify(
        "Post queue reset",
        level="success",
        reason=f"Archived old queue to {archive_path}. Clip files were not touched.",
    )
    return archive_path


def _vertical_clips_dir() -> Path:
    """Preferred on-disk folder for postable 9:16 exports."""
    media = _PROJECT_ROOT / "media" / "vertical_clips"
    if media.is_dir():
        return media
    legacy = _PROJECT_ROOT / "vertical_clips"
    return legacy if legacy.is_dir() else media


def resolve_clip_path(token: str) -> Path | None:
    """
    Resolve a user-supplied path or bare filename to an existing video file.

    Accepts absolute paths, paths relative to cwd, or just `Stress.mp4`
    (looked up under media/vertical_clips/).
    """
    if not token:
        return None
    raw = Path(token).expanduser()
    candidates = []
    if raw.is_absolute():
        candidates.append(raw)
    else:
        candidates.append(Path.cwd() / raw)
        candidates.append(_PROJECT_ROOT / raw)
        candidates.append(_vertical_clips_dir() / raw.name)
        # Also allow stem without extension
        if not raw.suffix:
            for ext in (".mp4", ".mov", ".m4v"):
                candidates.append(_vertical_clips_dir() / f"{raw.name}{ext}")
    for path in candidates:
        try:
            resolved = path.resolve()
        except Exception:
            continue
        if resolved.is_file():
            return resolved
    return None


def _suggest_titles_for_clip(
    clip: dict | None = None,
    *,
    filename: str = "",
    trigger: str = "reaction",
    game: str = "Gaming",
    score: float = 90.0,
    count: int = 3,
) -> tuple[list[str], list[str]]:
    """Return (titles, hashtags) for a queue row or bare filename."""
    stem = ""
    if clip:
        stem = Path(clip.get("clip_path") or "").stem
        score = float(clip.get("score") or score)
        tags = clip.get("hashtags") or []
        if tags and isinstance(tags[0], str) and tags[0].startswith("#"):
            # Prefer game-ish first hashtag without the hash when possible.
            game = tags[0].lstrip("#") or game
    if filename:
        stem = Path(filename).stem or stem
    context = {
        "clip_name": stem,
        "filename": filename or (Path(clip.get("clip_path") or "").name if clip else ""),
        "note": f"Hand-edited vertical clip named {stem}" if stem else "",
        "use_ai_titles": True,
    }
    try:
        from modules.Title_Generator import generate_titles

        titles, hashtags = generate_titles(
            trigger, game=game, score=score, context=context, count=count
        )
        if titles:
            return list(titles), list(hashtags or [])
    except Exception:
        pass
    # Filename-aware fallback when AI/templates are generic.
    label = (stem or "this clip").replace("_", " ").strip()
    fallback = [
        f"{label} 🔥 #{game}",
        f"You have to see this — {label} 💀 #{game}",
        f"POV: {label} 😂 #{game} #clips",
    ]
    return fallback[:count], [f"#{game}", "#gaming", "#clips", "#viral", "#fyp"]


def set_clip_title(
    title: str,
    clip_id: str | None = None,
    hashtags: list | None = None,
) -> dict:
    """Update the caption title (and optional hashtags) on a ready queue row."""
    title = (title or "").strip()
    if not title:
        return {}
    data = _load_ready()
    clip = _find_ready_clip(data, clip_id, require_file=False)
    if not clip:
        # Allow retitling held/approved-but-not-posted rows by id.
        if clip_id:
            for c in data.get("clips") or []:
                if c.get("id") == clip_id and c.get("status") in {
                    "ready",
                    "held",
                    "awaiting_approval",
                }:
                    clip = c
                    break
        if not clip:
            return {}
    clip["title"] = title
    if hashtags is not None:
        clip["hashtags"] = list(hashtags)
    # Keep platform plan captions roughly in sync when present.
    for plan in clip.get("platform_plan") or []:
        if not isinstance(plan, dict):
            continue
        if "title" in plan:
            plan["title"] = title
        if "caption" in plan:
            tags = " ".join(clip.get("hashtags") or [])
            plan["caption"] = f"{title}\n\n{tags}".strip() if tags else title
        if "description" in plan and plan.get("platform") in {
            "youtube_shorts",
            "kick",
        }:
            plan["description"] = title
    _save_ready(data)
    notify(
        f"Title updated on clip {clip.get('id')}",
        level="success",
        reason=title[:80],
    )
    return clip


def add_manual_clip(
    clip_path: str | Path,
    title: str | None = None,
    hashtags: list | None = None,
    score: float = 90.0,
    *,
    approve: bool = False,
    suggest_title: bool = False,
) -> dict:
    """
    Register a hand-edited video (usually under media/vertical_clips/) into
    the ready-to-post queue.

    Editing a file on disk does NOT put it in the queue — call this (or
    `bolt queue add`) so Bolt knows to schedule / approve / post it.
    """
    path = resolve_clip_path(str(clip_path))
    if not path:
        raise FileNotFoundError(
            f"Video not found: {clip_path}\n"
            f"  Looked in cwd and {_vertical_clips_dir()}"
        )

    # Avoid duplicate ready rows for the same file.
    data = _load_ready()
    for existing in data.get("clips") or []:
        if existing.get("status") != "ready":
            continue
        try:
            if Path(existing.get("clip_path") or "").resolve() == path:
                if approve:
                    plan = _ensure_auto_post_plan(existing)
                    plan["status"] = "approved"
                    plan["approved_at"] = _now().isoformat()
                    _save_ready(data)
                return existing
        except Exception:
            continue

    stem = path.stem.replace("_", " ").strip() or path.name
    tags = hashtags
    if suggest_title and not title:
        titles, gen_tags = _suggest_titles_for_clip(
            filename=path.name, score=float(score)
        )
        title = titles[0] if titles else stem
        if not tags:
            tags = gen_tags
    # Prefer a readable title from the filename when the user named it on purpose
    # (Stress.mp4 → "Stress …") unless they passed --title or --suggest-title.
    if not title:
        title = f"{stem} 🔥 #Gaming"

    item = queue_clip(
        str(path),
        title,
        hashtags=tags or ["#Gaming", "#clips", "#fyp"],
        score=float(score),
        tier="queue",
    )
    if approve:
        approved = approve_next_clip(item.get("id"))
        return approved or item
    return item


def clean_missing_clips(*, dry_run: bool = False) -> dict:
    """
    Mark ready rows whose video file is gone as scrapped (ghost cleanup).

    Does not delete any media. Clears the confusing "100 ready" count so
    `bolt queue` only reflects clips you can actually open and post.
    """
    data = _load_ready()
    now = _now()
    cleaned = []
    for clip in data.get("clips") or []:
        if clip.get("status") != "ready":
            continue
        if _clip_file_exists(clip):
            continue
        cleaned.append(
            {
                "id": clip.get("id"),
                "title": clip.get("title"),
                "clip_path": clip.get("clip_path"),
            }
        )
        if dry_run:
            continue
        clip["status"] = "scrapped"
        clip["scrapped_at"] = now.isoformat()
        clip["scrap_reason"] = "missing_video_file"
        plan = clip.get("auto_post")
        if isinstance(plan, dict):
            plan["status"] = "scrapped_missing_file"

    if not dry_run and cleaned:
        _save_ready(data)
        notify(
            f"Cleaned {len(cleaned)} ghost queue row(s)",
            level="success",
            reason="Marked ready rows with missing video files as scrapped. Media was not deleted.",
        )
    return {"cleaned": len(cleaned), "dry_run": dry_run, "clips": cleaned}


def queue_summary() -> dict:
    """Return counts for each status in the ready-to-post list."""
    data = _load_ready()
    clips = data["clips"]
    ready = [c for c in clips if c.get("status") == "ready"]
    return {
        "ready": sum(1 for c in ready if _is_alertable_clip(c)),
        "ready_total": len(ready),
        "awaiting_approval": sum(
            1
            for c in ready
            if c.get("auto_post", {}).get("status") == "awaiting_approval"
        ),
        "approved": sum(
            1 for c in ready if c.get("auto_post", {}).get("status") == "approved"
        ),
        "held": sum(1 for c in clips if c.get("status") == "held"),
        "publish_failed": sum(
            1 for c in ready if c.get("auto_post", {}).get("status") == "publish_failed"
        ),
        "missing": sum(1 for c in ready if not _clip_file_exists(c)),
        "below_floor": sum(
            1 for c in ready if _clip_file_exists(c) and not _score_clears_floor(c)
        ),
        "posted": sum(1 for c in clips if c.get("status") == "posted"),
        "total": len(clips),
        "consecutive_ignored_reviews": int(
            data.get("consecutive_ignored_reviews", 0)
        ),
    }


def render_dashboard(
    max_clips: int = 8,
    max_chars: int = 480,
    *,
    actionable_only: bool = True,
) -> str:
    """
    Build a Twitch-chat-friendly dashboard of the current posting queue.

    By default only shows **actionable** clips (ready + video file exists),
    sorted by what to decide first. Pass actionable_only=False for the old
    full dump (including ghost rows with missing files).

    Designed to fit in 1-2 Twitch messages (~480 chars each) and show
    enough detail to make an informed !postnow / !dontpost decision
    without leaving chat.
    """
    summary = queue_summary()
    data = _load_ready()
    clips = data["clips"]
    ignored = summary.get("consecutive_ignored_reviews", 0)
    actionable = _actionable_clips(clips)
    header = (
        f"📋 Queue: {summary['ready']} alertable / "
        f"{len(actionable)} with file / "
        f"{summary['ready_total']} ready rows / "
        f"{summary['awaiting_approval']} awaiting / "
        f"{summary['approved']} approved / "
        f"{summary['held']} held / "
        f"{summary['publish_failed']} retrying"
    )
    if summary.get("missing"):
        header += f"  👻{summary['missing']} ghost"
    if ignored > 0:
        header += f"  ⚠️ ignored×{ignored}"

    lines = [header, "─" * 40]
    if actionable_only:
        display = actionable
        if not display:
            lines.append("  (no clips with a local video file)")
            if summary.get("missing"):
                lines.append(
                    f"  tip: {summary['missing']} ready rows point at missing files — "
                    f"run `bolt queue clean`"
                )
        for clip in display[:max_clips]:
            plan = clip.get("auto_post", {}) or {}
            plan_status = plan.get("status", "—")
            attempts = plan.get("attempt_count", 0)
            title = (clip.get("title", "?") or "?")[:22]
            score = clip.get("score", 0)
            clip_id = clip.get("id", "????")
            fname = _clip_display_name(clip)[:28]
            bits = []
            if plan_status and plan_status != "—":
                bits.append(plan_status)
            if attempts:
                bits.append(f"try{attempts}")
            status_text = "/".join(bits) if bits else "—"
            lines.append(
                f"  {clip_id} ⭐{score:>3} | {title:<22} | {status_text}"
            )
            lines.append(f"           📁 {fname}")
        if len(display) > max_clips:
            lines.append(f"  …and {len(display) - max_clips} more with files")
    else:
        shown = 0
        for clip in clips:
            if shown >= max_clips:
                break
            if clip.get("status") in ("posted", "scrapped"):
                continue
            plan = clip.get("auto_post", {}) or {}
            plan_status = plan.get("status", "—")
            attempts = plan.get("attempt_count", 0)
            title = (clip.get("title", "?") or "?")[:24]
            score = clip.get("score", 0)
            clip_id = clip.get("id", "????")
            bits = []
            if plan_status != "—":
                bits.append(plan_status)
            if attempts:
                bits.append(f"try{attempts}")
            if not _clip_file_exists(clip) and clip.get("status") == "ready":
                bits.append("MISSING")
            if clip.get("hold_reason"):
                reason = (clip.get("hold_reason", "") or "")[:30]
                bits.append(f"reason={reason}")
            status_text = "/".join(bits) if bits else "—"
            lines.append(f"  {clip_id} ⭐{score:>3} | {title:<24} | {status_text}")
            shown += 1
        if len(clips) > max_clips:
            lines.append(f"  …and {len(clips) - max_clips} more")

    if summary["held"]:
        reasons = []
        for c in clips:
            if c.get("status") == "held" and c.get("hold_reason"):
                reasons.append(f"{c.get('id')}:{c['hold_reason'][:40]}")
        if reasons:
            lines.append("─" * 40)
            lines.append("Held clips:")
            for r in reasons[:3]:
                lines.append(f"  • {r}")
            if len(reasons) > 3:
                lines.append(f"  …and {len(reasons) - 3} more")

    if actionable and actionable_only:
        lines.append("─" * 40)
        lines.append(
            "Decide:  bolt queue next  |  bolt approve  |  bolt dontpost <why>  |  bolt postnow"
        )

    out = "\n".join(lines)
    if len(out) > max_chars:
        out = out[: max_chars - 3] + "…"
    return out


def show_next_clip(*, open_video: bool = False) -> dict | None:
    """Print a full card for the next actionable clip. Optionally open the video."""
    clips = _actionable_clips()
    if not clips:
        print("\n  No postable clips right now.")
        print("  (ready rows with missing video files do not count)\n")
        s = queue_summary()
        if s.get("missing"):
            print(
                f"  {s['missing']} ghost row(s) still say ready — run: bolt queue clean\n"
            )
        return None
    clip = clips[0]
    print()
    print(_format_clip_card(clip, index=1, total=len(clips)))
    print()
    print("  No need to open ready_to_post.json.")
    print("  Commands for THIS clip (id optional — defaults to next):")
    print(f"    bolt approve {clip.get('id')}")
    print(f"    bolt dontpost {clip.get('id')} <reason>")
    print(f"    bolt postnow {clip.get('id')}")
    print("    bolt queue decide     # walk through all with prompts")
    print()
    if open_video:
        _open_clip_video(clip)
    return clip


def interactive_decide(*, open_first: bool = True) -> int:
    """
    Walk through every actionable clip with a simple prompt.

    No JSON, no remembering ids — open / approve / hold / post-now / skip.
    Returns number of decisions made (approve/hold/post).
    """
    decisions = 0
    skipped_ids: set[str] = set()
    opened_once = False

    while True:
        clips = [
            c
            for c in _actionable_clips()
            if c.get("id") not in skipped_ids
        ]
        if not clips:
            # If we only skipped, offer to loop again from the top.
            remaining = _actionable_clips()
            if remaining and skipped_ids:
                print(
                    f"\n  Looped all {len(skipped_ids)} clip(s) without a decision."
                )
                try:
                    again = input("  review skipped again? [y/N]> ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print("\n  quit")
                    break
                if again in {"y", "yes"}:
                    skipped_ids.clear()
                    continue
            print("\n  Queue clear of postable clips. Done.\n")
            break

        clip = clips[0]
        total = len(clips)
        print()
        print(_format_clip_card(clip, index=1, total=total))
        print()
        print("  [o] open video")
        print("  [a] approve for next peak")
        print("  [p] post now (TikTok)")
        print("  [h] hold / don't post (asks for reason)")
        print("  [s] skip to next (leave as ready)")
        print("  [q] quit")
        if open_first and not opened_once:
            _open_clip_video(clip)
            opened_once = True

        try:
            choice = input("\n  choice> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  quit")
            break

        if not choice or choice in {"q", "quit", "exit"}:
            break
        if choice in {"o", "open"}:
            _open_clip_video(clip)
            continue
        if choice in {"a", "approve", "y", "yes"}:
            approved = approve_next_clip(clip.get("id"))
            if approved:
                print(f"  ✓ approved {approved.get('id')} for peak auto-post")
                decisions += 1
            else:
                print("  could not approve that clip", file=sys.stderr)
            continue
        if choice in {"p", "post", "postnow", "post-now"}:
            result = post_now(clip.get("id"))
            publish = result.get("result") or {}
            if publish.get("success"):
                print(f"  ✓ posted {clip.get('id')}")
                decisions += 1
            else:
                print(
                    f"  post failed: {publish.get('error', 'unknown')}",
                    file=sys.stderr,
                )
            continue
        if choice in {"h", "hold", "n", "no", "reject", "dontpost"}:
            try:
                reason = input("  reason (helps Bolt learn)> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n  cancelled hold")
                continue
            if not reason:
                reason = "held during interactive review"
            held = reject_next_clip(reason, clip.get("id"))
            if held:
                print(f"  ✓ held {held.get('id')}: {reason}")
                decisions += 1
            else:
                print("  could not hold that clip", file=sys.stderr)
            continue
        if choice in {"s", "skip", "next"}:
            skipped_ids.add(str(clip.get("id")))
            print(f"  skipped {clip.get('id')} for now")
            continue
        print("  unknown choice — use o/a/p/h/s/q")

    return decisions


# ── CLI ────────────────────────────────────────────────────────────────────────

QUEUE_CLI_HELP = """
Bolt post queue — ready clips, peak-hour approval, and posting.

IMPORTANT:
  Approval is NOT done in media/vertical_clips/.
  Queue *state* lives in Data/ready_to_post.json (ids, scores, approve/hold).
  Video *files* live under media/vertical_clips/ (watch them; don't "approve" there).

Simplest flow (no JSON, no remembering ids):
  bolt queue clean                   # drop ghost rows (missing video files)
  bolt queue list                    # only clips with a real local file
  bolt queue next                    # show the next clip + path (+ open with --open)
  bolt queue decide                  # interactive: open / approve / hold / post / skip
  bolt approve                       # approve that next clip for peak
  bolt dontpost "weak hook"          # hold next clip + reason
  bolt postnow                       # publish next clip now

Already edited files in media/vertical_clips/ (your final cuts):
  bolt queue add Stress.mp4 Hands.mp4 Leaving.mp4
  bolt queue add Stress.mp4 --approve          # queue + mark approved for peak
  bolt queue add Stress.mp4 --title "My hook"  # custom caption title
  bolt queue add Stress.mp4 --suggest-title    # AI/template title options applied
  # Editing a file does NOT register it — you must `queue add` once.

Titles / captions:
  bolt queue title                   # Suggest titles for the next postable clip
  bolt queue title <clip_id>         # Suggest titles for a specific clip
  bolt queue title <clip_id> 1       # Apply suggestion #1
  bolt queue title <clip_id> "Hook"  # Set a custom title
  bolt monitor_titles                # How past titles performed (learning)

Usage:
  bolt queue                         Summary + peak window (default)
  bolt queue status                  Same as summary
  bolt queue list                    Actionable clips only (id, score, file)
  bolt queue list --all              Include ghost / non-file rows
  bolt queue next [--open]           Show next postable clip card
  bolt queue decide                  Interactive review (recommended)
  bolt queue add <file> [file…]      Register hand-edited vertical clips
  bolt queue title [clip_id] [N|text] Suggest or set a caption title
  bolt queue approve [clip_id]       Approve for next peak auto-post
  bolt queue reject [clip_id] <why>  Hold a clip and record the reason
  bolt queue post-now [clip_id]      Publish immediately (TikTok)
  bolt queue mark-posted [clip_id]   Mark as posted (after manual upload)
  bolt queue clean [--dry-run]       Scrap ready rows whose video is missing
  bolt queue check                   Peak-window check + Discord alert if due
  bolt queue tick                    Run one auto-post scheduler tick
  bolt queue review-window           Send the 30-min pre-peak review alert
  bolt queue help                    This message

Short aliases (same module):
  bolt approve [clip_id]
  bolt postnow [clip_id]
  bolt dontpost [clip_id] <reason>

Legacy flags still work: --summary --approve --post-now --reject --mark-posted
"""


def _print_summary() -> None:
    s = queue_summary()
    with_file = len(_actionable_clips())
    print(
        f"\n  📋  Post Queue: {with_file} you can post  |  "
        f"{s['ready']} alertable  |  "
        f"{s['ready_total']} ready rows  |  {s['posted']} posted  |  {s['total']} total\n"
    )
    print(
        f"      auto-post: {s['awaiting_approval']} awaiting approval, "
        f"{s['approved']} approved, {s['held']} held, {s['publish_failed']} failed\n"
    )
    if s["missing"] or s["below_floor"]:
        print(
            f"      ignored: {s['missing']} ghost (missing file), "
            f"{s['below_floor']} below score floor"
        )
        if s["missing"]:
            print("               → run `bolt queue clean` to clear ghosts from the count\n")
        else:
            print()
    print("      Approve here (CLI / Twitch), not in the media folder.")
    print(f"      state:  {READY_FILE}")
    print("      videos: media/vertical_clips/\n")
    print("      quick:  bolt queue next  |  bolt queue decide  |  bolt approve\n")


def _looks_like_clip_id(token: str) -> bool:
    """Heuristic: short hex-ish ids from queue_clip (e.g. 55a802e8)."""
    if not token or token.startswith("-"):
        return False
    if len(token) > 16:
        return False
    return all(c.isalnum() or c in "-_" for c in token)


def _parse_reject_args(tokens: list[str]) -> tuple[str, str | None]:
    """Return (reason, clip_id|None) from reject/dontpost argv tokens."""
    if not tokens:
        return "", None
    if _looks_like_clip_id(tokens[0]) and len(tokens) >= 2:
        return " ".join(tokens[1:]).strip(), tokens[0]
    if _looks_like_clip_id(tokens[0]) and len(tokens) == 1:
        return "", tokens[0]
    return " ".join(tokens).strip(), None


def run_queue_cli(argv: list[str] | None = None) -> int:
    """CLI entry for ``bolt queue …`` / ``python -m modules.Peak_Hour_Notifier``."""
    args = list(argv if argv is not None else [])

    # Help always wins.
    if "--help" in args or "-h" in args or (args and args[0] in ("help",)):
        print(QUEUE_CLI_HELP.strip())
        return 0

    # ── Legacy flag forms (kept for scripts / docs) ──────────────────────────
    # Only when the *first* token is a flag (or bare flags with no subcommand).
    # Otherwise `bolt queue add X --approve` would be stolen by legacy --approve
    # and never register the file.
    first = args[0] if args else ""
    legacy_mode = (not args) or first.startswith("-")

    if legacy_mode:
        if "--mark-posted" in args:
            idx = args.index("--mark-posted")
            clip_id = (
                args[idx + 1]
                if idx + 1 < len(args) and not args[idx + 1].startswith("--")
                else None
            )
            mark_posted(clip_id)
            return 0
        if "--review-window" in args:
            n = alert_review_window()
            print(f"review alerts sent: {n}")
            return 0
        if "--auto-post-tick" in args:
            print(json.dumps(process_auto_post_queue(), indent=2))
            return 0
        if "--post-now" in args:
            idx = args.index("--post-now")
            clip_id = (
                args[idx + 1]
                if idx + 1 < len(args) and not args[idx + 1].startswith("--")
                else None
            )
            print(json.dumps(post_now(clip_id), indent=2, default=str))
            return 0
        if "--approve" in args:
            idx = args.index("--approve")
            clip_id = (
                args[idx + 1]
                if idx + 1 < len(args) and not args[idx + 1].startswith("--")
                else None
            )
            clip = approve_next_clip(clip_id)
            if not clip:
                print("no ready clip found to approve", file=sys.stderr)
                return 1
            print(json.dumps(clip, indent=2, default=str))
            return 0
        if "--reject" in args:
            idx = args.index("--reject")
            rest = args[idx + 1 :]
            reason, clip_id = _parse_reject_args(rest)
            clip = reject_next_clip(reason, clip_id)
            if not clip:
                print("no ready clip found to hold", file=sys.stderr)
                return 1
            print(json.dumps(clip, indent=2, default=str))
            return 0
        if "--reset-queue" in args:
            path = reset_queue()
            print(f"queue reset → {path}")
            return 0
        if "--summary" in args:
            _print_summary()
            return 0
        if "--dashboard" in args or "--list" in args:
            print(render_dashboard(max_clips=20, max_chars=4000))
            return 0

    # ── Friendly subcommand forms ────────────────────────────────────────────
    if not args:
        action = "status"
        rest: list[str] = []
    else:
        action, *rest = args

    action = action.lower().replace("_", "-")

    if action in ("help",):
        print(QUEUE_CLI_HELP.strip())
        return 0

    if action in ("status", "summary", "queue"):
        is_peak, info = _is_peak_now()
        print(f"\n  🕐  Current time zone: {POSTING_TIMEZONE}")
        print(f"  {'🔥 PEAK TIME' if is_peak else '💤 Off-peak'}  —  {info}")
        _print_summary()
        return 0

    if action in ("list", "dashboard", "qstatus"):
        show_all = "--all" in rest or "-a" in rest
        print(
            render_dashboard(
                max_clips=20,
                max_chars=8000,
                actionable_only=not show_all,
            )
        )
        return 0

    if action in ("next", "show", "show-next"):
        open_video = "--open" in rest or "-o" in rest
        clip = show_next_clip(open_video=open_video)
        return 0 if clip else 1

    if action in ("decide", "review", "triage", "pick"):
        # Interactive walkthrough. `review-window` remains the Discord ping.
        n = interactive_decide(open_first="--no-open" not in rest)
        print(f"decisions made: {n}")
        return 0

    if action in ("add", "add-clip", "register", "import"):
        # bolt queue add Stress.mp4 Hands.mp4 [--approve] [--title "..."] [--score 90]
        flags = set()
        title = None
        score = 90.0
        paths: list[str] = []
        i = 0
        while i < len(rest):
            tok = rest[i]
            if tok in ("--approve", "-a"):
                flags.add("approve")
                i += 1
                continue
            if tok in ("--suggest-title", "--ai-title", "--gen-title"):
                flags.add("suggest_title")
                i += 1
                continue
            if tok == "--title" and i + 1 < len(rest):
                title = rest[i + 1]
                i += 2
                continue
            if tok == "--score" and i + 1 < len(rest):
                try:
                    score = float(rest[i + 1])
                except ValueError:
                    print(f"invalid --score: {rest[i + 1]}", file=sys.stderr)
                    return 2
                i += 2
                continue
            if tok.startswith("-"):
                print(f"unknown flag for queue add: {tok}", file=sys.stderr)
                return 2
            paths.append(tok)
            i += 1
        if not paths:
            print(
                "usage: bolt queue add <file> [file…] [--approve] [--suggest-title] "
                "[--title TEXT] [--score N]",
                file=sys.stderr,
            )
            print(
                f"  files usually live in {_vertical_clips_dir()}",
                file=sys.stderr,
            )
            return 2
        if title is not None and len(paths) > 1:
            print(
                "note: --title applies only to the first file; others use filename",
                file=sys.stderr,
            )
        added = 0
        for idx, path_tok in enumerate(paths):
            use_title = title if idx == 0 else None
            try:
                item = add_manual_clip(
                    path_tok,
                    title=use_title,
                    score=score,
                    approve="approve" in flags,
                    suggest_title="suggest_title" in flags and use_title is None,
                )
            except FileNotFoundError as exc:
                print(str(exc), file=sys.stderr)
                continue
            added += 1
            state = (item.get("auto_post") or {}).get("status") or item.get("status")
            print(
                f"  + {item.get('id')}  {state}  "
                f"⭐{item.get('score')}  {_clip_display_name(item)}"
            )
            if item.get("title"):
                print(f"      title: {item.get('title')}")
        if not added:
            return 1
        print(
            f"\nadded {added} clip(s). Next: bolt queue list  |  bolt queue title  |  bolt postnow"
        )
        return 0

    if action in ("title", "titles", "retitle", "caption"):
        # bolt queue title [clip_id]           → suggest
        # bolt queue title [clip_id] 1         → apply suggestion N
        # bolt queue title [clip_id] "My hook" → set custom
        clip_id = None
        apply_token = None
        if rest:
            if _looks_like_clip_id(rest[0]):
                clip_id = rest[0]
                apply_token = " ".join(rest[1:]).strip() if len(rest) > 1 else None
            else:
                apply_token = " ".join(rest).strip()

        data = _load_ready()
        clip = _find_ready_clip(data, clip_id, require_file=True)
        if not clip and clip_id:
            for c in data.get("clips") or []:
                if c.get("id") == clip_id:
                    clip = c
                    break
        if not clip:
            print("no postable clip found for title tools", file=sys.stderr)
            return 1

        print(_format_clip_card(clip))
        titles, tags = _suggest_titles_for_clip(clip)
        print("\n  Suggested titles:")
        for i, t in enumerate(titles, 1):
            print(f"    {i}. {t}")
        if tags:
            print(f"  tags: {' '.join(tags[:10])}")

        if not apply_token:
            print(
                f"\n  Apply one:  bolt queue title {clip.get('id')} 1"
            )
            print(
                f"  Or custom:  bolt queue title {clip.get('id')} \"Your hook here\""
            )
            return 0

        # Numeric → pick suggestion; otherwise treat as custom title.
        if apply_token.isdigit():
            idx = int(apply_token)
            if idx < 1 or idx > len(titles):
                print(f"pick 1–{len(titles)}", file=sys.stderr)
                return 2
            chosen = titles[idx - 1]
            updated = set_clip_title(chosen, clip.get("id"), hashtags=tags or None)
        else:
            updated = set_clip_title(apply_token, clip.get("id"))
        if not updated:
            print("could not update title", file=sys.stderr)
            return 1
        print(f"\n  ✓ title set on {updated.get('id')}: {updated.get('title')}")
        return 0

    if action in ("approve",):
        clip_id = rest[0] if rest else None
        clip = approve_next_clip(clip_id)
        if not clip:
            print(
                "no postable clip found to approve "
                "(need status=ready + local video file)",
                file=sys.stderr,
            )
            return 1
        print(
            f"approved clip {clip.get('id')} for the next peak post"
            f"  ({clip.get('title', '')[:60]})"
        )
        print(f"  file: {_clip_display_name(clip)}")
        return 0

    if action in ("reject", "hold", "dontpost", "dont-post", "stopclip"):
        reason, clip_id = _parse_reject_args(rest)
        clip = reject_next_clip(reason, clip_id)
        if not clip:
            print("no ready clip found to hold", file=sys.stderr)
            return 1
        print(f"held clip {clip.get('id')}: {clip.get('hold_reason', reason)}")
        return 0

    if action in ("post-now", "postnow", "post"):
        clip_id = rest[0] if rest else None
        result = post_now(clip_id)
        clip = result.get("clip") or {}
        publish = result.get("result") or {}
        if not clip:
            print(publish.get("error", "no ready clip found"), file=sys.stderr)
            return 1
        if publish.get("success"):
            print(f"posted clip {clip.get('id')}")
            return 0
        print(
            f"tried to post clip {clip.get('id')}, but: "
            f"{publish.get('error', 'unknown error')}",
            file=sys.stderr,
        )
        return 1

    if action in ("mark-posted", "markposted", "posted"):
        clip_id = rest[0] if rest else None
        mark_posted(clip_id)
        return 0

    if action in ("clean", "clean-missing", "prune", "prune-missing"):
        dry = "--dry-run" in rest or "--dry" in rest
        result = clean_missing_clips(dry_run=dry)
        label = "would scrap" if dry else "scrapped"
        print(f"{label} {result['cleaned']} ghost ready row(s) (missing video file)")
        for row in result.get("clips") or []:
            print(f"  - {row.get('id')}  {row.get('title', '')[:50]}")
        if dry and result["cleaned"]:
            print("re-run without --dry-run to apply")
        return 0

    if action in ("check", "alert", "peak"):
        is_peak, info = _is_peak_now()
        print(f"\n  🕐  Current time zone: {POSTING_TIMEZONE}")
        print(f"  {'🔥 PEAK TIME' if is_peak else '💤 Off-peak'}  —  {info}")
        _print_summary()
        alert_peak_window()
        return 0

    if action in ("tick", "auto-post-tick", "process"):
        print(json.dumps(process_auto_post_queue(), indent=2))
        return 0

    if action in ("review-window",):
        n = alert_review_window()
        print(f"review alerts sent: {n}")
        return 0

    if action in ("reset", "reset-queue"):
        path = reset_queue()
        print(f"queue reset → {path}")
        return 0

    print(f"unknown queue action: {action}", file=sys.stderr)
    print("Run: bolt queue help", file=sys.stderr)
    return 2


if __name__ == "__main__":
    import sys

    raise SystemExit(run_queue_cli(sys.argv[1:]))
