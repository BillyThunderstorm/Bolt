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

Where clips are saved:
  clips/           → raw highlight clips (horizontal, same as your recording)
  vertical_clips/  → TikTok-ready 9:16 format (this is what you post)

Both folders are inside your Bolt folder on iCloud Drive.
"""

import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Find recordings folder ─────────────────────────────────────────────────────

def find_recordings_folder() -> Path:
    """
    Find the recordings folder, trying a few common locations.
    Returns the folder path (creates it if needed).
    """
    # Check config.json first
    config_path = Path("config.json")
    if config_path.exists():
        try:
            with open(config_path) as f:
                config = json.load(f)
                folder = Path(config.get("recordings_folder", "recordings"))
                if folder.exists():
                    return folder
        except Exception:
            pass

    # Check .env
    env_folder = os.getenv("RECORDINGS_FOLDER", "")
    if env_folder and Path(env_folder).exists():
        return Path(env_folder)

    # Default: relative recordings/ folder
    folder = Path("recordings")
    folder.mkdir(exist_ok=True)
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
    print("  🦊  Bolt — Process Recordings")
    print("  ─" * 28)
    print()


def print_recordings(recordings: list, folder: Path):
    if not recordings:
        print(f"  ○  No recordings found in:  {folder.resolve()}")
        print()
        print("  To add recordings:")
        print(f"     1. Copy your .mp4 or .mkv files into:  {folder.resolve()}")
        print("     2. OR in OBS: Settings → Output → Recording → set path to that folder")
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
    clips_dir    = Path("clips").resolve()
    vertical_dir = Path("vertical_clips").resolve()
    print()
    print("  📁  Where to find your clips after processing:")
    print(f"     Horizontal clips:  {clips_dir}")
    print(f"     TikTok (9:16):     {vertical_dir}")
    print()


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print_header()

    folder     = find_recordings_folder()
    recordings = find_recordings(folder)
    mode       = sys.argv[1] if len(sys.argv) > 1 else "all"

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
        # Try treating argv[1] as a number (index)
        try:
            idx = int(mode) - 1
            to_process = [recordings[idx]]
            print(f"  Processing #{idx+1}:  {recordings[idx].name}")
        except (ValueError, IndexError):
            print(f"  ✗  Unknown mode: {mode}")
            print("     Usage: python3 process_recordings.py [all | latest | list | 1..N]")
            return

    print()

    # ── Load config + brain ───────────────────────────────────────────────────
    config = {}
    try:
        with open("config.json") as f:
            config = json.load(f)
    except Exception:
        print("  ⚠  config.json not found — using defaults")

    brain = ""
    brain_path = Path("Bolt_brain.md")
    if brain_path.exists():
        brain = brain_path.read_text()
        print("  ✓  Bolt_brain.md loaded — AI titles will match your style")
    else:
        print("  ○  Bolt_brain.md not found — using generic AI titles")

    print()

    # ── Process each recording ────────────────────────────────────────────────
    from bot import process_recording

    for i, recording in enumerate(to_process, 1):
        print(f"  ━━━  [{i}/{len(to_process)}]  {recording.name}  ━━━")
        print()

        try:
            process_recording(str(recording), config, brain)
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
        queue_file = Path("data/ready_to_post.json")
        if queue_file.exists():
            with open(queue_file) as f:
                queue = json.load(f)
            items = queue if isinstance(queue, list) else queue.get("queue", [])
            unposted = [x for x in items if not x.get("posted", False)]
            if unposted:
                print(f"  🦊  {len(unposted)} clip(s) ready to post in Discord queue")
                print("     Run:  python3 -m modules.Peak_Hour_Notifier --summary")
                print()
    except Exception:
        pass


if __name__ == "__main__":
    main()
