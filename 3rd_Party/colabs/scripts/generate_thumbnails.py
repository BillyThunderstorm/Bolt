#!/usr/bin/env python3
"""
3rd_Party/colabs/scripts/generate_thumbnails.py — Generate JPG thumbnails for Bolt clips
=========================================================================================
Walks one or more clip directories (default: media/clips/, media/vertical_clips/),
extracts a representative frame from each .mp4 via ffmpeg, and writes a
matching .jpg alongside the source. Skips videos that already have a
fresh thumbnail (newer than the source) unless --force is given.

Frame selection strategy (configurable, defaults to "smart"):
  - smart: seek to 1/3 of duration. If the average luma of the extracted
    frame is below LUMA_MIN, try 1/2 then 2/3. Stops at the first frame
    that's not mostly-black. Falls back to frame 0 if all candidates fail.
  - first: always frame 0
  - middle: always duration/2

Usage:
  python3 3rd_Party/colabs/scripts/generate_thumbnails.py
  python3 3rd_Party/colabs/scripts/generate_thumbnails.py media/clips/ media/vertical_clips/
  python3 3rd_Party/colabs/scripts/generate_thumbnails.py --strategy first
  python3 3rd_Party/colabs/scripts/generate_thumbnails.py --force
  python3 3rd_Party/colabs/scripts/generate_thumbnails.py --dry-run

Library use:
  from generate_thumbnails import generate_thumbnail
  path = generate_thumbnail("media/clips/clip01.mp4")
"""

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

# Post-reorg: REPO_ROOT and standard subpaths. _paths.py also chdir's us
# to the repo root so any CWD-relative paths below still work.
# Make _paths importable in BOTH direct invocation and `from scripts import X`.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _paths import (  # noqa: E402
    REPO_ROOT, CLIPS_DIR, VERTICAL_CLIPS_DIR, DATA_DIR,
)


# --- Configuration --------------------------------------------------------

# Post-reorg: default directories moved to media/.
DEFAULT_DIRECTORIES = [str(CLIPS_DIR), str(VERTICAL_CLIPS_DIR)]
SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}
THUMBNAIL_EXTENSION = ".jpg"
DEFAULT_WIDTH = 1280
JPEG_QUALITY = 2  # ffmpeg q:v scale (lower = better, 2 is visually lossless)
LUMA_MIN = 24  # 0-255; below this we treat the frame as "mostly black"
SEEK_FRACTIONS = (1 / 3, 1 / 2, 2 / 3)  # tried in order for the smart strategy
# Post-reorg: state file now under Data/data/.
STATE_FILE = DATA_DIR / "thumbnail_state.json"

# External tools
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"


# --- Data classes ---------------------------------------------------------


@dataclass
class ThumbnailResult:
    source: str
    output: Optional[str]
    strategy: str
    width: int
    duration_sec: Optional[float] = None
    seek_seconds: Optional[float] = None
    skipped: bool = False
    error: Optional[str] = None


# --- Core helpers ---------------------------------------------------------


def probe_duration(video_path: Path) -> Optional[float]:
    """Return the clip duration in seconds, or None if probe fails."""
    try:
        result = subprocess.run(
            [
                FFPROBE,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except (TypeError, ValueError):
        return None


def _ffmpeg_extract_frame(
    video_path: Path, seek_seconds: float, output_path: Path, width: int
) -> bool:
    """Extract a single frame from `video_path` at `seek_seconds` to `output_path`.

    Returns True on success. ffmpeg's -ss before -i does a fast keyframe seek,
    which is fast and good enough for thumbnails.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [
                FFMPEG,
                "-y",
                "-loglevel",
                "error",
                "-ss",
                f"{seek_seconds:.3f}",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-q:v",
                str(JPEG_QUALITY),
                "-vf",
                f"scale={width}:-1",
                str(output_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and output_path.exists()


def _measure_average_luma(jpeg_path: Path) -> Optional[float]:
    """Return mean luma (0-255) of a JPEG, or None if measurement fails."""
    try:
        result = subprocess.run(
            [
                FFMPEG,
                "-loglevel",
                "error",
                "-i",
                str(jpeg_path),
                "-vf",
                "scale=1:1,format=gray",
                "-frames:v",
                "1",
                "-f",
                "rawvideo",
                "-",
            ],
            capture_output=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not result.stdout:
        return None
    # Single grayscale pixel; one byte.
    return float(result.stdout[0])


def _pick_seek_seconds(strategy: str, duration: float) -> float:
    """Translate a strategy name into a concrete seek offset in seconds."""
    if duration <= 0:
        return 0.0
    if strategy == "first":
        return 0.0
    if strategy == "middle":
        return duration / 2
    # smart and any unknown -> default to the first SEEK_FRACTIONS point
    return duration * SEEK_FRACTIONS[0]


def _thumbnail_path_for(video_path: Path) -> Path:
    return video_path.with_suffix(THUMBNAIL_EXTENSION)


def _needs_regeneration(
    video_path: Path, thumbnail_path: Path, force: bool
) -> bool:
    if force:
        return True
    if not thumbnail_path.exists():
        return True
    try:
        return thumbnail_path.stat().st_mtime < video_path.stat().st_mtime
    except FileNotFoundError:
        return True


# --- State persistence ----------------------------------------------------


def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


# --- Public API -----------------------------------------------------------


def generate_thumbnail(
    video_path: str | Path,
    output_path: Optional[str | Path] = None,
    strategy: str = "smart",
    width: int = DEFAULT_WIDTH,
    dry_run: bool = False,
) -> ThumbnailResult:
    """Generate a single thumbnail for `video_path`.

    Parameters
    ----------
    video_path: the source video (.mp4, .mov, .m4v, .webm)
    output_path: where to write the .jpg. Defaults to <stem>.jpg next to the video.
    strategy: "smart" | "first" | "middle"
    width: output width in pixels (height auto, aspect preserved)
    dry_run: if True, build the plan but don't call ffmpeg

    Returns a ThumbnailResult with the outcome.
    """
    src = Path(video_path)
    if not src.exists():
        return ThumbnailResult(
            source=str(src), output=None, strategy=strategy, width=width,
            error=f"source not found: {src}",
        )

    out = Path(output_path) if output_path else _thumbnail_path_for(src)
    duration = probe_duration(src)
    seek = _pick_seek_seconds(strategy, duration or 0)

    if dry_run:
        return ThumbnailResult(
            source=str(src),
            output=str(out),
            strategy=strategy,
            width=width,
            duration_sec=duration,
            seek_seconds=seek,
        )

    # Smart strategy: try SEEK_FRACTIONS until one isn't mostly black.
    if strategy == "smart" and duration:
        candidates = [duration * f for f in SEEK_FRACTIONS]
        for cand in candidates:
            if _ffmpeg_extract_frame(src, cand, out, width):
                luma = _measure_average_luma(out)
                if luma is None or luma >= LUMA_MIN:
                    return ThumbnailResult(
                        source=str(src),
                        output=str(out),
                        strategy=strategy,
                        width=width,
                        duration_sec=duration,
                        seek_seconds=cand,
                    )
        # All candidates were too dark; fall through to absolute frame 0.
        seek = 0.0

    ok = _ffmpeg_extract_frame(src, seek, out, width)
    return ThumbnailResult(
        source=str(src),
        output=str(out) if ok else None,
        strategy=strategy,
        width=width,
        duration_sec=duration,
        seek_seconds=seek,
        error=None if ok else "ffmpeg extraction failed",
    )


def generate_for_directory(
    directory: str | Path,
    strategy: str = "smart",
    width: int = DEFAULT_WIDTH,
    force: bool = False,
    dry_run: bool = False,
) -> list[ThumbnailResult]:
    """Walk `directory` and generate thumbnails for every supported video."""
    root = Path(directory)
    if not root.exists():
        return [
            ThumbnailResult(
                source=str(root),
                output=None,
                strategy=strategy,
                width=width,
                error=f"directory not found: {root}",
            )
        ]

    results: list[ThumbnailResult] = []
    for video in sorted(root.iterdir()):
        if video.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if not _needs_regeneration(video, _thumbnail_path_for(video), force):
            results.append(
                ThumbnailResult(
                    source=str(video),
                    output=str(_thumbnail_path_for(video)),
                    strategy=strategy,
                    width=width,
                    skipped=True,
                )
            )
            continue
        results.append(
            generate_thumbnail(
                video, strategy=strategy, width=width, dry_run=dry_run
            )
        )
    return results


# --- CLI ------------------------------------------------------------------


def _print_summary(results: list[ThumbnailResult], dry_run: bool) -> None:
    made = sum(1 for r in results if r.output and not r.skipped and not r.error)
    skipped = sum(1 for r in results if r.skipped)
    failed = sum(1 for r in results if r.error)
    label = "Would generate" if dry_run else "Generated"
    print(f"\n{label}: {made}")
    print(f"Skipped (already fresh): {skipped}")
    print(f"Failed: {failed}")
    print(f"Total videos inspected: {len(results)}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate JPG thumbnails for Bolt clips."
    )
    parser.add_argument(
        "directories",
        nargs="*",
        help=f"Directories to scan. Default: {' '.join(DEFAULT_DIRECTORIES)}",
    )
    parser.add_argument(
        "--strategy",
        choices=("smart", "first", "middle"),
        default="smart",
        help="Frame selection strategy (default: smart)",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=DEFAULT_WIDTH,
        help=f"Output width in pixels (default: {DEFAULT_WIDTH})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate even when an existing thumbnail is newer than the source",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan the work without invoking ffmpeg",
    )
    parser.add_argument(
        "--save-state",
        action="store_true",
        help="Persist a summary of results to data/thumbnail_state.json",
    )
    args = parser.parse_args()

    directories = args.directories or DEFAULT_DIRECTORIES
    all_results: list[ThumbnailResult] = []
    for path_str in directories:
        path = Path(path_str)
        if path.is_file():
            # Single-file mode.
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                print(f"  skip   {path} (unsupported extension)")
                continue
            if not _needs_regeneration(path, _thumbnail_path_for(path), args.force):
                all_results.append(
                    ThumbnailResult(
                        source=str(path),
                        output=str(_thumbnail_path_for(path)),
                        strategy=args.strategy,
                        width=args.width,
                        skipped=True,
                    )
                )
                continue
            all_results.append(
                generate_thumbnail(
                    path,
                    strategy=args.strategy,
                    width=args.width,
                    dry_run=args.dry_run,
                )
            )
        else:
            all_results.extend(
                generate_for_directory(
                    path,
                    strategy=args.strategy,
                    width=args.width,
                    force=args.force,
                    dry_run=args.dry_run,
                )
            )

    for r in all_results:
        if r.error:
            print(f"  ERROR  {r.source}: {r.error}")
        elif r.skipped:
            print(f"  skip   {r.source} -> {r.output}")
        elif r.output:
            seek = f"@ {r.seek_seconds:.1f}s" if r.seek_seconds is not None else ""
            print(f"  {'plan' if args.dry_run else 'made'}   {r.source} -> {r.output} {seek}")

    _print_summary(all_results, args.dry_run)

    if args.save_state:
        state = _load_state()
        state["last_run"] = {
            "timestamp": datetime.now().isoformat(),
            "strategy": args.strategy,
            "width": args.width,
            "dry_run": args.dry_run,
            "results": [asdict(r) for r in all_results],
        }
        _save_state(state)
        print(f"\nState saved to {STATE_FILE}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
