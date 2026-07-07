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
READY_FILE = Path("data/ready_to_post.json")
CONFIG_FILE = Path("config.json")
REJECTION_LOG = Path("data/post_rejections.jsonl")

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


def _is_alertable_clip(clip: dict) -> bool:
    """
    Return True when a queue row is safe to include in peak-hour alerts.

    Old queue rows can survive config changes or iCloud sync without their media
    files. Keep those rows for history, but do not alert Billy to post clips that
    are missing locally or below the current score floor.
    """
    return (
        clip.get("status") == "ready"
        and clip.get("tier", "queue") == "queue"
        and _clip_file_exists(clip)
        and _score_clears_floor(clip)
    )


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
            ]
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


def _review_message(clips: list[dict]) -> str:
    lines = [
        "🔔 **Post ready and awaiting your approval.**",
        "Peak hours are close. Reply in Twitch chat with `!postnow` to approve now or `!dontpost <reason>` to hold.",
        "If the deadline passes with no rejection, Bolt will try to auto-post.",
        "",
    ]
    for clip in clips:
        plan = clip.get("auto_post", {})
        lines.append(
            f"- `{clip.get('id')}` **{clip.get('title')}** | score {clip.get('score')} | deadline {plan.get('approval_deadline')}"
        )
    return "\n".join(lines)


def approve_next_clip(clip_id: str = None) -> dict:
    """Approve one waiting clip, or the first waiting/ready clip."""
    data = _load_ready()
    now = _now()
    for clip in data["clips"]:
        if clip.get("status") != "ready":
            continue
        if clip_id and clip.get("id") != clip_id:
            continue
        plan = _ensure_auto_post_plan(clip, now)
        if plan.get("status") in {"scheduled", "awaiting_approval", "publish_failed"}:
            plan["status"] = "approved"
            plan["approved_at"] = now.isoformat()
            _save_ready(data)
            notify(
                f"Approved clip {clip.get('id')} for auto-post",
                level="success",
                reason="Bolt will post at the scheduled peak time, or you can use !postnow to publish immediately.",
            )
            return clip
    return {}


def reject_next_clip(reason: str = "", clip_id: str = None) -> dict:
    """Hold one waiting/ready clip and record why it should not post."""
    data = _load_ready()
    now = _now()
    reason = reason.strip()
    if not reason:
        reason = "No rejection reason provided yet"

    for clip in data["clips"]:
        if clip.get("status") != "ready":
            continue
        if clip_id and clip.get("id") != clip_id:
            continue
        plan = _ensure_auto_post_plan(clip, now)
        if plan.get("status") in {
            "scheduled",
            "awaiting_approval",
            "approved",
            "publish_failed",
        }:
            clip["status"] = "held"
            clip["held_at"] = now.isoformat()
            clip["hold_reason"] = reason
            plan["status"] = "rejected"
            plan["rejected_at"] = now.isoformat()
            plan["rejection_reason"] = reason
            _record_rejection(clip, reason)
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
    return {}


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
    for clip in data["clips"]:
        if clip.get("status") != "ready":
            continue
        if clip_id and clip.get("id") != clip_id:
            continue
        if not force and not _is_alertable_clip(clip):
            continue
        result = _publish_clip(clip, now, reason="manual override")
        _save_ready(data)
        return {"clip": clip, "result": result}
    return {"clip": None, "result": {"success": False, "error": "No ready clip found"}}


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
        if deadline_missed or approved_due:
            result = _publish_clip(
                clip, now, reason="deadline missed" if deadline_missed else "approved"
            )
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
        _send_discord(_review_message(waiting))
        notify(
            "Post ready and awaiting your approval.",
            level="success",
            reason=f"{stats['review_alerted']} clip(s) entered the review window.",
        )

    _save_ready(data)
    return stats


def _publish_clip(clip: dict, now: datetime, reason: str) -> dict:
    plan = _ensure_auto_post_plan(clip, now)
    plan["last_publish_attempt_at"] = now.isoformat()
    plan["last_publish_reason"] = reason
    try:
        from modules.TikTok_Publisher import publish_clip

        config = _auto_posting_config()
        result = publish_clip(
            clip.get("clip_path", ""),
            clip.get("title", ""),
            hashtags=clip.get("hashtags", []),
            privacy=config["privacy"],
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
            reason=f"Published after {reason}.",
        )
    else:
        plan["status"] = "publish_failed"
        plan["publish_error"] = result.get("error", "unknown error")
        notify(
            f"Auto-post failed for clip {clip.get('id')}",
            level="warning",
            reason=f"{plan['publish_error']}. Clip remains ready for manual posting or retry.",
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
    }


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    args = sys.argv[1:]

    if "--mark-posted" in args:
        mark_posted()
    elif "--review-window" in args:
        alert_review_window()
    elif "--auto-post-tick" in args:
        result = process_auto_post_queue()
        print(json.dumps(result, indent=2))
    elif "--post-now" in args:
        clip_id = (
            args[args.index("--post-now") + 1]
            if args.index("--post-now") + 1 < len(args)
            else None
        )
        print(json.dumps(post_now(clip_id), indent=2, default=str))
    elif "--approve" in args:
        clip_id = (
            args[args.index("--approve") + 1]
            if args.index("--approve") + 1 < len(args)
            else None
        )
        print(json.dumps(approve_next_clip(clip_id), indent=2, default=str))
    elif "--reject" in args:
        idx = args.index("--reject")
        clip_id = (
            args[idx + 1]
            if idx + 1 < len(args) and not args[idx + 1].startswith("--")
            else None
        )
        reason = " ".join(args[idx + 2 :] if clip_id else args[idx + 1 :])
        print(json.dumps(reject_next_clip(reason, clip_id), indent=2, default=str))
    elif "--reset-queue" in args:
        reset_queue()
    elif "--summary" in args:
        s = queue_summary()
        print(
            f"\n  📋  Post Queue: {s['ready']} alertable  |  "
            f"{s['ready_total']} ready rows  |  {s['posted']} posted  |  {s['total']} total\n"
        )
        print(
            f"      auto-post: {s['awaiting_approval']} awaiting approval, "
            f"{s['approved']} approved, {s['held']} held, {s['publish_failed']} failed\n"
        )
        if s["missing"] or s["below_floor"]:
            print(
                f"      ignored: {s['missing']} missing file(s), {s['below_floor']} below score floor\n"
            )
    else:
        # Default: check peak hours and alert if applicable
        is_peak, info = _is_peak_now()
        print(f"\n  🕐  Current time zone: {POSTING_TIMEZONE}")
        print(f"  {'🔥 PEAK TIME' if is_peak else '💤 Off-peak'}  —  {info}")
        s = queue_summary()
        print(
            f"  📋  Post Queue: {s['ready']} alertable / {s['ready_total']} ready row(s)\n"
        )
        alert_peak_window()
