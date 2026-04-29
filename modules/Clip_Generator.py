#!/usr/bin/env python3
"""
modules/Clip_Generator.py — Cut highlight clips from recordings
===============================================================
Takes a source video file and a list of HighlightEvent objects,
cuts each highlight into its own clip file using MoviePy or ffmpeg,
with configurable padding before/after each highlight.
"""

import os
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional

try:
    from modules.notifier import notify
except ImportError:
    def notify(msg, level="info", reason=None):
        prefix = {"info": "ℹ", "success": "✓", "warning": "⚠", "error": "✗"}.get(level, "•")
        print(f"  {prefix}  {msg}")
        if reason:
            print(f"     → {reason}")

try:
    from modules.Highlight_Detector import HighlightEvent
except ImportError:
    from dataclasses import dataclass as _dc
    @_dc
    class HighlightEvent:
        timestamp: float
        duration: float
        score: float
        trigger: str
        source: str = "audio"


@dataclass
class GeneratedClip:
    source_file: str
    output_file: str
    start_time: float
    end_time: float
    duration: float
    highlight: "HighlightEvent"
    success: bool
    error: Optional[str] = None


def generate_clips(
    source_file: str,
    highlights: List["HighlightEvent"],
    output_dir: str = "clips",
    pad_before: float = 12.0,
    pad_after: float = 20.0,
    min_duration: float = 10.0,
    max_duration: float = 120.0,
) -> List[GeneratedClip]:
    """
    Cut one clip per highlight from source_file.

    Parameters
    ----------
    source_file  : path to the source recording
    highlights   : list of HighlightEvent objects
    output_dir   : folder to write clips into
    pad_before   : seconds of footage to include before the highlight peak
    pad_after    : seconds of footage to include after the highlight peak
    min_duration : clips shorter than this are skipped
    max_duration : clips longer than this are clamped

    Returns
    -------
    List of GeneratedClip objects (check .success)
    """
    source = Path(source_file)
    if not source.exists():
        notify(f"Source file not found: {source_file}", level="error",
               reason="Clip generation skipped — check that OBS saved the recording "
                      "to the expected path before calling generate_clips().")
        return []

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Detect total duration once
    total_duration = _get_duration(str(source))
    notify(
        f"Cutting {len(highlights)} clip(s) from {source.name}",
        level="info",
        reason=f"Source duration: {total_duration:.1f}s | "
               f"pad_before={pad_before}s, pad_after={pad_after}s | "
               f"output → {output_dir}/"
    )

    results: List[GeneratedClip] = []
    stem = source.stem

    for i, event in enumerate(highlights, start=1):
        # ── Failure recovery: wrap the whole per-clip body ─────────────────
        # Any exception inside this block (corrupt event field, weird filename,
        # filesystem hiccup, ffprobe glitch) is caught, logged, and the loop
        # moves on. One bad highlight should never kill the rest of the batch.
        try:
            start = max(0.0, event.timestamp - pad_before)
            end   = min(total_duration, event.timestamp + event.duration + pad_after)
            duration = end - start

            notify(
                f"  Clip {i}/{len(highlights)} — {event.trigger} @ {event.timestamp:.1f}s "
                f"(score {event.score:.0f})",
                level="info",
                reason=f"Window: {start:.1f}s → {end:.1f}s ({duration:.1f}s). "
                       f"pad_before pulls in the build-up; pad_after captures the reaction."
            )

            if duration < min_duration:
                notify(
                    f"  Skipping clip {i} — only {duration:.1f}s (min {min_duration}s)",
                    level="warning",
                    reason="The highlight was too short after clamping to file boundaries. "
                           "Lower min_duration in config or increase pad_before/pad_after."
                )
                results.append(GeneratedClip(
                    source_file=str(source), output_file="",
                    start_time=start, end_time=end, duration=duration,
                    highlight=event, success=False, error="too_short"
                ))
                continue

            if duration > max_duration:
                notify(
                    f"  Clamping clip {i} to {max_duration}s (was {duration:.1f}s)",
                    level="info",
                    reason="Clip exceeded max_duration. Extra footage trimmed from the end "
                           "to keep TikTok under the platform upload limit."
                )
                end = start + max_duration
                duration = max_duration

            out_name = f"{stem}_clip{i:02d}_{event.trigger}_{int(event.timestamp)}.mp4"
            out_path  = str(Path(output_dir) / out_name)

            success, error = _cut_clip_ffmpeg(str(source), out_path, start, duration)

            if success:
                notify(
                    f"  ✓ Saved: {out_name}",
                    level="success",
                    reason=f"ffmpeg cut {duration:.1f}s at {start:.1f}s without re-encoding "
                           "(stream copy) for maximum speed. Re-encoding only happens in "
                           "Clip_Factory when formatting for TikTok."
                )
            else:
                notify(f"  ✗ Failed to cut clip {i}: {error}", level="error",
                       reason="ffmpeg returned a non-zero exit code. Check that the source "
                              "file is not corrupted and that ffmpeg is installed.")

            results.append(GeneratedClip(
                source_file=str(source),
                output_file=out_path if success else "",
                start_time=start,
                end_time=end,
                duration=duration,
                highlight=event,
                success=success,
                error=error if not success else None,
            ))

        except Exception as exc:
            # Don't let one weird event nuke the whole batch — log and continue.
            notify(
                f"  ✗ Unexpected error on clip {i}: {exc}",
                level="error",
                reason="An exception was raised mid-loop. The clip was skipped and "
                       "the next highlight will be processed normally. Full traceback "
                       "is in logs/daily_log.txt if logging is wired in."
            )
            results.append(GeneratedClip(
                source_file=str(source),
                output_file="",
                start_time=getattr(event, "timestamp", 0.0),
                end_time=getattr(event, "timestamp", 0.0),
                duration=0.0,
                highlight=event,
                success=False,
                error=f"exception: {exc}",
            ))
            continue

    successful = sum(1 for r in results if r.success)
    notify(
        f"Clip generation complete: {successful}/{len(highlights)} clips saved",
        level="success" if successful == len(highlights) else "warning",
        reason=f"Clips written to {output_dir}/. "
               "Failed clips are logged above — they will NOT enter the ranking pipeline."
    )
    return results


# ── ffmpeg helpers ─────────────────────────────────────────────────────────────

def _cut_clip_ffmpeg(
    source: str, output: str, start: float, duration: float
) -> tuple:
    """
    Use ffmpeg stream-copy for speed (no re-encode).
    Returns (success: bool, error_message: str | None).
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", source,          # input FIRST — then seek (slower but audio stays in sync)
        "-ss", str(start),     # accurate seek after input avoids audio dropout
        "-t", str(duration),
        "-c:v", "copy",        # copy video stream (fast, no quality loss)
        "-c:a", "aac",         # re-encode audio — fixes sync issues with Opus/OBS recordings
        "-b:a", "192k",        # good quality audio
        "-movflags", "+faststart",
        output,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0:
            return True, None
        return False, result.stderr[-400:] if result.stderr else "unknown ffmpeg error"
    except FileNotFoundError:
        return False, "ffmpeg not found — install via: brew install ffmpeg"
    except subprocess.TimeoutExpired:
        return False, "ffmpeg timed out after 5 minutes"
    except Exception as exc:
        return False, str(exc)


def _get_duration(filepath: str) -> float:
    """Return video duration in seconds via ffprobe, or 0 on failure."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        filepath,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return float(result.stdout.strip())
    except Exception:
        return 0.0
