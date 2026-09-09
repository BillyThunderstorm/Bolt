#!/usr/bin/env python3
"""
Nexus CLI

By default uses free local Ollama only.
Add ``--paid`` to allow the xAI Grok API for this one call
(also enabled globally with NEXUS_ALLOW_PAID=true).
Gemini is not used unless NEXUS_USE_GEMINI=true.

Soft-fail + status live in ``modules.Nexus_Creator``::

    bolt nexus status
    bolt nexus status --json
    bolt nexus status --probe
    bolt nexus "your question" [--paid]
"""

import sys
from pathlib import Path

# Ensure Core is importable
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "Core"))

from modules.Nexus_Creator import main

if __name__ == "__main__":
    raise SystemExit(main())
