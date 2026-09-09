"""Resolve a working ffmpeg / ffprobe binary.

Homebrew's PATH ``ffmpeg`` can fail to launch (broken dylib, missing
libfreetype). Clip cuts, highlight audio extract, and vertical encode all
need a binary that actually starts. Prefer ffmpeg-full, then the first
candidate that responds to ``-version``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from functools import lru_cache
from typing import Optional

_FFMPEG_CANDIDATES = (
    "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
    "/opt/homebrew/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
)


def _works(path: str) -> bool:
    if not path or not os.path.isfile(path) or not os.access(path, os.X_OK):
        return False
    try:
        result = subprocess.run(
            [path, "-version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _pair(ffmpeg_path: str) -> str:
    """ffprobe lives next to ffmpeg in Homebrew prefixes."""
    sibling = os.path.join(os.path.dirname(ffmpeg_path), "ffprobe")
    if _works(sibling):
        return sibling
    which = shutil.which("ffprobe")
    if which and _works(which):
        return which
    return sibling if os.path.isfile(sibling) else "ffprobe"


@lru_cache(maxsize=1)
def ffmpeg_bin() -> str:
    env = (os.environ.get("BOLT_FFMPEG") or "").strip()
    if env and _works(env):
        return env
    for candidate in _FFMPEG_CANDIDATES:
        if _works(candidate):
            return candidate
    which = shutil.which("ffmpeg")
    if which and _works(which):
        return which
    return which or "ffmpeg"


@lru_cache(maxsize=1)
def ffprobe_bin() -> str:
    env = (os.environ.get("BOLT_FFPROBE") or "").strip()
    if env and _works(env):
        return env
    return _pair(ffmpeg_bin())


def probe_video(path: str) -> Optional[dict]:
    """Return {width, height, fps} for the first video stream, or None."""
    try:
        result = subprocess.run(
            [
                ffprobe_bin(),
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,r_frame_rate",
                "-of",
                "csv=p=0",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    parts = (result.stdout or "").strip().split(",")
    if len(parts) < 2:
        return None
    try:
        width = int(parts[0])
        height = int(parts[1])
    except ValueError:
        return None
    fps = None
    if len(parts) >= 3 and "/" in parts[2]:
        num, den = parts[2].split("/", 1)
        try:
            fps = float(num) / float(den) if float(den) else None
        except ValueError:
            fps = None
    return {"width": width, "height": height, "fps": fps}
