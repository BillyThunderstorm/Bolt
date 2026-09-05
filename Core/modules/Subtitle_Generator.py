"""
Subtitle Generator
==================
Transcribes a video clip's audio using OpenAI Whisper (local model).
Returns word-level segments and a full transcript string.
Falls back to an empty transcript if Whisper is not installed.

Optional install (heavy; not in default `uv sync`):
  uv sync --extra subtitles
  # or: pip install openai-whisper
"""

from __future__ import annotations

from pathlib import Path


def generate_subtitles_with_timestamps(
    video_path: str, model_size: str = "base"
) -> tuple:
    """
    Returns (segments, transcript_text).
    segments: list of dicts with keys: start, end, text
    transcript_text: full transcript as a single string
    """
    try:
        import whisper

        model = whisper.load_model(model_size)
        result = model.transcribe(video_path, word_timestamps=False)
        segments = [
            {"start": s["start"], "end": s["end"], "text": s["text"]}
            for s in result.get("segments", [])
        ]
        text = result.get("text", "").strip()
        return segments, text
    except ImportError:
        print(
            "[SubtitleGenerator] Whisper not installed — "
            "run: uv sync --extra subtitles  (or: pip install openai-whisper)"
        )
        return [], ""
    except Exception as exc:
        print(f"[SubtitleGenerator] Transcription error: {exc}")
        return [], ""


def _format_srt_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp HH:MM:SS,mmm."""
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(
    video_path: str,
    segments: list,
    output_path: str | None = None,
) -> str | None:
    """
    Write an SRT sidecar next to the clip (or to output_path).
    Returns the SRT path, or None if there is nothing to write.
    """
    if not segments:
        return None

    out = output_path or str(Path(video_path).with_suffix(".srt"))
    blocks: list[str] = []
    idx = 0
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        idx += 1
        start = _format_srt_timestamp(float(seg.get("start", 0) or 0))
        end = _format_srt_timestamp(float(seg.get("end", 0) or 0))
        blocks.append(f"{idx}\n{start} --> {end}\n{text}")

    if not blocks:
        return None

    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    return out


def whisper_available() -> bool:
    """True when the local openai-whisper package can be imported."""
    try:
        import whisper  # noqa: F401

        return True
    except ImportError:
        return False
