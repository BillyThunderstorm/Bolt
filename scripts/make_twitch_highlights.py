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

Output: a single MP4 at media/output/YYYY-MM-DD_highlight_reel.mp4
(--output NAME lands under media/output/; an absolute path is used as-is).
Uses the working ffmpeg from FFmpeg_Bin (ffmpeg-full), not a broken PATH
ffmpeg. Problems print ``Highlights unavailable: …`` and exit 1 (no stack).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
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
SOFT = "Highlights unavailable:"


def _ffmpeg() -> Optional[str]:
    """Working ffmpeg (FFmpeg_Bin prefers ffmpeg-full), else None."""
    try:
        from modules.FFmpeg_Bin import working_ffmpeg

        return working_ffmpeg()
    except Exception:
        return shutil.which("ffmpeg")


def _ffprobe() -> str:
    try:
        from modules.FFmpeg_Bin import ffprobe_bin

        return ffprobe_bin()
    except Exception:
        return shutil.which("ffprobe") or "ffprobe"


def _concat_line(path: Path) -> str:
    """One concat-demuxer line; escapes apostrophes in the path."""
    return "file '" + str(path.resolve()).replace("'", "'\\''") + "'\n"


def has_audio(path: str) -> bool:
    try:
        result = subprocess.run(
            [_ffprobe(), "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=index", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=10,
        )
        return bool(result.stdout.strip())
    except Exception:
        return False

# ── Helpers ─────────────────────────────────────────────────────────────────────

def get_clip_duration(path: str) -> float:
    """Get clip duration in seconds via ffprobe."""
    try:
        result = subprocess.run(
            [_ffprobe(), "-v", "quiet", "-show_entries", "format=duration",
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

    # Prefer the real ranker sidecar over anything baked into the filename.
    # (audio_spike_NNNN is a timestamp, not a quality metric.)
    try:
        from modules.Clip_Ranker import read_clip_sidecar

        sidecar = read_clip_sidecar(CLIPS_DIR / clip_name)
        if sidecar.get("ranked_score") is not None:
            score += float(sidecar["ranked_score"])
        elif sidecar.get("highlight_score") is not None:
            score += float(sidecar["highlight_score"]) * 0.5
    except Exception:
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
                    width: int = 1920, height: int = 1080,
                    out_path: Optional[str] = None) -> str:
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

    out_path = out_path or str(OUTPUT_DIR / "_title_card.png")
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

    out_path = str(OUTPUT_DIR / f"_intro_{index}.png")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path


def compile_highlight_reel(clips: list[dict], output_path: Path,
                           title: str, subtitle: str) -> bool:
    """Stitch clips together into a highlight reel video (never raises)."""
    if not clips:
        print(f"  ✗  {SOFT} no clips to compile")
        return False
    ff = _ffmpeg()
    if not ff:
        print(f"  ✗  {SOFT} no working ffmpeg (brew install ffmpeg-full, "
              "or set BOLT_FFMPEG)")
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="_highlights_", dir=output_path.parent))
    try:
        return _compile(ff, clips, output_path, title, subtitle, work)
    except subprocess.TimeoutExpired as exc:
        print(f"  ✗  {SOFT} ffmpeg timed out after {exc.timeout:.0f}s")
        return False
    except Exception as exc:
        print(f"  ✗  {SOFT} {exc}")
        return False
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _compile(ff: str, clips: list[dict], output_path: Path,
             title: str, subtitle: str, work: Path) -> bool:
    # Title card → 3 s video with silent stereo audio (PIL text; plain card
    # if Pillow is missing).
    title_video = work / "title.mp4"
    print("  🎬  Creating title card…")
    try:
        card = make_title_card(title, subtitle, out_path=str(work / "title.png"))
        card_in = ["-loop", "1", "-i", card]
    except Exception:
        card_in = ["-f", "lavfi", "-i", "color=c=0x0a0a0f:s=1920x1080:r=30"]
    result = subprocess.run([
        ff, "-y", *card_in,
        "-f", "lavfi", "-t", "3", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-t", "3", "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-r", "30",
        "-vf", "scale=1920:1080",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
        "-shortest",
        str(title_video)
    ], capture_output=True, text=True, timeout=60)
    segments = [title_video] if result.returncode == 0 and title_video.exists() else []
    if not segments:
        print(f"  ⚠️  Title card failed (continuing without): {result.stderr[-300:]}")

    # Normalise every clip to 1920x1080 / 30 fps / yuv420p / AAC 48 kHz stereo
    # so the concat never sees mismatched codecs, sizes or a missing audio track.
    for i, clip in enumerate(clips, 1):
        print(f"  🎬  Scaling clip {i}/{len(clips)}: {clip['name'][:50]}…")
        scaled_path = work / f"scaled_{i:02d}.mp4"
        audio_in: list[str] = []
        audio_map = ["-map", "0:a:0"]
        if not has_audio(clip["path"]):
            audio_in = ["-f", "lavfi", "-i",
                        "anullsrc=channel_layout=stereo:sample_rate=48000"]
            audio_map = ["-map", "1:a:0", "-shortest"]
        try:
            result = subprocess.run([
                ff, "-y", "-i", clip["path"], *audio_in,
                "-map", "0:v:0", *audio_map,
                "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,"
                       "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1",
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-r", "30", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
                str(scaled_path)
            ], capture_output=True, text=True,
                timeout=max(120, int((clip.get("duration") or 0) * 6)))
        except subprocess.TimeoutExpired:
            print(f"  ⚠️  Scaling timed out for clip {i}; skipping")
            continue

        if (result.returncode != 0 or not scaled_path.exists()
                or scaled_path.stat().st_size < 1000):
            print(f"  ⚠️  Scaling failed for clip {i}: {result.stderr[-300:]}")
            continue
        segments.append(scaled_path)

    if not any(seg != title_video for seg in segments):
        print(f"  ✗  {SOFT} every clip failed to scale (see warnings above)")
        return False

    list_file = work / "concat_list.txt"
    with open(list_file, "w") as f:
        for seg in segments:
            f.write(_concat_line(seg))

    # Never report a stale reel from an earlier run as success.
    output_path.unlink(missing_ok=True)
    print(f"  🎬  Concatenating {len(segments)} segments…")
    result = subprocess.run([
        ff, "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_path)
    ], capture_output=True, text=True, timeout=1800)

    duration = get_clip_duration(str(output_path)) if output_path.exists() else 0.0
    if result.returncode == 0 and duration > 0:
        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"\n  ✅  Highlight reel created!")
        print(f"     📁 {output_path}")
        print(f"     ⏱️  {duration:.0f}s ({duration/60:.1f} min)")
        print(f"     💾 {size_mb:.1f} MB")
        return True
    print(f"  ✗  {SOFT} ffmpeg concat failed")
    if result.stderr:
        print(f"     {result.stderr.strip()[-500:]}")
    return False


# ── Main ───────────────────────────────────────────────────────────────────────

# (no extra dir needed — OUTPUT_DIR already defined above)


def main(argv=None):
    raw = list(argv) if argv is not None else sys.argv[1:]
    if raw and raw[0] == "status":
        from modules.Twitch_Stats import status as vod_status
        import json as _json
        sp = argparse.ArgumentParser(prog="bolt highlights status")
        sp.add_argument("--json", action="store_true")
        sp.add_argument("--probe", action="store_true")
        sargs = sp.parse_args(raw[1:])
        info = vod_status(probe=sargs.probe)
        info = dict(info)
        info["clips_dir"] = str(CLIPS_DIR)
        info["clips_count"] = len(list_clips())
        if info["clips_count"] == 0 and not info.get("hint"):
            info["hint"] = (
                f"Highlight reel unavailable: no clips in {CLIPS_DIR} "
                "(run bolt recordings first)."
            )
        elif info["clips_count"] == 0:
            info["hint"] = (
                f"Highlight reel unavailable: no clips in {CLIPS_DIR} "
                "(run bolt recordings first). " + (info.get("hint") or "")
            )
        if sargs.json:
            print(_json.dumps(info, indent=2))
        else:
            print("ready:", info["ready"])
            print("clips_dir:", info["clips_dir"])
            print("clips_count:", info["clips_count"])
            print("yt_dlp_found:", info["yt_dlp_found"])
            if info.get("hint"):
                print("hint:", info["hint"])
        return 0

    parser = argparse.ArgumentParser(description="Compile Twitch highlight VOD from clips")
    parser.add_argument("--count", type=int, default=10, help="Number of clips to include (default: 10)")
    parser.add_argument("--game", type=str, help="Filter clips by game keyword")
    parser.add_argument("--list", action="store_true", help="List top clips by score")
    parser.add_argument("--output", type=str, help="Custom output filename")
    args = parser.parse_args(raw)

    print("\n  ⚡️  Bolt — Twitch Highlight Reel Compiler\n")

    if args.count < 1:
        print(f"  ✗  {SOFT} --count must be 1 or more")
        return 1

    clips = list_clips()

    if not clips:
        print(
            f"  ✗  {SOFT} no clips in {CLIPS_DIR} "
            f"(run bolt recordings or bolt auto_clip_twitch first)."
        )
        return 1

    # Filter by game if specified
    if args.game:
        clips = filter_by_game(clips, args.game)
        print(f"  Filtered to {len(clips)} clips matching '{args.game}'")
        if not clips:
            print(f"  ✗  {SOFT} no clips match --game {args.game!r}")
            return 1

    if args.list:
        print(f"  Top {min(args.count, len(clips))} clips by score:\n")
        print(f"  {'#':<4} {'Score':>7} {'Duration':>8}  Name")
        print(f"  {'─' * 70}")
        for i, c in enumerate(clips[:args.count], 1):
            print(f"  {i:<4} {c['score']:>7.0f} {c['duration']:>7.0f}s  {c['name'][:45]}")
        print()
        return 0

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
        output_path = OUTPUT_DIR / args.output  # absolute --output wins
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
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
