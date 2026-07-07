#!/usr/bin/env python3
"""
scripts/twitch_vod_downloader.py
================================
Download a short sample of your past Twitch broadcasts so the
Anomaly_Detector baseline can be built from real history.

This is the backfill path for Tier 4.2 (statistical anomaly detection).
The repo's recordings/ folder is empty (the reorg script wiped it),
so we pull the data straight from Twitch's VOD archive.

What it does
------------
For each of the N most recent broadcasts (or saved highlights) on
your channel:
  1. Records the metadata (title, date, duration, view count).
  2. Downloads a SAMPLE WINDOW of the VOD via ffmpeg + the HLS
     playlist URL. We don't grab the whole 4-hour stream — a 5-minute
     sample from the middle is plenty to characterize the audio
     profile (mean RMS, std RMS, spike count, silence ratio).
  3. Saves the .mp4 sample to <output_dir>/<video_id>.mp4.

The output directory is yours — point Anomaly_Detector at it next:

    # Build profiles from each downloaded sample:
    for f in vod_samples/*.mp4; do
        python3 -m modules.Anomaly_Detector "$f" --game "$GAME"
    done

Credentials
-----------
Uses the same TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET as the rest of
Bolt. Add them to your .env file (or export them) and the script
will pick them up via Twitch_Stats.

Usage
-----
    # Download the 10 most recent broadcasts, 5-minute samples
    python3 scripts/twitch_vod_downloader.py --type archive --limit 10 \\
        --sample-minutes 5 --output-dir /tmp/vod_samples

    # Download saved highlights (highlights are kept forever; archives
    # expire after 14-60 days depending on your partner status)
    python3 scripts/twitch_vod_downloader.py --type highlight --limit 5

    # Dry run — list VODs without downloading
    python3 scripts/twitch_vod_downloader.py --limit 10 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# Repo-root-relative imports
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "Core"))

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

from modules.Twitch_Stats import TwitchStats  # noqa: E402


HLS_PLAYLIST_TEMPLATE = "https://usher.ttvnw.net/vod/{video_id}.m3u8"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "vod_samples"


def parse_iso8601_duration(duration: str) -> int:
    """
    Convert a Twitch ISO 8601 duration string ("2h13m47s") to seconds.
    Returns 0 if the format is unrecognised.
    """
    if not duration:
        return 0
    total = 0
    h = re.search(r"(\d+)h", duration)
    m = re.search(r"(\d+)m", duration)
    s = re.search(r"(\d+)s", duration)
    if h:
        total += int(h.group(1)) * 3600
    if m:
        total += int(m.group(1)) * 60
    if s:
        total += int(s.group(1))
    return total


def derive_sample_start(duration_seconds: int, sample_seconds: int) -> int:
    """
    Pick a start time for the sample window.

    Twitch streams usually have ~5 min of "stream starting" at the top
    and ~10 min of "stream ending" at the bottom. We skip 10% on each
    end and grab the middle. If the VOD is shorter than the requested
    sample + buffer, we just take the full middle slice.
    """
    if duration_seconds <= 0:
        return 0
    if duration_seconds <= sample_seconds:
        return 0
    margin = max(60, int(duration_seconds * 0.1))  # 10% margin, min 1 min
    earliest = margin
    latest = duration_seconds - margin - sample_seconds
    if latest <= earliest:
        return margin
    # Bias slightly later than the midpoint — game audio tends to
    # have more action in the second half.
    midpoint = (earliest + latest) // 2 + int((latest - earliest) * 0.1)
    return max(earliest, min(midpoint, latest))


def download_sample(
    video_id: str,
    output_path: Path,
    sample_seconds: int,
    start_seconds: int,
    user_token: Optional[str] = None,
) -> bool:
    """
    Download a sample window of a Twitch VOD via ffmpeg.

    Uses the HLS playlist URL. ffmpeg handles the segment fetching
    internally and we copy the resulting mp4 to disk. We copy the
    codec (no re-encode) so it's fast and lossless.

    If `user_token` is provided it's appended to the HLS URL as
    ?token=... — Twitch's VOD CDN requires a User Access Token to
    authorize downloads. The App Access Token (used for the Helix
    listing API) is not sufficient.

    Returns True on success, False otherwise.
    """
    url = HLS_PLAYLIST_TEMPLATE.format(video_id=video_id)
    if user_token:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}token={user_token}"

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_seconds),
        "-i", url,
        "-t", str(sample_seconds),
        "-c", "copy",          # no re-encode
        "-bsf:v", "h264_mp4toannexb",  # HLS -> MP4 fixup
        "-f", "mp4",
        str(output_path),
    ]
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            timeout=600,  # 10 min — HLS download can be slow
        )
        if r.returncode != 0:
            err = r.stderr.decode(errors="ignore")
            # 403 from the VOD CDN means the App Access Token isn't
            # sufficient — Twitch's VOD endpoints require a User Access
            # Token for the channel owner (with `channel:read` scope).
            if "403" in err or "Forbidden" in err:
                print(
                    "  [warn] VOD CDN returned 403. The Helix App Access Token\n"
                    "         can list VODs but not download them. You need a\n"
                    "         User Access Token (channel owner, with\n"
                    "         'channel:read' or 'videos:read' scope) passed via\n"
                    "         --user-token. See:\n"
                    "         https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/",
                    file=sys.stderr,
                )
            else:
                print(
                    f"  [warn] ffmpeg returned {r.returncode} for {video_id}: "
                    f"{err[-300:]}",
                    file=sys.stderr,
                )
            return False
        if not output_path.exists() or output_path.stat().st_size < 1024:
            return False
        return True
    except subprocess.TimeoutExpired:
        print(f"  [warn] ffmpeg timed out for {video_id}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"  [warn] ffmpeg failed for {video_id}: {e}", file=sys.stderr)
        return False


def list_videos(
    channel: str,
    video_type: str,
    limit: int,
) -> list:
    """List VODs for a channel via Twitch Helix."""
    try:
        ts = TwitchStats(channel=channel)
    except EnvironmentError as e:
        print(f"[error] {e}", file=sys.stderr)
        sys.exit(1)

    user = ts.get_user()
    user_id = user.get("id")
    if not user_id:
        print(f"[error] Could not resolve user_id for channel '{channel}'", file=sys.stderr)
        sys.exit(1)
    print(f"Channel: {user.get('display_name')} (id={user_id})")
    print(f"Fetching up to {limit} {video_type}(s)...")
    videos = ts.get_videos(user_id=user_id, video_type=video_type, limit=limit)
    print(f"  found {len(videos)} VOD(s)")
    return videos


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--channel", default=None,
        help="Twitch channel login (default: from TWITCH_CHANNEL env or BillyandRandyGaming)",
    )
    parser.add_argument(
        "--type", default="archive",
        choices=["archive", "highlight", "upload"],
        help="VOD type: 'archive' = past broadcasts, 'highlight' = saved highlights, 'upload' = manual uploads",
    )
    parser.add_argument(
        "--limit", type=int, default=10,
        help="Max number of VODs to process (default: 10)",
    )
    parser.add_argument(
        "--sample-minutes", type=int, default=5,
        help="Length of each VOD sample to download, in minutes (default: 5)",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
        help=f"Where to write the .mp4 samples (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--metadata-file", type=Path, default=None,
        help="Where to write the VOD metadata JSON (default: <output-dir>/metadata.json)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="List VODs and their planned sample windows, but don't download.",
    )
    parser.add_argument(
        "--skip-existing", action="store_true",
        help="Skip VODs whose <video_id>.mp4 already exists in output-dir.",
    )
    parser.add_argument(
        "--user-token", default=os.environ.get("TWITCH_USER_TOKEN"),
        help="Twitch User Access Token (channel owner). Required for VOD downloads — "
             "the App Access Token is not enough. Generate one with channel:read scope.",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = args.metadata_file or (args.output_dir / "metadata.json")

    sample_seconds = args.sample_minutes * 60

    channel = args.channel or TwitchStats().channel
    videos = list_videos(channel, args.type, args.limit)
    if not videos:
        print("Nothing to do.")
        return 0

    # Load existing metadata if we're appending, so we don't clobber history.
    existing_meta = []
    if metadata_path.exists():
        try:
            with open(metadata_path, encoding="utf-8") as f:
                existing_meta = json.load(f)
        except Exception:
            existing_meta = []

    new_meta: list = []
    for v in videos:
        duration_sec = parse_iso8601_duration(v.get("duration", ""))
        start = derive_sample_start(duration_sec, sample_seconds)
        meta = {
            "id": v["id"],
            "title": v.get("title", ""),
            "created_at": v.get("created_at", ""),
            "duration": v.get("duration", ""),
            "duration_seconds": duration_sec,
            "view_count": v.get("view_count", 0),
            "url": v.get("url", ""),
            "sample_start_seconds": start,
            "sample_duration_seconds": min(sample_seconds, duration_sec) if duration_sec else sample_seconds,
            "sample_path": str(args.output_dir / f"{v['id']}.mp4"),
        }
        if args.dry_run:
            print(
                f"  {v['id']} | {v.get('created_at', '?')} | "
                f"{v.get('duration', '?'):>8} | "
                f"{v.get('view_count', 0):>6} views | "
                f"sample {start}s..{start + meta['sample_duration_seconds']}s | "
                f"{v.get('title', '')[:50]}"
            )
        else:
            out_file = Path(meta["sample_path"])
            if args.skip_existing and out_file.exists() and out_file.stat().st_size > 0:
                print(f"  [skip] {v['id']} (already exists)")
                new_meta.append(meta)
                continue
            print(
                f"  [download] {v['id']} | "
                f"{v.get('title', '')[:50]} | "
                f"sample {start}s..{start + meta['sample_duration_seconds']}s"
            )
            ok = download_sample(
                v["id"],
                out_file,
                meta["sample_duration_seconds"],
                start,
                user_token=args.user_token,
            )
            meta["download_ok"] = ok
            if not ok and out_file.exists():
                # Clean up partial files so retries work.
                out_file.unlink()
            new_meta.append(meta)
        # Be polite to the Twitch CDN
        time.sleep(0.5)

    if not args.dry_run:
        # Merge with existing metadata, de-dup by id.
        seen = {m["id"] for m in new_meta}
        merged = list(new_meta)
        for m in existing_meta:
            if m.get("id") not in seen:
                merged.append(m)
        merged.sort(key=lambda m: m.get("created_at", ""), reverse=True)
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2)
        print(f"\nWrote metadata for {len(merged)} VOD(s) to {metadata_path}")
        ok_count = sum(1 for m in new_meta if m.get("download_ok"))
        print(f"Downloaded {ok_count} / {len(new_meta)} sample(s) to {args.output_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
