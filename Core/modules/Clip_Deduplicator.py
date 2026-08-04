#!/usr/bin/env python3
"""
modules/Clip_Deduplicator.py — Filter duplicate clips
======================================================
Uses three complementary signals to detect duplicates:
  1. Perceptual hash (pHash) of a content frame (skips black intro frames)
  2. Timestamp proximity (clips within 30s of each other)
  3. File size similarity (within 10%)

If imagehash + Pillow are installed, pHash comparison is enabled.
Otherwise, only timestamp + size checks are used.

Key fix: Videos with black intro frames / letterbox bars produce
all-black thumbnails from frame 1.  We now:
  - Seek to 3s into the video (skips intro/title cards)
  - Crop to the non-black content area before hashing
  - Fall back to multiple seek positions if the first is black
"""

from __future__ import annotations  # so type hints like Image.Image don't evaluate at import

import os
import json
import time
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
    import imagehash
    from PIL import Image
    HAS_PHASH = True
except ImportError:
    HAS_PHASH = False

# Anchor to repo root so the writer doesn't drift back to CWD.
# 3 levels: Clip_Deduplicator.py -> modules/ -> Core/ -> <repo root>
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEEN_FILE = str(_PROJECT_ROOT / "Data" / "seen_clips.json")
TIMESTAMP_WINDOW_S = 30.0  # clips within this many seconds are suspect
SIZE_RATIO_THRESHOLD = 0.10  # within 10% file size = suspect
PHASH_THRESHOLD = 8  # Hamming distance (lower = more similar)
FRAME_SEEK_SECONDS = [3, 7, 12, 20]  # try these timestamps to find a non-black frame
BLACK_THRESHOLD = 10  # pixel value below which we consider a frame "black"


class ClipDeduplicator:
    """
    Stateful deduplicator that remembers clips across sessions (via seen_clips.json).
    """

    def __init__(self, seen_file: str = SEEN_FILE):
        self.seen_file = seen_file
        self._seen: List[dict] = self._load()
        method = "pHash + timestamp + size" if HAS_PHASH else "timestamp + size"
        notify(
            f"ClipDeduplicator initialised ({method})",
            level="info",
            reason="Duplicate detection prevents the same moment from being posted "
            "multiple times if replay buffer overlap or reprocessing occurs. "
            + (
                "Install imagehash + Pillow for stronger pHash detection."
                if not HAS_PHASH
                else ""
            ),
        )

    def is_duplicate(self, clip_path: str, timestamp: Optional[float] = None) -> bool:
        """
        Return True if this clip appears to be a duplicate of something already seen.

        Parameters
        ----------
        clip_path : path to the clip file
        timestamp : highlight timestamp in the source recording (seconds)
        """
        path = Path(clip_path)
        if not path.exists():
            return False

        size = path.stat().st_size
        ts = timestamp or time.time()
        phash = _compute_phash(str(path)) if HAS_PHASH else None

        for seen in self._seen:
            if _is_match(seen, size, ts, phash):
                notify(
                    f"Duplicate detected: {path.name}",
                    level="warning",
reason=f"Matches previously seen clip {Path(seen.get('path', '?')).name} at {seen.get('timestamp', '?')}s. "
                    "Skipping to avoid duplicate posts.",
                )
                return True

        # Not a duplicate — record it
        self._seen.append(
            {
                "path": str(path),
                "size": size,
                "timestamp": ts,
                "phash": str(phash) if phash else None,
                "added": time.time(),
            }
        )
        self._save()
        return False

    def filter_clips(
        self, clips: list, timestamps: Optional[List[float]] = None
    ) -> list:
        """
        Filter a list of clip objects, removing duplicates.
        clips must have a .output_file attribute.
        """
        timestamps = timestamps or [None] * len(clips)
        unique = []
        for clip, ts in zip(clips, timestamps):
            path = getattr(clip, "output_file", "")
            if not path:
                continue
            if self.is_duplicate(path, ts):
                continue
            unique.append(clip)
        return unique

    def _load(self) -> list:
        if Path(self.seen_file).exists():
            try:
                with open(self.seen_file) as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save(self):
        # Keep only the last 500 entries to avoid unbounded growth
        if len(self._seen) > 500:
            self._seen = self._seen[-500:]
        try:
            with open(self.seen_file, "w") as f:
                json.dump(self._seen, f, indent=2)
        except Exception:
            pass

    # ── Highlight series (Tier 2 spec: "group related clips into series") ───
    #
    # A series is a set of clips that look visually similar — the same kill
    # from slightly different angles, or the same moment captured at slightly
    # different timestamps. Grouping them lets:
    #   - the user pick the best one
    #   - the auto-publisher keep the highest-scoring one and drop the rest
    #   - analytics aggregate views across the series instead of splitting them

    def group_into_series(self, clips: list) -> List[List]:
        """
        Cluster clips that are visually similar into "highlight series".

        Parameters
        ----------
        clips : list of objects, each with .output_file (and ideally .score)
                Objects without .output_file are silently dropped.

        Returns
        -------
        list of series. Each series is a list of clip objects that look alike.
        Singletons (clips with no near-match) are still returned as their
        own series so callers can iterate uniformly.

        The algorithm is O(n^2) which is fine up to a few hundred clips per
        batch — clip generation rarely produces more than that in one run.
        """
        valid = [c for c in clips if getattr(c, "output_file", "")]
        if not valid:
            return []

        # Compute pHashes up front so we only do it once per clip.
        hashes: List[Optional[object]] = []
        for c in valid:
            hashes.append(
                _compute_phash(str(c.output_file)) if HAS_PHASH else None
            )

        parent = list(range(len(valid)))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i: int, j: int) -> None:
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[ri] = rj

        for i in range(len(valid)):
            for j in range(i + 1, len(valid)):
                if hashes[i] is None or hashes[j] is None:
                    continue
                if abs(hashes[i] - hashes[j]) <= PHASH_THRESHOLD:
                    union(i, j)

        # Collect groups by root.
        groups: Dict[int, List] = {}
        for idx in range(len(valid)):
            root = find(idx)
            groups.setdefault(root, []).append(valid[idx])

        # Stable order: sort groups by their best score (desc), then by first
        # appearance. Helps the user see "winner + alternates" in summary output.
        series = sorted(
            groups.values(),
            key=lambda grp: (-max(getattr(c, "score", 0) for c in grp), grp[0].output_file),
        )
        return series

    def keep_best_in_each_series(
        self, clips: list, min_group_size: int = 2
    ) -> Tuple[list, dict]:
        """
        Group clips into series, keep the highest-scoring one per series,
        drop the rest. Series with only one clip are passed through unchanged
        (no similarity match — nothing to dedupe against).

        Returns (kept_clips, series_info) where series_info maps each kept
        clip's output_file to a dict describing its series (size, dropped
        paths, best score).
        """
        series = self.group_into_series(clips)
        kept: list = []
        info: Dict[str, dict] = {}

        for group in series:
            if len(group) < min_group_size:
                # No near-duplicates — pass through, but tag so downstream
                # code can still see "this wasn't in a series".
                kept.extend(group)
                for c in group:
                    info[str(c.output_file)] = {
                        "series_size": 1,
                        "dropped": [],
                        "best_score": getattr(c, "score", 0),
                        "winner": True,
                    }
                continue

            winner = max(group, key=lambda c: getattr(c, "score", 0))
            dropped = [c for c in group if c is not winner]
            kept.append(winner)

            info[str(winner.output_file)] = {
                "series_size": len(group),
                "dropped": [str(c.output_file) for c in dropped],
                "best_score": getattr(winner, "score", 0),
                "winner": True,
            }
            for c in dropped:
                info[str(c.output_file)] = {
                    "series_size": len(group),
                    "dropped": [],
                    "best_score": getattr(winner, "score", 0),
                    "winner": False,
                }

        notify(
            f"Highlight series: {len(series)} group(s) from {len(clips)} clip(s)",
            level="info",
            reason=(
                f"Kept {len(kept)} (best per series); "
                f"dropped {len(clips) - len(kept)} near-duplicate(s)."
            ),
        )
        return kept, info


def filter_with_report(clips: list, timestamps: Optional[List[float]] = None) -> tuple:
    """
    Convenience function. Returns (unique_clips, duplicate_clips).
    """
    dedup = ClipDeduplicator()
    timestamps = timestamps or [None] * len(clips)
    unique, dupes = [], []
    for clip, ts in zip(clips, timestamps):
        path = getattr(clip, "output_file", "")
        if dedup.is_duplicate(path, ts):
            dupes.append(clip)
        else:
            unique.append(clip)

    notify(
        f"Deduplication: {len(unique)} unique, {len(dupes)} duplicate(s) removed",
        level="success" if not dupes else "info",
        reason="Duplicates are skipped in the ranking pipeline. "
        "They are NOT deleted from disk so you can review them manually.",
    )
    return unique, dupes


# ── Helpers ────────────────────────────────────────────────────────────────────


def _is_black_frame(img: Image.Image) -> bool:
    """Check if an image is mostly black (all pixels below threshold)."""
    w, h = img.size
    # Sample a grid of pixels
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


def _crop_to_content(img: Image.Image) -> Image.Image:
    """
    Crop away black letterbox bars (top/bottom/left/right).
    Returns the cropped image with only the visible content area.
    """
    w, h = img.size
    top, bottom, left, right = 0, h, 0, w

    # Find top boundary (scan center column)
    for y in range(0, h, 5):
        px = img.getpixel((w // 2, y))
        val = max(px[:3]) if isinstance(px, tuple) else px
        if val > BLACK_THRESHOLD:
            top = max(0, y - 5)
            break

    # Find bottom boundary
    for y in range(h - 1, 0, -5):
        px = img.getpixel((w // 2, y))
        val = max(px[:3]) if isinstance(px, tuple) else px
        if val > BLACK_THRESHOLD:
            bottom = min(h, y + 5)
            break

    # Find left boundary (scan center row)
    for x in range(0, w, 5):
        px = img.getpixel((x, h // 2))
        val = max(px[:3]) if isinstance(px, tuple) else px
        if val > BLACK_THRESHOLD:
            left = max(0, x - 5)
            break

    # Find right boundary
    for x in range(w - 1, 0, -5):
        px = img.getpixel((x, h // 2))
        val = max(px[:3]) if isinstance(px, tuple) else px
        if val > BLACK_THRESHOLD:
            right = min(w, x + 5)
            break

    # Only crop if we found meaningful boundaries
    if bottom > top and right > left:
        return img.crop((left, top, right, bottom))
    return img

def _compute_phash(clip_path: str) -> Optional[object]:
    """
    Extract a content frame from the video and compute perceptual hash.

    Fixes for real-world issues:
    - Seeks past black intro/title card frames (tries 3s, 7s, 12s, 20s)
    - Crops away letterbox black bars before hashing so pHash samples
      actual game content, not black borders
    - Returns None if no non-black frame can be found
    """
    if not HAS_PHASH:
        return None

    for seek_sec in FRAME_SEEK_SECONDS:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-ss", str(seek_sec),
                    "-i", clip_path,
                    "-vframes", "1",
                    "-q:v", "2",
                    tmp_path,
                ],
                capture_output=True,
                timeout=15,
            )
            if not (os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0):
                continue

            img = Image.open(tmp_path)
            if _is_black_frame(img):
                continue  # try next seek position

            # Crop to content area to avoid letterbox bars skewing the hash
            cropped = _crop_to_content(img)
            return imagehash.phash(cropped)

        except Exception:
            continue
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    # All seek positions yielded black frames — last resort: try frame 1
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", clip_path, "-vframes", "1", "-q:v", "2", tmp_path],
            capture_output=True,
            timeout=15,
        )
        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
            img = Image.open(tmp_path)
            if not _is_black_frame(img):
                cropped = _crop_to_content(img)
                return imagehash.phash(cropped)
    except Exception:
        pass
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    return None


def _is_match(seen: dict, size: int, timestamp: float, phash: Optional[object]) -> bool:
    """Return True if the new clip matches a seen entry."""
    # Timestamp proximity check
    seen_ts = seen.get("timestamp", -9999)
    if abs(seen_ts - timestamp) <= TIMESTAMP_WINDOW_S:
        # Also check size similarity
        seen_size = seen.get("size", 0)
        if seen_size > 0:
            ratio = abs(size - seen_size) / seen_size
            if ratio <= SIZE_RATIO_THRESHOLD:
                return True

    # pHash check (if available) — this is the strongest signal
    if phash is not None and seen.get("phash"):
        try:
            seen_hash = imagehash.hex_to_hash(seen["phash"])
            if abs(phash - seen_hash) <= PHASH_THRESHOLD:
                return True
        except Exception:
            pass

    return False