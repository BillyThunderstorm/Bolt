#!/usr/bin/env python3
"""
Filter the existing clip backlog by score.
Moves low-scoring clips into clips/_low_score/ so you only review the good ones.
"""

import os, shutil
from pathlib import Path
# Post-reorg path bootstrap. Adds the script's own dir to sys.path so
# `from _paths import …` works in both direct invocation and `from
# scripts import X` (test) contexts. The helper itself adds Core/ and
# 3rd_Party/llm/ to sys.path so `from modules import Y` resolves, and
# chdirs to the repo root for any CWD-relative paths the script uses.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from _paths import REPO_ROOT, DATA_DIR, CLIPS_DIR, LOGS_DIR, CONFIG_FILE  # noqa: E402

# Backward-compatible aliases for code that uses `ROOT` / `PROJECT_ROOT`.
PROJECT_ROOT = REPO_ROOT
ROOT = REPO_ROOT

from modules.Clip_Ranker import _score_clip, _load_history

CLIPS_DIR = Path("clips")
LOW_DIR = CLIPS_DIR / "_low_score"
LOW_DIR.mkdir(exist_ok=True)

THRESHOLD = 65
history = _load_history("Marvel Rivals")


# Build minimal clip-like objects from existing files
class FakeHighlight:
    def __init__(self):
        self.trigger = "highlight"
        self.score = 50.0


class FakeClip:
    def __init__(self, path):
        self.output_file = str(path)
        self.success = True
        self.highlight = FakeHighlight()


moved = 0
kept = 0
for clip in CLIPS_DIR.glob("*.mp4"):
    fc = FakeClip(clip)
    score, breakdown = _score_clip(fc, history)
    if score < THRESHOLD:
        shutil.move(str(clip), str(LOW_DIR / clip.name))
        moved += 1
    else:
        kept += 1
        print(f"  KEEP  {clip.name}  (score {score:.0f})")

print(f"\n✓ Kept {kept} clips above {THRESHOLD}")
print(f"✗ Moved {moved} clips to {LOW_DIR}")
