"""
Highlight Detector
==================
Analyses a video file's audio track for excitement spikes and returns
a list of HighlightEvent objects with timestamps and confidence scores.
"""

import os
import tempfile
import subprocess
import numpy as np
import librosa
from dataclasses import dataclass

WINDOW_SEC    = 2.0    # RMS window size
HOP_SEC       = 0.5    # step between windows
SPIKE_MULT    = float(os.getenv("SPIKE_MULTIPLIER", "2.8"))
MIN_GAP_SEC   = 15.0   # minimum seconds between highlights
SENSITIVITY   = float(os.getenv("HIGHLIGHT_SENSITIVITY", "0.7"))


@dataclass
class HighlightEvent:
    timestamp:  float
    type:       str   = "audio_spike"
    confidence: float = 0.0

    # ── Clip_Generator uses these names ──────────────────────────────────────
    # "trigger" is the same thing as "type" — just a naming inconsistency that
    # was causing a crash because Clip_Generator couldn't find the attribute.
    # "score" maps confidence (0–1) to a 0–100 scale for ranking.
    # "duration" is the size of the detected audio spike window in seconds.
    trigger:    str   = ""
    score:      float = 0.0
    duration:   float = 2.0   # seconds — the spike window Clip_Generator pads around

    def __post_init__(self):
        # Keep trigger/score in sync with type/confidence automatically.
        # This means you can always use either name and get the same value.
        if not self.trigger:
            self.trigger = self.type
        if not self.score:
            self.score = round(self.confidence * 100, 1)  # 0.0–1.0 → 0–100


def detect_highlights(video_path: str, sensitivity: float = SENSITIVITY) -> list:
    """
    Analyse audio and return list of HighlightEvent objects.
    """
    # librosa can't read .mkv/.mp4 containers directly —
    # so we use ffmpeg to extract a clean mono WAV first,
    # then load that. The temp file is deleted automatically.
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = tmp.name
        tmp.close()

        result = subprocess.run(
            [
                "ffmpeg", "-y",                     # overwrite if exists
                "-i", video_path,                   # input video
                "-vn",                              # no video — audio only
                "-ac", "1",                         # mono
                "-ar", "22050",                     # match librosa default
                "-f", "wav",                        # output format
                tmp_path,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,              # suppress opus timestamp spam
        )

        if result.returncode != 0:
            print(f"[HighlightDetector] ffmpeg failed to extract audio from: {video_path}")
            return []

        y, sr = librosa.load(tmp_path, sr=22050, mono=True)
    except Exception as exc:
        print(f"[HighlightDetector] Could not load audio: {exc}")
        return []
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass

    hop    = int(HOP_SEC * sr)
    win    = int(WINDOW_SEC * sr)
    rms    = librosa.feature.rms(y=y, frame_length=win, hop_length=hop)[0]
    times  = librosa.frames_to_time(range(len(rms)), sr=sr, hop_length=hop)

    baseline   = float(np.median(rms))
    threshold  = baseline * (SPIKE_MULT * (1.0 - sensitivity + 0.5))
    last_ts    = -MIN_GAP_SEC
    events     = []

    for i, (t, level) in enumerate(zip(times, rms)):
        if level >= threshold and (t - last_ts) >= MIN_GAP_SEC:
            confidence = min(1.0, float(level / threshold) - 1.0)
            events.append(HighlightEvent(
                timestamp  = float(t),
                type       = "audio_spike",
                confidence = round(confidence, 3),
            ))
            last_ts = t

    return events
