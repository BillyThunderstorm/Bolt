#!/usr/bin/env python3
"""Plan timeline, what's due, and the morning-briefing line.

The timeline chart is replaced between ``bolt:timeline:start`` and
``bolt:timeline:end``. The rest of the note stays. A missing vault adds nothing.
"""

from __future__ import annotations

import re
from datetime import date, time, timedelta
from typing import List, Optional, Tuple

from modules.Vault_Dates import When, now_ct, speak_when
from modules.Vault_Store import (
    ACTIVITY_REL,
    BOARD_REL,
    CALENDAR_INDEX_REL,
    TASKS_REL,
    TIMELINE_END,
    TIMELINE_REL,
    TIMELINE_START,
    VaultNote,
    VaultStore,
    timeline_template,
    vault_exists,
)

_DUE = re.compile(
    r"^(?:please\s+)?what(?:'s| is) due(?: (?:today|tomorrow|this week))?[.!?]*$",
    re.I,
)
_SKIP_RELS = {BOARD_REL, TIMELINE_REL, ACTIVITY_REL, CALENDAR_INDEX_REL}
_MARKER = re.compile(
    rf"%% {re.escape(TIMELINE_START)} %%.*?%% {re.escape(TIMELINE_END)} %%",
    re.S,
)


def try_overview(text: str) -> Optional[str]:
    soft = re.sub(r"\s+", " ", (text or "").strip())
    if not _DUE.match(soft):
        return None
    if not vault_exists():
        return "I can't see the vault yet, so I don't know what's due."
    scope = "today"
    if re.search(r"\btomorrow\b", soft, re.I):
        scope = "tomorrow"
    elif re.search(r"\bthis week\b", soft, re.I):
        scope = "week"
    line = due_line(scope)
    if line:
        return line
    label = {"today": "today", "tomorrow": "tomorrow", "week": "this week"}[scope]
    return f"Nothing is due {label}."


def due_line(scope: str = "today") -> str:
    """One sentence for the briefing or for chat. Empty when nothing is due."""
    if not vault_exists():
        return ""
    store = VaultStore()
    if not store.root.is_dir():
        return ""
    start, end = _window(scope)
    items = _due_items(store, start, end)
    if not items:
        return ""
    label = {"today": "today", "tomorrow": "tomorrow", "week": "this week"}.get(scope, "today")
    bits = [f"{title}, {kind}, {speak_when(when)}" for kind, title, when in items]
    return f"Due {label}: " + "; ".join(bits) + "."


def refresh_inside(store: VaultStore) -> None:
    """Rewrite the mermaid block. Caller is already inside a vault change."""
    if store._txn is None:
        return
    path = store.root / TIMELINE_REL
    current = path.read_text(encoding="utf-8") if path.is_file() else timeline_template()
    updated = render_timeline(current, _chart_rows(store))
    if updated != current:
        store.write_text(TIMELINE_REL, updated)


def render_timeline(current: str, rows: List[Tuple[str, str, str]]) -> str:
    block = (
        f"%% {TIMELINE_START} %%\n"
        "```mermaid\n"
        + _chart(rows)
        + f"\n```\n%% {TIMELINE_END} %%"
    )
    if _MARKER.search(current):
        return _MARKER.sub(lambda _match: block, current, count=1)
    base = current.rstrip()
    if base:
        base += "\n\n"
    return base + block + "\n"


def vault_memory_notes(store: Optional[VaultStore] = None) -> List[VaultNote]:
    """Notes worth searching. Skips archive, dot folders, and Bolt's own boards."""
    if store is None:
        if not vault_exists():
            return []
        store = VaultStore()
    if not store.root.is_dir():
        return []
    notes = []
    for note in store.list_notes():
        if note.rel in _SKIP_RELS or note.rel.startswith("90 Archive"):
            continue
        notes.append(note)
    return notes


def _chart(rows: List[Tuple[str, str, str]]) -> str:
    lines = ["gantt", "    title Coming up", "    dateFormat YYYY-MM-DD"]
    tasks = [row for row in rows if row[0] == "task"]
    events = [row for row in rows if row[0] == "event"]
    if not tasks and not events:
        lines.extend(["    section Plan", "    Nothing scheduled :milestone, 2026-10-19, 0d"])
        return "\n".join(lines)
    if tasks:
        lines.append("    section Tasks")
        for _kind, title, iso in tasks:
            lines.append(f"    {_label(title)} :{iso}, 1d")
    if events:
        lines.append("    section Events")
        for _kind, title, iso in events:
            lines.append(f"    {_label(title)} :{iso}, 1d")
    return "\n".join(lines)


def _chart_rows(store: VaultStore) -> List[Tuple[str, str, str]]:
    rows: List[Tuple[str, str, str, str]] = []
    for note in store.list_notes():
        if not (note.kind == "task" or note.rel.startswith(TASKS_REL + "/")):
            continue
        if str(note.frontmatter.get("status") or "").lower() == "done":
            continue
        due = str(note.frontmatter.get("due") or "")
        if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", due):
            rows.append(("task", note.title, due, due))
    for note in store.list_events():
        iso = str(note.frontmatter.get("date") or "")
        if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", iso):
            rows.append(("event", note.title, iso, iso))
    rows.sort(key=lambda item: (item[3], item[0], item[1].lower()))
    return [(kind, title, iso) for kind, title, iso, _sort in rows[:12]]


def _due_items(store: VaultStore, start: date, end: date) -> List[Tuple[str, str, When]]:
    found: List[Tuple[str, str, When]] = []
    for note in store.list_notes():
        if not (note.kind == "task" or note.rel.startswith(TASKS_REL + "/")):
            continue
        if str(note.frontmatter.get("status") or "").lower() == "done":
            continue
        due = _parse_day(str(note.frontmatter.get("due") or ""))
        if due and start <= due <= end:
            found.append(("task", note.title, When(due)))
    for note in store.list_events():
        day = _parse_day(str(note.frontmatter.get("date") or ""))
        if not day or not (start <= day <= end):
            continue
        clock = _parse_clock(str(note.frontmatter.get("startTime") or ""))
        found.append(("event", note.title, When(day, clock)))
    found.sort(key=lambda item: (item[2].day, item[2].hhmm, item[1].lower()))
    return found


def _window(scope: str) -> Tuple[date, date]:
    today = now_ct().date()
    if scope == "tomorrow":
        day = today + timedelta(days=1)
        return day, day
    if scope == "week":
        sunday = today + timedelta(days=(6 - today.weekday()))
        return today, sunday
    return today, today


def _parse_day(raw: str) -> Optional[date]:
    if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", raw or ""):
        return None
    year, month, day = (int(part) for part in raw.split("-"))
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_clock(raw: str) -> Optional[time]:
    if not re.fullmatch(r"\d{2}:\d{2}", raw or ""):
        return None
    hour, minute = (int(part) for part in raw.split(":"))
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)


def _label(title: str) -> str:
    text = re.sub(r"[:#]", " ", title or "")
    text = re.sub(r"\s+", " ", text).strip()
    return (text[:40] or "Note")
