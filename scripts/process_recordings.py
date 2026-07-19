#!/usr/bin/env python3
"""
process_recordings.py — Process your existing recordings right now
===================================================================
Run this to turn recordings you already have into TikTok-ready clips.

Usage:
  python3 process_recordings.py           → process ALL recordings in the folder
  python3 process_recordings.py latest    → process the most recent recording only
  python3 process_recordings.py list      → just show what recordings are found

How it works:
  This runs the same full pipeline as bot.py:
    detect highlights → cut clips → generate titles → add subtitles
    → rank by virality → format to 9:16 → save to post queue

Where clips are saved (post-reorg):
  media/clips/         → raw highlight clips (horizontal, same as your recording)
  media/vertical_clips/ → TikTok-ready 9:16 format (this is what you post)
"""

import os
import sys
import json
from pathlib import Path

# Make project root importable when this script is run directly.
# The helper module adds Core/ and scripts/ to sys.path so
# `from modules import X` and `from bot import process_recording` resolve.
# Make _paths importable in BOTH direct invocation and `from scripts import X`.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _paths import (  # noqa: E402
    REPO_ROOT, CLIPS_DIR, VERTICAL_CLIPS_DIR, RECORDINGS_DIR,
    BOLT_BRAIN_FILE, DATA_DIR,
)

# Backward-compatible aliases for code that uses `ROOT` / `PROJECT_ROOT`.
PROJECT_ROOT = REPO_ROOT
ROOT = REPO_ROOT


from modules.Config_Loader import load_config

config = load_config()

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from modules.Think_Learn_Decide import BrainController

# ── Find recordings folder ─────────────────────────────────────────────────────


def find_recordings_folder() -> Path:
    """
    Find the recordings folder, trying a few common locations.
    Returns the folder path (creates it if needed).

    Post-reorg: live recordings/ at the repo root was deleted (2026-07-07
    reorg). The archived copy lives at Data/archive/recordings. We look
    there first, then fall back to config.json, .env, and finally a
    CWD-relative path.
    """
    # Post-reorg: archived recordings are the only on-disk set we know about.
    if RECORDINGS_DIR.exists():
        return RECORDINGS_DIR

    # Check config.json first (config may have a custom path)
    config_path = Path("Core/config.json")
    if config_path.exists():
        try:
            with open(config_path) as f:
                config = json.load(f)
                folder = Path(config.get("recordings_folder", "Data/archive/recordings"))
                if folder.exists():
                    return folder
        except Exception:
            pass

    # Check .env
    env_folder = os.getenv("RECORDINGS_FOLDER", "")
    if env_folder and Path(env_folder).exists():
        return Path(env_folder)

    # Default: the archived recordings folder
    folder = Path("Data/archive/recordings")
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def find_recordings(folder: Path) -> list:
    """Find all video files in the recordings folder, newest first."""
    extensions = [".mp4", ".mkv", ".mov", ".avi"]
    files = []
    for ext in extensions:
        files.extend(folder.glob(f"*{ext}"))
    return sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)


# ── Display helpers ────────────────────────────────────────────────────────────


def print_header():
    print()
    print("  ⚡️  Bolt — Process Recordings")
    print("  ─" * 28)
    print()


def print_recordings(recordings: list, folder: Path):
    if not recordings:
        print(f"  ○  No recordings found in:  {folder.resolve()}")
        print()
        print("  To add recordings:")
        print(f"     1. Copy your .mp4 or .mkv files into:  {folder.resolve()}")
        print(
            "     2. OR in OBS: Settings → Output → Recording → set path to that folder"
        )
        print()
        return False

    print(f"  Found {len(recordings)} recording(s) in:  {folder.resolve()}")
    print()
    for i, f in enumerate(recordings, 1):
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"  [{i}]  {f.name}  ({size_mb:.0f} MB)")
    print()
    return True


def print_output_paths():
    # Post-reorg: default to media/clips and media/vertical_clips, but
    # honor config.json if it specifies custom paths.
    clips_dir = REPO_ROOT / config.get("clips_folder", "media/clips")
    vertical_dir = REPO_ROOT / config.get("vertical_clips_folder", "media/vertical_clips")

    clips_dir.mkdir(parents=True, exist_ok=True)
    vertical_dir.mkdir(parents=True, exist_ok=True)
    print()
    print("  📁  Where to find your clips after processing:")
    print(f"     Horizontal clips:  {clips_dir}")
    print(f"     TikTok (9:16):     {vertical_dir}")
    print()


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Bolt — Process recordings into TikTok-ready clips"
    )
    parser.add_argument(
        "mode",
        nargs="?",
        default="all",
        help="all | latest | list | 1..N (default: all)",
    )
    parser.add_argument(
        "--content-type", "-t",
        default="gaming",
        choices=["gaming", "review", "skincare", "tech"],
        help="Content type: gaming (default), review, skincare, tech — controls title style and caption strategy",
    )
    args = parser.parse_args()
    mode = args.mode
    content_type = args.content_type

    print_header()
    if content_type != "gaming":
        print(f"  📂  Content type: {content_type.upper()}")
        print()

    folder = find_recordings_folder()
    recordings = find_recordings(folder)

    # ── List mode ─────────────────────────────────────────────────────────────
    if mode == "list":
        print_recordings(recordings, folder)
        print_output_paths()
        return

    if not print_recordings(recordings, folder):
        return

    # ── Pick which recordings to process ─────────────────────────────────────
    if mode == "latest":
        to_process = [recordings[0]]
        print(f"  Processing latest:  {recordings[0].name}")
    elif mode == "all":
        to_process = recordings
        print(f"  Processing all {len(recordings)} recording(s)…")
    else:
        # Try treating mode as a number (index)
        try:
            idx = int(mode) - 1
            to_process = [recordings[idx]]
            print(f"  Processing #{idx + 1}:  {recordings[idx].name}")
        except (ValueError, IndexError):
            print(f"  ✗  Unknown mode: {mode}")
            print(
                "     Usage: python3 process_recordings.py [all | latest | list | 1..N] [--content-type gaming|review|skincare|tech]"
            )
            return

    print()

    # config is already loaded at the top through Config_Loader

    brain = ""
    # Post-reorg: bolt_brain.md moved to Core/bolt_brain.md.
    brain_path = BOLT_BRAIN_FILE
    if brain_path.exists():
        brain = brain_path.read_text()
        print("  ✓  bolt_brain.md loaded — AI titles will match your style")
    else:
        print("  ○  bolt_brain.md not found — using generic AI titles")

    print()

    brain_controller = BrainController(config, brain)

    # ── Inject content_type into config so bot.py can use it ─────────────────
    config["content_type"] = content_type

    # ── Process each recording ────────────────────────────────────────────────
    from bot import process_recording

    for i, recording in enumerate(to_process, 1):
        print(f"  ━━━  [{i}/{len(to_process)}]  {recording.name}  ━━━")
        print()

        try:
            process_recording(
                str(recording), config, brain, intelligence=brain_controller
            )
        except KeyboardInterrupt:
            print("\n  Stopped by user. Partial results may have been saved.")
            break
        except Exception as e:
            print(f"  ✗  Failed to process {recording.name}: {e}")
            import traceback

            traceback.print_exc()
            continue

        print()

    # ── Show where to find clips ──────────────────────────────────────────────
    print_output_paths()

    # ── Show post queue summary ───────────────────────────────────────────────
    try:
        # Post-reorg: queue file lives under Data/data/.
        queue_file = DATA_DIR / "ready_to_post.json"
        if queue_file.exists():
            with open(queue_file) as f:
                queue = json.load(f)
            items = (
                queue
                if isinstance(queue, list)
                else queue.get("clips", queue.get("queue", []))
            )
            unposted = [
                x
                for x in items
                if x.get("status", "ready") == "ready" and not x.get("posted", False)
            ]
            if unposted:
                print(f"  🦊  {len(unposted)} ready queue row(s)")
                print("     Run:  python3 -m modules.Peak_Hour_Notifier --summary")
                print()
    except Exception:
        pass


if __name__ == "__main__":
    main()
