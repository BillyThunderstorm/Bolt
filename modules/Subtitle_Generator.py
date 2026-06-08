"""
Subtitle Generator
==================
Transcribes a video clip's audio using OpenAI Whisper (local model).
Returns word-level segments and a full transcript string.
Falls back to an empty transcript if Whisper is not installed.
"""

import os

def generate_subtitles_with_timestamps(video_path: str,
                                        model_size: str = "base") -> tuple:
    """
    Returns (segments, transcript_text).
    segments: list of dicts with keys: start, end, text
    transcript_text: full transcript as a single string
    """
    try:
        import whisper
        model    = whisper.load_model(model_size)
        result   = model.transcribe(video_path, word_timestamps=False)
        segments = [{"start": s["start"], "end": s["end"], "text": s["text"]}
                    for s in result.get("segments", [])]
        text     = result.get("text", "").strip()
        return segments, text
    except ImportError:
        print("[SubtitleGenerator] Whisper not installed — run: pip3 install openai-whisper")
        return [], ""
    except Exception as exc:
        print(f"[SubtitleGenerator] Transcription error: {exc}")
        return [], ""
