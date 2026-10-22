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
    "setup.py", "requirements.txt", "Makefile", "pyproject.toml", "uv.lock",
    ".python-version",
    # Website numbers mirror (site_data_writer writes it for the bolt-api
    # Worker) and the legacy Jekyll CI config.
    "site-data.json", "_config.yml",
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
    "dist", "archive", "vod_samples", "Sites", "bolt_cli",
    # macOS / vendored noise that should never trigger a finding
    ".venv", ".git", ".vscode", "node_modules", "__pycache__",
]


def is_root_allowed(name: str) -> bool:
    """Return True if `name` is on the explicit allow-list of files
    that are allowed to live at the repo root."""
    return name in ROOT_ALLOWED


# Plain-words description of everything that is SUPPOSED to sit at the
# repo root. `bolt layout run --all` prints these so William can see what
# each top-level item is for. Anything at the root that is not here, not
# on ROOT_ALLOWED and not in KNOWN_TOP_LEVEL_DIRS is listed as "look at".
ROOT_EXPLAINED = {
    "Core": "Bolt's code (bot, modules, config).",
    "App": "Menu bar app and the checkup page.",
    "Data": "Bolt's data: queue, memory, configs, backups, tests.",
    "Docs": "Guides and status docs (READINESS, BOLT_NOW).",
    "3rd_Party": "Outside code Bolt borrows (colabs, vendored tools).",
    "media": "Recordings, clips, vertical clips and reels.",
    "scripts": "Helper scripts the bolt command and cron run.",
    "bin": "The bolt command itself (bin/bolt).",
    "logs": "Log files.",
    "dist": "Built Bolt.app.",
    "vod_samples": "Sample VODs for testing.",
    "Sites": "Website source (Cloudflare Pages pages + the bolt-api Worker).",
    "bolt_cli": "Small shim so `bolt` works after `uv sync` (pyproject).",
    "tests": "Tests.", "memory": "Memory files.", "api": "API code.",
    "archive": "Archived old files.",
    "README.md": "Project readme.", "AGENTS.md": "Notes for AI helpers.",
    "LICENSE": "License file.",
    "pyproject.toml": "Python project settings.", "uv.lock": "Package versions lock (uv).",
    "site-data.json": "Copy of Data/site-data.json that the website Worker reads (written by site_data_writer) - leave it.",
    "_config.yml": "Config for the old GitHub Jekyll check - leave it.",
    "setup.py": "Old install script.", "requirements.txt": "Old package list.",
    "launch.py": "Old launcher kept at the root on purpose.",
    "Bolt_Personality.txt": "Bolt's personality notes.",
    "Bolt_Personality.pages": "Bolt's personality notes (Pages).",
}

# Hidden items at the root that are normal (tools, git, env files).
HIDDEN_OK = {
    ".git", ".github", ".gitignore", ".gitattributes", ".DS_Store",
    ".venv", ".vscode", ".pytest_cache", ".ruff_cache", ".mypy_cache",
    ".python-version", ".env", ".env.local", ".env.example", ".example.env",
    ".cursor", ".idea",
}

# Hidden items worth a note, as (glob, note, fix). Notes are never
# counted as problems - they are just things William may want to know.
HIDDEN_NOTES = [
    (
        ".env*.bak*",
        "Backup copy of your keys file (made during an earlier settings change). Git ignores it, so it is safe, but it holds API keys.",
        "Keep it, or move it into Data/backups/ if you want the top folder tidier.",
    ),
    (
        ".tmp.drive*",
        "Temporary folder made by the Google Drive app.",
        "Leave it alone; Google Drive manages it.",
    ),
]
