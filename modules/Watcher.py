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
"""

import os
import time
from dotenv import load_dotenv

load_dotenv()

RECORDINGS_FOLDER = os.getenv("RECORDINGS_FOLDER", "recordings")
WATCH_INTERVAL    = float(os.getenv("WATCH_INTERVAL", "5"))
WATCH_EXTENSIONS  = {".mp4", ".mkv", ".mov", ".avi"}
STABLE_WAIT_SEC   = 3.0   # seconds to wait before declaring the file stable


def watch_folder(folder: str = RECORDINGS_FOLDER):
    """
    Generator that yields the absolute path of every new video file
    that appears in `folder`, in order of detection.

    Usage
    -----
        for recording in watch_folder():
            process(recording)
    """
    os.makedirs(folder, exist_ok=True)
    processed: set = set()

    print(f"[Watcher] Monitoring '{folder}' for new recordings…  "
          f"(Ctrl+C to stop)")

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
            print(f"[Watcher] New recording detected: {filename}")
            yield full_path

        time.sleep(WATCH_INTERVAL)


def _is_stable(path: str) -> bool:
    """
    Return True if the file has stopped growing.
    Waits STABLE_WAIT_SEC and compares file sizes.
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
