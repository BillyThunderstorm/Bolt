#!/usr/bin/env python3
"""
scripts/nexus_advice.py — Quick CLI for Nexus Creator
======================================================
Ask Nexus for content strategy advice.

Usage:
  python3 scripts/nexus_advice.py "How should I title my Hades 2 clips?"
  python3 scripts/nexus_advice.py --next
  python3 scripts/nexus_advice.py --caption "2026-07-01_clip01.mp4" --desc "Epic boss fight" -p tiktok
  python3 scripts/nexus_advice.py "skincare review strategy" --context "Posted 17 product review clips, getting low views"
"""

import sys
from pathlib import Path

# Make project root importable
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.Nexus_Creator import main

if __name__ == "__main__":
    main()