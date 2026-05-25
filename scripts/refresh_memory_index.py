#!/usr/bin/env python3
"""Refresh Bolt's local memory retrieval index."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.Memory_Index import MEMORY_INDEX_FILE, refresh_memory_index


def main() -> int:
    payload = refresh_memory_index()
    print(f"Indexed {payload['entry_count']} memory entries -> {MEMORY_INDEX_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
