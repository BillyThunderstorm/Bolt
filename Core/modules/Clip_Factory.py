"""
Clip Factory
============
Converts a horizontal gameplay clip into a vertical TikTok/Shorts format.

Default style: "crop" — centre-crops to 9:16 when the strip is wide enough.
720p (and most 1080p 16:9) auto-switches to "blur_fill" — full gameplay, blurred 9:16 background.
Already-vertical sources are not recropped. Alternative: "letterbox".

Quality settings:
  - CRF 18 with libx264 (near-lossless, preserves source detail)
  - slow preset (best quality/size balance)
  - lanczos scale, no unsharp (sharpen-on-upscale is what made motion look VHS)
  - 720p 16:9 sources use blur-fill instead of cropping a ~405px strip
  - already-9:16 sources are not recropped
  - audio at 192kbps / 48kHz (preserves source quality)
  - +faststart for streaming-optimized MP4

When `transcript_segments` are provided (from bot.py Step D / Subtitle_Generator),
timed captions are burned in via ffmpeg drawtext (same visual family as Text_Overlay).
Missing segments or ffmpeg/drawtext failure → continue without burn-in; never kill the pipeline.

Uses ffmpeg directly for reliable, fast, high-quality encoding.
Falls back to moviepy only if ffmpeg is unavailable.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Post-reorg: this module lives in Core/modules but the canonical post-reorg
# paths live in scripts/_paths.py. Add that dir to sys.path
# so we can import it here.
_SCRIPT_DIR = Path(__file__).resolve().parent
_CORE_DIR = _SCRIPT_DIR.parent
_REPO_ROOT = _CORE_DIR.parent
_PATHS_DIR = _REPO_ROOT / "scripts"
if str(_PATHS_DIR) not in sys.path:
    sys.path.insert(0, str(_PATHS_DIR))

from _paths import VERTICAL_CLIPS_DIR

try:
    from modules.FFmpeg_Bin import ffmpeg_bin, probe_video
except ImportError:
    from FFmpeg_Bin import ffmpeg_bin, probe_video

TARGET_W = 1080
TARGET_H = 1920
DEFAULT_CRF = 18
DEFAULT_PRESET = "slow"
# Center-crop of 720p 16:9 is only ~405px wide. Upscaling that strip is the
# VHS-on-motion look. Below this width, use blur-fill instead.
MIN_CROP_STRIP_PX = 640

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Verdana Bold.ttf",
    "/System/Library/Fonts/Supplemental/Tahoma Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]


def _ffmpeg_binary() -> str:
    """Return a ffmpeg that actually launches (not a broken PATH binary)."""
    return ffmpeg_bin()


def _find_bold_font() -> str:
    """Return the path to the first available bold font on macOS."""
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return "Arial"


def _escape_drawtext(text: str) -> str:
    """Escape special characters for ffmpeg drawtext filter values."""
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )


def _normalize_caption_text(text: str, max_words: int = 12) -> str:
    """Trim / soft-truncate a segment for on-screen readability."""
    cleaned = " ".join((text or "").strip().split())
    if not cleaned:
        return ""
    words = cleaned.split()
    if len(words) > max_words:
        cleaned = " ".join(words[:max_words]) + "…"
    return cleaned


def build_caption_drawtext_filter(
    transcript_segments: list | None,
    font_path: str | None = None,
) -> str | None:
    """
    Build a drawtext filter chain from Whisper-style segments.

    Each segment is a dict with keys: start, end, text.
    Returns None when there is nothing to burn in.
    """
    if not transcript_segments:
        return None

    font = font_path or _find_bold_font()
    font_escaped = _escape_drawtext(font)
    filters: list[str] = []

    for seg in transcript_segments:
        if not isinstance(seg, dict):
            continue
        text = _normalize_caption_text(seg.get("text") or "")
        if not text:
            continue
        try:
            start = float(seg.get("start", 0) or 0)
            end = float(seg.get("end", 0) or 0)
        except (TypeError, ValueError):
            continue
        if end <= start:
            end = start + 1.5
        # Clamp negative / nonsense times
        if start < 0:
            start = 0.0
        if end < 0:
            continue

        text_escaped = _escape_drawtext(text)
        # Commas inside enable= must be escaped so they are not filter separators.
        enable = f"between(t\,{start:.3f}\,{end:.3f})"
        drawtext = (
            f"drawtext="
            f"fontfile='{font_escaped}':"
            f"text='{text_escaped}':"
            f"fontsize=h/22:"
            f"fontcolor=white:"
            f"borderw=3:"
            f"bordercolor=black:"
            f"shadowx=1:shadowy=1:"
            f"shadowcolor=black@0.5:"
            f"x=(w-text_w)/2:"
            f"y=h*0.72:"
            f"enable='{enable}'"
        )
        filters.append(drawtext)

    return ",".join(filters) if filters else None


def choose_vertical_mode(
    style: str,
    width: int | None = None,
    height: int | None = None,
) -> str:
    """Pick the 9:16 layout. Never sharpen-upscale a thin crop."""
    style = (style or "crop").strip().lower()
    if width and height and height >= width * 1.3:
        if width == TARGET_W and height == TARGET_H:
            return "passthrough"
        return "scale"
    if style == "letterbox":
        return "letterbox"
    if style == "blur_fill":
        return "blur_fill"
    if width and height:
        strip = int(height * TARGET_W / TARGET_H)
        if strip < MIN_CROP_STRIP_PX:
            return "blur_fill"
    return "crop"


def _vertical_vf(style: str) -> str:
    """Simple -vf chain (crop / letterbox / scale). No unsharp."""
    if style == "scale":
        return f"scale={TARGET_W}:{TARGET_H}:flags=lanczos"
    if style == "crop":
        return (
            f"crop=ih*{TARGET_W}/{TARGET_H}:ih,"
            f"scale={TARGET_W}:{TARGET_H}:flags=lanczos"
        )
    return (
        f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2:color=black"
    )


def _blur_fill_filter() -> str:
    """Keep the full 16:9 play, fill 9:16 with a blurred copy of the same frame."""
    return (
        f"[0:v]split=2[fg][bg];"
        f"[bg]scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={TARGET_W}:{TARGET_H},gblur=sigma=24[bg];"
        f"[fg]scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease:flags=lanczos[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2:format=auto,format=yuv420p"
    )


def _run_ffmpeg(
    video_path: str,
    out_path: str,
    vf: str | None = None,
    crf: int = DEFAULT_CRF,
    preset: str = DEFAULT_PRESET,
    timeout: int = 300,
    filter_complex: str | None = None,
    copy_video: bool = False,
) -> tuple[bool, str]:
    """Run ffmpeg. Returns (ok, stderr_tail)."""
    cmd = [_ffmpeg_binary(), "-y", "-i", video_path]
    if copy_video:
        cmd.extend(["-c:v", "copy"])
    else:
        if filter_complex:
            cmd.extend(["-filter_complex", filter_complex, "-map", "[v]", "-map", "0:a:0?"])
        elif vf:
            cmd.extend(["-vf", vf])
        cmd.extend(
            [
                "-c:v",
                "libx264",
                "-crf",
                str(crf),
                "-preset",
                preset,
                "-pix_fmt",
                "yuv420p",
            ]
        )
    cmd.extend(
        [
            "-movflags",
            "+faststart",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            out_path,
        ]
    )
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout)
        err = (result.stderr or b"").decode(errors="replace")[-400:]
        return result.returncode == 0, err
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as exc:
        return False, str(exc)


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

    If transcript_segments is provided, burn timed captions into the vertical
    frame. On missing segments or ffmpeg/drawtext failure, degrade gracefully
    and still return a vertical (or original) clip — never raise.
    """
    output_dir = output_dir or str(VERTICAL_CLIPS_DIR)
    os.makedirs(output_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(video_path))[0]
    out_path = os.path.join(output_dir, f"{base}_tiktok.mp4")

    probed = probe_video(video_path) or {}
    src_w = probed.get("width")
    src_h = probed.get("height")
    mode = choose_vertical_mode(style, src_w, src_h)
    if mode == "blur_fill" and style == "crop":
        print(
            f"[ClipFactory] {base}: {src_w}x{src_h} crop strip is too thin — "
            "using blur-fill so motion stays sharp"
        )

    ffmpeg_path = _ffmpeg_binary()
    if not shutil.which("ffmpeg") and not os.path.isfile(ffmpeg_path):
        if transcript_segments:
            print(
                f"[ClipFactory] No ffmpeg — skipping caption burn-in for {base}"
            )
        return _format_with_moviepy(video_path, out_path, style)

    caption_vf = None
    try:
        caption_vf = build_caption_drawtext_filter(transcript_segments)
    except Exception as exc:
        print(f"[ClipFactory] Caption filter build failed for {base}: {exc}")
        caption_vf = None

    def _encode(*, with_captions: bool) -> tuple[bool, str]:
        captions = caption_vf if with_captions else None
        if mode == "passthrough" and not captions:
            ok, err = _run_ffmpeg(
                video_path, out_path, crf=crf, preset=preset, copy_video=True
            )
            if ok:
                return ok, err
            return _run_ffmpeg(
                video_path,
                out_path,
                vf=_vertical_vf("scale"),
                crf=crf,
                preset=preset,
            )
        if mode == "blur_fill":
            graph = _blur_fill_filter()
            if captions:
                graph = f"{graph}[v0];[v0]{captions}[v]"
            else:
                graph = f"{graph}[v]"
            return _run_ffmpeg(
                video_path,
                out_path,
                crf=crf,
                preset=preset,
                filter_complex=graph,
            )
        vf = _vertical_vf(mode if mode in ("crop", "letterbox", "scale") else "letterbox")
        if captions:
            vf = f"{vf},{captions}"
        return _run_ffmpeg(video_path, out_path, vf=vf, crf=crf, preset=preset)

    if caption_vf:
        ok, err = _encode(with_captions=True)
        if ok:
            print(
                f"[ClipFactory] Burned {len(transcript_segments or [])} "
                f"caption segment(s) into {base}_tiktok.mp4"
            )
            return out_path
        print(
            f"[ClipFactory] Caption burn-in failed for {base} — "
            f"retrying without captions: {err}"
        )

    ok, err = _encode(with_captions=False)
    if ok:
        return out_path

    print(f"[ClipFactory] ffmpeg failed for {base}: {err}")
    return _format_with_moviepy(video_path, out_path, style)


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
