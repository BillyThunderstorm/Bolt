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
    bolt vods status                  # creds / yt-dlp / working ffmpeg
    bolt vods list --limit 10         # list VODs, no download
    bolt vods --dry-run --limit 10    # same
    bolt vods download --limit 3 --sample-minutes 5
    bolt vods --limit 3               # same (download is the default)

    # Don't type docs <brackets> — zsh treats < as a redirect.
    bolt vods --channel itssimplybilly --dry-run
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

from modules.Twitch_Stats import (  # noqa: E402
    TwitchStats,
    status as vod_status,
    find_yt_dlp,
    find_ffmpeg,
)


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


def ytdlp_sample_cmd(
    yt_dlp: str,
    video_id: str,
    output_path: Path,
    start_seconds: int,
    sample_seconds: int,
    ffmpeg_path: Optional[str] = None,
) -> list[str]:
    """Build the yt-dlp argv for a timed VOD sample (no network)."""
    url = f"https://www.twitch.tv/videos/{video_id}"
    end = start_seconds + max(1, sample_seconds)
    cmd = [
        yt_dlp,
        "--no-progress",
        "--no-update",
        "--force-keyframes-at-cuts",
        "--download-sections",
        f"*{start_seconds}-{end}",
        "-f",
        "best[height<=480]/best[height<=720]/best",
        "--merge-output-format",
        "mp4",
        "-o",
        str(output_path),
        url,
    ]
    if ffmpeg_path:
        loc = Path(ffmpeg_path)
        ffmpeg_loc = str(loc.parent) if loc.is_file() or loc.name.startswith("ffmpeg") else str(loc)
        cmd[1:1] = ["--ffmpeg-location", ffmpeg_loc]
    return cmd


def _file_ok(path: Path) -> bool:
    return path.exists() and path.stat().st_size >= 1024


def _download_via_ytdlp(
    video_id: str,
    output_path: Path,
    sample_seconds: int,
    start_seconds: int,
    ffmpeg_path: str,
) -> bool:
    yt = find_yt_dlp()
    if not yt:
        return False
    cmd = ytdlp_sample_cmd(
        yt, video_id, output_path, start_seconds, sample_seconds, ffmpeg_path
    )
    print(
        f"  [yt-dlp] {video_id}  {start_seconds}s+{sample_seconds}s → {output_path.name}",
        flush=True,
    )
    try:
        r = subprocess.run(cmd, timeout=600)
    except subprocess.TimeoutExpired:
        print(f"  [warn] yt-dlp timed out for {video_id}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"  [warn] yt-dlp failed for {video_id}: {e}", file=sys.stderr)
        return False
    if r.returncode != 0:
        print(
            f"  [warn] yt-dlp returned {r.returncode} for {video_id}",
            file=sys.stderr,
        )
        return False
    return _file_ok(output_path)


def _download_via_ffmpeg(
    video_id: str,
    output_path: Path,
    sample_seconds: int,
    start_seconds: int,
    user_token: Optional[str] = None,
    ffmpeg_path: Optional[str] = None,
) -> bool:
    """
    Last-resort HLS grab. Twitch's unsigned usher URL often 403s;
    yt-dlp is the working path because it fetches a signed playlist.
    """
    ff = ffmpeg_path or find_ffmpeg() or "ffmpeg"
    url = HLS_PLAYLIST_TEMPLATE.format(video_id=video_id)
    if user_token:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}token={user_token}"

    cmd = [
        ff, "-y",
        "-ss", str(start_seconds),
        "-i", url,
        "-t", str(sample_seconds),
        "-c", "copy",
        "-bsf:v", "h264_mp4toannexb",
        "-f", "mp4",
        str(output_path),
    ]
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            timeout=600,
        )
        if r.returncode != 0:
            err = r.stderr.decode(errors="ignore")
            if "403" in err or "Forbidden" in err:
                print(
                    "  [warn] VOD CDN returned 403 on the raw HLS URL.\n"
                    "         Use yt-dlp (bolt vods status) instead of a\n"
                    "         User Access Token for public VODs. For\n"
                    "         subscriber-only VODs, pass --user-token.",
                    file=sys.stderr,
                )
            elif "Library not loaded" in err or "dyld" in err:
                print(
                    "  [warn] ffmpeg on PATH is broken (missing dylib). "
                    "Bolt wants ffmpeg-full. Try: brew install ffmpeg-full",
                    file=sys.stderr,
                )
            else:
                print(
                    f"  [warn] ffmpeg returned {r.returncode} for {video_id}: "
                    f"{err[-300:]}",
                    file=sys.stderr,
                )
            return False
        return _file_ok(output_path)
    except subprocess.TimeoutExpired:
        print(f"  [warn] ffmpeg timed out for {video_id}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"  [warn] ffmpeg failed for {video_id}: {e}", file=sys.stderr)
        return False


def download_sample(
    video_id: str,
    output_path: Path,
    sample_seconds: int,
    start_seconds: int,
    user_token: Optional[str] = None,
) -> bool:
    """
    Download a sample window of a Twitch VOD.

    Prefer yt-dlp with a working ffmpeg (FFmpeg_Bin / ffmpeg-full). yt-dlp
    fetches a signed Twitch playlist, so public VODs do not need
    TWITCH_USER_TOKEN. Raw ffmpeg HLS is a fallback and often 403s.

    Returns True on success, False otherwise.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_path = find_ffmpeg()
    if find_yt_dlp() and ffmpeg_path:
        if _download_via_ytdlp(
            video_id, output_path, sample_seconds, start_seconds, ffmpeg_path
        ):
            return True
        print(
            "  [warn] yt-dlp sample failed; trying ffmpeg HLS fallback…",
            file=sys.stderr,
            flush=True,
        )
    if ffmpeg_path:
        return _download_via_ffmpeg(
            video_id,
            output_path,
            sample_seconds,
            start_seconds,
            user_token=user_token,
            ffmpeg_path=ffmpeg_path,
        )
    print(
        "VOD unavailable: need yt-dlp and a working ffmpeg "
        "(PATH ffmpeg is often a broken Homebrew dylib; "
        "brew install ffmpeg-full). Check: bolt vods status",
        file=sys.stderr,
    )
    return False


def list_videos(
    channel: str,
    video_type: str,
    limit: int,
) -> list:
    """List VODs for a channel via Twitch Helix."""
    ts, err = TwitchStats.try_create(channel=channel)
    if ts is None:
        print(f"VOD unavailable: {err}", file=sys.stderr)
        sys.exit(1)

    user = ts.get_user()
    user_id = user.get("id")
    if not user_id:
        detail = user.get("error") or f"Could not resolve user_id for channel '{channel}'"
        print(f"VOD unavailable: {detail}", file=sys.stderr)
        sys.exit(1)
    print(f"Channel: {user.get('display_name')} (id={user_id})")
    print(f"Fetching up to {limit} {video_type}(s)...")
    videos = ts.get_videos(user_id=user_id, video_type=video_type, limit=limit)
    print(f"  found {len(videos)} VOD(s)")
    return videos


def _cli_status(*, as_json: bool = False, probe: bool = False, channel: str | None = None) -> int:
    """Print VOD readiness; always exit 0 (soft-fail informational)."""
    info = vod_status(probe=probe, channel=channel)
    if as_json:
        print(json.dumps(info, indent=2))
        return 0
    print("ready:", info["ready"])
    print("client_id_set:", info["client_id_set"])
    print("client_secret_set:", info["client_secret_set"])
    print("channel_set:", info["channel_set"])
    print("channel:", info["channel"])
    print("yt_dlp_found:", info["yt_dlp_found"])
    print("yt_dlp_path:", info["yt_dlp_path"])
    print("ffmpeg_found:", info["ffmpeg_found"])
    print("ffmpeg_path:", info["ffmpeg_path"])
    if info.get("hint"):
        print("hint:", info["hint"])
    if probe:
        print("probe_ok:", info.get("probe_ok"))
        print("probe_detail:", info.get("probe_detail"))
    return 0


def main(argv: list | None = None) -> int:
    raw = list(argv) if argv is not None else sys.argv[1:]

    # status subcommand / flags (bolt vods status [--json] [--probe])
    if raw and raw[0] in ("status", "vod-status", "vod_status"):
        status_argv = raw[1:]
        sp = argparse.ArgumentParser(prog="bolt vods status")
        sp.add_argument("--json", action="store_true")
        sp.add_argument("--probe", action="store_true")
        sp.add_argument("--channel", default=None)
        sargs = sp.parse_args(status_argv)
        return _cli_status(as_json=sargs.json, probe=sargs.probe, channel=sargs.channel)

    # bolt vods list → dry-run listing (no download)
    if raw and raw[0] in ("list", "ls"):
        raw = ["--dry-run"] + raw[1:]
    elif raw and raw[0] in ("download", "get", "pull", "sample"):
        raw = raw[1:]

    # Bare flags: bolt vods --json / --probe (treat as status)
    if raw and all(
        a in ("--json", "--probe", "--help", "-h")
        or a.startswith("--channel")
        for a in raw
    ) and any(a in ("--json", "--probe") for a in raw):
        sp = argparse.ArgumentParser(prog="bolt vods status")
        sp.add_argument("--json", action="store_true")
        sp.add_argument("--probe", action="store_true")
        sp.add_argument("--channel", default=None)
        sargs = sp.parse_args(raw)
        return _cli_status(as_json=sargs.json, probe=sargs.probe, channel=sargs.channel)

    parser = argparse.ArgumentParser(
        prog="bolt vods",
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
        help="Twitch User Access Token (channel owner). Only needed for the "
             "ffmpeg HLS fallback / subscriber-only VODs. Public archives "
             "download via yt-dlp without this.",
    )
    args = parser.parse_args(raw)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = args.metadata_file or (args.output_dir / "metadata.json")

    sample_seconds = args.sample_minutes * 60

    if args.channel:
        channel = args.channel.strip().lower()
    else:
        ts, err = TwitchStats.try_create()
        if ts is None:
            print(f"VOD unavailable: {err}", file=sys.stderr)
            return 1
        channel = ts.channel

    # Dry-run / list still OK without tools. Downloads need yt-dlp + working ffmpeg.
    yt = find_yt_dlp()
    ff = find_ffmpeg()
    if not args.dry_run:
        if not yt:
            print(
                "VOD unavailable: yt-dlp not found in venv or PATH "
                "(brew install yt-dlp / pip install yt-dlp). "
                "Check: bolt vods status",
                file=sys.stderr,
            )
            return 1
        if not ff:
            print(
                "VOD unavailable: no working ffmpeg. Homebrew's PATH ffmpeg "
                "often exists and then crashes (missing dylib). "
                "Install ffmpeg-full or set BOLT_FFMPEG. "
                "Check: bolt vods status",
                file=sys.stderr,
            )
            return 1
        print(f"downloader: yt-dlp ({yt})", flush=True)
        print(f"ffmpeg: {ff}", flush=True)

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
                meta["download_ok"] = True
                meta["skipped"] = True
                new_meta.append(meta)
                continue
            print(
                f"  [download] {v['id']} | "
                f"{v.get('title', '')[:50]} | "
                f"sample {start}s..{start + meta['sample_duration_seconds']}s",
                flush=True,
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
        if new_meta and ok_count == 0:
            print(
                "VOD unavailable: every sample failed. "
                "Public VODs need yt-dlp + a working ffmpeg (ffmpeg-full), "
                "not the raw usher HLS URL. Check: bolt vods status",
                file=sys.stderr,
            )
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
