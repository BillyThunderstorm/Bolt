#!/usr/bin/env python3
"""
modules/Video_Intelligence.py — Tier 2 (2.1) frame-level video analysis
========================================================================
Extracts on-screen text from clip frames so Bolt can generate data-driven
titles (e.g. "15 Kill Streak", "3v5 Clutch", "Triple Kill").

Pipeline:
  1. Pick the most informative frame from the clip (skip black intros,
     prefer mid-clip action). Uses ffmpeg + the same crop-to-content
     heuristic as Clip_Deduplicator.
  2. Run Tesseract OCR on the frame.
  3. Filter OCR output to game-stat-shaped lines (numbers, kill words,
     score-like patterns). Generic text (chat, menus) is dropped so the
     caller only sees signal.
  4. Return a list of stat snippets, sorted by confidence/position.

Optional dependency: pytesseract + tesseract binary. Both are
installable via `pip install pytesseract` and `brew install tesseract`.
If either is missing the module returns [] and reports HAS_OCR=False.

Usage:
    from modules.Video_Intelligence import extract_stats, HAS_OCR

    if HAS_OCR:
        stats = extract_stats(clip_path)
        # stats = ["15 KILL STREAK", "3v5 CLUTCH", "Score 27 - 19"]
        for s in stats:
            print(f"  detected: {s}")
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

try:
    import pytesseract
    from PIL import Image
    HAS_OCR = True
    # Per Tier 2 spec: psm 6 = "Assume a single uniform block of text".
    # Works well for HUD elements like kill feeds and scoreboards.
    _OCR_CONFIG = "--psm 6"
except ImportError:
    HAS_OCR = False
    pytesseract = None  # type: ignore
    Image = None  # type: ignore
    _OCR_CONFIG = ""


# Same seek strategy as Clip_Deduplicator: skip the intro / title cards.
FRAME_SEEK_SECONDS: List[float] = [3.0, 7.0, 12.0, 20.0]
BLACK_THRESHOLD: int = 10  # avg pixel below this counts as "black frame"

# Words/phrases we want to KEEP from OCR output. Lines that don't match
# any of these patterns are dropped — chat text, menu items, and other
# noise shouldn't pollute the stat list.
_KEEP_PATTERNS = [
    re.compile(r"\bKILL\b", re.IGNORECASE),
    re.compile(r"\bSTREAK\b", re.IGNORECASE),
    re.compile(r"\bDOUBLE\b|\bTRIPLE\b|\bQUAD\b|\bACE\b", re.IGNORECASE),
    re.compile(r"\bCLUTCH\b", re.IGNORECASE),
    re.compile(r"\bVICTORY\b|\bDEFEAT\b|\bDRAW\b", re.IGNORECASE),
    re.compile(r"\bWIN\b|\bLOSS\b", re.IGNORECASE),
    re.compile(r"\bROUND\b", re.IGNORECASE),
    re.compile(r"\bMVP\b", re.IGNORECASE),
    re.compile(r"\b\d+\s*[-:vs]\s*\d+\b"),  # scores like "27-19", "3:2", "5v5"
    re.compile(r"\b\d+\s*KILL", re.IGNORECASE),
    re.compile(r"\b\d+v\d+\b"),  # "3v5", "5v5" team counts
    re.compile(r"\b\d{1,2}:\d{2}\b"),  # clock times
    re.compile(r"\bSCORE\b", re.IGNORECASE),
]


def _is_black_frame(img) -> bool:
    """Quick 'is this frame mostly black?' check (matches Clip_Deduplicator)."""
    try:
        w, h = img.size
        samples = []
        for y in range(0, h, max(1, h // 20)):
            for x in range(0, w, max(1, w // 20)):
                px = img.getpixel((x, y))
                if isinstance(px, tuple):
                    samples.append(max(px[:3]))
                else:
                    samples.append(px)
        avg = sum(samples) / len(samples) if samples else 0
        return avg < BLACK_THRESHOLD
    except Exception:
        return True


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _extract_frame(clip_path: str, seek_seconds: float) -> Optional[object]:
    """Extract a single frame at `seek_seconds` and return a PIL Image, or None."""
    if not _has_ffmpeg() or not HAS_OCR:
        return None
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-ss", str(seek_seconds),
                    "-i", clip_path,
                    "-vframes", "1",
                    "-q:v", "2",
                    tmp_path,
                ],
                capture_output=True,
                timeout=15,
            )
            if not Path(tmp_path).exists() or Path(tmp_path).stat().st_size == 0:
                return None
            img = Image.open(tmp_path)
            if _is_black_frame(img):
                return None
            return img
        finally:
            try:
                Path(tmp_path).unlink()
            except Exception:
                pass
    except Exception:
        return None


def _run_ocr(img) -> str:
    """Run Tesseract on a PIL Image and return the raw text."""
    if not HAS_OCR:
        return ""
    try:
        # Convert to grayscale to help OCR with colored HUDs.
        gray = img.convert("L")
        return pytesseract.image_to_string(gray, config=_OCR_CONFIG) or ""
    except Exception:
        return ""


def _stat_lines(text: str) -> List[str]:
    """Filter OCR text to lines that look like game stats."""
    if not text:
        return []
    hits: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or len(line) < 3:
            continue
        if any(p.search(line) for p in _KEEP_PATTERNS):
            # Normalize: collapse multiple spaces, strip punctuation noise.
            cleaned = re.sub(r"\s+", " ", line)
            cleaned = cleaned.strip(" .,;:\t")
            if cleaned and cleaned not in hits:
                hits.append(cleaned)
    return hits


def extract_stats(
    clip_path: str,
    seek_seconds: Optional[List[float]] = None,
) -> List[str]:
    """
    Pull game-stat-shaped text from a clip by OCR'ing several frames.

    Returns a deduplicated list of stat lines. Empty list means either
    no OCR is available, no usable frame could be extracted, or no
    stat-shaped text was found in the clip.

    Multiple seek positions are tried; the first frame that yields any
    stat-shaped text short-circuits the rest (saves time on long clips).
    """
    if not HAS_OCR or not _has_ffmpeg():
        return []
    if not Path(clip_path).exists():
        return []

    seeks = seek_seconds or FRAME_SEEK_SECONDS
    for seek in seeks:
        img = _extract_frame(clip_path, seek)
        if img is None:
            continue
        text = _run_ocr(img)
        hits = _stat_lines(text)
        if hits:
            return hits

    # Fallback: if no seek produced stats, return whatever the first
    # non-black frame's OCR found. Helps when the stat appears in a
    # non-default region (longer matches, etc).
    img = _extract_frame(clip_path, seeks[0])
    if img is not None:
        return _stat_lines(_run_ocr(img))
    return []


def extract_stats_multi(
    clip_path: str,
    seek_seconds: Optional[List[float]] = None,
) -> Tuple[List[str], List[Tuple[float, str]]]:
    """
    Like extract_stats, but returns (deduplicated_stats, per_frame_text)
    so callers can see what each frame said. Useful for debugging OCR
    without re-running.

    per_frame_text is a list of (seek_seconds, raw_ocr_text) tuples.
    """
    if not HAS_OCR or not _has_ffmpeg():
        return [], []
    if not Path(clip_path).exists():
        return [], []

    seeks = seek_seconds or FRAME_SEEK_SECONDS
    all_hits: List[str] = []
    per_frame: List[Tuple[float, str]] = []
    for seek in seeks:
        img = _extract_frame(clip_path, seek)
        if img is None:
            per_frame.append((seek, ""))
            continue
        text = _run_ocr(img)
        per_frame.append((seek, text))
        for h in _stat_lines(text):
            if h not in all_hits:
                all_hits.append(h)
    return all_hits, per_frame


# ── CLI ────────────────────────────────────────────────────────────────────────


def _main() -> int:
    import argparse, sys

    parser = argparse.ArgumentParser(
        description="Extract game-stat text from a clip via OCR."
    )
    parser.add_argument("clip_path")
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print raw OCR text from each seek position.",
    )
    args = parser.parse_args()

    if not HAS_OCR:
        print("OCR unavailable: install pytesseract + tesseract to enable.")
        print("  pip install pytesseract")
        print("  brew install tesseract")
        return 1
    if not _has_ffmpeg():
        print("ffmpeg not found on PATH.")
        return 1

    if args.verbose:
        hits, per_frame = extract_stats_multi(args.clip_path)
        for seek, text in per_frame:
            print(f"--- frame at {seek}s ---")
            print(text or "(black or unreadable)")
        print()
    else:
        hits = extract_stats(args.clip_path)

    print(f"Detected {len(hits)} stat line(s):")
    for h in hits:
        print(f"  {h}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_main())
