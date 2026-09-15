#!/usr/bin/env python3
"""
BOLT SYSTEM VERIFICATION & HEALTH CHECK (lightweight)
=======================================================
Former SHELL: pre-reorg CWD-relative paths (config.json / bot.py / clips /
vertical_clips / data at repo root) so every check failed after the Core /
Data / media split.

Prefer the READY audit:

    bolt doctor

This script is the PARTIAL soft-fail surface behind ``bolt health`` — a
quick post-reorg path + import smoke check. Soft-fail prefix via CLI:
``Health check unavailable:``.

Usage:
  python3 scripts/health_check.py
  bolt health run
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from _paths import (  # noqa: E402
    REPO_ROOT,
    CORE_DIR,
    MODULES_DIR,
    DATA_DIR,
    MEDIA_DIR,
    CLIPS_DIR,
    VERTICAL_CLIPS_DIR,
    RECORDINGS_DIR,
    MEMORY_DIR,
    MEMORY_HOT_FILE,
    CONFIG_FILE,
    BOT_FILE,
    BOLT_BRAIN_FILE,
    LOGS_DIR,
)

LAUNCH_FILE = CORE_DIR / "launch.py"
ENV_FILE = REPO_ROOT / ".env"


def run_health_check() -> int:
    """Run lightweight post-reorg health check. Returns 0/1."""
    print("\n" + "=" * 75)
    print(f" BOLT HEALTH CHECK — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 75 + "\n")
    print(f"  repo: {REPO_ROOT}")
    print("  note: prefer `bolt doctor` for the full live/mocked/stale audit\n")

    checks_passed = 0
    checks_failed = 0
    checks_warning = 0

    # ========== CHECK 1: Files ==========
    print("[1] REQUIRED FILES (post-reorg)")
    print("-" * 75)

    required_files = {
        CONFIG_FILE: "Configuration",
        BOLT_BRAIN_FILE: "Creator profile",
        ENV_FILE: "Environment variables",
        BOT_FILE: "Main entry point",
        LAUNCH_FILE: "Launcher script",
        MEMORY_HOT_FILE: "Hot memory",
    }

    for path, desc in required_files.items():
        rel = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
        if path.exists():
            size = path.stat().st_size
            print(f"  ✓ {str(rel):40} ({desc:25}) {size:,} bytes")
            checks_passed += 1
        else:
            # .env / bolt_brain / MEMORY often optional for clip-only
            if path in (ENV_FILE, BOLT_BRAIN_FILE, MEMORY_HOT_FILE):
                print(f"  ⚠ {str(rel):40} ({desc:25}) MISSING (optional)")
                checks_warning += 1
            else:
                print(f"  ✗ {str(rel):40} ({desc:25}) MISSING")
                checks_failed += 1

    # ========== CHECK 2: Directories ==========
    print("\n[2] REQUIRED DIRECTORIES (post-reorg)")
    print("-" * 75)

    required_dirs = {
        MODULES_DIR: "Pipeline modules",
        RECORDINGS_DIR: "Input recordings",
        CLIPS_DIR: "Generated clips",
        VERTICAL_CLIPS_DIR: "TikTok-formatted clips",
        DATA_DIR: "Cache and rankings",
        MEMORY_DIR: "Persistent memory",
        LOGS_DIR: "Logs",
        MEDIA_DIR: "Media root",
        CORE_DIR: "Core source",
    }

    for path, desc in required_dirs.items():
        rel = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
        if path.exists() and path.is_dir():
            try:
                count = len(list(path.iterdir()))
            except Exception:
                count = 0
            print(f"  ✓ {str(rel):40} ({desc:25}) {count:4} items")
            checks_passed += 1
        else:
            if path in (RECORDINGS_DIR, CLIPS_DIR, VERTICAL_CLIPS_DIR, MEMORY_DIR, LOGS_DIR):
                print(f"  ⚠ {str(rel):40} ({desc:25}) MISSING (creatable)")
                checks_warning += 1
            else:
                print(f"  ✗ {str(rel):40} ({desc:25}) MISSING")
                checks_failed += 1

    # ========== CHECK 3: Python Modules ==========
    print("\n[3] PYTHON DEPENDENCIES")
    print("-" * 75)

    # required-ish for clip factory vs optional extras
    python_deps = {
        "requests": ("HTTP client", False),
        "dotenv": ("Environment loading", False),
        "librosa": ("Audio analysis", True),
        "moviepy": ("Video editing", True),
        "cv2": ("Video processing", True),
        "openai": ("OpenAI API", True),
        "whisper": ("Speech recognition", True),
        "twitchio": ("Twitch bot", True),
    }

    for module, (desc, optional) in python_deps.items():
        try:
            __import__(module)
            print(f"  ✓ {module:20} ({desc:25})")
            checks_passed += 1
        except ImportError:
            if optional:
                print(f"  ⚠ {module:20} ({desc:25}) NOT INSTALLED (optional)")
                checks_warning += 1
            else:
                print(f"  ✗ {module:20} ({desc:25}) NOT INSTALLED")
                checks_failed += 1

    # ========== CHECK 4: Bolt Modules ==========
    print("\n[4] BOLT PIPELINE MODULES")
    print("-" * 75)

    if str(CORE_DIR) not in sys.path:
        sys.path.insert(0, str(CORE_DIR))

    bolt_modules = [
        "modules.Config_Loader",
        "modules.Highlight_Detector",
        "modules.Clip_Generator",
        "modules.Title_Generator",
        "modules.Subtitle_Generator",
        "modules.Clip_Ranker",
        "modules.Clip_Factory",
        "modules.Think_Learn_Decide",
        "modules.Bolt_Chat",
        "modules.Bolt_Memory",
        "modules.LLM_Handler",
    ]

    for module in bolt_modules:
        try:
            __import__(module)
            print(f"  ✓ {module}")
            checks_passed += 1
        except Exception as e:
            print(f"  ✗ {module}")
            print(f"    → {str(e)[:60]}")
            checks_failed += 1

    # ========== CHECK 5: Configuration ==========
    print("\n[5] CONFIGURATION")
    print("-" * 75)

    try:
        from modules.Config_Loader import load_config

        config = load_config()
        print("  ✓ Core/config.json loads successfully")
        print(f"    • Game: {config.get('game')}")
        print(f"    • Min score: {config.get('min_post_score')}")
        print(f"    • Max clips/session: {config.get('max_clips_per_session')}")
        checks_passed += 1
    except Exception as e:
        print(f"  ✗ Core/config.json error: {e}")
        checks_failed += 1

    # ========== CHECK 6: Environment ==========
    print("\n[6] ENVIRONMENT VARIABLES")
    print("-" * 75)

    env_checks = {
        "OPENAI_API_KEY": "LLM API key (optional — Ollama/templates work)",
        "TWITCH_CHANNEL": "Twitch channel (optional for chat)",
        "TWITCH_BOT_TOKEN": "Twitch bot OAuth (optional for chat)",
        "XAI_API_KEY": "Grok / Nexus paid path (optional)",
    }

    for key, desc in env_checks.items():
        val = os.getenv(key, "").strip()
        if val and not val.startswith("sk_your") and "YOUR_" not in val.upper():
            print(f"  ✓ {key:25} Set")
            checks_passed += 1
        else:
            print(f"  ⚠ {key:25} Not set → {desc}")
            checks_warning += 1

    # ========== CHECK 7: API Connectivity (no live call) ==========
    print("\n[7] API CLIENTS (no live network call)")
    print("-" * 75)

    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if openai_key and not openai_key.startswith("sk_your"):
        print("  ✓ OPENAI_API_KEY configured")
        try:
            from openai import OpenAI

            OpenAI(api_key=openai_key)
            print("  ✓ OpenAI client initialized successfully")
            checks_passed += 1
        except Exception as e:
            print(f"  ⚠ OpenAI client error: {e}")
            checks_warning += 1
    else:
        print("  • OPENAI_API_KEY not set (LLM features use Ollama/templates)")

    # ========== SUMMARY ==========
    print("\n" + "=" * 75)
    print(" HEALTH CHECK SUMMARY")
    print("=" * 75)

    total_checks = checks_passed + checks_failed + checks_warning
    print("\nResults:")
    print(f"  ✓ Passed:   {checks_passed}/{total_checks}")
    print(f"  ⚠ Warnings: {checks_warning}/{total_checks}")
    print(f"  ✗ Failed:   {checks_failed}/{total_checks}")

    if checks_failed == 0 and checks_warning <= 3:
        print("\n✓ SYSTEM READY (lightweight)")
        print("\nPrefer full audit: bolt doctor")
        print("Start Bolt:          bolt launch")
        return 0
    if checks_failed == 0:
        print("\n⚠ SYSTEM OPERATIONAL (with warnings)")
        print("\nPrefer full audit: bolt doctor")
        print("Start Bolt:          bolt launch")
        return 0

    print("\n✗ SYSTEM NOT READY")
    print("\nFix failed checks, or run: bolt doctor")
    return 1


if __name__ == "__main__":
    exit_code = run_health_check()
    print("\n" + "=" * 75 + "\n")
    sys.exit(exit_code)
