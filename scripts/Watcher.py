"""Thin wrapper so `bolt watch` uses Core/modules/Watcher.py.

The real watcher (processed-log, newest-pending, mark-after-yield) lives
in Core. This file only bootstraps sys.path.
"""

from __future__ import annotations

import sys
from pathlib import Path

_CORE = Path(__file__).resolve().parents[1] / "Core"
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

from modules.Watcher import (  # noqa: E402
    RECORDINGS_FOLDER,
    WATCH_INTERVAL,
    load_processed,
    mark_processed,
    is_processed,
    list_pending_recordings,
    watch_folder,
)

__all__ = [
    "RECORDINGS_FOLDER",
    "WATCH_INTERVAL",
    "load_processed",
    "mark_processed",
    "is_processed",
    "list_pending_recordings",
    "watch_folder",
]


if __name__ == "__main__":
    for path in watch_folder():
        print(path)
