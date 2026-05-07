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

WHY persistence matters:
  The original used an in-memory set that reset every launch. This meant
  every restart reprocessed every file in recordings/ from scratch, causing
  hundreds of duplicate clips. Now processed filenames are saved to
  data/processed_recordings.json and loaded on startup — Bolt remembers
  exactly which files it has already handled.
"""

import os
import json
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

RECORDINGS_FOLDER = os.getenv("RECORDINGS_FOLDER", "recordings")
WATCH_INTERVAL    = float(os.getenv("WATCH_INTERVAL", "5"))
WATCH_EXTENSIONS  = {".mp4", ".mkv", ".mov", ".avi"}
STABLE_WAIT_SEC   = 3.0   # seconds to wait before declaring the file stable

# Where we persist the list of already-processed filenames across restarts.
# Without this file, every launch re-runs the full pipeline on every recording.
PROCESSED_LOG = Path(__file__).parent.parent / "data" / "processed_recordings.json"


def _load_processed() -> set:
    """
    Load the set of already-processed filenames from disk.
    Returns an empty set if the file does not exist yet (first run).
    """
    try:
        with open(PROCESSED_LOG) as f:
            return set(json.load(f))
    except Exception:
        return set()


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


def watch_folder(folder: str = RECORDINGS_FOLDER):
    """
    Generator that yields the absolute path of every new video file
    that appears in folder, in order of detection.

    Processed filenames are persisted to data/processed_recordings.json
    so Bolt never reprocesses the same recording across restarts.

    Usage
    -----
        for recording in watch_folder():
            process(recording)
    """
    os.makedirs(folder, exist_ok=True)

    # Load from disk — survives restarts, no more duplicate processing
    processed: set = _load_processed()

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
            if filename in processed:
                continue

            full_path = os.path.join(folder, filename)
            if not _is_stable(full_path):
                continue   # still being written — check again next cycle

            processed.add(filename)
            _save_processed(processed)   # persist immediately so restarts stay clean
            print(f"[Watcher] New recording detected: {filename}")
            yield full_path

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
