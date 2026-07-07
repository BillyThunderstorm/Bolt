#!/usr/bin/env python3
"""
Bolt Daily Briefing Generator
Generates a morning briefing with queue status, storage, and action items.

Post-reorg (July 2026): uses _paths.py to resolve REPO_ROOT and the
standard subpaths. Output now lands in Docs/briefings/daily/ (was
briefings/daily/ at the repo root).
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Single source of truth for paths (REPO_ROOT, DATA_DIR, CLIPS_DIR, etc.).
# _paths.py also cd's us to the repo root, so any CWD-relative paths the
# rest of this script uses still work as if invoked from there.
# Make _paths importable in BOTH direct invocation and `from scripts import X`.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _paths import (  # noqa: E402
    REPO_ROOT, DATA_DIR, CLIPS_DIR, LOGS_DIR, DAILY_BRIEFINGS_DIR,
)

# Memory-aware briefing config
MEMORY_QUERIES = [
    ("recent clip performance", "performance_outcome"),
    ("recent decisions actions", "decision_event"),
    ("current focus creator lane", "content_memory"),
]
MEMORY_RETRIEVE_LIMIT = 3


def _retrieve_briefing_memory() -> list:
    """Pull memory entries that should shape today's briefing.

    Returns a list of dicts: {title, source, kind, summary, score}.
    Best-effort: if the memory index is unavailable or retrieval fails,
    returns an empty list so the briefing still renders with fallback items.
    """
    try:
        # Local import to avoid hard-failing the briefing if memory stack breaks.
        from modules.Memory_Index import retrieve_memory
    except Exception:
        return []

    aggregated = []
    seen_keys = set()
    for query, _kind_hint in MEMORY_QUERIES:
        try:
            hits = retrieve_memory(query, limit=MEMORY_RETRIEVE_LIMIT)
        except Exception:
            continue
        for hit in hits:
            key = (hit.get("source"), hit.get("title"), hit.get("summary"))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            aggregated.append(
                {
                    "title": hit.get("title") or "Memory",
                    "source": hit.get("source") or "",
                    "kind": hit.get("kind") or "",
                    "summary": hit.get("summary") or hit.get("text") or "",
                    "score": hit.get("score", 0),
                }
            )
    # Sort strongest-first, cap so the briefing stays scannable.
    aggregated.sort(key=lambda x: x["score"], reverse=True)
    return aggregated[:6]


def _memory_to_action_items(memory_hits: list) -> list:
    """Translate memory hits into concrete action items when possible.

    Falls back to a generic item only when no memory is available. We keep
    this rule-based (not LLM) so the briefing stays free, deterministic,
    and auditable. The first performance_outcome hit becomes the canonical
    "Review last clip performance" reminder so we don't double-list it.
    """
    actions = []
    performance_review_added = False
    for hit in memory_hits:
        kind = hit.get("kind", "")
        summary = hit.get("summary", "")
        title = hit.get("title", "")
        if kind == "performance_outcome" and not performance_review_added:
            actions.append("Review last clip performance and log outcomes")
            performance_review_added = True
            continue
        if kind == "decision_event":
            actions.append(
                f"Follow up on recent decision: {title} — {summary[:120]}"
            )
        elif kind == "content_memory" or kind == "markdown":
            actions.append(f"Creator note active: {title} — {summary[:120]}")
        else:
            actions.append(f"Memory flagged: {title} — {summary[:120]}")
        if len(actions) >= 3:
            break
    return actions


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

    # Post-reorg: live recordings/ was deleted (2026-07-07). Show 0
    # rather than failing on a missing folder.
    from _paths import RECORDINGS_DIR as _recordings_dir
    recordings_gb, recordings_str = get_dir_size(_recordings_dir)
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
    memory_hits = _retrieve_briefing_memory()

    # One-line SMS facts (no markdown table junk)
    sms_facts = [
        f"{queue['total']} clips ready",
        f"disk {storage['disk_percent']}%",
        f"{processed_count} recordings processed",
        f"{len(memory_hits)} memory notes",
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

## Memory Notes

"""
    if memory_hits:
        for i, hit in enumerate(memory_hits, 1):
            source = hit["source"] or "memory"
            briefing += f"{i}. **[{source}]** {hit['title']}\n"
            if hit["summary"]:
                briefing += f"   - {hit['summary'][:240]}\n"
        briefing += "\n"
    else:
        briefing += (
            "*No relevant memory retrieved. The briefing is using generic items.*\n\n"
        )

    briefing += """---

## Action Items For Today

"""

    # Prefer memory-grounded actions, fall back to generic ones.
    actions = _memory_to_action_items(memory_hits)

    if not actions:
        # Fallback only if memory retrieval returned nothing.
        actions = []

    if queue["total"] > 0:
        actions.append(
            f"Upload {queue['total']} clip(s) from queue to TikTok/Shorts/Reels"
        )

    if int(storage["disk_percent"]) > 80:
        actions.append(
            "Run storage cleanup: `python3 scripts/maintenance/storage_optimization.sh`"
        )

    # Only add the universal performance reminder if the memory-driven one
    # wasn't already added (dedup against memory-grounded actions above).
    if "Review last clip performance and log outcomes" not in actions:
        actions.append("Review clip performance and log results")
    actions.append("Check for new recordings to process")

    for i, action in enumerate(actions[:7], 1):
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
        # Refresh calendar feeds so the email can attach today's ICS.
        calendar_attachments: list = []
        try:
            from generate_calendar import build_all_feeds

            written = build_all_feeds()
            for name, path in written.items():
                if path and path.exists():
                    calendar_attachments.append((name, path))
            if calendar_attachments:
                names = ", ".join(n for n, _ in calendar_attachments)
                print(f"Calendar feeds refreshed: {names}", file=__import__("sys").stderr)
        except Exception as exc:
            print(f"Calendar feed refresh skipped: {exc}", file=__import__("sys").stderr)

        send_briefing(briefing, sms_summary, attachments=calendar_attachments)
        print("Briefing sent to Billy", file=__import__("sys").stderr)


if __name__ == "__main__":
    main()
