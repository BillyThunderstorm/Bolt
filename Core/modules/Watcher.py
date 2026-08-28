"""
Folder Watcher
==============
Continuously monitors the recordings folder for new video files and yields
their absolute paths as they become available.

Improvements over original
--------------------------
• Watches both .mp4 AND .mkv (OBS saves replays as .mkv)
• Waits until the file is stable (no longer being written to) before yielding
• Configurable via env vars: RECORDINGS_FOLDER, WATCH_INTERVAL
• Persists processed filenames to disk — survives restarts without reprocessing
• Marks a file processed AFTER the caller finishes it (not before yield),
  so a crash mid-pipeline can retry. process_recording also marks on exit.

WHY persistence matters:
  The original used an in-memory set that reset every launch. This meant
  every restart reprocessed every file in recordings/ from scratch, causing
  hundreds of duplicate clips. Now processed filenames are saved to
  Data/processed_recordings.json and loaded on startup — Bolt remembers
  exactly which files it has already handled.
"""

import os
import sys
import json
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:

    def load_dotenv(*args, **kwargs):
        return False


# Post-reorg: Watcher lives in Core/modules but the canonical post-reorg
# paths live in scripts/_paths.py. Add that dir to sys.path
# so we can import it here.
_SCRIPT_DIR = Path(__file__).resolve().parent
_CORE_DIR = _SCRIPT_DIR.parent
_REPO_ROOT = _CORE_DIR.parent
_PATHS_DIR = _REPO_ROOT / "scripts"
if str(_PATHS_DIR) not in sys.path:
    sys.path.insert(0, str(_PATHS_DIR))

from _paths import RECORDINGS_DIR  # noqa: E402

load_dotenv()

RECORDINGS_FOLDER = os.getenv("RECORDINGS_FOLDER", str(RECORDINGS_DIR))
WATCH_INTERVAL = float(os.getenv("WATCH_INTERVAL", "5"))
WATCH_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi"}
_STEM_PREFER = {".mp4": 0, ".mkv": 1, ".mov": 2, ".avi": 3}
STABLE_WAIT_SEC = 3.0  # seconds to wait before declaring the file stable

# Where we persist the list of already-processed filenames across restarts.
# Without this file, every launch re-runs the full pipeline on every recording.
PROCESSED_LOG = Path(__file__).resolve().parents[2] / "Data" / "processed_recordings.json"


def load_processed() -> set:
    """Load already-processed filenames. Empty set on first run or read error."""
    try:
        with open(PROCESSED_LOG) as f:
            raw = json.load(f)
        if isinstance(raw, list):
            return set(str(x) for x in raw)
        if isinstance(raw, dict):
            return set(str(x) for x in raw.get("processed", raw.get("files", [])))
    except Exception:
        pass
    return set()


def _load_processed() -> set:
    """Back-compat alias used by older callers/tests."""
    return load_processed()


def _save_processed(processed: set):
    """
    Persist the processed set to disk after each new file is handled.
    This is what prevents duplicate processing across restarts.
    """
    PROCESSED_LOG.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(PROCESSED_LOG, "w") as f:
            json.dump(sorted(processed), f, indent=2)
    except Exception as e:
        print(f"[Watcher] Could not save processed log: {e}")


def is_processed(filename: str, processed: set | None = None) -> bool:
    """True if this file (or a same-stem sibling like .mov/.mp4) is already done."""
    names = processed if processed is not None else load_processed()
    name = Path(filename).name
    if name in names:
        return True
    stem = Path(name).stem
    return any(Path(p).stem == stem for p in names)


def mark_processed(filename: str) -> None:
    """Record a filename as handled. Idempotent. Also records the basename only."""
    name = Path(filename).name
    processed = load_processed()
    if name in processed:
        return
    processed.add(name)
    _save_processed(processed)


def list_pending_recordings(folder: str | Path | None = None) -> list[Path]:
    """Video files in *folder* that are not yet processed, newest mtime first.

    Same-stem duplicates (.mp4 / .mov / .mkv) collapse to one preferred file
    so a replay exported twice is not treated as two new recordings.
    """
    target = Path(folder) if folder else Path(RECORDINGS_FOLDER)
    if not target.is_dir():
        return []
    files: list[Path] = []
    for ext in WATCH_EXTENSIONS:
        files.extend(target.glob(f"*{ext}"))
    best: dict[str, Path] = {}
    for path in files:
        prev = best.get(path.stem)
        if prev is None or _STEM_PREFER.get(path.suffix.lower(), 9) < _STEM_PREFER.get(
            prev.suffix.lower(), 9
        ):
            best[path.stem] = path
    processed = load_processed()
    pending = [p for p in best.values() if not is_processed(p.name, processed)]
    return sorted(pending, key=lambda p: p.stat().st_mtime, reverse=True)


def watch_folder(folder: str = RECORDINGS_FOLDER):
    """
    Generator that yields the absolute path of every new video file
    that appears in folder, in order of detection.

    Processed filenames are persisted to Data/processed_recordings.json
    AFTER the caller finishes the yielded file, so a crash mid-pipeline
    can retry. process_recording also marks on exit.

    Usage
    -----
        for recording in watch_folder():
            process(recording)
    """
    os.makedirs(folder, exist_ok=True)

    processed: set = load_processed()

    print(f"[Watcher] Monitoring '{folder}' for new recordings...  (Ctrl+C to stop)")
    print(f"[Watcher] {len(processed)} previously processed file(s) will be skipped.")

    while True:
        try:
            files = os.listdir(folder)
        except FileNotFoundError:
            print(f"[Watcher] Folder not found: {folder}")
            time.sleep(WATCH_INTERVAL)
            continue

        for filename in sorted(files):
            _, ext = os.path.splitext(filename)
            if ext.lower() not in WATCH_EXTENSIONS:
                continue
            if is_processed(filename, processed):
                continue

            full_path = os.path.join(folder, filename)
            if not _is_stable(full_path):
                continue  # still being written — check again next cycle

            print(f"[Watcher] New recording detected: {filename}")
            yield full_path
            # Mark after the caller finishes (or crashes out of this iteration).
            processed.add(filename)
            _save_processed(processed)

        time.sleep(WATCH_INTERVAL)


def _is_stable(path: str) -> bool:
    """
    Return True if the file has stopped growing.
    Waits STABLE_WAIT_SEC and compares file sizes before and after.
    """
    try:
        size_before = os.path.getsize(path)
        if size_before == 0:
            return False
        time.sleep(STABLE_WAIT_SEC)
        size_after = os.path.getsize(path)
        return size_before == size_after
    except OSError:
        return False
