#!/usr/bin/env python3
"""
modules/Clip_Deduplicator.py — Filter duplicate clips
======================================================
Uses three complementary signals to detect duplicates:
  1. Perceptual hash (pHash) of the first frame
  2. Timestamp proximity (clips within 30s of each other)
  3. File size similarity (within 10%)

If imagehash + Pillow are installed, pHash comparison is enabled.
Otherwise, only timestamp + size checks are used.
"""

import os
import json
import time
from pathlib import Path
from typing import List, Optional

try:
    from modules.notifier import notify
except ImportError:
    def notify(msg, level="info", reason=None):
        prefix = {"info": "ℹ", "success": "✓", "warning": "⚠", "error": "✗"}.get(level, "•")
        print(f"  {prefix}  {msg}")
        if reason:
            print(f"     → {reason}")

try:
    import imagehash
    from PIL import Image
    import subprocess as _sp
    HAS_PHASH = True
except ImportError:
    HAS_PHASH = False

SEEN_FILE = "seen_clips.json"
TIMESTAMP_WINDOW_S = 30.0   # clips within this many seconds are suspect
SIZE_RATIO_THRESHOLD = 0.10  # within 10% file size = suspect
PHASH_THRESHOLD = 8          # Hamming distance (lower = more similar)


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
                   + ("Install imagehash + Pillow for stronger pHash detection." if not HAS_PHASH else "")
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
                    reason=f"Matches previously seen clip at timestamp {seen.get('timestamp', '?'):.1f}s. "
                           "Skipping to avoid duplicate posts."
                )
                return True

        # Not a duplicate — record it
        self._seen.append({
            "path": str(path),
            "size": size,
            "timestamp": ts,
            "phash": str(phash) if phash else None,
            "added": time.time(),
        })
        self._save()
        return False

    def filter_clips(self, clips: list, timestamps: Optional[List[float]] = None) -> list:
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
               "They are NOT deleted from disk so you can review them manually."
    )
    return unique, dupes


# ── Helpers ────────────────────────────────────────────────────────────────────

def _compute_phash(clip_path: str) -> Optional[object]:
    """Extract first frame and compute perceptual hash."""
    if not HAS_PHASH:
        return None
    import subprocess, tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", clip_path, "-vframes", "1", "-q:v", "2", tmp_path],
            capture_output=True, timeout=15
        )
        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
            img = Image.open(tmp_path)
            return imagehash.phash(img)
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

    # pHash check (if available)
    if phash is not None and seen.get("phash"):
        try:
            seen_hash = imagehash.hex_to_hash(seen["phash"])
            if abs(phash - seen_hash) <= PHASH_THRESHOLD:
                return True
        except Exception:
            pass

    return False
