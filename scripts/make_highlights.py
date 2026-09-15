#!/usr/bin/env python3
"""
make_highlights.py — forwarder (was SHELL)
==========================================
Former file was an invalid indented Twitch Helix "create clip" paste
(IndentationError). Soft-fail product surface is now:

    bolt make-highlights status|list|run

This script forwards to the real local stitcher
``scripts/make_twitch_highlights.py`` (same engine as ``bolt highlights``).
Helix create-clip from VOD is not implemented here — use ``bolt vods`` for
Helix list/download.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

_ENGINE = Path(__file__).resolve().parent / "make_twitch_highlights.py"


def main() -> int:
    if not _ENGINE.is_file():
        print(
            f"Highlights unavailable: engine missing ({_ENGINE})",
            file=sys.stderr,
        )
        return 0
    sys.argv[0] = str(_ENGINE)
    try:
        runpy.run_path(str(_ENGINE), run_name="__main__")
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        return 1
    except Exception as exc:
        print(f"Highlights unavailable: forward failed ({exc})", file=sys.stderr)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
