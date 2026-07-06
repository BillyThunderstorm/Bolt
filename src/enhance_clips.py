#!/usr/bin/env python3
"""
enhance_clips.py — Pipeline: Smart_Trim → Text_Overlay
======================================================
Processes all vertical clips through the enhancement pipeline:

  1. Smart_Trim  → vertical_clips_trimmed/  (find peak, trim to 18s)
  2. Text_Overlay → vertical_clips_final/   (burn hook captions)

Idempotent: skips clips that already exist in vertical_clips_final/.
Supports --dry-run and --limit flags for testing.

Usage:
  python3 enhance_clips.py              # process all clips
  python3 enhance_clips.py --limit 5    # process first 5 clips only
  python3 enhance_clips.py --dry-run    # show what would be done
"""

import argparse
import sys
from pathlib import Path

# Ensure we can import from modules/ regardless of CWD
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from modules.Config_Loader import load_config
from modules.notifier import notify
from modules.Smart_Trim import smart_trim, TRIMMED_DIR
from modules.Text_Overlay import add_text_overlay, FINAL_DIR

CONFIG = load_config()

# Source directory for vertical clips
VERTICAL_DIR = PROJECT_ROOT / CONFIG.get("vertical_clips_folder", "vertical_clips")


def main():
    parser = argparse.ArgumentParser(
        description="Enhance vertical clips: Smart_Trim → Text_Overlay"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without processing any clips",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process N clips (for testing)",
    )
    args = parser.parse_args()

    # ── Scan for vertical clips ────────────────────────────────────────────
    if not VERTICAL_DIR.exists():
        notify(
            f"Vertical clips directory not found: {VERTICAL_DIR}",
            level="error",
            reason="Run Clip_Factory first to generate vertical clips from horizontal recordings.",
        )
        sys.exit(1)

    clips = sorted(VERTICAL_DIR.glob("*.mp4"))

    if not clips:
        notify(
            f"No .mp4 clips found in {VERTICAL_DIR}",
            level="warning",
        )
        sys.exit(0)

    # Apply limit if specified
    if args.limit and args.limit > 0:
        clips = clips[: args.limit]

    # Ensure output directories exist
    TRIMMED_DIR.mkdir(parents=True, exist_ok=True)
    FINAL_DIR.mkdir(parents=True, exist_ok=True)

    total = len(clips)
    notify(
        f"Enhance pipeline: {total} clip(s) to process",
        level="startup",
        reason=f"Smart_Trim → {TRIMMED_DIR.name}/ | Text_Overlay → {FINAL_DIR.name}/"
        + (f" | DRY RUN (no files will be written)" if args.dry_run else ""),
    )

    # ── Counters for summary ───────────────────────────────────────────────
    trimmed = 0
    overlaid = 0
    skipped = 0
    failed = 0

    for i, clip in enumerate(clips, start=1):
        clip_name = clip.name
        final_path = FINAL_DIR / clip_name

        # ── Skip if already exists in final (idempotent) ──────────────────
        if final_path.exists():
            print(f"Processing {i}/{total}: {clip_name}... SKIP (already in final)")
            skipped += 1
            continue

        if args.dry_run:
            print(f"Processing {i}/{total}: {clip_name}... WOULD TRIM + OVERLAY")
            continue

        print(f"Processing {i}/{total}: {clip_name}...")

        # ── Step 1: Smart_Trim ────────────────────────────────────────────
        try:
            trimmed_path = smart_trim(str(clip))
            if trimmed_path != str(clip):
                trimmed += 1
            # If smart_trim returned the original (skip), we still pass it
            # to Text_Overlay — the clip might just be short enough already.
        except Exception as exc:
            notify(
                f"Smart_Trim failed for {clip_name}: {exc}",
                level="error",
            )
            # Use the original clip as fallback — Text_Overlay can still work
            trimmed_path = str(clip)
            failed += 1

        # ── Step 2: Text_Overlay ──────────────────────────────────────────
        try:
            result_path = add_text_overlay(trimmed_path)
            if result_path != trimmed_path:
                overlaid += 1
            elif result_path == trimmed_path:
                # Text_Overlay failed and returned input path
                failed += 1
        except Exception as exc:
            notify(
                f"Text_Overlay failed for {clip_name}: {exc}",
                level="error",
            )
            failed += 1

    # ── Summary ────────────────────────────────────────────────────────────
    print()
    print("=" * 50)
    print(f"Enhance pipeline complete!")
    print(f"  Total clips:  {total}")
    print(f"  Trimmed:      {trimmed}")
    print(f"  Overlaid:     {overlaid}")
    print(f"  Skipped:      {skipped}")
    print(f"  Failed:       {failed}")
    if args.dry_run:
        print(f"  (DRY RUN — no files were written)")
    print("=" * 50)

    notify(
        f"Pipeline summary: {trimmed} trimmed, {overlaid} overlaid, "
        f"{skipped} skipped, {failed} failed",
        level="success" if failed == 0 else "warning",
    )


if __name__ == "__main__":
    main()