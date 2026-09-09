#!/usr/bin/env python3
"""
Bolt Site Data Writer
=====================
Generates site-data.json from Bolt's live data and optionally
commits it to GitHub so the Cloudflare Worker can serve it.

Usage:
  python3 scripts/site_data_writer.py          # Generate only
  python3 scripts/site_data_writer.py --push   # Generate + soft-fail git push
  python3 scripts/site_data_writer.py --path /custom/path/site-data.json
  python3 scripts/site_data_writer.py status [--json] [--probe]

Add to bot.py pipeline:
  from site_data_writer import write_site_data
  write_site_data(push=True)

Post-reorg (July 2026): the script was moved to
scripts/ but its internal REPO_ROOT math wasn't
updated. Now uses _paths.py so REPO_ROOT, DATA_DIR, CLIPS_DIR etc.
resolve against the new layout.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Post-reorg: REPO_ROOT and standard subpaths.
# Make _paths importable in BOTH direct invocation and `from scripts import X`.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _paths import (  # noqa: E402
    REPO_ROOT, DATA_DIR, CLIPS_DIR, DAILY_BRIEFINGS_DIR, CONFIG_FILE,
)


def _tiktok_key_ok() -> bool:
    try:
        from modules.TikTok_Auth import tiktok_api_enabled

        if not tiktok_api_enabled():
            return True
    except Exception:
        pass
    return bool(os.getenv("TIKTOK_ACCESS_TOKEN"))

# Backward-compatible aliases for code that uses `ROOT` / `PROJECT_ROOT`.
PROJECT_ROOT = REPO_ROOT
ROOT = REPO_ROOT


DATA_DIR = DATA_DIR  # alias kept for backwards compat with downstream code
CLIPS_DIR = CLIPS_DIR
VERTICAL_DIR = REPO_ROOT / "media" / "vertical_clips"
BRIEFINGS_DIR = DAILY_BRIEFINGS_DIR
QUEUE_FILE = DATA_DIR / "multi_platform_queue.json"
CONFIG_FILE = CONFIG_FILE  # Core/config.json
SITE_DATA_FILE = DATA_DIR / "site-data.json"

CT = timezone(timedelta(hours=-5))


def _load_json(path, default=None):
    if default is None:
        default = {}
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _latest_briefing():
    if not BRIEFINGS_DIR.exists():
        return {"date": datetime.now(CT).strftime("%A, %B %d, %Y"), "action_items": []}

    briefing_files = sorted(BRIEFINGS_DIR.glob("briefing_*.md"), reverse=True)
    if not briefing_files:
        briefing_files = sorted(BRIEFINGS_DIR.glob("*.md"), reverse=True)
    if not briefing_files:
        return {"date": datetime.now(CT).strftime("%A, %B %d, %Y"), "action_items": []}

    latest = briefing_files[0]
    content = latest.read_text()
    date_str = latest.stem.replace("briefing_", "").replace(".md", "")
    try:
        dt = datetime.strptime(date_str, "%Y%m%d")
        date_display = dt.strftime("%A, %B %d, %Y")
    except ValueError:
        date_display = date_str.replace("-", " ")

    action_items = []
    in_actions = False
    for line in content.splitlines():
        if "Action Items" in line:
            in_actions = True
            continue
        if in_actions:
            stripped = line.strip()
            if (
                stripped.startswith("#")
                or stripped.startswith("```")
                or stripped.startswith("---")
            ):
                in_actions = False
                continue
            if stripped and stripped[0].isdigit():
                item = stripped.lstrip("0123456789. ").strip()
                if item:
                    action_items.append(item)

    return {"date": date_display, "action_items": action_items}


def _clip_queue():
    data = _load_json(QUEUE_FILE, {"items": []})
    items = data.get("items", [])

    clips = []
    for item in items[:12]:
        platforms = item.get("platforms", [])
        tiktok = next((p for p in platforms if p.get("platform") == "tiktok"), None)
        title = "Untitled clip"
        if tiktok:
            caption = tiktok.get("caption", "")
            title = caption.split("\n")[0] if caption else "Untitled clip"
        clips.append(
            {
                "id": item.get("queue_id", ""),
                "created": item.get("created_at", ""),
                "title": title,
                "platforms": len(platforms),
                "status": tiktok.get("status", "queued") if tiktok else "queued",
            }
        )
    return clips


def _system_status():
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env")
    except ImportError:
        pass

    clips_count = 0
    if CLIPS_DIR.exists():
        clips_count = len(list(CLIPS_DIR.glob("*.mp4"))) + len(
            list(CLIPS_DIR.glob("*.mkv"))
        )

    vertical_count = 0
    if VERTICAL_DIR.exists():
        vertical_count = len(list(VERTICAL_DIR.glob("*.mp4")))

    queue_data = _load_json(QUEUE_FILE, {"items": []})
    queue_count = len(queue_data.get("items", []))

    config = _load_json(CONFIG_FILE, {})

    return {
        "clips_made": clips_count,
        "vertical_clips": vertical_count,
        "ready_to_post": queue_count,
        "recordings_processed": len(
            _load_json(DATA_DIR / "processed_recordings.json", [])
        ),
        "api_keys": {
            "twitch": bool(os.getenv("TWITCH_CLIENT_ID")),
            "obs": bool(os.getenv("OBS_PASSWORD")),
            "discord": bool(os.getenv("DISCORD_WEBHOOK_URL")),
            "tiktok": _tiktok_key_ok(),
        },
    }


def _peak_hours():
    config = _load_json(CONFIG_FILE, {})
    windows = config.get("peak_notifications", {}).get("windows", [])
    now = datetime.now(CT)
    current_hour = now.hour

    result = []
    for w in windows:
        start = w.get("start_hour", 0)
        end = w.get("end_hour", 0)
        label = w.get("label", "")
        active = start <= current_hour < end
        result.append(
            {
                "label": label,
                "start_hour": start,
                "end_hour": end,
                "start_display": f"{start % 12 or 12} {'AM' if start < 12 else 'PM'}",
                "end_display": f"{end % 12 or 12} {'AM' if end < 12 else 'PM'}",
                "active": active,
            }
        )
    return result


def write_site_data(push=False, output_path=None):
    """Generate site-data.json from Bolt's live data.

    Args:
        push: If True, git add + commit + push after writing.
        output_path: Override output path (default: Data/site-data.json)

    Returns:
        Path to the written file.
    """
    site_data = {
        "generated_at": datetime.now(CT).strftime("%Y-%m-%d %H:%M:%S"),
        "status": _system_status(),
        "queue": _clip_queue(),
        "briefing": _latest_briefing(),
        "peaks": _peak_hours(),
    }

    path = Path(output_path) if output_path else SITE_DATA_FILE
    path.write_text(json.dumps(site_data, indent=2) + "\n")
    print(f"  ⚡  Wrote site data to {path}")

    if push:
        try:
            subprocess.run(
                ["git", "add", str(path)],
                cwd=str(REPO_ROOT),
                check=True,
                capture_output=True,
                timeout=30,
            )
            msg = f"Update site data — {datetime.now(CT).strftime('%b %d, %H:%M')}"
            subprocess.run(
                ["git", "commit", "-m", msg],
                cwd=str(REPO_ROOT),
                check=True,
                capture_output=True,
                timeout=30,
            )
            subprocess.run(
                ["git", "push"],
                cwd=str(REPO_ROOT),
                check=True,
                capture_output=True,
                timeout=60,
            )
            print("  ⚡  Pushed to GitHub")
        except subprocess.TimeoutExpired:
            print(
                "  ⚠  Sites unavailable: git push timed out "
                "(local site-data.json was still written)"
            )
        except subprocess.CalledProcessError as e:
            err = e.stderr.decode() if e.stderr else str(e)
            print(f"  ⚠  Sites unavailable: Git push failed: {err}")
            print(
                "     Local write OK. Manual: git add Data/site-data.json "
                "&& git commit -m 'Update site data' && git push"
            )
        except OSError as e:
            print(f"  ⚠  Sites unavailable: git not available ({e})")

    return path


def status(*, probe: bool = False):
    """Write-path / git-remote readiness. Never raises."""
    info = {
        "ready": True,
        "site_data_path": str(SITE_DATA_FILE),
        "site_data_exists": SITE_DATA_FILE.exists(),
        "site_data_mtime": None,
        "git_remote": False,
        "hint": "",
    }
    try:
        if SITE_DATA_FILE.exists():
            ts = SITE_DATA_FILE.stat().st_mtime
            info["site_data_mtime"] = datetime.fromtimestamp(ts).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
    except OSError as exc:
        info["ready"] = False
        info["hint"] = f"Sites unavailable: cannot stat site-data ({exc})"
    try:
        r = subprocess.run(
            ["git", "remote"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=5,
        )
        info["git_remote"] = bool((r.stdout or "").strip()) and r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        info["git_remote"] = False

    if not info["hint"]:
        if info["git_remote"]:
            info["hint"] = (
                "Local write path OK; git remote present. "
                "Try: bolt site / bolt site --push"
            )
        else:
            info["hint"] = (
                "Sites unavailable: git remote not configured "
                "(local write still works; --push soft-fails)"
            )

    if probe:
        info["probe_ok"] = False
        info["probe_detail"] = ""
        try:
            probe_path = DATA_DIR / ".site-data-probe.json"
            write_site_data(push=False, output_path=str(probe_path))
            ok = probe_path.exists() and probe_path.stat().st_size > 0
            try:
                probe_path.unlink(missing_ok=True)
            except OSError:
                pass
            if ok:
                info["probe_ok"] = True
                info["probe_detail"] = f"ok — wrote probe under {DATA_DIR.name}/"
            else:
                info["probe_detail"] = "Sites unavailable: probe write empty"
                info["hint"] = info["probe_detail"]
                info["ready"] = False
        except Exception as exc:
            info["probe_detail"] = f"Sites unavailable: probe failed ({exc})"
            info["hint"] = info["probe_detail"]
            info["ready"] = False
    return info


def print_status(*, as_json: bool = False, probe: bool = False) -> int:
    """Print write-specific status. Always exit 0."""
    info = status(probe=probe)
    if as_json:
        print(json.dumps(info, indent=2, default=str))
        return 0
    print("\n  Site data writer")
    print("  " + "─" * 40)
    flag = "✓" if info.get("ready") else "○"
    print(f"  {flag}  ready: {bool(info.get('ready'))}")
    print(f"      path: {info.get('site_data_path')}")
    print(f"      exists: {info.get('site_data_exists')}")
    if info.get("site_data_mtime"):
        print(f"      mtime: {info.get('site_data_mtime')}")
    print(f"      git_remote: {info.get('git_remote')}")
    if info.get("hint"):
        print(f"      → {info['hint']}")
    if probe:
        pflag = "✓" if info.get("probe_ok") else "○"
        print(f"  {pflag}  probe: {info.get('probe_detail') or '(none)'}")
    print()
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] in ("-h", "--help", "help"):
        print(
            "site_data_writer — write Data/site-data.json\n"
            "  python scripts/site_data_writer.py\n"
            "  python scripts/site_data_writer.py --push\n"
            "  python scripts/site_data_writer.py status [--json] [--probe]\n"
            "  python scripts/site_data_writer.py --path /custom/site-data.json\n"
        )
        raise SystemExit(0)

    json_out = "--json" in args
    probe = "--probe" in args
    push = "--push" in args
    path_arg = None
    for i, arg in enumerate(args):
        if arg == "--path" and i + 1 < len(args):
            path_arg = args[i + 1]

    positionals = [a for a in args if not a.startswith("-")]
    if positionals and positionals[0].lower() in ("status", "check", "ready"):
        raise SystemExit(print_status(as_json=json_out, probe=probe))
    if not positionals and (json_out or probe) and not push and path_arg is None:
        raise SystemExit(print_status(as_json=json_out, probe=probe))

    write_site_data(push=push, output_path=path_arg)
