#!/usr/bin/env python3
"""
Smart Trim
==========
Re-analyzes a vertical clip's audio to find the EXACT peak moment,
then trims to an optimal viral duration (default 18s).

The peak is positioned at ~28% through the output so the build-up is
SHORT and the payoff hits fast — that's the TikTok hook pattern:
give the viewer the action before they have time to scroll.

Uses librosa for audio analysis (same pattern as Highlight_Detector)
and ffmpeg for the actual trim (re-encode with libx264 since we're
cutting already-processed vertical clips).
"""

import os
import tempfile
import subprocess
from pathlib import Path

try:
    from modules.notifier import notify
except ImportError:

    def notify(msg, level="info", reason=None):
        prefix = {"info": "ℹ", "success": "✓", "warning": "⚠", "error": "✗"}.get(
            level, "•"
        )
        print(f"  {prefix}  {msg}")
        if reason:
            print(f"     → {reason}")


try:
    from modules.Config_Loader import load_config
except ImportError:

    def load_config():
        return {}


CONFIG = load_config()
CORE_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = CORE_ROOT.parent
PROJECT_ROOT = REPO_ROOT  # clips live under repo media/, not Core/

# Default output directory for trimmed clips
TRIMMED_DIR = REPO_ROOT / "media" / "vertical_clips_trimmed"

# Analysis parameters — match Highlight_Detector's approach
WINDOW_SEC = 1.0   # smaller window than Highlight_Detector for finer peak detection
HOP_SEC = 0.25     # finer hop for more precise timestamp


def smart_trim(
    video_path: str,
    target_duration: float = 18.0,
    peak_position: float = 0.28,
    output_dir: str | None = None,
) -> str:
    """
    Re-analyze a vertical clip's audio, find the peak moment, and trim
    to target_duration with the peak positioned at peak_position through
    the output.

    Parameters
    ----------
    video_path    : path to the vertical clip (9:16 .mp4)
    target_duration : desired output length in seconds (default 18)
    peak_position : fraction of output duration where the peak should land
                    (0.28 = ~28% through, so a quick build-up then payoff)
    output_dir    : where to write the trimmed clip; defaults to
                    media/vertical_clips_trimmed/ in the repo root

    Returns
    -------
    Path to the trimmed output file, or the original path if trimming
    was skipped (clip too short, already optimal, etc.).
    """
    clip = Path(video_path)
    if not clip.exists():
        notify(f"Smart_Trim: file not found: {video_path}", level="error")
        return video_path

    # Determine output path
    out_dir = Path(output_dir) if output_dir else TRIMMED_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = str(out_dir / clip.name)

    # Get clip duration via ffprobe
    total_duration = _get_duration(str(clip))
    if total_duration <= 0:
        notify(
            f"Smart_Trim: could not get duration for {clip.name}, skipping",
            level="warning",
        )
        return video_path

    # Edge case: clip is already shorter than or equal to target — skip
    if total_duration <= target_duration:
        notify(
            f"Smart_Trim: {clip.name} is {total_duration:.1f}s (≤ {target_duration}s), skipping",
            level="info",
            reason="Clip is already short enough for TikTok. No trim needed.",
        )
        return video_path

    # Find the peak energy timestamp in the audio
    peak_ts = _find_audio_peak(str(clip))
    if peak_ts is None:
        notify(
            f"Smart_Trim: could not analyze audio for {clip.name}, skipping",
            level="warning",
        )
        return video_path

    notify(
        f"Smart_Trim: peak at {peak_ts:.1f}s in {clip.name} ({total_duration:.1f}s total)",
        level="info",
        reason=f"Trimming to {target_duration}s with peak at {peak_position*100:.0f}% through.",
    )

    # Calculate trim window so peak lands at peak_position
    # start = peak_ts - (peak_position * target_duration)
    start = peak_ts - (peak_position * target_duration)

    # Clamp start to valid range
    # Must be >= 0 and leave enough room for full target_duration
    max_start = total_duration - target_duration
    start = max(0.0, min(start, max_start))

    # If clamping pushed the peak off-target, that's fine — we prioritize
    # not cutting off the beginning or end of the clip over perfect positioning.
    actual_peak_pos = (peak_ts - start) / target_duration
    if abs(actual_peak_pos - peak_position) > 0.15:
        notify(
            f"Smart_Trim: peak shifted to {actual_peak_pos*100:.0f}% (target {peak_position*100:.0f}%) due to edge clamping",
            level="info",
            reason="Clip boundaries prevented perfect peak placement. "
            "The hook still hits early enough for TikTok retention.",
        )

    # Trim with ffmpeg — re-encode since we're cutting already-processed files
    success, error = _trim_with_ffmpeg(str(clip), out_path, start, target_duration)

    if success:
        notify(
            f"Smart_Trim: trimmed {clip.name} → {target_duration}s (start {start:.1f}s)",
            level="success",
            reason=f"Re-encoded with libx264 CRF 18 for quality. Peak at ~{actual_peak_pos*100:.0f}% through.",
        )
        return out_path
    else:
        notify(
            f"Smart_Trim: ffmpeg failed for {clip.name}: {error}",
            level="error",
        )
        return video_path


# ── Audio analysis ────────────────────────────────────────────────────────────


def _find_audio_peak(video_path: str) -> float | None:
    """
    Extract audio via ffmpeg, load with librosa, and return the
    timestamp of maximum RMS energy.

    Follows the same pattern as Highlight_Detector: extract a mono WAV
    temp file with ffmpeg, load with librosa, analyze, then clean up.
    """
    import librosa
    import numpy as np

    tmp_path = None
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = tmp.name
        tmp.close()

        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", video_path,
                "-map", "0:a:0",
                "-vn",          # audio only
                "-ac", "1",     # mono
                "-ar", "22050", # match librosa default
                "-f", "wav",
                tmp_path,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        if result.returncode != 0:
            return None

        y, sr = librosa.load(tmp_path, sr=22050, mono=True)

    except Exception as exc:
        notify(f"Smart_Trim: audio load error: {exc}", level="error")
        return None
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    # Compute RMS energy with fine-grained windows
    hop = int(HOP_SEC * sr)
    win = int(WINDOW_SEC * sr)
    rms = librosa.feature.rms(y=y, frame_length=win, hop_length=hop)[0]
    times = librosa.frames_to_time(range(len(rms)), sr=sr, hop_length=hop)

    if len(rms) == 0:
        return None

    # The peak is the single highest energy moment
    peak_idx = int(np.argmax(rms))
    return float(times[peak_idx])


# ── ffmpeg helpers ────────────────────────────────────────────────────────────


def _trim_with_ffmpeg(
    source: str, output: str, start: float, duration: float
) -> tuple:
    """
    Re-encode trim with ffmpeg. We use libx264 -crf 18 -preset medium
    because we're trimming already-processed vertical clips — stream
    copy would be faster but can cause keyframe issues on non-GOP-aligned
    cuts, and quality matters for TikTok's algorithm.

    Returns (success: bool, error_message: str | None).
    """
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start:.3f}",       # seek before input for fast + accurate trim
        "-i", source,
        "-t", f"{duration:.3f}",
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        output,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
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