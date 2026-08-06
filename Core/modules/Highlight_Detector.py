"""
Highlight Detector
==================
Analyses a video file's audio track for excitement spikes and returns
a list of HighlightEvent objects with timestamps and confidence scores.

Designed to stay strict on long VODs: local-max peaks only, robust baseline,
prominence gate, min gap, confidence floor, and a hard candidate cap.
"""

from __future__ import annotations

import os
import tempfile
import subprocess
from dataclasses import dataclass
from typing import List, Optional

from modules.Config_Loader import load_config

config = load_config()
_CFG = config.get("highlight", config) if isinstance(config.get("highlight"), dict) else config

WINDOW_SEC = 2.0
HOP_SEC = 0.5

# Module-level fallbacks (live values are re-read from config.json each call).
SPIKE_MULT = float(_CFG.get("energy_multiplier", os.getenv("SPIKE_MULTIPLIER", "3.2")))
MIN_GAP_SEC = float(_CFG.get("min_gap_seconds", 45.0))
SENSITIVITY = float(
    _CFG.get(
        "highlight_sensitivity",
        _CFG.get("sensitivity", os.getenv("HIGHLIGHT_SENSITIVITY", "0.45")),
    )
)

# ── Hard confidence floor ─────────────────────────────────────────────────────
# An audio spike that BARELY crosses the energy threshold has near-zero
# confidence (think: someone coughing during a quiet moment). Without this
# floor, those events still get cut into clips, transcribed by Whisper, and
# ranked — wasting cycles on clips that are 99% guaranteed to be junk.
# Tune in config.json → highlight.min_confidence
# (default 0.35 ≈ needs to be ~35%+ above the spike threshold).
MIN_CONFIDENCE = float(_CFG.get("min_confidence", 0.35))

# Peak must also beat local neighbors by this relative margin (prominence).
# 0.20 = peak RMS is at least 20% louder than the local median around it.
MIN_PROMINENCE = float(_CFG.get("min_prominence", 0.20))

# Never return more than this many events from the detector itself
# (bot.py also caps before cutting; this is the early hard stop).
MAX_CANDIDATES = int(
    _CFG.get(
        "max_candidates",
        config.get("max_highlight_candidates", 15) if isinstance(config, dict) else 15,
    )
)


@dataclass
class HighlightEvent:
    timestamp: float
    type: str = "audio_spike"
    confidence: float = 0.0

    # ── Clip_Generator uses these names ──────────────────────────────────────
    # "trigger" is the same thing as "type" — just a naming inconsistency that
    # was causing a crash because Clip_Generator couldn't find the attribute.
    # "score" maps confidence (0–1) to a 0–100 scale for ranking.
    # "duration" is the size of the detected audio spike window in seconds.
    trigger: str = ""
    score: float = 0.0
    duration: float = 2.0  # seconds — the spike window Clip_Generator pads around

    def __post_init__(self):
        # Keep trigger/score in sync with type/confidence automatically.
        # This means you can always use either name and get the same value.
        if not self.trigger:
            self.trigger = self.type
        if not self.score:
            self.score = round(self.confidence * 100, 1)  # 0.0–1.0 → 0–100


def _load_highlight_settings() -> dict:
    """Re-read highlight + top-level caps so config edits apply mid-process."""
    try:
        full = load_config()
    except Exception:
        full = {}
    live = full.get("highlight") if isinstance(full.get("highlight"), dict) else {}
    return {
        "spike_mult": float(live.get("energy_multiplier", SPIKE_MULT)),
        "min_gap": float(live.get("min_gap_seconds", MIN_GAP_SEC)),
        "min_confidence": float(live.get("min_confidence", MIN_CONFIDENCE)),
        "min_prominence": float(live.get("min_prominence", MIN_PROMINENCE)),
        "max_candidates": int(
            live.get(
                "max_candidates",
                full.get("max_highlight_candidates", MAX_CANDIDATES),
            )
        ),
        "baseline_percentile": float(live.get("baseline_percentile", 60.0)),
        "peak_neighborhood_sec": float(live.get("peak_neighborhood_sec", 3.0)),
        "local_window_sec": float(live.get("local_window_sec", 20.0)),
    }


def detect_highlights(video_path: str, sensitivity: float = SENSITIVITY) -> List[HighlightEvent]:
    """
    Analyse audio and return list of HighlightEvent objects.

    Pipeline:
      1. Extract mono WAV via ffmpeg
      2. Frame-level RMS energy
      3. Robust global threshold (percentile baseline × multiplier × sensitivity)
      4. Keep only local maxima that clear threshold + prominence
      5. Confidence floor
      6. Enforce min-gap, keeping the strongest peak in each conflict
      7. Cap to max_candidates by score
    """
    import librosa
    import numpy as np

    settings = _load_highlight_settings()
    spike_mult = settings["spike_mult"]
    min_gap = settings["min_gap"]
    min_confidence = settings["min_confidence"]
    min_prominence = settings["min_prominence"]
    max_candidates = max(1, settings["max_candidates"])
    baseline_percentile = settings["baseline_percentile"]
    peak_neighborhood_sec = settings["peak_neighborhood_sec"]
    local_window_sec = settings["local_window_sec"]

    # librosa can't read .mkv/.mp4 containers directly —
    # so we use ffmpeg to extract a clean mono WAV first,
    # then load that. The temp file is deleted automatically.
    tmp_path: Optional[str] = None
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = tmp.name
        tmp.close()

        result = subprocess.run(
            [
                "ffmpeg",
                "-y",  # overwrite if exists
                "-i",
                video_path,  # input video
                "-map",
                "0:a:0",
                "-vn",  # no video — audio only
                "-ac",
                "1",  # mono
                "-ar",
                "22050",  # match librosa default
                "-f",
                "wav",  # output format
                tmp_path,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,  # suppress opus timestamp spam
        )

        if result.returncode != 0:
            print(
                f"[HighlightDetector] ffmpeg failed to extract audio from: {video_path}"
            )
            return []

        y, sr = librosa.load(tmp_path, sr=22050, mono=True)
    except Exception as exc:
        print(f"[HighlightDetector] Could not load audio: {exc}")
        return []
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    hop = int(HOP_SEC * sr)
    win = int(WINDOW_SEC * sr)
    rms = librosa.feature.rms(y=y, frame_length=win, hop_length=hop)[0]
    times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)

    if len(rms) == 0:
        return []

    # Robust baseline: percentile of RMS (not median-of-quiet which can be too
    # low on loud streams, flooding us with "spikes").
    baseline = float(np.percentile(rms, baseline_percentile))
    # Higher sensitivity → lower threshold → more spikes. Clamp sens into 0..1.
    sens = max(0.0, min(1.0, float(sensitivity)))
    # sens=0.45 → (1 - 0.45 + 0.5) = 1.05; sens=0.7 → 0.8 (looser)
    threshold = baseline * (spike_mult * (1.0 - sens + 0.5))
    if baseline <= 0 or threshold <= 0:
        print("[HighlightDetector] Audio baseline is zero — no spikes detected.")
        return []

    # Frames needed for local-max neighborhood and prominence window.
    neigh_frames = max(1, int(peak_neighborhood_sec / HOP_SEC))
    local_frames = max(neigh_frames + 1, int(local_window_sec / HOP_SEC))

    candidates: List[tuple] = []  # (timestamp, level, confidence, score)
    rejected_weak = 0
    rejected_not_peak = 0
    rejected_prominence = 0

    for i, (t, level) in enumerate(zip(times, rms)):
        level_f = float(level)
        if level_f < threshold:
            continue

        # Local maximum only — drop frames on the slope of a longer shout.
        left = max(0, i - neigh_frames)
        right = min(len(rms), i + neigh_frames + 1)
        neighborhood = rms[left:right]
        if level_f < float(np.max(neighborhood)) - 1e-12:
            rejected_not_peak += 1
            continue
        # If several frames share the max, keep the first (leftmost) of the plateau.
        if i > 0 and float(rms[i - 1]) >= level_f - 1e-12 and float(rms[i - 1]) >= threshold:
            # previous frame is equal peak on the same plateau → skip
            if float(rms[i - 1]) >= level_f - 1e-12 and i - 1 >= left:
                # only skip if previous is within neighborhood and also a peak candidate
                pass
            if float(rms[i - 1]) == level_f or (
                abs(float(rms[i - 1]) - level_f) < 1e-9 and float(rms[i - 1]) >= threshold
            ):
                # keep only the center-ish: if previous is equally loud, skip this
                if float(rms[i - 1]) >= level_f:
                    rejected_not_peak += 1
                    continue

        # Prominence vs local median (ignores the peak itself).
        loc_left = max(0, i - local_frames)
        loc_right = min(len(rms), i + local_frames + 1)
        local = np.concatenate([rms[loc_left:i], rms[i + 1 : loc_right]])
        if len(local) == 0:
            local_med = baseline
        else:
            local_med = float(np.median(local))
        if local_med <= 0:
            prominence = 1.0 if level_f > 0 else 0.0
        else:
            prominence = (level_f / local_med) - 1.0
        if prominence < min_prominence:
            rejected_prominence += 1
            continue

        # Confidence: how far above the global threshold (0 at threshold, 1 at 2×).
        confidence = min(1.0, float(level_f / threshold) - 1.0)
        # Blend a little prominence so clear peaks rank higher.
        confidence = min(1.0, 0.7 * confidence + 0.3 * min(1.0, prominence))
        if confidence < min_confidence:
            rejected_weak += 1
            continue

        score = round(confidence * 100, 1)
        candidates.append((float(t), level_f, round(confidence, 3), score))

    # Enforce min-gap greedily by strength (not by time-order first-come).
    # That way a weak early cough doesn't block a real play 10s later.
    candidates.sort(key=lambda c: c[3], reverse=True)  # score desc
    selected: List[tuple] = []
    for cand in candidates:
        t = cand[0]
        if any(abs(t - kept[0]) < min_gap for kept in selected):
            continue
        selected.append(cand)
        if len(selected) >= max_candidates:
            break

    # Chronological order for the rest of the pipeline.
    selected.sort(key=lambda c: c[0])

    events = [
        HighlightEvent(
            timestamp=t,
            type="audio_spike",
            confidence=conf,
            score=score,
        )
        for t, _level, conf, score in selected
    ]

    print(
        f"[HighlightDetector] {len(events)} highlights kept "
        f"(cap={max_candidates}, gap≥{min_gap:.0f}s, conf≥{min_confidence}, "
        f"prom≥{min_prominence}). "
        f"Dropped: weak={rejected_weak}, not_peak={rejected_not_peak}, "
        f"prominence={rejected_prominence}. "
        f"threshold={threshold:.5f} baseline_p{baseline_percentile:.0f}={baseline:.5f}"
    )

    return events
