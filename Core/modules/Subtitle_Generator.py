"""
Subtitle Generator
==================
Transcribes a video clip's audio using OpenAI Whisper (local model).
Returns word-level segments and a full transcript string.
Backends, in order:
  1. ``import whisper`` inside Bolt's venv (``uv sync --extra subtitles``)
  2. an openai-whisper ``whisper`` CLI already on the Mac (``WHISPER_CLI`` env,
     PATH, or the python.org / Homebrew bin dirs) — no venv install needed
Falls back to an empty transcript if neither is available.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_CLI_CANDIDATES = (
    "/Library/Frameworks/Python.framework/Versions/Current/bin/whisper",
    "/Library/Frameworks/Python.framework/Versions/3.14/bin/whisper",
    "/Library/Frameworks/Python.framework/Versions/3.13/bin/whisper",
    "/Library/Frameworks/Python.framework/Versions/3.12/bin/whisper",
    "/opt/homebrew/bin/whisper",
    "/usr/local/bin/whisper",
)


def _has_module() -> bool:
    try:
        import whisper  # noqa: F401

        return True
    except ImportError:
        return False


def whisper_cli() -> str | None:
    """Path to an openai-whisper CLI outside the venv, or None."""
    env = os.environ.get("WHISPER_CLI", "").strip()
    cands = [env] if env else []
    found = shutil.which("whisper")
    if found:
        cands.append(found)
    cands.extend(_CLI_CANDIDATES)
    venv_bin = str(Path(sys.executable).parent)
    for c in cands:
        if not c or not os.path.isfile(c) or not os.access(c, os.X_OK):
            continue
        if str(Path(c).parent) == venv_bin and not _has_module():
            continue  # stale venv shim without the package
        try:
            head = Path(c).read_text(errors="ignore")[:400]
        except OSError:
            continue
        if "whisper" in head:  # openai-whisper entry point, not whisper.cpp
            return c
    return None


def whisper_backend() -> str | None:
    """'module', 'cli:<path>', or None."""
    if _has_module():
        return "module"
    cli = whisper_cli()
    return f"cli:{cli}" if cli else None


def _transcribe_cli(cli: str, video_path: str, model_size: str) -> tuple:
    with tempfile.TemporaryDirectory(prefix="bolt_whisper_") as tmp:
        r = subprocess.run(
            [cli, str(video_path), "--model", model_size, "--output_format", "json",
             "--output_dir", tmp, "--fp16", "False", "--verbose", "False"],
            capture_output=True, text=True, timeout=1800,
        )
        out = Path(tmp) / (Path(video_path).stem + ".json")
        if r.returncode != 0 or not out.is_file():
            raise RuntimeError(f"whisper CLI failed: {(r.stderr or r.stdout)[-200:]}")
        data = json.loads(out.read_text(encoding="utf-8"))
    segments = [
        {"start": s["start"], "end": s["end"], "text": s["text"]}
        for s in data.get("segments", [])
    ]
    return segments, (data.get("text") or "").strip()


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
        cli = whisper_cli()
        if cli:
            try:
                return _transcribe_cli(cli, video_path, model_size)
            except Exception as exc:
                print(f"[SubtitleGenerator] Transcription error (CLI): {exc}")
                return [], ""
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
    """True when openai-whisper is importable or a whisper CLI is on the Mac."""
    return whisper_backend() is not None
