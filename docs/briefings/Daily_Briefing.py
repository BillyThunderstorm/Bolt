import json
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).parent
BRIEFING_DIR = ROOT / "briefings" / "daily"


def _section(title: str, body: str) -> str:
    body = body.strip() or "No signal available."
    return f"## {title}\n{body}"


def _calendar_context() -> str:
    try:
        from modules.Google_Calender import format_for_briefing

        return format_for_briefing()
    except Exception as exc:
        return f"Calendar unavailable: {exc}"


def _gmail_context() -> str:
    try:
        from modules.Gmail_Briefing import format_for_briefing

        return format_for_briefing()
    except Exception as exc:
        return f"Gmail unavailable: {exc}"


def _memory_context() -> str:
    try:
        from modules.Memory_Index import format_retrieved_context, retrieve_memory

        results = retrieve_memory(
            "daily briefing creator priorities Bolt project content creation product testing AI learning",
            limit=4,
            kinds=["markdown", "decision", "outcome", "queue"],
        )
        return format_retrieved_context(results)
    except Exception as exc:
        return f"Bolt memory unavailable: {exc}"


def _action_items(calendar: str, gmail: str, memory: str) -> list[str]:
    actions = [
        "Review the calendar blocks and protect the highest-value work window.",
        "Check any real inbox item surfaced above before opening the full inbox.",
        "Move one Bolt or creator-system task forward and capture the result in memory.",
    ]

    if "Nothing scheduled today" in calendar:
        actions[0] = "Pick one focused Bolt/content block and put it on the calendar."
    if "No important unread" in gmail or "Gmail unavailable" in gmail:
        actions[1] = (
            "Do a quick manual Gmail scan for real people, account alerts, products, or creator work."
        )
    if "(no relevant memory found)" in memory or "unavailable" in memory.lower():
        actions[2] = (
            "Add one useful note to Bolt memory so tomorrow's briefing has stronger context."
        )

    return actions


def generate_briefing() -> Path:
    """Create today's local Bolt briefing and return its path."""
    today = date.today()
    day_label = datetime.now().strftime("%A, %B %-d")
    calendar = _calendar_context()
    gmail = _gmail_context()
    memory = _memory_context()
    actions = _action_items(calendar, gmail, memory)

    briefing = "\n\n".join(
        [
            f"# Bolt Daily Briefing - {day_label}",
            _section("On The Calendar Today", calendar),
            _section("Inbox - What Actually Needs Attention", gmail),
            _section("Bolt & Content Creation - Today's Focus", memory),
            "## Reminder Checklist\n" + "\n".join(f"- [ ] {item}" for item in actions),
            "## Shortcut Payload\n"
            "Use the checklist above for Reminders, then notify: "
            f'"Bolt briefing ready: {len(actions)} actions for today."',
            "",
        ]
    )

    filename = BRIEFING_DIR / f"{today}.md"
    latest = BRIEFING_DIR / "latest.md"
    tasks_txt = BRIEFING_DIR / "latest_tasks.txt"
    tasks_json = BRIEFING_DIR / "latest_tasks.json"
    filename.parent.mkdir(parents=True, exist_ok=True)

    with open(filename, "w", encoding="utf-8") as f:
        f.write(briefing)
    with open(latest, "w", encoding="utf-8") as f:
        f.write(briefing)
    with open(tasks_txt, "w", encoding="utf-8") as f:
        f.write("\n".join(actions) + "\n")
    with open(tasks_json, "w", encoding="utf-8") as f:
        json.dump(
            {
                "date": str(today),
                "briefing": str(latest),
                "tasks": actions,
            },
            f,
            indent=2,
        )

    try:
        display_path = filename.relative_to(ROOT)
    except ValueError:
        display_path = filename
    print(f"Created {display_path}")
    return filename


if __name__ == "__main__":
    generate_briefing()
