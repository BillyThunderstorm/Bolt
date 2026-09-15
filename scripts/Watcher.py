"""Thin wrapper so `bolt watch` / direct script runs use soft-fail Folder_Watch.

The real watcher library (processed-log, newest-pending, mark-after-yield) lives
in Core/modules/Watcher.py. Soft-fail CLI is Core/modules/Folder_Watch.py
(status/list/run). Prefer `bolt launch` for live mode.
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
    from modules.Folder_Watch import main

    raise SystemExit(main())
