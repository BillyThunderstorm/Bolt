#!/usr/bin/env python3
"""
Apple_Reminders.py — write Bolt briefings into Reminders.app
============================================================
Primary delivery channel from user_profile.json (list name: "Bolt").

Uses JXA via osascript so we do not need EventKit bindings. First run
may prompt for Reminders access; after that it is silent.

Public API:
  ensure_list(name)
  create_reminder(title, body="", *, due=None, list_name="Bolt", alert=True)
  replace_today_briefing(actions, *, briefing_path=None, summary="", list_name="Bolt")
  parse_action_items(briefing_text)
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional

DEFAULT_LIST = "Bolt"
BRIEFING_MARKER = "Bolt briefing"
ACTION_PREFIX = "Bolt · "


def _env_list_name() -> str:
    return (os.getenv("BOLT_REMINDERS_LIST") or DEFAULT_LIST).strip() or DEFAULT_LIST


def parse_action_items(briefing_text: str) -> list[str]:
    """Pull numbered items from the 'Action Items For Today' section."""
    if not briefing_text:
        return []
    lines = briefing_text.splitlines()
    capturing = False
    items: list[str] = []
    for raw in lines:
        line = raw.strip()
        if line.startswith("## "):
            capturing = line.lower().startswith("## action items")
            continue
        if not capturing:
            continue
        if line.startswith("---"):
            break
        if not line:
            continue
        # "1. Do the thing" or "- Do the thing"
        if line[0].isdigit() and "." in line[:4]:
            items.append(line.split(".", 1)[1].strip())
        elif line.startswith(("- ", "* ")):
            items.append(line[2:].strip())
    return [i for i in items if i]


def _jxa(script: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _escape_js(value: str) -> str:
    return json.dumps("" if value is None else str(value))


def ensure_list(name: str = DEFAULT_LIST) -> bool:
    """Create the Reminders list if it is missing. Returns True on success."""
    list_name = name or _env_list_name()
    script = f"""
const app = Application("Reminders");
app.includeStandardAdditions = true;
const name = {_escape_js(list_name)};
const existing = app.lists.whose({{name: name}})();
if (existing.length === 0) {{
    const list = app.List({{name: name}});
    app.lists.push(list);
}}
name;
"""
    try:
        result = _jxa(script)
        return result.returncode == 0
    except Exception:
        return False


def create_reminder(
    title: str,
    body: str = "",
    *,
    due: Optional[datetime] = None,
    list_name: str = DEFAULT_LIST,
    alert: bool = True,
) -> bool:
    """Add one reminder. Best-effort; returns False if Reminders is unavailable."""
    title = (title or "").strip()
    if not title:
        return False
    list_name = list_name or _env_list_name()
    when = due or datetime.now()
    # JXA Date is constructed from a parseable local string.
    due_str = when.strftime("%Y-%m-%dT%H:%M:%S")
    remind_js = "true" if alert else "false"
    script = f"""
const app = Application("Reminders");
const listName = {_escape_js(list_name)};
let lists = app.lists.whose({{name: listName}})();
if (lists.length === 0) {{
    const created = app.List({{name: listName}});
    app.lists.push(created);
    lists = app.lists.whose({{name: listName}})();
}}
const list = lists[0];
const due = new Date({_escape_js(due_str)});
const props = {{
    name: {_escape_js(title[:200])},
    body: {_escape_js(body[:2000])},
    dueDate: due
}};
if ({remind_js}) {{
    props.remindMeDate = due;
}}
list.reminders.push(app.Reminder(props));
"ok";
"""
    try:
        result = _jxa(script)
        return result.returncode == 0
    except Exception:
        return False


def _complete_today_briefing_reminders(list_name: str) -> int:
    """Mark today's previous Bolt briefing reminders complete so re-sends replace them."""
    script = f"""
const app = Application("Reminders");
const listName = {_escape_js(list_name)};
const lists = app.lists.whose({{name: listName}})();
if (lists.length === 0) {{
    0;
}} else {{
    const list = lists[0];
    const today = new Date();
    const y = today.getFullYear();
    const m = today.getMonth();
    const d = today.getDate();
    const marker = {_escape_js(BRIEFING_MARKER)};
    const prefix = {_escape_js(ACTION_PREFIX)};
    let n = 0;
    const rem = list.reminders();
    for (let i = 0; i < rem.length; i++) {{
        const r = rem[i];
        if (r.completed()) continue;
        const name = String(r.name() || "");
        if (name.indexOf(marker) !== 0 && name.indexOf(prefix) !== 0) continue;
        let due = null;
        try {{ due = r.dueDate(); }} catch (e) {{ due = null; }}
        let sameDay = false;
        if (due) {{
            sameDay = due.getFullYear() === y && due.getMonth() === m && due.getDate() === d;
        }} else {{
            sameDay = true;
        }}
        if (sameDay) {{
            r.completed = true;
            n += 1;
        }}
    }}
    n;
}}
"""
    try:
        result = _jxa(script)
        if result.returncode != 0:
            return 0
        return int((result.stdout or "0").strip() or "0")
    except Exception:
        return 0


def replace_today_briefing(
    actions: Iterable[str],
    *,
    briefing_path: Optional[Path] = None,
    summary: str = "",
    list_name: str = DEFAULT_LIST,
    due: Optional[datetime] = None,
    alert: bool = True,
) -> dict:
    """
    Replace today's Bolt briefing reminders with a summary + one item per action.

    Returns a result dict; never raises. Missing Reminders access is reported
    in `error` so callers can fall back to another channel.
    """
    list_name = list_name or _env_list_name()
    items = [str(a).strip() for a in (actions or []) if str(a).strip()]
    when = due or datetime.now()
    path = Path(briefing_path) if briefing_path else None
    path_line = str(path) if path else ""
    file_url = path.resolve().as_uri() if path and path.exists() else path_line

    result = {
        "ok": False,
        "list": list_name,
        "summary": False,
        "actions_created": 0,
        "replaced": 0,
        "error": "",
    }

    if not ensure_list(list_name):
        result["error"] = "Reminders list could not be created (permission?)"
        return result

    result["replaced"] = _complete_today_briefing_reminders(list_name)

    numbered = "\n".join(f"{i}. {item}" for i, item in enumerate(items, 1)) or "(no action items)"
    body_parts = [
        summary.strip() if summary else "Daily briefing is ready.",
        "",
        numbered,
        "",
        "Open the briefing to review or revise:",
        file_url or path_line,
        "",
        "Queue review: bolt day --decide",
        "Stats: bolt stats",
    ]
    summary_title = f"{BRIEFING_MARKER} ready — {len(items)} action{'s' if len(items) != 1 else ''}"
    result["summary"] = create_reminder(
        summary_title,
        "\n".join(body_parts).strip(),
        due=when,
        list_name=list_name,
        alert=alert,
    )
    # Stagger action due times by 1 minute so Reminders stays readable.
    created = 0
    for i, item in enumerate(items[:8]):
        action_due = when + timedelta(minutes=i + 1)
        ok = create_reminder(
            f"{ACTION_PREFIX}{item}"[:200],
            f"From today's briefing.\n{file_url or path_line}\nRevise or complete, then check this off.",
            due=action_due,
            list_name=list_name,
            alert=False,
        )
        if ok:
            created += 1
    result["actions_created"] = created
    result["ok"] = bool(result["summary"] or created)
    if not result["ok"]:
        result["error"] = result["error"] or "Reminders write failed"
    return result


if __name__ == "__main__":
    import sys

    sample = [
        "Review the queue (`bolt day --decide`)",
        "Check Apple Reminders for today's briefing",
    ]
    out = replace_today_briefing(
        sample,
        summary="Test briefing from Apple_Reminders.py",
        briefing_path=Path("Docs/briefings/daily/latest_morning.md"),
    )
    print(json.dumps(out, indent=2))
    sys.exit(0 if out.get("ok") else 1)
