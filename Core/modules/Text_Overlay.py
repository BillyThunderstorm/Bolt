#!/usr/bin/env python3
"""
Text Overlay
============
Generates and burns on-screen text overlays into vertical clips —
the big bold captions that drive TikTok engagement.

Workflow:
  1. Transcribe the clip with Whisper (base model) for word-level timestamps
  2. Generate a short hook caption (2-6 words) from the transcript
  3. Detect category from AI_Title_Generator keywords for hook style
  4. Burn the text onto the video with ffmpeg drawtext:
     - Large bold white text with black outline (stroke)
     - Positioned upper-center so gameplay stays visible
     - Hook shows for first 3-4 seconds, then fades out
     - Optional second caption if transcript has a good later moment

Outputs to vertical_clips_final/ by default.
"""

import os
import shutil
import subprocess
from pathlib import Path

# ── ffmpeg path resolution ─────────────────────────────────────────────────────
# The default homebrew ffmpeg is built without libfreetype, so the drawtext
# filter is missing. ffmpeg-full (keg-only) has it. We prefer ffmpeg-full when
# available, falling back to whatever ffmpeg is on PATH.
_FFMPEG_FULL = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"


def _ffmpeg_binary() -> str:
    """Return the best available ffmpeg path (prefer ffmpeg-full for drawtext)."""
    if os.path.isfile(_FFMPEG_FULL) and os.access(_FFMPEG_FULL, os.X_OK):
        return _FFMPEG_FULL
    return shutil.which("ffmpeg") or "ffmpeg"


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
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Default output directory for final clips with overlays
FINAL_DIR = PROJECT_ROOT / "vertical_clips_final"

# ── Font discovery ────────────────────────────────────────────────────────────
# macOS font paths — we look for bold fonts for maximum visibility on TikTok.
# Arial Bold is the most reliable fallback; Helvetica Neue Bold is also common.
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Verdana Bold.ttf",
    "/System/Library/Fonts/Supplemental/Tahoma Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]


def _find_bold_font() -> str:
    """Return the path to the first available bold font on macOS."""
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    # Last resort — let ffmpeg pick a default
    return "Arial"


# ── Hook generation ───────────────────────────────────────────────────────────

# Excitement keywords that signal a good hook moment in gaming clips.
# These are words players yell when something hype happens — catching
# them in the transcript means we can pull the exact phrase that was
# spoken at the peak moment.
EXCITEMENT_KEYWORDS = [
    "insane", "crazy", "no way", "bro", "let's go", "clutch",
    "cracked", "unreal", "wtf", "holy", "damn", "omg",
    "absolutely", "incredible", "dirty", "nasty", "beast",
    "god", "goated", "diff", "smoked", "cooked", "done",
    "easy", "too easy", "write that down", "lights out",
]

# Generic viral hooks used as fallback when no good phrase is found.
# These are categorized by AI_Title_Generator's category system so
# the hook style matches the clip's energy.
GENERIC_HOOKS = {
    "reaction": ["NO WAY", "BRO WHAT", "WAIT FOR IT", "I CAN'T BELIEVE THIS"],
    "achievement": ["CLUTCH KING", "TOO EASY", "WRITE THAT DOWN", "GG EZ"],
    "funny": ["BRO 💀", "NAH", "YOU'RE DONE", "ACTUAL BUG"],
    "hype": ["INSANE PLAY", "BRO IS CRACKED", "UNREAL CLIP", "DIFFERENT BREED"],
    "challenge": ["WATCH THIS", "DID THAT WORK?", "NO WAY THIS WORKS", "BROKEN"],
    "informative": ["WATCH THIS", "PRO TIP", "DO THIS", "REMEMBER THIS"],
    "default": ["INSANE PLAY", "WAIT FOR IT", "NO WAY", "CLUTCH"],
}


def _detect_category(transcript: str) -> str:
    """
    Detect the clip's category from transcript keywords.
    Uses AI_Title_Generator's CATEGORY_KEYWORDS if available,
    falls back to a simplified version otherwise.
    """
    try:
        from modules.AI_Title_Generator import CATEGORY_KEYWORDS
    except ImportError:
        CATEGORY_KEYWORDS = {
            "reaction": ["insane", "crazy", "no way", "what", "omg", "bro", "wait"],
            "achievement": ["finally", "clutch", "first time", "win", "victory", "ranked"],
            "funny": ["lol", "lmao", "bug", "glitch", "wtf", "accident", "oops"],
            "hype": ["go off", "cracked", "nasty", "goated", "diff", "aim"],
            "challenge": ["try", "test", "see if", "attempt", "challenge", "strategy"],
            "informative": ["how", "tip", "trick", "tutorial", "learn", "guide"],
        }

    transcript_lower = transcript.lower()
    best_cat = "default"
    best_score = 0

    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in transcript_lower)
        if score > best_score:
            best_score = score
            best_cat = category

    return best_cat


def _generate_hook(transcript: str, segments: list, peak_ts: float | None = None) -> str:
    """
    Generate a short punchy hook caption (2-6 words) from the transcript.

    Strategy:
    1. Look for excitement keywords in segments near the peak moment
    2. Extract the surrounding 2-6 word phrase
    3. If nothing good found, use a generic viral hook based on category

    Parameters
    ----------
    transcript : full transcript text
    segments   : Whisper segments with start/end/text
    peak_ts    : timestamp of audio peak (for finding the right phrase)

    Returns
    -------
    A short uppercase hook string (2-6 words).
    """
    if not transcript.strip():
        category = "default"
        return _pick_generic_hook(category)

    # Look for excitement keywords in the transcript
    # If we have segments and a peak timestamp, prioritize phrases near the peak
    transcript_lower = transcript.lower()

    # Collect all keyword matches with their positions in the transcript
    best_phrase = None
    best_score = 0

    for kw in EXCITEMENT_KEYWORDS:
        idx = transcript_lower.find(kw)
        if idx == -1:
            continue

        # Score this match — prefer matches near the peak
        score = len(kw)  # longer keywords are more specific
        if peak_ts is not None and segments:
            # Find which segment this keyword falls in
            for seg in segments:
                seg_text = seg.get("text", "").lower()
                if kw in seg_text:
                    seg_mid = (seg["start"] + seg["end"]) / 2
                    # Closer to peak = higher score
                    distance = abs(seg_mid - peak_ts)
                    if distance < 5.0:
                        score += 10  # strongly prefer near-peak phrases
                    elif distance < 10.0:
                        score += 5
                    break

        if score > best_score:
            best_score = score
            # Extract a short phrase around the keyword (2-6 words)
            best_phrase = _extract_phrase(transcript, idx, kw)

    if best_phrase:
        return best_phrase

    # Fallback: use generic hook based on detected category
    category = _detect_category(transcript)
    return _pick_generic_hook(category)


def _extract_phrase(transcript: str, keyword_idx: int, keyword: str) -> str:
    """
    Extract a punchy 2-6 word phrase from the transcript centered
    around the found keyword. Returns it uppercase.
    """
    # Split transcript into words while tracking positions
    before = transcript[:keyword_idx]
    after = transcript[keyword_idx:]

    before_words = before.split()
    after_words = after.split()

    # Take 1-2 words before the keyword and the keyword + 1-3 words after
    # This gives us 2-6 words total
    pre = before_words[-2:] if len(before_words) >= 2 else before_words[-1:]
    post = after_words[:3]  # keyword + up to 2 more words

    phrase_words = pre + post

    # Trim to max 6 words
    if len(phrase_words) > 6:
        phrase_words = phrase_words[:6]

    # Clean up and uppercase for that shouty TikTok caption look
    phrase = " ".join(phrase_words).strip()
    # Remove trailing punctuation
    phrase = phrase.rstrip(".,!?;:")
    return phrase.upper()


def _pick_generic_hook(category: str) -> str:
    """Pick a random generic hook for the given category."""
    import random
    hooks = GENERIC_HOOKS.get(category, GENERIC_HOOKS["default"])
    return random.choice(hooks)


# ── Whisper transcription ─────────────────────────────────────────────────────


def _transcribe(video_path: str, model_size: str = "base") -> tuple:
    """
    Transcribe the clip with Whisper. Returns (segments, transcript_text).
    Uses word_timestamps=True for more precise timing on captions.
    """
    try:
        import whisper

        model = whisper.load_model(model_size)
        result = model.transcribe(video_path, word_timestamps=True)
        segments = [
            {"start": s["start"], "end": s["end"], "text": s["text"].strip()}
            for s in result.get("segments", [])
        ]
        text = result.get("text", "").strip()
        return segments, text
    except ImportError:
        notify(
            "Text_Overlay: Whisper not installed — run: pip3 install openai-whisper",
            level="warning",
        )
        return [], ""
    except Exception as exc:
        notify(f"Text_Overlay: transcription error: {exc}", level="error")
        return [], ""


# ── Audio peak detection (for hook timing) ────────────────────────────────────


def _find_peak_timestamp(video_path: str) -> float | None:
    """
    Quick audio peak detection for hook timing.
    Reuses the same librosa pattern as Highlight_Detector/Smart_Trim.
    """
    import tempfile
    import librosa
    import numpy as np

    tmp_path = None
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = tmp.name
        tmp.close()

        result = subprocess.run(
            [
                _ffmpeg_binary(), "-y",
                "-i", video_path,
                "-map", "0:a:0",
                "-vn", "-ac", "1",
                "-ar", "22050", "-f", "wav",
                tmp_path,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        if result.returncode != 0:
            return None

        y, sr = librosa.load(tmp_path, sr=22050, mono=True)
    except Exception:
        return None
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    hop = int(0.25 * sr)
    win = int(1.0 * sr)
    rms = librosa.feature.rms(y=y, frame_length=win, hop_length=hop)[0]
    times = librosa.frames_to_time(range(len(rms)), sr=sr, hop_length=hop)

    if len(rms) == 0:
        return None

    peak_idx = int(np.argmax(rms))
    return float(times[peak_idx])


# ── ffmpeg drawtext overlay ───────────────────────────────────────────────────


def _build_drawtext_filter(
    hook_text: str,
    font_path: str,
    duration: float,
    hook_display_sec: float = 3.5,
    second_caption: str | None = None,
    second_caption_start: float | None = None,
) -> str:
    """
    Build the ffmpeg drawtext filter chain for burning text onto the video.

    - Hook text: top-center, large bold white with black stroke, fades out
    - Optional second caption: appears later if there's a good moment

    Returns the complete filter string for -vf.
    """
    # Escape special characters for ffmpeg filter syntax
    # Backslash, colon, single quote, and percent need escaping
    def _escape(text: str) -> str:
        return (
            text.replace("\\", "\\\\")
                .replace(":", "\\:")
                .replace("'", "\\'")
                .replace("%", "\\%")
        )

    hook_escaped = _escape(hook_text)
    font_escaped = _escape(font_path)

    # Position: upper-center area
    # x = centered: (w-text_w)/2
    # y = upper third: h*0.08 (about 8% from top — leaves room for TikTok UI)
    x_expr = f"(w-text_w)/2"
    y_expr = f"h*0.08"

    # Fade: show for hook_display_sec seconds, then fade out over 0.5s
    fade_out_start = hook_display_sec
    fade_out_end = hook_display_sec + 0.5

    # alpha expression: fully visible until fade_out_start, then linear fade to 0
    alpha = (
        f"if(lt(t,{fade_out_start}),1,"
        f"if(lt(t,{fade_out_end}),1-(t-{fade_out_start})/{fade_out_end-fade_out_start},0))"
    )

    # Main hook drawtext filter
    drawtext_hook = (
        f"drawtext="
        f"fontfile='{font_escaped}':"
        f"text='{hook_escaped}':"
        f"fontsize=h/18:"           # scale font to video height (~106px on 1920)
        f"fontcolor=white:"
        f"borderw=4:"               # thick black outline for readability
        f"bordercolor=black:"
        f"shadowx=2:shadowy=2:"     # subtle drop shadow
        f"shadowcolor=black@0.5:"
        f"x={x_expr}:y={y_expr}:"
        f"alpha='{alpha}'"
    )

    filters = [drawtext_hook]

    # Optional second caption — appears later in the clip
    if second_caption and second_caption_start is not None:
        caption_escaped = _escape(second_caption)
        cap_fade_in = second_caption_start
        cap_fade_out = second_caption_start + 3.0
        cap_alpha = (
            f"if(lt(t,{cap_fade_in}),0,"
            f"if(lt(t,{cap_fade_in}+0.3),(t-{cap_fade_in})/0.3,"
            f"if(lt(t,{cap_fade_out}),1,"
            f"if(lt(t,{cap_fade_out}+0.3),1-(t-{cap_fade_out})/0.3,0))))"
        )
        # Second caption positioned slightly lower
        drawtext_cap = (
            f"drawtext="
            f"fontfile='{font_escaped}':"
            f"text='{caption_escaped}':"
            f"fontsize=h/22:"           # slightly smaller than hook
            f"fontcolor=white:"
            f"borderw=3:"
            f"bordercolor=black:"
            f"shadowx=1:shadowy=1:"
            f"shadowcolor=black@0.5:"
            f"x={x_expr}:y=h*0.18:"
            f"alpha='{cap_alpha}'"
        )
        filters.append(drawtext_cap)

    return ",".join(filters)


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


# ── Main entry point ──────────────────────────────────────────────────────────


def add_text_overlay(
    video_path: str,
    output_path: str | None = None,
) -> str:
    """
    Generate and burn on-screen text overlays into a vertical clip.

    Parameters
    ----------
    video_path : path to the vertical clip (9:16 .mp4)
    output_path : where to write the final clip; if None, outputs to
                  vertical_clips_final/ with the same filename

    Returns
    -------
    Path to the output file with text burned in.
    """
    clip = Path(video_path)
    if not clip.exists():
        notify(f"Text_Overlay: file not found: {video_path}", level="error")
        return video_path

    # Determine output path
    if output_path:
        out_path = output_path
    else:
        FINAL_DIR.mkdir(parents=True, exist_ok=True)
        out_path = str(FINAL_DIR / clip.name)

    # Get clip duration
    duration = _get_duration(str(clip))
    if duration <= 0:
        notify(
            f"Text_Overlay: could not get duration for {clip.name}, skipping",
            level="warning",
        )
        return video_path

    # Step 1: Transcribe with Whisper
    whisper_model = CONFIG.get("whisper_model", "base")
    notify(
        f"Text_Overlay: transcribing {clip.name} (Whisper {whisper_model})...",
        level="info",
    )
    segments, transcript = _transcribe(str(clip), whisper_model)

    # Step 2: Find audio peak for hook timing
    peak_ts = _find_peak_timestamp(str(clip))

    # Step 3: Generate hook caption
    hook_text = _generate_hook(transcript, segments, peak_ts)
    notify(
        f"Text_Overlay: hook = \"{hook_text}\"",
        level="info",
        reason=f"Transcript: \"{transcript[:80]}...\"" if len(transcript) > 80 else f"Transcript: \"{transcript}\"",
    )

    # Step 4: Look for a second caption moment
    # Find a segment after the peak that has excitement keywords
    second_caption = None
    second_caption_start = None
    if segments and peak_ts is not None:
        for seg in segments:
            seg_mid = (seg["start"] + seg["end"]) / 2
            if seg_mid > peak_ts + 3.0:  # at least 3s after peak
                seg_text_lower = seg["text"].lower()
                for kw in EXCITEMENT_KEYWORDS:
                    if kw in seg_text_lower:
                        # Use a short version of this segment's text
                        words = seg["text"].split()
                        if 2 <= len(words) <= 6:
                            second_caption = " ".join(words).upper().rstrip(".,!?;:")
                        else:
                            second_caption = _pick_generic_hook(_detect_category(transcript))
                        second_caption_start = seg["start"]
                        break
                if second_caption:
                    break

    # Step 5: Build drawtext filter and burn with ffmpeg
    font_path = _find_bold_font()
    vf = _build_drawtext_filter(
        hook_text=hook_text,
        font_path=font_path,
        duration=duration,
        second_caption=second_caption,
        second_caption_start=second_caption_start,
    )

    cmd = [
        _ffmpeg_binary(), "-y",
        "-i", str(clip),
        "-vf", vf,
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-c:a", "copy",       # audio is unchanged — just copy it
        out_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            notify(
                f"Text_Overlay: burned \"{hook_text}\" into {clip.name}",
                level="success",
                reason=f"Hook shows for 3.5s then fades. "
                f"{'Second caption at ' + str(round(second_caption_start, 1)) + 's.' if second_caption else 'No second caption.'}",
            )
            return out_path
        else:
            notify(
                f"Text_Overlay: ffmpeg failed for {clip.name}: {result.stderr[-300:]}",
                level="error",
            )
            return video_path
    except Exception as exc:
        notify(f"Text_Overlay: error processing {clip.name}: {exc}", level="error")
        return video_path