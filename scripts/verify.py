#!/usr/bin/env python3
"""
Bolt setup verifier.

Run from anywhere with:
    python3 scripts/verify.py
"""

import importlib
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)


def mark(ok, label, detail=""):
    icon = "PASS" if ok else "FAIL"
    suffix = f" - {detail}" if detail else ""
    print(f"  [{icon}] {label}{suffix}")


def check_files():
    print("\nChecking project files...")
    required_files = [
        "bot.py",
        "launch.py",
        "config.json",
        "requirements.txt",
        "README.md",
        "Bolt_brain.md",
        "docs/guides/SETUP_GUIDE.md",
        "docs/PROJECT_STATUS.md",
    ]
    required_modules = [
        "modules/Watcher.py",
        "modules/Highlight_Detector.py",
        "modules/Clip_Generator.py",
        "modules/Subtitle_Generator.py",
        "modules/AI_Title_Generator.py",
        "modules/Title_Generator.py",
        "modules/Clip_Ranker.py",
        "modules/Clip_Deduplicator.py",
        "modules/TikTok_Publisher.py",
        "modules/OBS_Integration.py",
        "modules/Clip_Factory.py",
        "modules/Post_Queue.py",
        "modules/Peak_Hour_Notifier.py",
        "modules/Think_Learn_Decide.py",
        "modules/Multi_Publisher.py",
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
    for rel in [
        "recordings",
        "clips",
        "vertical_clips",
        "modules",
        "assets",
        "data",
        "logs",
        "memory",
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
        config = json.loads(Path("config.json").read_text(encoding="utf-8"))
    except Exception as exc:
        mark(False, "config.json", str(exc))
        return False

    required = [
        "game",
        "auto_format_tiktok",
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
