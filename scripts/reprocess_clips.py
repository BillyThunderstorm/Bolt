#!/usr/bin/env python3
"""
reprocess_clips.py — Reprocess existing clips into TikTok vertical format
and rebuild the multi-platform post queue with correct file paths.

Usage:
  python3 scripts/reprocess_clips.py           → reprocess all clips
  python3 scripts/reprocess_clips.py --dry-run → just show what would be done

Does NOT auto-upload to TikTok (manual queue only). Soft-fail CLI wrapper:
  bolt reprocess status|list|run
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Repo root (not scripts/)
REPO_ROOT = Path(__file__).resolve().parents[1]
_CORE = REPO_ROOT / "Core"
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))


def _resolve_clips_dir() -> Path:
    modern = REPO_ROOT / "media" / "clips"
    legacy = REPO_ROOT / "clips"
    if modern.is_dir():
        return modern
    if legacy.is_dir():
        return legacy
    return modern


def _resolve_vertical_dir() -> Path:
    modern = REPO_ROOT / "media" / "vertical_clips"
    legacy = REPO_ROOT / "vertical_clips"
    if modern.is_dir():
        return modern
    if legacy.is_dir():
        return legacy
    return modern


CLIPS_DIR = _resolve_clips_dir()
VERTICAL_DIR = _resolve_vertical_dir()
QUEUE_FILE = REPO_ROOT / "Data" / "multi_platform_queue.json"
OLD_QUEUE_FILE = REPO_ROOT / "Data" / "multi_platform_queue.json.bak"

format_for_tiktok = None  # type: ignore
load_config = None  # type: ignore
_IMPORT_ERROR = ""

try:
    from modules.Clip_Factory import format_for_tiktok as _fft
    from modules.Config_Loader import load_config as _lc

    format_for_tiktok = _fft
    load_config = _lc
except Exception as exc:  # soft import — clear message, no traceback dump
    _IMPORT_ERROR = str(exc)

STYLE = "letterbox"
HASHTAGS = ["gaming", "clips", "viral", "fyp"]
if load_config is not None:
    try:
        config = load_config()
        STYLE = config.get("tiktok_style", STYLE)
        HASHTAGS = config.get("hashtags", HASHTAGS)
    except Exception as exc:
        print(f"Warning: config load failed ({exc}); using defaults", file=sys.stderr)

PEAK_WINDOWS = [
    {"label": "Morning", "start_hour": 7, "end_hour": 9},
    {"label": "Lunch", "start_hour": 12, "end_hour": 14},
    {"label": "Prime Time", "start_hour": 19, "end_hour": 22},
]

PLATFORMS = [
    {
        "platform": "tiktok",
        "label": "TikTok",
        "max_duration_seconds": 60,
        "aspect_ratio": "9:16",
    },
    {
        "platform": "youtube_shorts",
        "label": "YouTube Shorts",
        "max_duration_seconds": 60,
        "aspect_ratio": "9:16",
    },
    {
        "platform": "instagram_reels",
        "label": "Instagram Reels",
        "max_duration_seconds": 90,
        "aspect_ratio": "9:16",
    },
    {
        "platform": "twitter",
        "label": "X (Twitter)",
        "max_duration_seconds": 140,
        "aspect_ratio": "9:16",
    },
]


def get_clips():
    """Get all mp4 clips in the clips directory."""
    if not CLIPS_DIR.is_dir():
        return []
    return sorted(CLIPS_DIR.glob("*.mp4"))


def get_existing_vertical():
    """Get set of clip names that already have vertical versions."""
    existing = set()
    if not VERTICAL_DIR.is_dir():
        return existing
    for f in VERTICAL_DIR.glob("*_tiktok.mp4"):
        base = f.stem.replace("_tiktok", "")
        existing.add(base)
    return existing


def build_queue_entry(clip_path, vertical_path, index):
    """Build a queue entry with all platform info."""
    clip_name = Path(clip_path).stem
    hashtags = " ".join(f"#{h}" for h in HASHTAGS)

    title = clip_name.replace("_audio_spike_", " - Highlight ").replace("_", " ")

    window = PEAK_WINDOWS[index % len(PEAK_WINDOWS)]

    platforms = []
    for p in PLATFORMS:
        entry = {
            "platform": p["platform"],
            "label": p["label"],
            "status": "manual_upload_ready",
            "clip_path": str(vertical_path),
            "title": title,
            "caption": f"{title}\n\n{hashtags}",
            "description": f"{title}\n\nDaily gaming highlights.\n\n{hashtags}",
            "instructions": f"Upload manually to {p['label']}. Use original audio or a trending sound.",
            "max_duration_seconds": p["max_duration_seconds"],
            "aspect_ratio": p["aspect_ratio"],
            "scheduled_for_window": window["label"],
        }
        platforms.append(entry)

    return {
        "queue_id": f"reprocess-{index:03d}",
        "created_at": datetime.now().isoformat(),
        "clip_name": clip_name,
        "original_clip_path": str(clip_path),
        "platforms": platforms,
    }


def main() -> int:
    dry_run = "--dry-run" in sys.argv or "-n" in sys.argv

    if _IMPORT_ERROR and not dry_run:
        print(
            f"Error: Core imports failed ({_IMPORT_ERROR}). "
            "Ensure PYTHONPATH includes Core/ (or run via: bolt reprocess run).",
            file=sys.stderr,
        )
        return 1

    clips = get_clips()
    existing_vertical = get_existing_vertical()
    need = max(0, len(clips) - len(existing_vertical))

    print(f"REPO_ROOT: {REPO_ROOT}")
    print(f"Found {len(clips)} clips in {CLIPS_DIR.relative_to(REPO_ROOT)}/")
    print(f"Already have vertical versions for {len(existing_vertical)} clips ({VERTICAL_DIR.relative_to(REPO_ROOT)}/)")
    print(f"Need to process: {need}")
    print(f"Queue: {QUEUE_FILE.relative_to(REPO_ROOT)}")
    print()

    if dry_run:
        if not clips:
            print(f"  (no *.mp4 under {CLIPS_DIR})")
        for clip in clips:
            base = clip.stem
            status = "✓ exists" if base in existing_vertical else "→ process"
            print(f"  {status}  {clip.name}")
        if _IMPORT_ERROR:
            print(
                f"\nNote: Core imports currently fail ({_IMPORT_ERROR}); "
                "dry-run listing only. Fix imports before a real run.",
                file=sys.stderr,
            )
        return 0

    if format_for_tiktok is None:
        print(
            f"Error: Clip_Factory.format_for_tiktok unavailable ({_IMPORT_ERROR})",
            file=sys.stderr,
        )
        return 1

    # Ensure dirs exist before writing
    VERTICAL_DIR.mkdir(parents=True, exist_ok=True)
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Backup old queue beside it
    if QUEUE_FILE.exists():
        shutil.copy(QUEUE_FILE, OLD_QUEUE_FILE)
        print(f"Backed up old queue to {OLD_QUEUE_FILE.name}")

    new_items = []
    processed = 0
    skipped = 0
    failed = 0

    for i, clip in enumerate(clips):
        base = clip.stem
        vertical_path = VERTICAL_DIR / f"{base}_tiktok.mp4"

        if base in existing_vertical and vertical_path.exists():
            print(f"[{i+1}/{len(clips)}] SKIP (already exists): {clip.name}")
            skipped += 1
        else:
            print(f"[{i+1}/{len(clips)}] PROCESSING: {clip.name}")
            try:
                result = format_for_tiktok(
                    str(clip), output_dir=str(VERTICAL_DIR), style=STYLE
                )
                if result and os.path.exists(result):
                    vertical_path = Path(result)
                    print(
                        f"  → Done: {vertical_path.name} "
                        f"({vertical_path.stat().st_size / (1024*1024):.1f} MB)"
                    )
                    processed += 1
                else:
                    print("  → FAILED: formatter returned invalid path")
                    failed += 1
                    continue
            except Exception as e:
                print(f"  → FAILED: {e}")
                failed += 1
                continue

        entry = build_queue_entry(clip, vertical_path, i)
        new_items.append(entry)

    queue_data = {"items": new_items}
    with open(QUEUE_FILE, "w") as f:
        json.dump(queue_data, f, indent=2)

    print()
    print("=" * 60)
    print("COMPLETE")
    print(f"  Processed: {processed}")
    print(f"  Skipped (already existed): {skipped}")
    print(f"  Failed: {failed}")
    print(f"  Total in queue: {len(new_items)}")
    print(f"  Queue saved to: {QUEUE_FILE}")
    print("  (No TikTok auto-upload — queue is manual_upload_ready)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
