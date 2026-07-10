"""
Clip Factory
============
Converts a horizontal gameplay clip into a vertical TikTok/Shorts format.

Default style: "crop" — centre-crops to 9:16, fills the entire frame.
Alternative: "letterbox" — scales to fit width, pads with black bars top/bottom.

Quality settings:
  - CRF 18 with libx264 (near-lossless, preserves source detail)
  - slow preset (best quality/size balance)
  - lanczos scaling + unsharp filter (sharp upscale from 720p → 1080p)
  - audio at 192kbps / 48kHz (preserves source quality)
  - +faststart for streaming-optimized MP4

Uses ffmpeg directly for reliable, fast, high-quality encoding.
Falls back to moviepy only if ffmpeg is unavailable.
"""

import os
import subprocess
import shutil
import sys
from pathlib import Path

# Post-reorg: this module lives in Core/modules but the canonical post-reorg
# paths live in 3rd_Party/colabs/scripts/_paths.py. Add that dir to sys.path
# so we can import it here.
_SCRIPT_DIR = Path(__file__).resolve().parent
_CORE_DIR = _SCRIPT_DIR.parent
_REPO_ROOT = _CORE_DIR.parent
_PATHS_DIR = _REPO_ROOT / "3rd_Party" / "colabs" / "scripts"
if str(_PATHS_DIR) not in sys.path:
    sys.path.insert(0, str(_PATHS_DIR))

from _paths import VERTICAL_CLIPS_DIR

TARGET_W = 1080
TARGET_H = 1920
DEFAULT_CRF = 18
DEFAULT_PRESET = "slow"


def format_for_tiktok(
    video_path: str,
    transcript_segments: list = None,
    output_dir: str | None = None,
    style: str = "crop",
    crf: int = DEFAULT_CRF,
    preset: str = DEFAULT_PRESET,
) -> str:
    """
    Convert clip to vertical 9:16 format. Returns output path.
    """
    output_dir = output_dir or str(VERTICAL_CLIPS_DIR)
    os.makedirs(output_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(video_path))[0]
    out_path = os.path.join(output_dir, f"{base}_tiktok.mp4")

    # Check if ffmpeg is available
    if not shutil.which("ffmpeg"):
        return _format_with_moviepy(video_path, out_path, style)

    # Build the video filter chain
    if style == "crop":
        # Centre-crop to 9:16 then upscale to 1080x1920
        # crop=width:height from centre, then scale with lanczos for sharp results
        vf = f"crop=ih*{TARGET_W}/{TARGET_H}:ih,scale={TARGET_W}:{TARGET_H}:flags=lanczos,unsharp=5:5:0.8:3:3:0.4"
    else:
        # Letterbox — scale to fit width, pad top/bottom with black
        vf = (
            f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease:flags=lanczos,"
            f"pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2:color=black"
        )

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", vf,
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", preset,
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        out_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode != 0:
            print(f"[ClipFactory] ffmpeg failed for {base}: {result.stderr.decode()[-200:]}")
            return _format_with_moviepy(video_path, out_path, style)
        return out_path
    except subprocess.TimeoutExpired:
        print(f"[ClipFactory] ffmpeg timed out for {base}")
        return video_path
    except Exception as exc:
        print(f"[ClipFactory] Error processing {base}: {exc}")
        return video_path


def _format_with_moviepy(video_path: str, out_path: str, style: str = "crop") -> str:
    """Fallback: use moviepy if ffmpeg is not available."""
    from moviepy import VideoFileClip, CompositeVideoClip, ColorClip

    clip = None
    try:
        clip = VideoFileClip(video_path)

        if style == "crop":
            target_ratio = TARGET_W / TARGET_H
            src_ratio = clip.w / clip.h
            if src_ratio > target_ratio:
                new_w = int(clip.h * target_ratio)
                x1 = (clip.w - new_w) // 2
                clip = clip.cropped(x1=x1, x2=x1 + new_w)
            clip = clip.resized((TARGET_W, TARGET_H))
        else:
            scale = TARGET_W / clip.w
            new_h = int(clip.h * scale)
            resized = clip.resized((TARGET_W, new_h))
            y_pos = (TARGET_H - new_h) // 2
            bg = ColorClip(
                (TARGET_W, TARGET_H), color=(0, 0, 0), duration=clip.duration
            )
            clip = CompositeVideoClip([bg, resized.with_position(("center", y_pos))])

        clip.write_videofile(
            out_path,
            codec="libx264",
            audio_codec="aac",
            audio_bitrate="192k",
            audio_fps=48000,
            ffmpeg_params=["-crf", str(DEFAULT_CRF), "-preset", "medium",
                           "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
            logger=None,
        )
        return out_path
    except Exception as exc:
        print(f"[ClipFactory] moviepy fallback failed: {exc}")
        return video_path
    finally:
        if clip is not None:
            try:
                clip.close()
            except Exception:
                pass