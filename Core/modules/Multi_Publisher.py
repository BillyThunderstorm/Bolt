#!/usr/bin/env python3
"""No-cost multi-platform publishing planner.

This module does not upload clips. It turns one finished vertical clip into a
manual posting plan for TikTok, YouTube Shorts, Instagram Reels, and Kick so
Bolt can expand reach without needing paid APIs or new hosted services.
"""

from __future__ import annotations

import json
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
        "instagram": Platform.INSTAGRAM_REELS,
        "reels": Platform.INSTAGRAM_REELS,
    }
    try:
        return aliases.get(normalized, Platform(normalized))
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
            "Does not upload — writes Data/multi_platform_queue.json."
        )
    )
    sub = parser.add_subparsers(dest="cmd")

    p_status = sub.add_parser(
        "status", help="Show recent saved platform plans (default)"
    )
    p_status.add_argument(
        "--limit", type=int, default=10, help="How many queue items to show"
    )
    p_status.add_argument("--json", action="store_true")

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

    if args.cmd == "status":
        items = list_platform_queue(limit=args.limit)
        if args.json:
            json.dump(items, sys.stdout, indent=2)
            sys.stdout.write("\n")
            return 0
        path = PLATFORM_QUEUE_FILE
        print(f"Multi-platform queue: {path}")
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

    parser.print_help()
    return 2


if __name__ == "__main__":
    import sys

    sys.exit(_main())
