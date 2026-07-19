#!/usr/bin/env python3
"""
reprocess_clips.py — Reprocess all existing clips into TikTok vertical format
and rebuild the post queue with correct file paths.

Usage:
  python3 reprocess_clips.py           → reprocess all clips
  python3 reprocess_clips.py --dry-run → just show what would be done
"""

import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime

# Make project root importable
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

CLIPS_DIR = PROJECT_ROOT / "clips"
VERTICAL_DIR = PROJECT_ROOT / "vertical_clips"
QUEUE_FILE = PROJECT_ROOT / "data" / "multi_platform_queue.json"
OLD_QUEUE_FILE = PROJECT_ROOT / "data" / "multi_platform_queue.json.bak"

from modules.Clip_Factory import format_for_tiktok
from modules.Config_Loader import load_config

config = load_config()
STYLE = config.get("tiktok_style", "letterbox")
HASHTAGS = config.get("hashtags", ["gaming", "clips", "viral", "fyp"])

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
    clips = sorted(CLIPS_DIR.glob("*.mp4"))
    return clips


def get_existing_vertical():
    """Get set of clip names that already have vertical versions."""
    existing = set()
    for f in VERTICAL_DIR.glob("*_tiktok.mp4"):
        # Extract original clip name
        base = f.stem.replace("_tiktok", "")
        existing.add(base)
    return existing


def build_queue_entry(clip_path, vertical_path, index):
    """Build a queue entry with all platform info."""
    clip_name = Path(clip_path).stem
    hashtags = " ".join(f"#{h}" for h in HASHTAGS)

    # Simple title from clip name
    title = clip_name.replace("_audio_spike_", " - Highlight ").replace("_", " ")

    # Spread clips across peak windows
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


def main():
    dry_run = "--dry-run" in sys.argv

    clips = get_clips()
    existing_vertical = get_existing_vertical()

    print(f"Found {len(clips)} clips in clips/")
    print(f"Already have vertical versions for {len(existing_vertical)} clips")
    print(f"Need to process: {len(clips) - len(existing_vertical)}")
    print()

    if dry_run:
        for clip in clips:
            base = clip.stem
            status = "✓ exists" if base in existing_vertical else "→ process"
            print(f"  {status}  {clip.name}")
        return

    # Backup old queue
    if QUEUE_FILE.exists():
        import shutil
        shutil.copy(QUEUE_FILE, OLD_QUEUE_FILE)
        print(f"Backed up old queue to {OLD_QUEUE_FILE.name}")

    # Process clips
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
                result = format_for_tiktok(str(clip), output_dir=str(VERTICAL_DIR), style=STYLE)
                if result and os.path.exists(result):
                    vertical_path = Path(result)
                    print(f"  → Done: {vertical_path.name} ({vertical_path.stat().st_size / (1024*1024):.1f} MB)")
                    processed += 1
                else:
                    print(f"  → FAILED: formatter returned invalid path")
                    failed += 1
                    continue
            except Exception as e:
                print(f"  → FAILED: {e}")
                failed += 1
                continue

        # Build queue entry
        entry = build_queue_entry(clip, vertical_path, i)
        new_items.append(entry)

    # Write new queue
    queue_data = {"items": new_items}
    with open(QUEUE_FILE, "w") as f:
        json.dump(queue_data, f, indent=2)

    print()
    print("=" * 60)
    print(f"COMPLETE")
    print(f"  Processed: {processed}")
    print(f"  Skipped (already existed): {skipped}")
    print(f"  Failed: {failed}")
    print(f"  Total in queue: {len(new_items)}")
    print(f"  Queue saved to: {QUEUE_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()