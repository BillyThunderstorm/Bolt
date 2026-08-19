#!/usr/bin/env python3
"""
Filter the existing clip backlog by score.

Scores come from real clip data — sidecar written at cut time, original
detector scores recovered from daily logs, or a fresh audio analysis.
Never uses a hardcoded highlight/50 stand-in.

Moves low-scoring clips into media/clips/_low_score/.
"""

import argparse
import shutil
import sys
from pathlib import Path

# Post-reorg path bootstrap. Adds the script's own dir to sys.path so
# `from _paths import …` works in both direct invocation and `from
# scripts import X` (test) contexts. The helper itself adds Core/ and
# 3rd_Party/llm/ to sys.path so `from modules import Y` resolves, and
# chdirs to the repo root for any CWD-relative paths the script uses.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from _paths import REPO_ROOT, CLIPS_DIR  # noqa: E402

# Backward-compatible aliases for code that uses `ROOT` / `PROJECT_ROOT`.
PROJECT_ROOT = REPO_ROOT
ROOT = REPO_ROOT

from modules.Clip_Ranker import (  # noqa: E402
    DISCARD_BELOW,
    clip_from_path,
    load_logged_highlight_scores,
    rank_clips,
)
from modules.Config_Loader import load_config  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Move low-scoring clips into media/clips/_low_score/"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Score and print decisions without moving files",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Keep clips at or above this score (default: config min_clip_score)",
    )
    parser.add_argument(
        "--game",
        default=None,
        help="Game key for history/learned boost (default: config.json game)",
    )
    args = parser.parse_args(argv)

    config = load_config()
    game = args.game or config.get("game") or "Gaming"
    threshold = args.threshold
    if threshold is None:
        threshold = float(config.get("min_clip_score", DISCARD_BELOW))

    low_dir = CLIPS_DIR / "_low_score"
    clips = sorted(p for p in CLIPS_DIR.glob("*.mp4") if p.is_file())
    if not clips:
        print(f"No clips in {CLIPS_DIR}")
        return 0

    logged = load_logged_highlight_scores()
    built = [
        clip_from_path(path, game=game, logged_scores=logged) for path in clips
    ]
    ranked = rank_clips(built, min_score=threshold, game=game)

    if not args.dry_run:
        low_dir.mkdir(parents=True, exist_ok=True)

    moved = 0
    kept = 0
    print(f"Scoring {len(ranked)} clip(s) for {game}  (keep ≥ {threshold:g})")
    for clip in ranked:
        name = Path(clip.output_file).name
        score = float(getattr(clip, "score", 0.0) or 0.0)
        breakdown = getattr(clip, "breakdown", "")
        source = getattr(clip, "score_source", "?")
        extra = f"{breakdown}  src={source}".strip()
        if score < threshold:
            print(f"  MOVE  {name}  (score {score:.0f})  {extra}")
            if not args.dry_run:
                dest = low_dir / name
                shutil.move(str(clip.output_file), str(dest))
                sidecar = Path(clip.output_file).with_suffix(".json")
                if sidecar.exists():
                    shutil.move(str(sidecar), str(dest.with_suffix(".json")))
            moved += 1
        else:
            print(f"  KEEP  {name}  (score {score:.0f})  {extra}")
            kept += 1

    verb = "Would move" if args.dry_run else "Moved"
    print(f"\n✓ Kept {kept} clips above {threshold:g}")
    print(f"✗ {verb} {moved} clips to {low_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
