"""
Clip Factory
============
Converts a horizontal gameplay clip into a vertical TikTok/Shorts format.
Supports two styles:
  letterbox — adds blurred background bars top/bottom (keeps full frame)
  crop      — centre-crops to 9:16 (loses sides)
"""

import os
from moviepy import VideoFileClip, CompositeVideoClip, ColorClip

TARGET_W = 1080
TARGET_H = 1920


def format_for_tiktok(video_path: str,
                      transcript_segments: list = None,
                      output_dir: str = "vertical_clips",
                      style: str = "letterbox") -> str:
    """
    Convert clip to vertical 9:16 format. Returns output path.
    """
    os.makedirs(output_dir, exist_ok=True)
    base     = os.path.splitext(os.path.basename(video_path))[0]
    out_path = os.path.join(output_dir, f"{base}_tiktok.mp4")

    clip = None
    try:
        clip = VideoFileClip(video_path)

        if style == "crop":
            # Centre-crop to 9:16
            target_ratio = TARGET_W / TARGET_H
            src_ratio    = clip.w / clip.h
            if src_ratio > target_ratio:
                new_w = int(clip.h * target_ratio)
                x1    = (clip.w - new_w) // 2
                clip  = clip.cropped(x1=x1, x2=x1 + new_w)
            clip = clip.resized((TARGET_W, TARGET_H))
        else:
            # Letterbox — scale to fit width, blur-pad height
            scale   = TARGET_W / clip.w
            new_h   = int(clip.h * scale)
            resized = clip.resized((TARGET_W, new_h))
            y_pos   = (TARGET_H - new_h) // 2
            bg      = ColorClip((TARGET_W, TARGET_H), color=(0, 0, 0),
                                 duration=clip.duration)
            clip    = CompositeVideoClip([bg, resized.with_position(("center", y_pos))])

        clip.write_videofile(
            out_path,
            codec       = "libx264",
            audio_codec = "aac",
            logger      = None,
        )
        return out_path

    except Exception as exc:
        print(f"[ClipFactory] Failed to format {os.path.basename(video_path)}: {exc}")
        return video_path   # return original as fallback

    finally:
        # Always close the clip, even if write_videofile raised an error.
        # Without this, Python's garbage collector raises a ResourceWarning
        # ("Enable tracemalloc...") because the file handle was never released.
        if clip is not None:
            try:
                clip.close()
            except Exception:
                pass
