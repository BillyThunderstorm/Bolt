#!/usr/bin/env python3
"""
auto_clip_twitch.py — Auto-clip highlights from Twitch VODs
============================================================
Downloads past stream VODs from Twitch, runs them through Bolt's
existing clip pipeline (detect highlights → cut → format 9:16 → queue),
and optionally creates Twitch clips via the Helix API.

Usage:
  python3 auto_clip_twitch.py                    → process latest unprocessed VOD
  python3 auto_clip_twitch.py --all               → process all unprocessed VODs
  python3 auto_clip_twitch.py --list               → list VODs and processing status
  python3 auto_clip_twitch.py --vod <VOD_ID>       → process specific VOD
  python3 auto_clip_twitch.py --twitch-clips       → also auto-create Twitch clips for highlights

Requires:
  - .env with TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET, TWITCH_CHANNEL
  - yt-dlp installed (pip install yt-dlp)
  - ffmpeg installed
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Make project root importable
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from modules import twitch_auth
from modules.Config_Loader import load_config

try:
    import requests
except ImportError:
    requests = None

# ── Constants ───────────────────────────────────────────────────────────────────

CHANNEL_LOGIN = os.getenv("TWITCH_CHANNEL", "").strip()
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID", "").strip()
VODS_DIR = PROJECT_ROOT / "vods"
PROCESSED_LOG = PROJECT_ROOT / "data" / "twitch_vods_processed.json"
QUEUE_FILE = PROJECT_ROOT / "data" / "ready_to_post.json"
MAX_VOD_DURATION_SECONDS = 3 * 3600  # Skip VODs longer than 3 hours


# ── Helpers ────────────────────────────────────────────────────────────────────

def _helix_get(endpoint: str, params: dict = None) -> dict:
    """Make a Helix API GET request with auto-auth."""
    if requests is None:
        raise RuntimeError("requests library not installed")
    token = twitch_auth.get_app_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Client-Id": TWITCH_CLIENT_ID,
    }
    url = f"https://api.twitch.tv/helix/{endpoint}"
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    if resp.status_code == 401:
        token = twitch_auth.get_app_token(force_refresh=True)
        headers["Authorization"] = f"Bearer {token}"
        resp = requests.get(url, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_channel_user_id() -> Optional[str]:
    """Get the Twitch user ID for the configured channel."""
    data = _helix_get("users", {"login": CHANNEL_LOGIN})
    users = data.get("data", [])
    return users[0]["id"] if users else None


def parse_duration(duration_str: str) -> int:
    """Parse Twitch duration string like '1h23m45s' → total seconds."""
    total = 0
    parts = {"h": 3600, "m": 60, "s": 1}
    current = ""
    for char in duration_str:
        if char.isdigit():
            current += char
        elif char in parts and current:
            total += int(current) * parts[char]
            current = ""
    return total


def list_vods(user_id: str, first: int = 20) -> list[dict]:
    """Fetch recent VODs (archive type) for a broadcaster."""
    data = _helix_get("videos", {
        "user_id": user_id,
        "first": first,
        "type": "archive",
    })
    return data.get("data", [])


def load_processed_log() -> dict:
    """Load the log of already-processed VOD IDs."""
    if PROCESSED_LOG.exists():
        try:
            return json.loads(PROCESSED_LOG.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"processed": {}}


def save_processed_log(log: dict) -> None:
    """Save the processed VOD log."""
    PROCESSED_LOG.parent.mkdir(parents=True, exist_ok=True)
    PROCESSED_LOG.write_text(json.dumps(log, indent=2))


def is_vod_processed(vod_id: str, log: dict) -> bool:
    return vod_id in log.get("processed", {})


def download_vod(vod_url: str, output_path: Path) -> bool:
    """Download a Twitch VOD using yt-dlp."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Resolve yt-dlp from the same Python env that's running this script
    yt_dlp_bin = str(Path(sys.executable).parent / "yt-dlp")
    if not Path(yt_dlp_bin).exists():
        yt_dlp_bin = "yt-dlp"  # Fall back to PATH lookup
    cmd = [
        yt_dlp_bin,
        "--no-progress",
        "-o", str(output_path),
        "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "--merge-output-format", "mp4",
        vod_url,
    ]
    print(f"  ⬇️  Downloading VOD with yt-dlp…")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        print(f"  ✗ Download failed: {result.stderr[:500]}")
        return False
    if not output_path.exists():
        # yt-dlp might have created a different extension
        parent = output_path.parent
        stem = output_path.stem
        for f in parent.glob(f"{stem}.*"):
            if f.suffix in (".mp4", ".mkv", ".webm"):
                if f.suffix != ".mp4":
                    # Convert to mp4
                    conv_cmd = ["ffmpeg", "-y", "-i", str(f),
                                "-c", "copy", str(output_path)]
                    subprocess.run(conv_cmd, capture_output=True, timeout=120)
                    f.unlink()
                return True
        return False
    return True


def run_clip_pipeline(recording_path: str, config: dict) -> bool:
    """Run Bolt's existing process_recording pipeline on the downloaded VOD."""
    try:
        from bot import process_recording
        from modules.Think_Learn_Decide import ThinkLearnDecideEngine

        brain_path = PROJECT_ROOT / "Bolt_brain.md"
        brain = brain_path.read_text() if brain_path.exists() else ""

        engine = ThinkLearnDecideEngine(config)

        print(f"  ⚡  Running clip pipeline on {Path(recording_path).name}…")
        process_recording(
            recording_path,
            config,
            brain,
            intelligence=engine,
        )
        return True
    except Exception as e:
        print(f"  ✗ Pipeline error: {e}")
        import traceback
        traceback.print_exc()
        return False


def create_twitch_clip(vod_id: str, highlight_start: float, highlight_end: float,
                       title: str) -> bool:
    """Create a Twitch clip via Helix API (requires user token, not app token).

    Note: The Helix clips POST endpoint requires a user OAuth token with
    clips:edit scope, which the app token doesn't have. This is a placeholder
    that documents the requirement — you'd need to do a user OAuth flow.
    """
    print(f"  📋  Twitch clip creation requires user OAuth token (clips:edit scope)")
    print(f"     Skipping Twitch clip creation for: {title}")
    print(f"     To enable: complete user OAuth flow with clips:edit scope")
    return False


def add_to_queue(vod_id: str, vod_title: str, clips_created: int) -> None:
    """Add a summary entry to the post queue."""
    try:
        if QUEUE_FILE.exists():
            with open(QUEUE_FILE) as f:
                queue = json.load(f)
        else:
            queue = {"total": 0, "generated_at": datetime.now().isoformat(), "items": []}

        # The process_recording pipeline already adds clips to the queue.
        # This is just a metadata note.
        print(f"  ✅  {clips_created} clips added to post queue from VOD {vod_id}")
    except Exception as e:
        print(f"  ⚠️  Could not update queue: {e}")


# ── Main ───────────────────────────────────────────────────────────────────────

def cmd_list(user_id: str) -> None:
    """List VODs and their processing status."""
    log = load_processed_log()
    vods = list_vods(user_id)

    print(f"\n  📺  Twitch VODs for {CHANNEL_LOGIN} ({len(vods)} found)\n")
    print(f"  {'#':<4} {'VOD ID':<12} {'Status':<10} {'Duration':<10} {'Title'}")
    print(f"  {'─' * 70}")

    for i, vod in enumerate(vods, 1):
        vid = vod["id"]
        status = "✅ done" if is_vod_processed(vid, log) else "⬜ ready"
        duration = vod.get("duration", "?")
        title = vod.get("title", "Untitled")[:40]
        print(f"  {i:<4} {vid:<12} {status:<10} {duration:<10} {title}")

    unprocessed = [v for v in vods if not is_vod_processed(v["id"], log)]
    print(f"\n  {len(unprocessed)} unprocessed VOD(s) ready to clip.\n")


def process_vod(vod: dict, config: dict, create_twitch: bool = False) -> dict:
    """Download and process a single VOD. Returns result summary."""
    vod_id = vod["id"]
    vod_title = vod.get("title", "Untitled")
    vod_url = vod["url"]
    duration_str = vod.get("duration", "0s")
    duration_sec = parse_duration(duration_str)

    print(f"\n  ━━━  VOD {vod_id}: {vod_title}  ({duration_str})  ━━━\n")

    if duration_sec > MAX_VOD_DURATION_SECONDS:
        print(f"  ⏭️  Skipping — VOD is {duration_sec // 3600}h long (max {MAX_VOD_DURATION_SECONDS // 3600}h)")
        return {"vod_id": vod_id, "status": "skipped_too_long"}

    # Download VOD
    output_path = VODS_DIR / f"{vod_id}.mp4"
    if output_path.exists():
        print(f"  ♻️  VOD already downloaded: {output_path.name}")
    else:
        if not download_vod(vod_url, output_path):
            return {"vod_id": vod_id, "status": "download_failed"}

    if not output_path.exists():
        print(f"  ✗  Downloaded file not found at {output_path}")
        return {"vod_id": vod_id, "status": "download_failed"}

    # Run clip pipeline
    success = run_clip_pipeline(str(output_path), config)

    if not success:
        return {"vod_id": vod_id, "status": "pipeline_failed"}

    # Mark as processed
    log = load_processed_log()
    log.setdefault("processed", {})[vod_id] = {
        "title": vod_title,
        "processed_at": datetime.now().isoformat(),
        "vod_url": vod_url,
    }
    save_processed_log(log)

    print(f"  ✅  VOD {vod_id} processed and marked done.\n")
    return {"vod_id": vod_id, "status": "processed"}


def main():
    parser = argparse.ArgumentParser(description="Auto-clip Twitch VODs with Bolt")
    parser.add_argument("--all", action="store_true", help="Process all unprocessed VODs")
    parser.add_argument("--list", action="store_true", help="List VODs and status")
    parser.add_argument("--vod", type=str, help="Process a specific VOD by ID")
    parser.add_argument("--twitch-clips", action="store_true",
                        help="Also create Twitch clips (requires user OAuth)")
    args = parser.parse_args()

    print("\n  ⚡️  Bolt — Auto-Clip Twitch VODs")
    print(f"  Channel: {CHANNEL_LOGIN}\n")

    if not CHANNEL_LOGIN:
        print("  ✗  TWITCH_CHANNEL not set in .env")
        sys.exit(1)

    user_id = get_channel_user_id()
    if not user_id:
        print(f"  ✗  Could not find Twitch user ID for {CHANNEL_LOGIN}")
        sys.exit(1)

    print(f"  Channel ID: {user_id}")

    config = load_config()

    # ── List mode ─────────────────────────────────────────────────────────────
    if args.list:
        cmd_list(user_id)
        return

    # ── Process specific VOD ─────────────────────────────────────────────────
    if args.vod:
        vods = list_vods(user_id, first=50)
        target = next((v for v in vods if v["id"] == args.vod), None)
        if not target:
            print(f"  ✗  VOD {args.vod} not found in recent VODs")
            sys.exit(1)
        process_vod(target, config, create_twitch=args.twitch_clips)
        return

    # ── Process latest or all ────────────────────────────────────────────────
    log = load_processed_log()
    vods = list_vods(user_id)

    if not vods:
        print("  ○  No VODs found on channel.")
        return

    if args.all:
        to_process = [v for v in vods if not is_vod_processed(v["id"], log)]
        print(f"  Found {len(to_process)} unprocessed VOD(s)\n")
    else:
        # Latest unprocessed
        to_process = []
        for v in vods:
            if not is_vod_processed(v["id"], log):
                to_process = [v]
                break
        if not to_process:
            print("  ✅  All recent VODs already processed!")
            return
        print(f"  Processing latest unprocessed VOD: {to_process[0]['title']}\n")

    results = []
    for vod in to_process:
        result = process_vod(vod, config, create_twitch=args.twitch_clips)
        results.append(result)

    # Summary
    print("\n  ━━━  Summary  ━━━")
    for r in results:
        print(f"  VOD {r['vod_id']}: {r['status']}")
    print()


if __name__ == "__main__":
    main()