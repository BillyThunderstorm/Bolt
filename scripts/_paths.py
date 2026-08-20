"""
Bolt scripts/_paths.py
=======================
Single source of truth for the post-reorg Bolt repo layout.

This module exists because the color-coded folder reorg (July 2026) moved
Bolt's source code, data, and media into named subfolders (`Core/`, `Data/`,
`media/`, `Docs/`, `3rd_Party/`). Many of the scripts under
`scripts/` were re-homed but their internal PROJECT_ROOT
arithmetic and hardcoded subpath strings were not updated. This helper
provides a single place to:

  * Compute the repo root correctly (parents[1] from any script in
    scripts/).
  * Add the right directories to sys.path so `from modules import X`
    resolves to `Core/modules/X`.
  * Export the standard subpath constants every script needs.

Usage from a script in `scripts/`:

    from _paths import (
        REPO_ROOT, CORE_DIR, DATA_ROOT, DATA_DIR, MEDIA_DIR, DOCS_DIR,
        LOGS_DIR, ARCHIVE_DIR, SCRIPTS_DIR, MEMORY_DIR, MEMORY_HOT_FILE,
        CLIPS_DIR, VERTICAL_CLIPS_DIR, RECORDINGS_DIR, OUTPUT_DIR,
        BRIEFINGS_DIR, CONFIG_FILE, BOT_FILE, REQUIREMENTS_FILE,
    )

The helper also does an `os.chdir(REPO_ROOT)` so any CWD-relative paths
the rest of the script uses still work.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# scripts/_paths.py  →  parents[1]  =  repo root
# (parents[0] = scripts/, parents[1] = repo root)
REPO_ROOT: Path = Path(__file__).resolve().parents[1]

# Core source tree
CORE_DIR: Path = REPO_ROOT / "Core"
MODULES_DIR: Path = CORE_DIR / "modules"
SRC_DIR: Path = CORE_DIR / "src"
CONFIG_FILE: Path = CORE_DIR / "config.json"
BOT_FILE: Path = CORE_DIR / "bot.py"
BOLT_BRAIN_FILE: Path = CORE_DIR / "bolt_brain.md"

# Data tree — live state lives directly under Data/.
# DATA_DIR and DATA_ROOT are the same path (Data/data/ was a leftover nest).
DATA_ROOT: Path = REPO_ROOT / "Data"
DATA_DIR: Path = DATA_ROOT
CONFIG_DIR: Path = DATA_ROOT / "configs"
CONTENT_DIR: Path = DATA_ROOT / "content"
MEMORY_DIR: Path = DATA_ROOT / "memory"
MEMORY_HOT_FILE: Path = DATA_ROOT / "MEMORY.md"
ARCHIVE_DIR: Path = DATA_ROOT / "archive"

# Media tree — active recordings live here in the new layout.
MEDIA_DIR: Path = REPO_ROOT / "media"
CLIPS_DIR: Path = MEDIA_DIR / "clips"
VERTICAL_CLIPS_DIR: Path = MEDIA_DIR / "vertical_clips"
OUTPUT_DIR: Path = MEDIA_DIR / "output"
RECORDINGS_DIR: Path = MEDIA_DIR / "Recordings"

# Docs tree
DOCS_DIR: Path = REPO_ROOT / "Docs"
BRIEFINGS_DIR: Path = DOCS_DIR / "briefings"
DAILY_BRIEFINGS_DIR: Path = BRIEFINGS_DIR / "daily"

# Misc
LOGS_DIR: Path = REPO_ROOT / "logs"
THIRDPARTY_DIR: Path = REPO_ROOT / "3rd_Party"
SCRIPTS_DIR: Path = REPO_ROOT / "scripts"
LLM_DIR: Path = THIRDPARTY_DIR / "llm"
VOD_SAMPLES_DIR: Path = THIRDPARTY_DIR / "vod_samples"
REQUIREMENTS_FILE: Path = DOCS_DIR / "requirements.txt"

# Make `from modules import X` resolve to `Core/modules/X`.
for _p in (CORE_DIR, SCRIPTS_DIR, LLM_DIR):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

# cd into the repo root so any CWD-relative paths the script uses still
# work as if the script had been invoked from there.
os.chdir(REPO_ROOT)
