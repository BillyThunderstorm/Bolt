#!/usr/bin/env python3
"""No-cost multi-platform publishing planner + honest auto-upload soft-fail.

Manual planner (READY): turns one finished vertical clip into a posting plan
for TikTok, YouTube Shorts, Instagram Reels, and Kick — captions, stagger
times, queue file — without paid APIs.

Auto-upload (PARTIAL / not implemented): ``try_publish`` and ``bolt multi
publish`` never upload; they soft-fail with ``Kick unavailable:`` /
``Instagram unavailable:`` (and similar) and point at ``bolt multi plan``.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Iterable, List, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo


DEFAULT_TIMEZONE = "America/Chicago"
# Anchor to repo Data/ (not CWD-relative pre-reorg data/).
# Multi_Publisher.py -> modules/ -> Core/ -> <repo root>
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLATFORM_QUEUE_FILE = _PROJECT_ROOT / "Data" / "multi_platform_queue.json"


class Platform(Enum):
    TIKTOK = "tiktok"
    YOUTUBE_SHORTS = "youtube_shorts"
    INSTAGRAM_REELS = "instagram_reels"
    KICK = "kick"


PLATFORM_LABELS = {
    Platform.TIKTOK: "TikTok",
    Platform.YOUTUBE_SHORTS: "YouTube Shorts",
    Platform.INSTAGRAM_REELS: "Instagram Reels",
    Platform.KICK: "Kick",
}

DEFAULT_PLATFORMS = [
    Platform.TIKTOK,
    Platform.YOUTUBE_SHORTS,
    Platform.INSTAGRAM_REELS,
    Platform.KICK,
]

STAGGER_DELAYS = {
    Platform.TIKTOK: timedelta(minutes=0),
    Platform.KICK: timedelta(minutes=10),
    Platform.YOUTUBE_SHORTS: timedelta(minutes=20),
    Platform.INSTAGRAM_REELS: timedelta(minutes=40),
}


def build_platform_plan(
    clip_path: str,
    title: str,
    hashtags: Optional[List[str]] = None,
    queued_at: Optional[datetime] = None,
    timezone: str = DEFAULT_TIMEZONE,
    platforms: Optional[Iterable[str | Platform]] = None,
) -> List[dict]:
    """Return manual posting metadata for each enabled platform."""
    tz = ZoneInfo(timezone)
    now = queued_at or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)

    tags = normalize_hashtags(hashtags or [])
    enabled = [_coerce_platform(p) for p in (platforms or DEFAULT_PLATFORMS)]
    plan = []
    for platform in enabled:
        scheduled_for = _next_platform_time(platform, now) + STAGGER_DELAYS[platform]
        metadata = _format_for_platform(platform, clip_path, title, tags)
        plan.append(
            {
                "platform": platform.value,
                "label": PLATFORM_LABELS[platform],
                "status": "manual_upload_ready",
                "scheduled_for": scheduled_for.isoformat(),
                "clip_path": str(clip_path),
                **metadata,
            }
        )
    return plan


def append_platform_plan(queue_id: str, platform_plan: List[dict]) -> dict:
    """Persist the platform plan to a dedicated no-cost queue file."""
    data = _load_platform_queue()
    data["items"] = [item for item in data["items"] if item.get("queue_id") != queue_id]
    data["items"].append(
        {
            "queue_id": queue_id,
            "created_at": datetime.now().isoformat(),
            "platforms": platform_plan,
        }
    )
    _save_platform_queue(data)
    return data["items"][-1]


def normalize_hashtags(hashtags: List[str]) -> List[str]:
    cleaned = []
    for tag in hashtags:
        text = str(tag).strip()
        if not text:
            continue
        if not text.startswith("#"):
            text = f"#{text}"
        text = text.replace(" ", "")
        if text not in cleaned:
            cleaned.append(text)
    return cleaned[:30]


def _format_for_platform(
    platform: Platform, clip_path: str, title: str, hashtags: List[str]
) -> dict:
    if platform == Platform.TIKTOK:
        return {
            "caption": _caption(title, hashtags[:5], limit=2200),
            "instructions": "Upload manually to TikTok with original game audio or a current trending sound.",
            "max_duration_seconds": 60,
            "aspect_ratio": "9:16",
        }
    if platform == Platform.YOUTUBE_SHORTS:
        yt_tags = _dedupe(["#Shorts", "#Gaming", *hashtags])[:15]
        return {
            "title": title[:100],
            "description": _caption(
                f"{title}\n\nDaily gaming highlights.",
                yt_tags,
                limit=5000,
            ),
            "instructions": "Upload manually as a YouTube Short; keep the vertical file and original audio.",
            "max_duration_seconds": 60,
            "aspect_ratio": "9:16",
        }
    if platform == Platform.INSTAGRAM_REELS:
        return {
            "caption": _caption(title, hashtags[:30], limit=2200),
            "instructions": "Upload manually as a Reel; use the same vertical clip and adjust cover frame in-app.",
            "max_duration_seconds": 90,
            "aspect_ratio": "9:16",
        }
    if platform == Platform.KICK:
        return {
            "title": title[:100],
            "description": f"Highlight from the stream: {Path(clip_path).name}",
            "instructions": "Share manually on Kick or use this metadata beside the stream clip.",
            "aspect_ratio": "9:16",
        }
    raise ValueError(f"Unsupported platform: {platform}")


def _next_platform_time(platform: Platform, now: datetime) -> datetime:
    target_hours = {
        Platform.TIKTOK: 19,
        Platform.YOUTUBE_SHORTS: 8,
        Platform.INSTAGRAM_REELS: 17,
        Platform.KICK: 19,
    }
    target = now.replace(hour=target_hours[platform], minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def _caption(title: str, hashtags: List[str], limit: int) -> str:
    text = f"{title}\n\n{' '.join(hashtags)}".strip()
    return text[:limit].rstrip()


def _dedupe(values: List[str]) -> List[str]:
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _coerce_platform(value: str | Platform) -> Platform:
    if isinstance(value, Platform):
        return value
    normalized = str(value).strip().lower()
    aliases = {
        "youtube": Platform.YOUTUBE_SHORTS,
        "shorts": Platform.YOUTUBE_SHORTS,
        "yt": Platform.YOUTUBE_SHORTS,
        "instagram": Platform.INSTAGRAM_REELS,
        "reels": Platform.INSTAGRAM_REELS,
        "ig": Platform.INSTAGRAM_REELS,
        "tt": Platform.TIKTOK,
    }
    if normalized in aliases:
        return aliases[normalized]
    try:
        return Platform(normalized)
    except ValueError as exc:
        raise ValueError(f"Unknown platform: {value}") from exc


def _load_platform_queue() -> dict:
    PLATFORM_QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if PLATFORM_QUEUE_FILE.exists():
        try:
            return json.loads(PLATFORM_QUEUE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"items": []}


def _save_platform_queue(data: dict) -> None:
    PLATFORM_QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PLATFORM_QUEUE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def list_platform_queue(limit: int = 10) -> list[dict]:
    """Return the newest platform-plan items (most recent first)."""
    data = _load_platform_queue()
    items = list(data.get("items") or [])
    items.reverse()
    return items[: max(1, limit)]


_UNAVAILABLE_PREFIX = {
    Platform.TIKTOK: "TikTok unavailable:",
    Platform.YOUTUBE_SHORTS: "YouTube Shorts unavailable:",
    Platform.INSTAGRAM_REELS: "Instagram unavailable:",
    Platform.KICK: "Kick unavailable:",
}


def status(*, probe: bool = False) -> dict:
    """
    Multi_Publisher readiness (separate from queue listing).

    ready = True when the manual planner works (module importable + can build
    a plan + queue path writable). auto_upload is False for every platform —
    Kick/IG (and TT/Shorts here) have no upload API wired.

    Soft-fail hints use ``Kick unavailable:`` / ``Instagram unavailable:``
    prefixes when auto-upload is requested/missing. Never raises; never hangs;
    never opens a browser. ``probe`` is accepted for API symmetry (no network).
    """
    del probe  # no live network probe for the planner
    platforms_info: dict = {}
    hints: list[str] = []
    plan_ok = False
    queue_writable = False
    recent_count = 0
    error = ""

    try:
        sample = build_platform_plan(
            "/tmp/bolt_multi_status_probe.mp4",
            "Bolt multi status probe",
            hashtags=["#Bolt"],
        )
        plan_ok = bool(sample) and len(sample) >= 1
    except Exception as exc:
        error = f"plan build failed: {exc}"
        plan_ok = False

    try:
        PLATFORM_QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Touch-check: directory must be writable; do not rewrite queue contents.
        queue_writable = os.access(PLATFORM_QUEUE_FILE.parent, os.W_OK)
        if PLATFORM_QUEUE_FILE.exists() and not os.access(PLATFORM_QUEUE_FILE, os.W_OK):
            queue_writable = False
    except Exception as exc:
        queue_writable = False
        if not error:
            error = f"queue path check failed: {exc}"

    try:
        data = _load_platform_queue()
        recent_count = len(data.get("items") or [])
    except Exception:
        recent_count = 0

    for platform in DEFAULT_PLATFORMS:
        prefix = _UNAVAILABLE_PREFIX[platform]
        platforms_info[platform.value] = {
            "label": PLATFORM_LABELS[platform],
            "manual_plan": bool(plan_ok),
            "auto_upload": False,
            "hint": (
                f"{prefix} auto-upload not implemented. "
                "Use `bolt multi plan` / queue package / upload manually."
            ),
        }
        hints.append(platforms_info[platform.value]["hint"])

    ready = bool(plan_ok and queue_writable)
    info: dict = {
        "ready": ready,
        "auto_upload": False,
        "manual_planner": True,
        "plan_ok": plan_ok,
        "queue_writable": queue_writable,
        "queue_file": str(PLATFORM_QUEUE_FILE),
        "recent_item_count": recent_count,
        "platforms": platforms_info,
        "hint": (
            "Manual multi plans READY (TikTok/Shorts/Reels/Kick). "
            "Auto-upload PARTIAL: Kick/Instagram (and all platforms here) "
            "soft-fail — use `bolt multi plan` then upload manually. "
            "TikTok Content Posting API remains paused (see PARTIAL publish)."
        ),
        "soft_fail_prefixes": {
            "kick": "Kick unavailable:",
            "instagram_reels": "Instagram unavailable:",
            "tiktok": "TikTok unavailable:",
            "youtube_shorts": "YouTube Shorts unavailable:",
        },
    }
    if error:
        info["error"] = error
        info["hint"] = f"Multi_Publisher planner issue: {error}"
        info["ready"] = False
    if not ready and not error:
        info["hint"] = (
            "Multi_Publisher planner not ready "
            f"(plan_ok={plan_ok}, queue_writable={queue_writable})."
        )
    return info


def try_publish(
    platform,
    clip_path=None,
    title=None,
    **_,
) -> dict:
    """
    Never uploads. Always soft-fails with platform unavailable prefixes.

    Returns a dict: ok=False, uploaded=False, platform, error/hint with
    ``Kick unavailable:`` / ``Instagram unavailable:`` etc. Never raises;
    never hangs; never opens a browser.
    """
    try:
        plat = _coerce_platform(platform)
    except Exception as exc:
        raw = str(platform).strip().lower()
        if raw in ("ig", "instagram", "reels", "instagram_reels"):
            prefix = "Instagram unavailable:"
            key = "instagram_reels"
        elif "kick" in raw:
            prefix = "Kick unavailable:"
            key = "kick"
        elif "tiktok" in raw or raw == "tt":
            prefix = "TikTok unavailable:"
            key = "tiktok"
        elif "youtube" in raw or "short" in raw:
            prefix = "YouTube Shorts unavailable:"
            key = "youtube_shorts"
        else:
            prefix = "Multi publish unavailable:"
            key = raw or "unknown"
        msg = (
            f"{prefix} unknown platform {platform!r} ({exc}). "
            "Use kick|instagram|instagram_reels|reels|ig|tiktok|youtube|shorts. "
            "Hint: `bolt multi plan` / queue package / manual upload."
        )
        return {
            "ok": False,
            "uploaded": False,
            "auto_upload": False,
            "platform": key,
            "clip_path": str(clip_path) if clip_path else None,
            "title": title,
            "error": msg,
            "hint": msg,
        }

    prefix = _UNAVAILABLE_PREFIX[plat]
    label = PLATFORM_LABELS[plat]
    msg = (
        f"{prefix} auto-upload not implemented for {label}. "
        "Use `bolt multi plan` (or Peak_Hour queue package) then upload manually. "
        "Never opens a browser from this command."
    )
    return {
        "ok": False,
        "uploaded": False,
        "auto_upload": False,
        "platform": plat.value,
        "label": label,
        "clip_path": str(clip_path) if clip_path else None,
        "title": title,
        "error": msg,
        "hint": msg,
    }


def _print_plan(platforms: list[dict], indent: str = "  ") -> None:
    for p in platforms:
        when = (p.get("scheduled_for") or "")[:16]
        label = p.get("label") or p.get("platform") or "?"
        status = p.get("status") or ""
        print(f"{indent}• {label:<18} {when}  [{status}]")
        instr = p.get("instructions")
        if instr:
            print(f"{indent}  {instr}")


def _main() -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description=(
            "No-cost multi-platform posting planner "
            "(TikTok / YouTube Shorts / Instagram Reels / Kick). "
            "Manual plans READY; auto-upload soft-fails "
            "(Kick unavailable: / Instagram unavailable:). "
            "Writes Data/multi_platform_queue.json — does not upload."
        )
    )
    sub = parser.add_subparsers(dest="cmd")

    p_status = sub.add_parser(
        "status",
        help="Readiness + recent saved platform plans (default)",
    )
    p_status.add_argument(
        "--limit", type=int, default=10, help="How many queue items to show"
    )
    p_status.add_argument("--json", action="store_true")
    p_status.add_argument(
        "--probe",
        action="store_true",
        help="Accepted for API symmetry (no network; planner-only)",
    )

    p_plan = sub.add_parser(
        "plan", help="Build a platform plan for one clip (optionally save)"
    )
    p_plan.add_argument("clip_path")
    p_plan.add_argument("title")
    p_plan.add_argument("--hashtags", nargs="*", default=[])
    p_plan.add_argument(
        "--save",
        metavar="QUEUE_ID",
        default=None,
        help="Persist under this queue id in Data/multi_platform_queue.json",
    )
    p_plan.add_argument("--json", action="store_true")

    p_show = sub.add_parser("show", help="Show one saved plan by queue id")
    p_show.add_argument("queue_id")
    p_show.add_argument("--json", action="store_true")

    p_pub = sub.add_parser(
        "publish",
        help=(
            "Soft-fail auto-upload (never uploads). "
            "kick|instagram|tiktok|youtube|…"
        ),
    )
    p_pub.add_argument(
        "platform",
        help="kick|instagram|instagram_reels|reels|ig|tiktok|youtube|shorts|…",
    )
    p_pub.add_argument("--clip", dest="clip_path", default=None)
    p_pub.add_argument("--title", default=None)
    p_pub.add_argument("--json", action="store_true")

    # Backward-compatible: `python -m modules.Multi_Publisher CLIP TITLE`
    # with no subcommand still builds a plan (no save).
    args, unknown = parser.parse_known_args()
    if args.cmd is None and unknown:
        # Legacy positional form
        legacy = argparse.ArgumentParser()
        legacy.add_argument("clip_path")
        legacy.add_argument("title")
        legacy.add_argument("--hashtags", nargs="*", default=[])
        larg = legacy.parse_args(unknown)
        plan = build_platform_plan(larg.clip_path, larg.title, larg.hashtags)
        print(json.dumps(plan, indent=2))
        return 0

    if args.cmd is None:
        args.cmd = "status"
        if not hasattr(args, "limit"):
            args.limit = 10
        if not hasattr(args, "json"):
            args.json = False
        if not hasattr(args, "probe"):
            args.probe = False

    if args.cmd == "status":
        info = status(probe=bool(getattr(args, "probe", False)))
        items = list_platform_queue(limit=args.limit)
        if args.json:
            payload = dict(info)
            payload["queue"] = {
                "file": str(PLATFORM_QUEUE_FILE),
                "recent_item_count": info.get("recent_item_count", 0),
                "items": items,
            }
            json.dump(payload, sys.stdout, indent=2)
            sys.stdout.write("\n")
            return 0
        # Human: lead with auto-upload honesty, then recent plans
        print("Multi_Publisher readiness")
        print("─" * 40)
        flag = "✓" if info.get("ready") else "○"
        print(f"  {flag}  ready (manual planner): {bool(info.get('ready'))}")
        print(f"  ○  auto_upload: False (all platforms)")
        print(f"  queue: {info.get('queue_file')}")
        print(f"  recent plans: {info.get('recent_item_count', 0)}")
        if info.get("hint"):
            print(f"  → {info['hint']}")
        print()
        print("  Per-platform:")
        for key, meta in (info.get("platforms") or {}).items():
            mp = "✓" if meta.get("manual_plan") else "○"
            print(
                f"    {mp} {meta.get('label') or key}: "
                f"manual_plan={bool(meta.get('manual_plan'))} "
                f"auto_upload={bool(meta.get('auto_upload'))}"
            )
            if meta.get("hint"):
                print(f"      → {meta['hint']}")
        print()
        path = PLATFORM_QUEUE_FILE
        print(f"Recent platform plans ({path})")
        if not items:
            print("  (empty — plans are written when Peak_Hour queues a clip)")
            return 0
        print(f"  Showing {len(items)} newest item(s)\n")
        for item in items:
            qid = item.get("queue_id") or "?"
            created = (item.get("created_at") or "")[:19]
            platforms = item.get("platforms") or []
            print(f"• {qid}  ({created})  {len(platforms)} platform(s)")
            _print_plan(platforms)
            print()
        return 0

    if args.cmd == "plan":
        plan = build_platform_plan(args.clip_path, args.title, args.hashtags)
        if args.save:
            append_platform_plan(args.save, plan)
        if args.json:
            json.dump(plan, sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            print(f"Plan for: {args.title}")
            print(f"Clip:     {args.clip_path}")
            if args.save:
                print(f"Saved as: {args.save} → {PLATFORM_QUEUE_FILE}")
            _print_plan(plan)
        return 0

    if args.cmd == "show":
        data = _load_platform_queue()
        match = next(
            (i for i in (data.get("items") or []) if i.get("queue_id") == args.queue_id),
            None,
        )
        if not match:
            print(f"No plan with queue_id={args.queue_id!r} in {PLATFORM_QUEUE_FILE}")
            return 1
        if args.json:
            json.dump(match, sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            print(f"queue_id: {match.get('queue_id')}")
            print(f"created:  {match.get('created_at')}")
            _print_plan(match.get("platforms") or [])
        return 0

    if args.cmd == "publish":
        result = try_publish(
            args.platform,
            clip_path=getattr(args, "clip_path", None),
            title=getattr(args, "title", None),
        )
        if args.json:
            json.dump(result, sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            print(result.get("error") or result.get("hint") or "publish soft-fail")
            print("  Hint: bolt multi plan <clip> \"<title>\" [--save QUEUE_ID]")
        return 0  # soft-fail informational (Streamlabs/Drive style)

    parser.print_help()
    return 2



if __name__ == "__main__":
    import sys

    sys.exit(_main())
