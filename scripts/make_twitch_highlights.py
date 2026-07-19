#!/usr/bin/env python3
"""
make_twitch_highlights.py — Compile best clips into a Twitch highlight VOD
==========================================================================
Selects top clips from your library, stitches them together with simple
transitions and title cards, and outputs a video ready to upload to Twitch
as a highlight VOD.

Usage:
  python3 make_twitch_highlights.py                    → compile top 10 clips
  python3 make_twitch_highlights.py --count 15         → compile top 15 clips
  python3 make_twitch_highlights.py --game "Hades 2"   → filter by game
  python3 make_twitch_highlights.py --list              → show top clips by score
  python3 make_twitch_highlights.py --output custom.mp4 → custom output path

Output: a single MP4 file (use --output to choose where; default lands
in the current working directory).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Make _paths importable in BOTH direct invocation and `from scripts import X`.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _paths import (  # noqa: E402
    REPO_ROOT, CLIPS_DIR as _CLIPS_DIR, VERTICAL_CLIPS_DIR as _VERTICAL_DIR,
    DATA_DIR, MEDIA_DIR,
)

# Backward-compatible aliases for code that uses `ROOT` / `PROJECT_ROOT`.
PROJECT_ROOT = REPO_ROOT
ROOT = REPO_ROOT


# Post-reorg: live clips/ and vertical_clips/ now live under media/.
CLIPS_DIR = _CLIPS_DIR
VERTICAL_DIR = _VERTICAL_DIR
QUEUE_FILE = DATA_DIR / "ready_to_post.json"
PERFORMANCE_FILE = DATA_DIR / "performance_outcomes.jsonl"
SEEN_CLIPS_FILE = DATA_DIR / "seen_clips.json"
# Post-reorg: there is no longer a dedicated highlight_reels/ folder. The
# default output lands at media/output/ (was highlight_reels/ at the root).
OUTPUT_DIR = MEDIA_DIR / "output"
TITLE_FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

# ── Helpers ─────────────────────────────────────────────────────────────────────

def get_clip_duration(path: str) -> float:
    """Get clip duration in seconds via ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=10
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def get_clip_score(clip_name: str) -> float:
    """Estimate clip quality score from available data."""
    score = 0.0

    # Check performance data for views
    if PERFORMANCE_FILE.exists():
        try:
            with open(PERFORMANCE_FILE) as f:
                for line in f:
                    try:
                        d = json.loads(line.strip())
                        if clip_name in (d.get("clip_path", "") or ""):
                            score += d.get("views", 0) * 2
                            score += d.get("likes", 0) * 5
                    except (json.JSONDecodeError, KeyError):
                        pass
        except OSError:
            pass

    # Check queue for posted status (posted = curated quality)
    if QUEUE_FILE.exists():
        try:
            with open(QUEUE_FILE) as f:
                queue = json.load(f)
            for item in queue.get("items", []):
                if clip_name in item.get("clip_name", ""):
                    if item.get("posted"):
                        score += 50  # Posted clips are curated
                    score += 10  # In queue = passed quality threshold
        except (OSError, json.JSONDecodeError):
            pass

    # Extract audio spike score from filename — use as tiebreaker only,
    # not primary score (it's a timestamp, not a quality metric)
    if "audio_spike_" in clip_name:
        try:
            spike_part = clip_name.split("audio_spike_")[-1]
            spike_val = int(spike_part.split("_")[0].split(".")[0])
            score += min(spike_val, 100) / 100  # Cap at 1 point — tiebreaker only
        except (ValueError, IndexError):
            pass

    return score


def list_clips() -> list[dict]:
    """List all available clips with metadata."""
    clips = []
    if not CLIPS_DIR.exists():
        return clips

    for f in sorted(CLIPS_DIR.glob("*.mp4")):
        clip_name = f.name
        score = get_clip_score(clip_name)
        duration = get_clip_duration(str(f))
        clips.append({
            "name": clip_name,
            "path": str(f),
            "score": score,
            "duration": duration,
        })

    clips.sort(key=lambda x: x["score"], reverse=True)
    return clips


def filter_by_game(clips: list[dict], game: str) -> list[dict]:
    """Filter clips by game keyword in filename."""
    game_lower = game.lower()
    return [c for c in clips if game_lower in c["name"].lower()]


def make_title_card(title: str, subtitle: str, duration: float = 3.0,
                    width: int = 1920, height: int = 1080) -> str:
    """Create a title card PNG for the video."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (width, height), (10, 10, 15))
    draw = ImageDraw.Draw(img)

    # Title
    try:
        title_font = ImageFont.truetype(TITLE_FONT, 80)
        sub_font = ImageFont.truetype(TITLE_FONT, 40)
    except Exception:
        title_font = ImageFont.load_default()
        sub_font = ImageFont.load_default()

    # Center title
    bbox = draw.textbbox((0, 0), title, font=title_font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(((width - tw) // 2, (height // 2) - th), title, font=title_font,
              fill=(255, 255, 255))

    # Subtitle
    bbox2 = draw.textbbox((0, 0), subtitle, font=sub_font)
    sw = bbox2[2] - bbox2[0]
    draw.text(((width - sw) // 2, (height // 2) + 20), subtitle, font=sub_font,
              fill=(180, 180, 180))

    out_path = str(OUTPUT_DIR / "_title_card.png")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path


def make_clip_intro(clip_name: str, index: int, total: int,
                    width: int = 1920, height: int = 1080) -> str:
    """Create a brief intro overlay for each clip."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype(TITLE_FONT, 48)
    except Exception:
        font = ImageFont.load_default()

    # Clip number badge
    text = f"Clip {index}/{total}"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    x = width - tw - 60
    y = 60

    # Background box
    draw.rounded_rectangle([x - 20, y - 10, x + tw + 20, y + th + 15],
                          radius=10, fill=(0, 0, 0, 200))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))

    out_path = str(PROJECT_DIR / "highlight_reels" / f"_intro_{index}.png")
    img.save(out_path)
    return out_path


def compile_highlight_reel(clips: list[dict], output_path: Path,
                           title: str, subtitle: str) -> bool:
    """Stitch clips together into a highlight reel video."""
    if not clips:
        print("  ✗ No clips to compile")
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Create title card
    title_card = make_title_card(title, subtitle)

    # Build the ffmpeg concat: title card → clips with transitions
    # We'll use the concat demuxer with a file list
    list_file = output_path.parent / "_concat_list.txt"

    # First, create the title card as a 3-second video with silent audio
    title_video = output_path.parent / "_title_video.mp4"
    print("  🎬  Creating title card…")
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", title_card,
        "-f", "lavfi", "-t", "3", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-t", "3", "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-r", "30",
        "-vf", "scale=1920:1080",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
        "-shortest",
        str(title_video)
    ], capture_output=True, text=True, timeout=30)

    # Scale each clip to 1920x1080 and write to temp files
    scaled_clips = []
    for i, clip in enumerate(clips, 1):
        print(f"  🎬  Scaling clip {i}/{len(clips)}: {clip['name'][:50]}…")
        scaled_path = output_path.parent / f"_scaled_{i:02d}.mp4"
        if scaled_path.exists():
            scaled_path.unlink()
        # Scale to fit 1920x1080 with padding (letterbox)
        result = subprocess.run([
            "ffmpeg", "-y", "-i", clip["path"],
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,"
                   "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-r", "30", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
            str(scaled_path)
        ], capture_output=True, text=True, timeout=120)

        if not scaled_path.exists() or scaled_path.stat().st_size < 1000:
            print(f"  ⚠️  Scaling failed for clip {i}: {result.stderr[-300:]}")
            continue
        scaled_clips.append(scaled_path)

    # Write concat list (use absolute paths)
    with open(list_file, "w") as f:
        f.write(f"file '{title_video.resolve()}'\n")
        for sc in scaled_clips:
            f.write(f"file '{sc.resolve()}'\n")

    # Concat all videos
    print(f"  🎬  Concatenating {len(scaled_clips) + 1} segments…")
    result = subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        str(output_path)
    ], capture_output=True, text=True, timeout=600)

    # Cleanup temp files
    title_video.unlink(missing_ok=True)
    list_file.unlink(missing_ok=True)
    for sc in scaled_clips:
        sc.unlink(missing_ok=True)
    Path(title_card).unlink(missing_ok=True)

    if output_path.exists():
        size_mb = output_path.stat().st_size / (1024 * 1024)
        duration = get_clip_duration(str(output_path))
        print(f"\n  ✅  Highlight reel created!")
        print(f"     📁 {output_path}")
        print(f"     ⏱️  {duration:.0f}s ({duration/60:.1f} min)")
        print(f"     💾 {size_mb:.1f} MB")
        return True
    else:
        print(f"  ✗  Failed to create highlight reel")
        if result.stderr:
            print(f"     {result.stderr[:500]}")
        return False


# ── Main ───────────────────────────────────────────────────────────────────────

# (no extra dir needed — OUTPUT_DIR already defined above)


def main():
    parser = argparse.ArgumentParser(description="Compile Twitch highlight VOD from clips")
    parser.add_argument("--count", type=int, default=10, help="Number of clips to include (default: 10)")
    parser.add_argument("--game", type=str, help="Filter clips by game keyword")
    parser.add_argument("--list", action="store_true", help="List top clips by score")
    parser.add_argument("--output", type=str, help="Custom output filename")
    args = parser.parse_args()

    print("\n  ⚡️  Bolt — Twitch Highlight Reel Compiler\n")

    clips = list_clips()

    if not clips:
        print("  ✗ No clips found in clips/ directory")
        sys.exit(1)

    # Filter by game if specified
    if args.game:
        clips = filter_by_game(clips, args.game)
        print(f"  Filtered to {len(clips)} clips matching '{args.game}'")

    if args.list:
        print(f"  Top {min(args.count, len(clips))} clips by score:\n")
        print(f"  {'#':<4} {'Score':>7} {'Duration':>8}  Name")
        print(f"  {'─' * 70}")
        for i, c in enumerate(clips[:args.count], 1):
            print(f"  {i:<4} {c['score']:>7.0f} {c['duration']:>7.0f}s  {c['name'][:45]}")
        print()
        return

    # Select top N clips
    selected = clips[:args.count]
    total_duration = sum(c["duration"] for c in selected)

    print(f"  Selected {len(selected)} clips (total {total_duration:.0f}s / {total_duration/60:.1f} min)")
    for i, c in enumerate(selected, 1):
        print(f"    {i}. {c['name'][:50]} (score: {c['score']:.0f}, {c['duration']:.0f}s)")

    # Generate title
    date_str = datetime.now().strftime("%B %Y")
    title = f"ThunderstormBilly Highlights"
    subtitle = f"{date_str} • {len(selected)} Clips"

    # Output path
    if args.output:
        output_path = OUTPUT_DIR / args.output
    else:
        filename = f"{datetime.now().strftime('%Y-%m-%d')}_highlight_reel.mp4"
        output_path = OUTPUT_DIR / filename

    print(f"\n  📁  Output: {output_path}")
    print(f"  🎬  Title: {title} — {subtitle}\n")

    success = compile_highlight_reel(selected, output_path, title, subtitle)

    if success:
        print(f"\n  📤  Upload to Twitch:")
        print(f"     1. Go to https://dashboard.twitch.tv/u/ThunderstormBilly/content/video-producer")
        print(f"     2. Click 'Upload'")
        print(f"     3. Select: {output_path}")
        print(f"     4. Title: {title} — {subtitle}")
        print(f"     5. Set visibility to Public\n")


if __name__ == "__main__":
    main()
