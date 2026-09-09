#!/usr/bin/env python3
"""Compatibility shim for legacy docs that still say ``python3 Core/src/launch.py``.

The real launcher lives at ``Core/launch.py`` (also ``bolt launch`` / ``bolt setup``).
This file forwards argv so old paths keep working instead of failing on an empty folder.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

_CORE = Path(__file__).resolve().parent.parent  # Core/
_REAL = _CORE / "launch.py"


def main() -> int:
    if not _REAL.is_file():
        print("Bolt launcher missing: Core/launch.py", file=sys.stderr)
        print("Use: bolt launch   or   bolt setup", file=sys.stderr)
        return 1
    # Preserve caller argv; point argv[0] at the real script for clearer traces.
    sys.argv[0] = str(_REAL)
    runpy.run_path(str(_REAL), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
