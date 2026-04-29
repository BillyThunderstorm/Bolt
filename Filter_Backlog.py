#!/usr/bin/env python3
"""
Compatibility wrapper.

Use scripts/Filter_Backlog.py as the canonical backlog filter script.
"""

import runpy
from pathlib import Path


if __name__ == "__main__":
    target = Path(__file__).parent / "scripts" / "Filter_Backlog.py"
    runpy.run_path(str(target), run_name="__main__")
