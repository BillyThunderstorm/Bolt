#!/usr/bin/env python3
"""
Bolt setup verifier.

Run from anywhere with:
    python3 scripts/verify.py

Post-reorg (July 2026): the verifier is rooted via the `scripts/_paths.py`
helper, which computes REPO_ROOT and adds the right directories to sys.path.
All required files / directories / module paths below use the new layout.
"""

import importlib
import json
import os
import sys
from pathlib import Path

# Single source of truth for the repo root and standard subpaths.
# Make _paths importable in BOTH direct invocation and `from scripts import X`.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _paths import (  # noqa: E402
    REPO_ROOT,
    CORE_DIR,
    DATA_DIR,
    DOCS_DIR,
    LOGS_DIR,
    MEDIA_DIR,
    MODULES_DIR,
    ARCHIVE_DIR,
)

# Backward-compatible aliases for code that uses `ROOT` / `PROJECT_ROOT`.
PROJECT_ROOT = REPO_ROOT
ROOT = REPO_ROOT



def mark(ok, label, detail=""):
    icon = "PASS" if ok else "FAIL"
    suffix = f" - {detail}" if detail else ""
    print(f"  [{icon}] {label}{suffix}")


def check_files():
    print("\nChecking project files...")
    # Post-reorg: files moved to Core/, Docs/, etc. _paths.py chdir's us to
    # the repo root, so these relative paths resolve from there.
    required_files = [
        "Core/bot.py",
        "Core/src/launch.py",
        "Core/config.json",
        "Docs/requirements.txt",
        "Core/bolt_brain.md",
        "Docs/guides/SETUP_GUIDE.md",
        "Docs/PROJECT_STATUS.md",
    ]
    required_modules = [
        "Core/modules/Watcher.py",
        "Core/modules/Highlight_Detector.py",
        "Core/modules/Clip_Generator.py",
        "Core/modules/Subtitle_Generator.py",
        "Core/modules/AI_Title_Generator.py",
        "Core/modules/Title_Generator.py",
        "Core/modules/Clip_Ranker.py",
        "Core/modules/Clip_Deduplicator.py",
        "Core/modules/TikTok_Publisher.py",
        "Core/modules/OBS_Integration.py",
        "Core/modules/Clip_Factory.py",
        "Core/modules/Post_Queue.py",
        "Core/modules/Peak_Hour_Notifier.py",
        "Core/modules/Think_Learn_Decide.py",
        "Core/modules/Multi_Publisher.py",
    ]
    missing = []
    for rel in required_files + required_modules:
        exists = Path(rel).exists()
        mark(exists, rel)
        if not exists:
            missing.append(rel)
    return not missing


def check_directories():
    print("\nChecking directories...")
    all_ok = True
    # Post-reorg: media/ is the live tree (clips/vertical_clips), Data/archive
    # holds the (archived) recordings, Data/data holds persistent state.
    for rel in [
        "Data/archive/recordings",
        "media/clips",
        "media/vertical_clips",
        "Core/modules",
        "App/assets",
        "Data/data",
        "logs",
        "Data/content",
    ]:
        path = Path(rel)
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
        ok = path.is_dir()
        mark(ok, rel + "/")
        all_ok = all_ok and ok
    return all_ok


def check_config():
    print("\nChecking configuration...")
    try:
        # Post-reorg: config moved to Core/config.json.
        config = json.loads(Path("Core/config.json").read_text(encoding="utf-8"))
    except Exception as exc:
        mark(False, "Core/config.json", str(exc))
        return False

    required = [
        "game",
        "highlight_sensitivity",
        "max_clips_per_session",
    ]
    ok = True
    for key in required:
        present = key in config
        mark(present, key, str(config.get(key)) if present else "missing")
        ok = ok and present

    score = config.get("min_post_score", config.get("min_clip_score"))
    mark(
        score is not None,
        "clip score floor",
        str(score) if score is not None else "missing min_post_score/min_clip_score",
    )
    return ok and score is not None


def load_env_file():
    env = {}
    path = Path(".env")
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def check_env():
    print("\nChecking environment file...")
    env = load_env_file()
    if not env:
        mark(False, ".env", "missing or empty")
        return False

    placeholders = {
        "",
        "your_key_here",
        "your_client_id_here",
        "your_client_secret_here",
        "your_obs_password_here",
        "your_discord_webhook_here",
    }
    optional = [
        ("OBS_PASSWORD", "needed when OBS integration is enabled"),
        ("TWITCH_BOT_TOKEN", "enables Twitch chat bot"),
        ("TWITCH_BOT_NAME", "enables Twitch chat bot"),
        ("TWITCH_CLIENT_ID", "enables Twitch stats/API"),
        ("TWITCH_CLIENT_SECRET", "enables Twitch stats/API"),
        ("DISCORD_WEBHOOK_URL", "enables peak-hour phone/Discord alerts"),
    ]
    mark(True, ".env", "present")
    for key, detail in optional:
        value = env.get(key, "")
        configured = value not in placeholders
        mark(configured, key, "configured" if configured else detail)
    return True


def check_imports():
    print("\nTesting module imports...")
    modules = [
        "modules.notifier",
        "modules.Watcher",
        "modules.Highlight_Detector",
        "modules.Clip_Generator",
        "modules.Subtitle_Generator",
        "modules.Clip_Factory",
        "modules.AI_Title_Generator",
        "modules.Title_Generator",
        "modules.Clip_Ranker",
        "modules.TikTok_Publisher",
        "modules.OBS_Integration",
        "modules.Think_Learn_Decide",
        "modules.Multi_Publisher",
    ]
    ok = True
    for name in modules:
        try:
            importlib.import_module(name)
            mark(True, name)
        except Exception as exc:
            mark(False, name, str(exc))
            ok = False
    return ok


def main():
    print("Bolt verification")
    print("=" * 50)
    checks = [
        ("Files", check_files),
        ("Directories", check_directories),
        ("Configuration", check_config),
        ("Environment", check_env),
        ("Module imports", check_imports),
    ]
    results = {name: func() for name, func in checks}
    print("\nSummary")
    print("=" * 50)
    for name, passed in results.items():
        print(f"{'PASS' if passed else 'WARN'}: {name}")
    if all(results.values()):
        print("\nBolt basics look good. Next: python3 launch.py --no-checklist")
        return 0
    print("\nSome checks still need attention. See FAIL lines above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
