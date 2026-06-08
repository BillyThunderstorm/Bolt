#!/usr/bin/env python3
"""
Bolt Site Data Writer
=====================
Generates site-data.json from Bolt's live data and optionally
commits it to GitHub so the Cloudflare Worker can serve it.

Usage:
  python3 scripts/site_data_writer.py          # Generate only
  python3 scripts/site_data_writer.py --push   # Generate + git push
  python3 scripts/site_data_writer.py --path /custom/path/site-data.json

Add to bot.py pipeline:
  from scripts.site_data_writer import write_site_data
  write_site_data(push=True)
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Bolt project root
BOLT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = BOLT_ROOT / "data"
CLIPS_DIR = BOLT_ROOT / "clips"
VERTICAL_DIR = BOLT_ROOT / "vertical_clips"
BRIEFINGS_DIR = BOLT_ROOT / "briefings" / "daily"
QUEUE_FILE = DATA_DIR / "multi_platform_queue.json"
CONFIG_FILE = BOLT_ROOT / "config.json"
SITE_DATA_FILE = BOLT_ROOT / "site-data.json"

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
            if stripped.startswith("#") or stripped.startswith("```") or stripped.startswith("---"):
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
        clips.append({
            "id": item.get("queue_id", ""),
            "created": item.get("created_at", ""),
            "title": title,
            "platforms": len(platforms),
            "status": tiktok.get("status", "queued") if tiktok else "queued",
        })
    return clips


def _system_status():
    try:
        from dotenv import load_dotenv
        load_dotenv(BOLT_ROOT / ".env")
    except ImportError:
        pass

    clips_count = 0
    if CLIPS_DIR.exists():
        clips_count = len(list(CLIPS_DIR.glob("*.mp4"))) + len(list(CLIPS_DIR.glob("*.mkv")))

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
        "recordings_processed": len(_load_json(DATA_DIR / "processed_recordings.json", [])),
        "api_keys": {
            "twitch": bool(os.getenv("TWITCH_CLIENT_ID")),
            "obs": bool(os.getenv("OBS_PASSWORD")),
            "discord": bool(os.getenv("DISCORD_WEBHOOK_URL")),
            "tiktok": bool(os.getenv("TIKTOK_ACCESS_TOKEN")),
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
        result.append({
            "label": label,
            "start_hour": start,
            "end_hour": end,
            "start_display": f"{start % 12 or 12} {'AM' if start < 12 else 'PM'}",
            "end_display": f"{end % 12 or 12} {'AM' if end < 12 else 'PM'}",
            "active": active,
        })
    return result


def write_site_data(push=False, output_path=None):
    """Generate site-data.json from Bolt's live data.

    Args:
        push: If True, git add + commit + push after writing.
        output_path: Override output path (default: BOLT_ROOT/site-data.json)

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
            subprocess.run(["git", "add", str(path)], cwd=str(BOLT_ROOT), check=True, capture_output=True)
            msg = f"Update site data — {datetime.now(CT).strftime('%b %d, %H:%M')}"
            subprocess.run(["git", "commit", "-m", msg], cwd=str(BOLT_ROOT), check=True, capture_output=True)
            subprocess.run(["git", "push"], cwd=str(BOLT_ROOT), check=True, capture_output=True)
            print(f"  ⚡  Pushed to GitHub")
        except subprocess.CalledProcessError as e:
            print(f"  ⚠  Git push failed: {e.stderr.decode() if e.stderr else e}")
            print(f"     You may need to commit manually: git add site-data.json && git commit -m 'Update site data' && git push")

    return path


if __name__ == "__main__":
    args = sys.argv[1:]
    push = "--push" in args
    path_arg = None
    for i, arg in enumerate(args):
        if arg == "--path" and i + 1 < len(args):
            path_arg = args[i + 1]

    write_site_data(push=push, output_path=path_arg)
