#!/usr/bin/env python3
"""
scripts/weekly_analysis.py — Bolt's Sunday Morning Insights
============================================================
Analyzes the past week's performance data and sends Billy actionable insights:
- Which trigger types performed best
- Optimal posting times
- Content patterns that work
- What to double down on next week

Runs automatically every Sunday at 9am via cron.
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PERFORMANCE_FILE = ROOT / "data" / "performance_outcomes.jsonl"
CLIPS_DIR = ROOT / "clips"
QUEUE_FILE = ROOT / "data" / "multi_platform_queue.json"

from scripts.send_notification import send_email, send_sms, send_briefing

# Memory-aware weekly insights config
WEEKLY_MEMORY_QUERIES = [
    ("creator vision focus areas content", "content_memory"),
    ("post performance trigger likes views", "performance_outcome"),
    ("recent decision actions clip ranking", "decision_event"),
    ("live streaming twitch peak hours audience", "content_memory"),
]
WEEKLY_MEMORY_LIMIT_PER_QUERY = 2


def _retrieve_weekly_memory() -> list:
    """Pull memory entries that should shape this week's insights.

    Uses a wider net than the daily briefing: four weekly-themed queries,
    capped per query, deduped by (source, title, summary), and ranked by
    retrieval score. Returns [] if memory retrieval is unavailable so the
    report still renders with the original recommendations.
    """
    try:
        from modules.Memory_Index import retrieve_memory
    except Exception:
        return []

    aggregated = []
    seen_keys = set()
    for query, _kind_hint in WEEKLY_MEMORY_QUERIES:
        try:
            hits = retrieve_memory(query, limit=WEEKLY_MEMORY_LIMIT_PER_QUERY)
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
    aggregated.sort(key=lambda x: x["score"], reverse=True)
    return aggregated[:8]


def _memory_to_recommendations(memory_hits: list) -> list:
    """Translate retrieved memory into concrete weekly recommendations.

    Returns a short, capped list (max 2) of memory-grounded suggestions so
    the recommendations section stays scannable. Rule-based on purpose so
    the report is free, deterministic, and auditable.
    """
    if not memory_hits:
        return []

    recs = []
    seen_themes = set()
    for hit in memory_hits:
        kind = hit.get("kind", "")
        title = hit.get("title", "")
        summary = hit.get("summary", "")
        # Dedup similar titles so we don't recommend the same creator lane twice.
        theme_key = title.split(":", 1)[0].strip().lower()
        if theme_key in seen_themes:
            continue
        seen_themes.add(theme_key)

        if kind == "performance_outcome":
            recs.append(
                f"Reflect last week's outcome ({title}) when planning next week's clips"
            )
        elif kind == "decision_event":
            recs.append(
                f"Carry forward recent decision: {title} — {summary[:100]}"
            )
        elif kind in ("content_memory", "markdown"):
            recs.append(f"Honor creator note: {title} — {summary[:100]}")
        else:
            recs.append(f"Memory flagged: {title}")

        if len(recs) >= 2:
            break
    return recs


def load_outcomes(days_back: int = 7) -> list:
    """Load performance outcomes from the last N days."""
    if not PERFORMANCE_FILE.exists():
        return []

    cutoff = datetime.now() - timedelta(days=days_back)
    outcomes = []

    with open(PERFORMANCE_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                ts = datetime.fromisoformat(data["timestamp"])
                if ts >= cutoff:
                    outcomes.append(data)
            except Exception:
                continue

    return outcomes


def load_queue_stats() -> dict:
    """Load current queue stats."""
    if not QUEUE_FILE.exists():
        return {"total": 0, "items": []}

    try:
        with open(QUEUE_FILE) as f:
            data = json.load(f)
            items = data.get("items", []) if isinstance(data, dict) else data
            return {"total": len(items), "items": items}
    except Exception:
        return {"total": 0, "items": []}


def analyze_triggers(outcomes: list) -> list:
    """Analyze which trigger types perform best."""
    trigger_stats = defaultdict(
        lambda: {"clips": 0, "views": 0, "likes": 0, "successes": 0}
    )

    for outcome in outcomes:
        triggers = outcome.get("trigger", "unknown").replace(",", " ").split()
        for trigger in triggers:
            trigger = trigger.strip().lower()
            if not trigger:
                continue
            trigger_stats[trigger]["clips"] += 1
            trigger_stats[trigger]["views"] += outcome.get("views", 0)
            trigger_stats[trigger]["likes"] += outcome.get("likes", 0)
            if outcome.get("success"):
                trigger_stats[trigger]["successes"] += 1

    # Calculate averages and sort by performance
    results = []
    for trigger, stats in trigger_stats.items():
        avg_views = stats["views"] / stats["clips"] if stats["clips"] > 0 else 0
        success_rate = stats["successes"] / stats["clips"] if stats["clips"] > 0 else 0
        results.append(
            {
                "trigger": trigger,
                "clips": stats["clips"],
                "avg_views": round(avg_views, 0),
                "success_rate": round(success_rate * 100, 0),
                "total_views": stats["views"],
            }
        )

    # Sort by avg_views descending
    results.sort(key=lambda x: x["avg_views"], reverse=True)
    return results


def analyze_timing(outcomes: list) -> dict:
    """Analyze posting time patterns from performance data."""
    timing_data = {}
    for o in outcomes:
        posted_at = o.get("posted_at") or o.get("logged_at")
        if not posted_at:
            continue
        # Try to extract hour from timestamp
        try:
            from datetime import datetime as _dt
            ts = o.get("posted_at") or o.get("logged_at")
            # Handle ISO format
            if "T" in str(ts):
                dt_obj = _dt.fromisoformat(str(ts).replace("Z", ""))
            else:
                dt_obj = _dt.strptime(str(ts), "%Y-%m-%d")
            hour = dt_obj.hour
            window = "morning" if 6 <= hour < 12 else "afternoon" if 12 <= hour < 17 else "evening" if 17 <= hour < 22 else "night"
            if window not in timing_data:
                timing_data[window] = {"views": 0, "posts": 0}
            timing_data[window]["views"] += o.get("views", 0)
            timing_data[window]["posts"] += 1
        except Exception:
            continue

    if not timing_data:
        return {
            "insight": "No posting timestamps available yet.",
            "recommendation": "Add --posted-at when logging performance to enable timing analysis.",
            "data": {},
        }

    # Calculate averages and find best window
    for window in timing_data:
        posts = timing_data[window]["posts"]
        timing_data[window]["avg_views"] = round(timing_data[window]["views"] / posts) if posts else 0

    best_window = max(timing_data, key=lambda w: timing_data[w].get("avg_views", 0))

    return {
        "insight": f"Best posting window: {best_window} ({timing_data[best_window]['avg_views']} avg views)",
        "recommendation": f"Prioritize {best_window} posting slots for maximum engagement.",
        "data": timing_data,
        "best_window": best_window,
    }


def generate_insights(outcomes: list, queue_stats: dict, memory_hits: list = None) -> str:
    """Generate the weekly insights report."""
    week_ago = datetime.now() - timedelta(days=7)
    if memory_hits is None:
        memory_hits = []  # default to empty if caller didn't pre-fetch

    # Basic stats
    total_clips_logged = len(outcomes)
    total_views = sum(o.get("views", 0) for o in outcomes)
    total_likes = sum(o.get("likes", 0) for o in outcomes)
    successes = sum(1 for o in outcomes if o.get("success"))
    success_rate = (
        (successes / total_clips_logged * 100) if total_clips_logged > 0 else 0
    )

    # Trigger analysis
    trigger_analysis = analyze_triggers(outcomes)

    # Build the report
    report = f"""# Bolt Weekly Insights
**Week of {week_ago.strftime("%b %d")} - {datetime.now().strftime("%b %d, %Y")}**

---

## Performance Summary

| Metric | This Week |
|--------|-----------|
| Clips Logged | {total_clips_logged} |
| Total Views | {total_views:,} |
| Total Likes | {total_likes:,} |
| Success Rate | {success_rate:.0f}% |

"""

    # Top performing triggers
    if trigger_analysis:
        report += "## 🎯 Top Performing Content Types\n\n"
        report += "| Trigger | Clips | Avg Views | Success Rate |\n"
        report += "|---------|-------|-----------|--------------|\n"
        for t in trigger_analysis[:5]:
            report += f"| {t['trigger']} | {t['clips']} | {t['avg_views']:,.0f} | {t['success_rate']:.0f}% |\n"

        # Generate insight
        if len(trigger_analysis) >= 2:
            best = trigger_analysis[0]
            report += f"\n**Insight:** `{best['trigger']}` clips average {best['avg_views']:,.0f} views"
            if best["success_rate"] >= 50:
                report += f" with {best['success_rate']:.0f}% success rate — **double down on this**.\n"
            else:
                report += " — keep testing variations.\n"
    else:
        report += "## 🎯 Content Performance\n\n"
        report += "*No clips logged this week. Start logging performance with:*\n"
        report += "```\npython3 scripts/log_clip_performance.py\n```\n\n"

    # Memory Highlights (new)
    report += """---

## 🧠 Memory Highlights

"""
    if memory_hits:
        for i, hit in enumerate(memory_hits, 1):
            source = hit["source"] or "memory"
            kind = hit["kind"] or "memory"
            title = hit["title"]
            summary = hit["summary"]
            report += f"{i}. **[{source}]** ({kind}) {title}\n"
            if summary:
                report += f"   - {summary[:240]}\n"
        report += "\n"
    else:
        report += (
            "*No relevant memory retrieved. Recommendations below are based on raw performance data only.*\n\n"
        )

    # Queue status
    report += f"""---

## Current Queue Status

**Clips ready to post:** {queue_stats["total"]}

"""

    if queue_stats["total"] > 0:
        report += "**Action:** Upload these clips this week, especially during peak hours (7-9pm).\n\n"

    # Recommendations
    report += """---

## Recommendations for Next Week

"""

    # Memory-grounded recommendation, only when memory is available.
    memory_recs = _memory_to_recommendations(memory_hits)
    for i, rec in enumerate(memory_recs, 1):
        report += f"{i}. {rec}\n"
    next_num = len(memory_recs) + 1

    if total_clips_logged == 0:
        report += f"{next_num}. **Start logging performance** — Bolt can't learn without data\n"
        next_num += 1
        report += f"{next_num}. **Post consistently** — aim for 3-5 clips this week\n"
        next_num += 1
        report += f"{next_num}. **Test different triggers** — kills, aces, multi-kills, etc.\n"
    else:
        if trigger_analysis:
            best = trigger_analysis[0]
            report += f"{next_num}. **Prioritize `{best['trigger']}` clips** — your best performer ({best['avg_views']:,.0f} avg views)\n"
            next_num += 1

        if queue_stats["total"] > 5:
            report += f"{next_num}. **Clear the queue** — you have 5+ clips ready, post daily\n"
            next_num += 1
        elif queue_stats["total"] > 0:
            report += f"{next_num}. **Post your {queue_stats['total']} queued clips** — don't let them sit\n"
            next_num += 1
        else:
            report += f"{next_num}. **Process new recordings** — your queue is empty\n"
            next_num += 1

        if success_rate < 30:
            report += f"{next_num}. **Experiment with hooks** — low success rate suggests testing new approaches\n"
        elif success_rate >= 50:
            report += f"{next_num}. **You're on a roll!** — keep the momentum going\n"

    report += f"""
---

*Generated by Bolt at {datetime.now().strftime("%I:%M %p")}*
*Run manually: `python3 scripts/weekly_analysis.py`*
"""

    return report


def main():
    """Generate and send weekly insights."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate weekly Bolt performance insights"
    )
    parser.add_argument(
        "--days", type=int, default=7, help="Analyze last N days (default: 7)"
    )
    parser.add_argument("--print", "-p", action="store_true", help="Print to stdout")
    parser.add_argument("--send", "-s", action="store_true", help="Send via email/SMS")
    args = parser.parse_args()

    outcomes = load_outcomes(args.days)
    queue_stats = load_queue_stats()
    memory_hits = _retrieve_weekly_memory()
    report = generate_insights(outcomes, queue_stats, memory_hits)

    if args.print:
        print(report)

    if args.send:
        # Send summary via SMS
        summary_lines = []
        if outcomes:
            total_views = sum(o.get("views", 0) for o in outcomes)
            successes = sum(1 for o in outcomes if o.get("success"))
            summary_lines.append(f"{len(outcomes)} clips logged")
            summary_lines.append(f"{total_views:,} total views")
            summary_lines.append(f"{successes}/{len(outcomes)} successful")
        else:
            summary_lines.append("No clips logged this week")
        summary_lines.append(f"{len(memory_hits)} memory hits")

        sms_text = "Bolt Weekly: " + " | ".join(summary_lines)

        sms_ok = send_sms(sms_text)
        email_ok = send_email("Bolt Weekly Insights", report)

        if sms_ok:
            print("Weekly SMS summary sent", file=sys.stderr)
        if email_ok:
            print("Weekly email report sent", file=sys.stderr)

    return report


if __name__ == "__main__":
    main()
