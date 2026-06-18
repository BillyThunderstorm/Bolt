#!/usr/bin/env python3
"""
Bolt Daily Briefing Generator
Generates a morning briefing with queue status, storage, and action items.
"""

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CLIPS_DIR = PROJECT_ROOT / "clips"
LOGS_DIR = PROJECT_ROOT / "logs"
OUTPUT_DIR = PROJECT_ROOT / "briefings" / "daily"


def get_queue_status() -> dict:
    """Load multi-platform queue status."""
    queue_file = DATA_DIR / "multi_platform_queue.json"
    if not queue_file.exists():
        return {"total": 0, "items": []}

    with open(queue_file) as f:
        data = json.load(f)

    items = data.get("items", [])
    return {
        "total": len(items),
        "items": items[:5],  # Show first 5
    }


def get_storage_status() -> dict:
    """Get storage metrics."""

    def get_dir_size(path: Path) -> tuple:
        if not path.exists():
            return 0, "0GB"
        try:
            # Use du -sk for kilobytes (more compatible)
            result = subprocess.run(
                ["du", "-sk", str(path)], capture_output=True, text=True
            )
            kb_val = int(result.stdout.split()[0])
            gb_val = kb_val / 1024 / 1024
            return gb_val, f"{gb_val:.2f}GB"
        except Exception as e:
            return 0, f"error ({e})"

    recordings_gb, recordings_str = get_dir_size(PROJECT_ROOT / "recordings")
    clips_gb, clips_str = get_dir_size(CLIPS_DIR)
    logs_gb, logs_str = get_dir_size(LOGS_DIR)

    # Disk usage
    try:
        result = subprocess.run(["df", "/"], capture_output=True, text=True)
        lines = result.stdout.strip().split("\n")
        if len(lines) > 1:
            parts = lines[1].split()
            disk_percent = parts[4].replace("%", "")
        else:
            disk_percent = "unknown"
    except Exception:
        disk_percent = "unknown"

    return {
        "recordings": recordings_str,
        "clips": clips_str,
        "logs": logs_str,
        "disk_percent": disk_percent,
    }


def get_recent_clips() -> list:
    """Get recently created clips."""
    if not CLIPS_DIR.exists():
        return []

    clips = []
    for f in CLIPS_DIR.glob("*.mp4"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            clips.append(
                {
                    "name": f.name,
                    "date": mtime.strftime("%Y-%m-%d"),
                    "size_mb": f.stat().st_size / 1024 / 1024,
                }
            )
        except Exception:
            pass

    # Sort by date, newest first
    clips.sort(key=lambda x: x["date"], reverse=True)
    return clips[:5]  # Show 5 most recent


def get_processed_recordings_count() -> int:
    """Count processed recordings."""
    recordings_file = DATA_DIR / "processed_recordings.json"
    if not recordings_file.exists():
        return 0

    with open(recordings_file) as f:
        data = json.load(f)

    return len(data) if isinstance(data, list) else 0


def generate_briefing() -> tuple[str, str]:
    """Generate the full briefing markdown and a clean SMS summary."""
    today = datetime.now()
    date_str = today.strftime("%A, %B %d, %Y")

    queue = get_queue_status()
    storage = get_storage_status()
    recent_clips = get_recent_clips()
    processed_count = get_processed_recordings_count()

    # One-line SMS facts (no markdown table junk)
    sms_facts = [
        f"{queue['total']} clips ready",
        f"disk {storage['disk_percent']}%",
        f"{processed_count} recordings processed",
    ]
    briefing_sms_summary = " | ".join(sms_facts)

    briefing = f"""# Bolt Daily Briefing

**{date_str}**

|---

## Queue Status

**Clips ready to post:** {queue["total"]}

"""

    if queue["total"] > 0:
        briefing += "### Ready for Upload\n\n"
        for i, item in enumerate(queue["items"], 1):
            created = item.get("created_at", "unknown")[:10]
            platforms = len(item.get("platforms", []))
            briefing += f"{i}. Created: {created} | Platforms: {platforms}\n"
        briefing += "\n"
    else:
        briefing += "*No clips currently in queue.*\n\n"

    briefing += f"""---

## Storage Status

| Directory | Size |
|-----------|------|
| Recordings | {storage["recordings"]} |
| Clips | {storage["clips"]} |
| Logs | {storage["logs"]} |
| **Disk Usage** | **{storage["disk_percent"]}%** |

"""

    if int(storage["disk_percent"]) > 80:
        briefing += (
            "⚠️ **Storage warning:** Disk usage above 80%. Consider running cleanup.\n\n"
        )
    elif int(storage["disk_percent"]) > 90:
        briefing += "🔴 **Storage critical:** Disk usage above 90%. Immediate cleanup recommended.\n\n"

    briefing += f"""---

## Recent Clips

"""

    if recent_clips:
        briefing += "| Clip | Date | Size |\n"
        briefing += "|------|------|------|\n"
        for clip in recent_clips:
            briefing += f"| {clip['name'][:40]}... | {clip['date']} | {clip['size_mb']:.1f}MB |\n"
    else:
        briefing += "*No clips found.*\n"

    briefing += f"""
---

## Processing Stats

- **Recordings processed:** {processed_count}

---

## Action Items For Today

"""

    # Dynamic action items based on state
    actions = []

    if queue["total"] > 0:
        actions.append(
            f"Upload {queue['total']} clip(s) from queue to TikTok/Shorts/Reels"
        )

    if int(storage["disk_percent"]) > 80:
        actions.append(
            "Run storage cleanup: `python3 scripts/maintenance/storage_optimization.sh`"
        )

    actions.append("Check for new recordings to process")
    actions.append("Review clip performance and log results")

    for i, action in enumerate(actions[:5], 1):
        briefing += f"{i}. {action}\n"

    briefing += f"""
---

## Quick Commands

```bash
# Process new recording
python3 launch.py process

# View queue
python3 -m modules.Post_Queue --list

# Check storage
python3 scripts/clip_deduplicator.py

# Run performance baseline
python3 scripts/performance_baseline.py
```

---

*Generated by Bolt at {today.strftime("%I:%M %p")}*
"""

    return briefing, briefing_sms_summary


def main():
    """Main entry point."""
    import argparse
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from send_notification import send_briefing

    parser = argparse.ArgumentParser(description="Generate Bolt Daily Briefing")
    parser.add_argument("--output", "-o", type=str, help="Output file path")
    parser.add_argument(
        "--print", "-p", action="store_true", help="Print to stdout only"
    )
    parser.add_argument(
        "--send", "-s", action="store_true", help="Send to Billy via email/SMS"
    )
    args = parser.parse_args()

    briefing, sms_summary = generate_briefing()

    if args.print or not args.output:
        print(briefing)

    if args.output:
        output_path = Path(args.output)
    else:
        # Default: save to briefings/daily/latest.md
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_DIR / f"briefing_{datetime.now().strftime('%Y%m%d')}.md"

    if args.output or not args.print:
        with open(output_path, "w") as f:
            f.write(briefing)
        print(f"\nBriefing saved to: {output_path}", file=__import__("sys").stderr)

    # Send notification if requested
    if args.send:
        send_briefing(briefing, sms_summary)
        print("Briefing sent to Billy", file=__import__("sys").stderr)


if __name__ == "__main__":
    main()
