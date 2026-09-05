"""
Bolt scripts/_layout_rules.py
=============================

Single source of truth for "where do files belong in the post-reorg
Bolt repo?" The post-July-2026 color-coded folder reorg moved source
into `Core/`, data into `Data/`, media into `media/`, docs into
`Docs/`, and vendored code into `3rd_Party/`. New files dropped at
the repo root usually mean someone forgot to put them somewhere
intentional. `scripts/check_layout.py` consults the rules in this
module to flag misplaced files.

RULES format
------------

Each rule is a tuple of `(matcher, expected, reason)`:

  * `matcher`   - a glob-style string (e.g. "*.mp4", "Multi_Publisher.py",
                  "*.rtf").  Matched against the basename of a file
                  sitting at the repo root.
  * `expected`  - the relative path where that file SHOULD live, e.g.
                  "Core/modules/Multi_Publisher.py" or
                  "media/Recordings/".  Used purely for the report.
  * `reason`    - one short human sentence explaining why, shown in
                  the report so the user can judge it themselves.

A basename matching multiple rules produces one finding per match.

To add a new rule: append to `RULES`.  Run `bolt layout` to verify.

Safety
------

This file is a *report-only* config. `check_layout.py` never moves
files. To turn findings into actual moves, write an explicit migration
script and review it before running it (see the prior reorg incident
in Bolt memory).
"""

from __future__ import annotations

from typing import List, Tuple

# (matcher, expected_path, reason)
RULES: List[Tuple[str, str, str]] = [
    # Source modules that were re-homed into Core/modules/ but copies
    # sometimes drift back to the repo root.
    (
        "Multi_Publisher.py",
        "Core/modules/Multi_Publisher.py",
        "Publisher logic belongs in Core/modules/ alongside the other pipeline modules.",
    ),

    (
        "101_hello_tinker.py",
        "3rd_Party/colabs/101_hello_tinker.py",
        "Colab/sandbox scripts belong in 3rd_Party/colabs/.",
    ),

    # Bulk media / state files that should never sit at the repo root.
    (
        "clip_history.json",
        "Data/clip_history.json",
        "Clip history is a data file, not a project artifact.",
    ),
    (
        "seen_clips.json",
        "Data/seen_clips.json",
        "Dedup state belongs under Data/.",
    ),
    (
        "structure.txt",
        "Docs/structure.txt",
        "A repo tree dump belongs in Docs/, not at the repo root.",
    ),
    (
        "think_learn_decide.md",
        "Docs/think_learn_decide.md",
        "Planning notes belong in Docs/.",
    ),

    # Catch-all for loose rich-text and one-off scratch files that
    # drift to the root from TextEdit / downloads.
    (
        "*.rtf",
        "Docs/scratch/",
        "RTF scratch files belong in Docs/scratch/ (or should be deleted).",
    ),

    # Media at the repo root instead of media/.
    (
        "*.mp4",
        "media/clips/",
        "Generated clips live under media/clips/.",
    ),
    (
        "*.mov",
        "media/Recordings/",
        "Source recordings live under media/Recordings/.",
    ),
    (
        "*.mp3",
        "media/Recordings/",
        "Audio recordings live under media/Recordings/.",
    ),
    (
        "*.wav",
        "media/Recordings/",
        "Audio recordings live under media/Recordings/.",
    ),
]


# Always allowed at the repo root, regardless of glob rules. This is
# the canonical "do not flag these" list - keep it small and obvious.
ROOT_ALLOWED: List[str] = [
    # Tooling / build
    "setup.py", "requirements.txt", "Makefile", "pyproject.toml",
    # Top-level docs
    "README.md", "AGENTS.md", "LICENSE",
    # Env (gitignored, but if they're committed somewhere we want to see them)
    ".env", ".env.example", ".env.local", ".example.env",
    # Hidden
    ".gitignore", ".gitattributes", ".DS_Store",
    # Personality
    "Bolt_Personality.txt", "Bolt_Personality.pages",
    # Top-level script entrypoint and a few legacy scripts the user
    # has explicitly left at the root.
    "launch.py", "_lazy_imports.py", "Scratchpad:",
]


# Directories that are part of the canonical layout - never flag the
# folder itself or its contents. (check_layout.py currently only
# inspects the repo root, so this list mainly serves as documentation
# of the expected structure and as a guard if we extend the scanner
# later.)
KNOWN_TOP_LEVEL_DIRS: List[str] = [
    "Core", "App", "Data", "Docs", "3rd_Party", "media",
    "scripts", "bin", "tests", "logs", "memory", "api",
    "dist", "archive", "vod_samples",
    # macOS / vendored noise that should never trigger a finding
    ".venv", ".git", ".vscode", "node_modules", "__pycache__",
]


def is_root_allowed(name: str) -> bool:
    """Return True if `name` is on the explicit allow-list of files
    that are allowed to live at the repo root."""
    return name in ROOT_ALLOWED
