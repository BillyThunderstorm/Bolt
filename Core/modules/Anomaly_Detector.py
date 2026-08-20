#!/usr/bin/env python3
"""
modules/Anomaly_Detector.py — Tier 4.2 statistical anomaly detection
=====================================================================
Learns what a "normal" recording looks like for a given game and flags
outliers in new recordings. Anomalies are the things that produce
junk clips: stream died (sudden silence), audio glitched (extreme
spike at the start/end), recording is mostly menu/loading screens
(very low overall energy), or the file is corrupted (RMS is all zero
or all maxed).

Pipeline:
  1. extract_audio_profile(recording_path) — runs ffmpeg + librosa
     to compute a small dict of features (duration, mean_rms, std_rms,
     max_rms, num_high_spikes, silence_ratio, etc.) and returns it.
  2. load_profiles(game) — loads all previously-saved profiles for
     a given game from Data/anomaly_profiles.jsonl.
  3. fit_baseline(profiles) — computes mean/std for each numeric
     feature across the loaded set. Returns a Baseline dataclass.
  4. score(profile, baseline) — returns an AnomalyReport listing any
     features that are more than N standard deviations from the
     mean, with a severity per feature. The overall report is
     "anomalous" if any feature crosses the threshold.
  5. save_profile(...) — appends the new profile to the JSONL so the
     baseline grows with every recording.

Why this matters:
  - Streams that died mid-game still get processed into 0-confidence
    highlights that pollute the queue. Anomaly detection flags them
    before they get ranked, saving Whisper + clip-generation cycles.
  - Corrupted recordings (maxed-out audio, all-zero audio) look
    "exciting" to the spike detector. The anomaly detector catches
    them first and routes them to manual review.
  - Long menu/loading segments produce dozens of false-positive
    audio events. Anomaly detection flags the recording so the
    operator can skip it.

No external API calls. The baseline is local. The profiles grow
over time as more recordings are processed.
"""

from __future__ import annotations

import json
import math
import os
import statistics
import subprocess
import tempfile
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Repo-root-relative data location. Same convention as Memory_Index.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "Data"
PROFILES_FILE = DATA_DIR / "anomaly_profiles.jsonl"

# Default Z-score threshold: any feature more than this many standard
# deviations from the baseline mean is flagged. 2.5 is a good default —
# tight enough to catch real outliers, loose enough that natural
# game-by-game variation doesn't trip it.
DEFAULT_Z_THRESHOLD = 2.5

# Minimum number of profiles needed before scoring makes sense. With
# fewer than this, the baseline is unreliable and the report is
# always "insufficient data".
MIN_PROFILES_FOR_SCORING = 3


# ── Audio profile extraction ──────────────────────────────────────────────────


def _run_ffmpeg_audio(video_path: str, out_path: str) -> bool:
    """Extract mono 22050Hz audio from a video. Returns True on success."""
    try:
        r = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", video_path,
                "-vn",          # no video
                "-ac", "1",     # mono
                "-ar", "22050", # match librosa
                "-f", "wav",
                out_path,
            ],
            capture_output=True,
            timeout=60,
        )
        return r.returncode == 0 and Path(out_path).exists() \
               and Path(out_path).stat().st_size > 0
    except Exception:
        return False


def extract_audio_profile(
    recording_path: str,
    sample_window_sec: float = 2.0,
    sample_hop_sec: float = 0.5,
    high_spike_z: float = 2.0,
) -> Optional[Dict[str, Any]]:
    """
    Compute a small numerical profile of a recording's audio.

    Returns a dict with these features (all numbers):
      - duration_sec: total length of the audio
      - mean_rms: average audio energy
      - std_rms: variability of energy (flat streams have low std)
      - max_rms: peak energy
      - silence_ratio: fraction of windows with RMS < 0.005 (near-silent)
      - num_high_spikes: count of RMS windows more than `high_spike_z`
        standard deviations above the mean (proxy for "exciting moments")

    Returns None if the file can't be read (missing, no ffmpeg, no
    librosa). The caller should treat None as "skip anomaly scoring".
    """
    if not Path(recording_path).exists():
        return None
    if not _has_ffmpeg() or not _has_librosa():
        return None

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        if not _run_ffmpeg_audio(recording_path, tmp_path):
            return None
        import librosa  # local import: optional dep
        import numpy as np

        y, sr = librosa.load(tmp_path, sr=22050, mono=True)
    except Exception:
        return None
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass

    if len(y) == 0:
        return None

    duration_sec = float(len(y) / sr)
    hop = int(sample_hop_sec * sr)
    win = int(sample_window_sec * sr)
    if hop <= 0 or win <= 0:
        return None
    rms = librosa.feature.rms(y=y, frame_length=win, hop_length=hop)[0]

    mean_rms = float(rms.mean())
    std_rms = float(rms.std())
    max_rms = float(rms.max())
    silence_threshold = 0.005
    silence_ratio = float((rms < silence_threshold).mean())

    if std_rms > 0:
        z = (rms - mean_rms) / std_rms
        num_high_spikes = int((z > high_spike_z).sum())
    else:
        # Flat recording (constant energy) — count zero spikes.
        num_high_spikes = 0

    return {
        "duration_sec": round(duration_sec, 2),
        "mean_rms": round(mean_rms, 5),
        "std_rms": round(std_rms, 5),
        "max_rms": round(max_rms, 5),
        "silence_ratio": round(silence_ratio, 3),
        "num_high_spikes": int(num_high_spikes),
    }


def _has_ffmpeg() -> bool:
    from shutil import which
    return which("ffmpeg") is not None


def _has_librosa() -> bool:
    try:
        import librosa  # noqa: F401
        return True
    except ImportError:
        return False


# ── Profile storage ──────────────────────────────────────────────────────────


def save_profile(
    recording_path: str,
    game: str,
    profile: Dict[str, Any],
    profiles_file: Path = PROFILES_FILE,
) -> None:
    """Append a profile to the JSONL. Each line is one self-contained record."""
    profiles_file.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now().isoformat(),
        "recording_path": str(recording_path),
        "game": game,
        "profile": profile,
    }
    with open(profiles_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def load_profiles(
    game: str,
    profiles_file: Path = PROFILES_FILE,
) -> List[Dict[str, Any]]:
    """Return all profile dicts for a given game, newest first."""
    if not profiles_file.exists():
        return []
    out: List[Dict[str, Any]] = []
    with open(profiles_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("game") == game:
                out.append(rec.get("profile") or {})
    return out


# ── Baseline + scoring ───────────────────────────────────────────────────────


@dataclass
class Baseline:
    """Per-feature (mean, std) computed from a set of past profiles."""
    game: str
    sample_size: int
    features: Dict[str, Tuple[float, float]] = field(default_factory=dict)

    def get(self, feature: str) -> Optional[Tuple[float, float]]:
        return self.features.get(feature)


def fit_baseline(
    profiles: List[Dict[str, Any]],
    game: str = "unknown",
) -> Optional[Baseline]:
    """
    Compute a Baseline from a list of historical profile dicts.
    Returns None if the list is empty.

    For each numeric feature in the first profile, we compute mean
    and std over the whole list. Features that are missing in some
    profiles are skipped (we don't zero-pad — that would skew the
    baseline for features that only sometimes exist).
    """
    if not profiles:
        return None
    feature_keys: set = set()
    for p in profiles:
        feature_keys.update(p.keys())

    features: Dict[str, Tuple[float, float]] = {}
    for key in feature_keys:
        values = [p[key] for p in profiles if isinstance(p.get(key), (int, float))]
        if len(values) < 2:
            # Can't compute std with one sample.
            continue
        mean = statistics.mean(values)
        # sample stdev: divide by (n-1). statistics.stdev already does this.
        try:
            std = statistics.stdev(values)
        except statistics.StatisticsError:
            std = 0.0
        if std == 0.0:
            # Constant feature (every recording has the same value):
            # leave it out of the baseline so we don't flag on a 0/0
            # z-score.
            continue
        features[key] = (mean, std)

    return Baseline(game=game, sample_size=len(profiles), features=features)


# ── Anomaly report ────────────────────────────────────────────────────────────


@dataclass
class AnomalyReport:
    game: str
    is_anomalous: bool
    severity: str  # "none" | "low" | "medium" | "high"
    insufficient_data: bool
    flagged_features: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    profile: Dict[str, Any] = field(default_factory=dict)
    baseline_size: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def score(
    profile: Dict[str, Any],
    baseline: Optional[Baseline],
    z_threshold: float = DEFAULT_Z_THRESHOLD,
) -> AnomalyReport:
    """
    Compare a profile to a baseline and return an AnomalyReport.

    Severity bands (based on the worst feature's |z|):
      - none:     no features over the threshold
      - low:      1 feature, |z| in [z_threshold, 2 * z_threshold)
      - medium:   1 feature, |z| >= 2 * z_threshold, OR 2 features low
      - high:     2+ features with |z| >= 2 * z_threshold
    """
    if baseline is None or baseline.sample_size < MIN_PROFILES_FOR_SCORING:
        return AnomalyReport(
            game=baseline.game if baseline else "unknown",
            is_anomalous=False,
            severity="none",
            insufficient_data=True,
            summary=(
                f"Insufficient data: need {MIN_PROFILES_FOR_SCORING} "
                f"profiles, have {baseline.sample_size if baseline else 0}."
            ),
            profile=profile,
            baseline_size=baseline.sample_size if baseline else 0,
        )

    flagged: List[Dict[str, Any]] = []
    for feat, value in profile.items():
        if not isinstance(value, (int, float)):
            continue
        ms = baseline.get(feat)
        if ms is None:
            continue
        mean, std = ms
        z = (value - mean) / std if std > 0 else 0.0
        if abs(z) >= z_threshold:
            direction = "high" if z > 0 else "low"
            flagged.append({
                "feature": feat,
                "value": value,
                "baseline_mean": round(mean, 4),
                "baseline_std": round(std, 4),
                "z_score": round(z, 2),
                "direction": direction,
            })

    # Severity bands.
    high_z = [f for f in flagged if abs(f["z_score"]) >= 2 * z_threshold]
    if not flagged:
        severity = "none"
        is_anom = False
    elif len(high_z) >= 2:
        severity = "high"
        is_anom = True
    elif len(high_z) == 1 or len(flagged) >= 2:
        severity = "medium"
        is_anom = True
    else:
        severity = "low"
        is_anom = True

    summary = _summarize(flagged, severity)
    return AnomalyReport(
        game=baseline.game,
        is_anomalous=is_anom,
        severity=severity,
        insufficient_data=False,
        flagged_features=flagged,
        summary=summary,
        profile=profile,
        baseline_size=baseline.sample_size,
    )


def _summarize(flagged: List[Dict[str, Any]], severity: str) -> str:
    if not flagged:
        return "Recording looks normal for this game."
    items = ", ".join(
        f"{f['feature']}={f['value']} ({f['direction']}, z={f['z_score']})"
        for f in flagged[:3]
    )
    if len(flagged) > 3:
        items += f" (+{len(flagged) - 3} more)"
    return f"{severity.upper()} anomaly: {items}"


# ── Convenience: detect + save in one call ──────────────────────────────────


def detect_and_record(
    recording_path: str,
    game: str,
    profiles_file: Path = PROFILES_FILE,
) -> Tuple[Optional[Dict[str, Any]], Optional[AnomalyReport]]:
    """
    One-shot helper: extract profile, save it, score against the
    baseline that includes this new profile, and return both.

    The score includes the new profile in the baseline (it's the most
    recent data and probably representative of "now"). If that's
    wrong for your use case, call extract_audio_profile + save_profile
    + load_profiles + fit_baseline + score separately.
    """
    profile = extract_audio_profile(recording_path)
    if profile is None:
        return None, None
    save_profile(recording_path, game, profile, profiles_file=profiles_file)
    historical = load_profiles(game, profiles_file=profiles_file)
    baseline = fit_baseline(historical, game=game)
    return profile, score(profile, baseline)


# ── CLI ──────────────────────────────────────────────────────────────────────


def _main() -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Score a recording against the historical baseline."
    )
    parser.add_argument("recording_path")
    parser.add_argument("--game", default="unknown")
    parser.add_argument(
        "--no-save", action="store_true",
        help="Don't append this profile to the JSONL.",
    )
    parser.add_argument(
        "--z", type=float, default=DEFAULT_Z_THRESHOLD,
        help=f"Z-score threshold (default {DEFAULT_Z_THRESHOLD})",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output JSON instead of a human report",
    )
    args = parser.parse_args()

    profile = extract_audio_profile(args.recording_path)
    if profile is None:
        print(f"Could not extract profile from {args.recording_path}.")
        print("Check that the file exists, ffmpeg is on PATH, and librosa is installed.")
        return 1

    if not args.no_save:
        save_profile(args.recording_path, args.game, profile)

    historical = load_profiles(args.game)
    baseline = fit_baseline(historical, game=args.game)
    report = score(profile, baseline, z_threshold=args.z)

    if args.json:
        json.dump(
            {"profile": profile, "report": report.to_dict()},
            sys.stdout, indent=2, default=str,
        )
        sys.stdout.write("\n")
    else:
        print(f"Recording: {args.recording_path}")
        print(f"Game:      {args.game}")
        print(f"Profile:   {profile}")
        print(f"Baseline:  n={report.baseline_size}")
        if report.insufficient_data:
            print(f"  {report.summary}")
            print("  (no anomaly scoring — need more recordings first)")
        else:
            print(f"  Severity: {report.severity}")
            print(f"  Anomalous: {report.is_anomalous}")
            print(f"  Summary:   {report.summary}")
            for f in report.flagged_features:
                print(
                    f"    {f['feature']}: {f['value']} (baseline {f['baseline_mean']}±{f['baseline_std']}, z={f['z_score']}, {f['direction']})"
                )
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_main())
