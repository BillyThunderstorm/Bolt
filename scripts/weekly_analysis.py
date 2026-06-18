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

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

PERFORMANCE_FILE = ROOT / "data" / "performance_outcomes.jsonl"
CLIPS_DIR = ROOT / "clips"
QUEUE_FILE = ROOT / "data" / "multi_platform_queue.json"

from scripts.send_notification import send_email, send_sms, send_briefing


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
    """Analyze posting time patterns."""
    # We don't have posted_at timestamps yet, but we can note when clips were created
    # For now, return a placeholder noting this needs posting timestamps
    return {
        "insight": "Track posting timestamps to analyze optimal times",
        "recommendation": "Add --posted-at flag when logging performance",
    }


def generate_insights(outcomes: list, queue_stats: dict) -> str:
    """Generate the weekly insights report."""
    week_ago = datetime.now() - timedelta(days=7)

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

    if total_clips_logged == 0:
        report += "1. **Start logging performance** — Bolt can't learn without data\n"
        report += "2. **Post consistently** — aim for 3-5 clips this week\n"
        report += "3. **Test different triggers** — kills, aces, multi-kills, etc.\n"
    else:
        if trigger_analysis:
            best = trigger_analysis[0]
            report += f"1. **Prioritize `{best['trigger']}` clips** — your best performer ({best['avg_views']:,.0f} avg views)\n"

        if queue_stats["total"] > 5:
            report += "2. **Clear the queue** — you have 5+ clips ready, post daily\n"
        elif queue_stats["total"] > 0:
            report += f"2. **Post your {queue_stats['total']} queued clips** — don't let them sit\n"
        else:
            report += "2. **Process new recordings** — your queue is empty\n"

        if success_rate < 30:
            report += "3. **Experiment with hooks** — low success rate suggests testing new approaches\n"
        elif success_rate >= 50:
            report += "3. **You're on a roll!** — keep the momentum going\n"

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
    report = generate_insights(outcomes, queue_stats)

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
