#!/usr/bin/env python3
"""
scripts/nexus_advice.py — Quick CLI for Nexus Creator
======================================================
Ask Nexus for content strategy advice.

Usage:
  python3 scripts/nexus_advice.py "How should I title my Hades 2 clips?"
  python3 scripts/nexus_advice.py --next
  python3 scripts/nexus_advice.py --caption "2026-07-01_clip01.mp4" --desc "Epic boss fight" -p tiktok
  python3 scripts/nexus_advice.py "skincare review strategy" --context "Posted 17 product review clips, getting low views"
"""

import sys
from pathlib import Path

# Make project root importable

# Make _paths importable in BOTH direct invocation (script dir on
# sys.path) and `from scripts import X` (tests). The helper also adds
# Core/ and 3rd_Party/llm/ to sys.path so `from modules import Y` works
# without any per-script sys.path shim, and chdirs to the repo root so
# CWD-relative paths the rest of the script uses still resolve.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from _paths import (  # noqa: E402
    REPO_ROOT,
    DATA_DIR,
    CLIPS_DIR,
    VERTICAL_CLIPS_DIR,
    MEDIA_DIR,
    LOGS_DIR,
    DAILY_BRIEFINGS_DIR,
    CONFIG_FILE,
    BOT_FILE,
    BOLT_BRAIN_FILE,
    VOD_SAMPLES_DIR,
    RECORDINGS_DIR,
)

# Backward-compatible aliases for code that uses `ROOT` / `PROJECT_ROOT`.
PROJECT_ROOT = REPO_ROOT
ROOT = REPO_ROOT

REPO_ROOT  # keep linter quiet about unused import
DATA_DIR

from modules.Nexus_Creator import main

if __name__ == "__main__":
    main()
