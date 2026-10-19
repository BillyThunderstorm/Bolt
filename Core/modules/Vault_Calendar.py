#!/usr/bin/env python3
"""Calendar events as notes in ``10 Bolt/Calendar``.

Full Calendar Remastered reads ``title``, ``allDay``, ``date``, and
``startTime`` / ``endTime``. Cancel hides an event by clearing ``date`` and
keeping the file. ``10 Bolt/Bolt Calendar.md`` is an index, never an event.
Times are spoken in CT. Nothing is written until William says yes.
"""

from __future__ import annotations

import re
from datetime import date, time
from typing import Any, Dict, List, Optional

from modules.Vault_Dates import When, end_after, now_ct, parse_when, speak_when
from modules.Vault_Filing import remember_saved
from modules.Vault_Pending import clear_pending, load_pending, register_applier, save_pending
from modules.Vault_Store import (
    CALENDAR_INDEX_NAME,
    CALENDAR_REL,
    TASKS_REL,
    VaultError,
    VaultNote,
    VaultStore,
    vault_exists,
)

_SCHEDULE = re.compile(
    r"^(?:please\s+)?(?:schedule|book|put on (?:my )?calendar|add (?:an )?event)\s+(?P<body>.+)$",
    re.I,
)
_CANCEL = re.compile(
    r"^(?:please\s+)?cancel (?P<title>.+?)(?:\s+please)?[.!?]*$",
    re.I,
)
_MOVE = re.compile(
    r"^(?:please\s+)?move (?P<title>.+?) to (?P<when>.+?)(?:\s+please)?[.!?]*$",
    re.I,
)
_LANE = re.compile(r"^(?:inbox|this week|doing|done)$", re.I)


def try_calendar(text: str) -> Optional[str]:
    soft = re.sub(r"\s+", " ", (text or "").strip())
    pending = load_pending()
    if pending and pending.get("kind") == "pick":
        return _answer_pick(pending, soft)
    scheduled = _SCHEDULE.match(soft)
    if scheduled:
        return _schedule(scheduled.group("body"))
    cancelled = _CANCEL.match(soft)
    if cancelled:
        return _cancel(cancelled.group("title"))
    move = _MOVE.match(soft)
    if not move or _LANE.match(move.group("when").strip()):
        return None
    found = parse_when(move.group("when"), now=now_ct())
    if not found:
        return None
    return _move(move.group("title"), found)


def apply_event(pending: Dict[str, Any]) -> str:
    if not vault_exists():
        raise VaultError("I can't see the vault yet, so I didn't schedule that.")
    when = _when_from(pending)
    end = str(pending.get("end") or "")
    store = VaultStore()
    note = store.add_note(
        str(pending.get("title") or "Untitled"),
        kind="page",
        area="10 Bolt",
        folder_rel=CALENDAR_REL,
        source="chat",
        extra=_event_meta(when, end),
    )
    remember_saved([{"rel": note.rel, "title": note.title, "type": "event"}])
    clear_pending()
    return f"Scheduled {note.title}. It's in {note.rel}."


def apply_event_move(pending: Dict[str, Any]) -> str:
    if not vault_exists():
        raise VaultError("I can't see the vault yet, so I didn't move that.")
    store = VaultStore()
    rel = str(pending.get("rel") or "")
    when = _when_from(pending)
    end = str(pending.get("end") or "")
    note = store.update_frontmatter(rel, _event_updates(when, end), summary=f"move event to {when.iso_date}")
    remember_saved([{"rel": note.rel, "title": note.title, "type": "event"}])
    clear_pending()
    return f"Moved {note.title} to {speak_when(when)}."


def apply_due(pending: Dict[str, Any]) -> str:
    if not vault_exists():
        raise VaultError("I can't see the vault yet, so I didn't change that due date.")
    store = VaultStore()
    rel = str(pending.get("rel") or "")
    iso = str(pending.get("date") or "")
    note = store.update_frontmatter(rel, {"due": iso}, summary=f"due {iso}")
    remember_saved([{"rel": note.rel, "title": note.title, "type": "task"}])
    clear_pending()
    return f"Set {note.title} due {_speak_pending(pending)}."


def apply_cancel(pending: Dict[str, Any]) -> str:
    if not vault_exists():
        raise VaultError("I can't see the vault yet, so I didn't cancel that.")
    store = VaultStore()
    rel = str(pending.get("rel") or "")
    note = store.read_note(rel)
    updates: Dict[str, Any] = {
        "cancelled": True,
        "cancelledDate": str(note.frontmatter.get("date") or ""),
        "date": None,
        "startTime": None,
        "endTime": None,
        "allDay": None,
    }
    if note.frontmatter.get("startTime"):
        updates["cancelledStart"] = note.frontmatter.get("startTime")
        updates["cancelledEnd"] = note.frontmatter.get("endTime")
    saved = store.update_frontmatter(rel, updates, summary=f"cancel {note.title}")
    clear_pending()
    return f"Cancelled {saved.title}. The note stays in {saved.rel}."


def _schedule(body: str) -> str:
    title, when = _split_when(body)
    if not title:
        return "What should I call that event?"
    if when is None:
        return "When should I put that on the calendar?"
    if not vault_exists():
        return "I can't see the vault yet, so I didn't schedule that. Set BOLT_VAULT_PATH and ask again."
    end = end_after(when.clock).strftime("%H:%M") if when.clock else ""
    spoken = f"I'll schedule {title} for {_speak_span(when, end)}. Say yes to save or no to cancel."
    save_pending(_payload("event", title=title, when=when, end=end, spoken=spoken))
    return spoken


def _cancel(title: str) -> str:
    if not vault_exists():
        return "I can't see the vault yet, so I didn't cancel that."
    store = VaultStore()
    store.ensure_scaffold()
    matches = _match(store.list_events(), title)
    if not matches:
        return f"I don't see an event called {title.strip()}."
    if len(matches) > 1:
        return _ask(matches, action="cancel", when=None)
    return _preview_cancel(matches[0])


def _move(title: str, when: When) -> str:
    if not vault_exists():
        return "I can't see the vault yet, so I didn't move that."
    store = VaultStore()
    store.ensure_scaffold()
    events = _match(store.list_events(), title)
    tasks = _match(_tasks(store), title)
    if not events and not tasks:
        return f"I don't see a note called {title.strip()}."
    if len(events) + len(tasks) > 1:
        return _ask(events + tasks, action="move", when=when)
    if events:
        return _preview_event_move(events[0], when)
    return _preview_due(tasks[0], when)


def _preview_cancel(note: VaultNote) -> str:
    current = _note_when(note)
    spoken = (
        f"I'll cancel {note.title}"
        + (f" on {speak_when(current)}" if current else "")
        + ". The note stays. Say yes to save or no to cancel."
    )
    save_pending({"kind": "cancel-event", "rel": note.rel, "title": note.title, "spoken": spoken})
    return spoken


def _preview_event_move(note: VaultNote, when: When) -> str:
    current = _note_when(note)
    target, end = _shifted(current, when, str(note.frontmatter.get("endTime") or ""))
    origin = f" from {speak_when(current)}" if current else ""
    spoken = (
        f"I'll move {note.title}{origin} to {_speak_span(target, end)}. "
        "Say yes to save or no to cancel."
    )
    save_pending(_payload("event-move", title=note.title, when=target, end=end, spoken=spoken, rel=note.rel))
    return spoken


def _preview_due(note: VaultNote, when: When) -> str:
    previous = str(note.frontmatter.get("due") or "")
    was = ""
    if previous:
        was = f" It was due {_speak_iso(previous)}."
    spoken = f"I'll set {note.title} due {speak_when(When(when.day))}.{was} Say yes to save or no to cancel."
    save_pending(
        {
            "kind": "due",
            "rel": note.rel,
            "title": note.title,
            "date": when.iso_date,
            "allDay": True,
            "spoken": spoken,
        }
    )
    return spoken


def _ask(notes: List[VaultNote], *, action: str, when: Optional[When]) -> str:
    options = []
    for note in notes:
        kind = "event" if note.rel.startswith(CALENDAR_REL + "/") else "task"
        options.append({"rel": note.rel, "title": note.title, "kind": kind})
    bits = [f"{index}, {row['kind']} {row['title']}" for index, row in enumerate(options, start=1)]
    spoken = "Which one: " + "; ".join(bits) + "? Say the number."
    payload: Dict[str, Any] = {"kind": "pick", "options": options, "action": action, "spoken": spoken}
    if when is not None:
        payload.update({"date": when.iso_date, "start": when.hhmm, "allDay": when.all_day})
    save_pending(payload)
    return spoken


def _answer_pick(pending: Dict[str, Any], text: str) -> Optional[str]:
    options = list(pending.get("options") or [])
    number = re.fullmatch(r"(?:number\s+)?(\d+)[.!?]?", text.strip(), re.I)
    if not number:
        return None
    index = int(number.group(1))
    if index < 1 or index > len(options):
        raise VaultError(f"I numbered {len(options)} notes. Say a number or no.")
    chosen = options[index - 1]
    if not vault_exists():
        return "I can't see the vault yet, so I didn't change that."
    note = VaultStore().read_note(str(chosen.get("rel") or ""))
    action = str(pending.get("action") or "")
    if action == "cancel":
        return _preview_cancel(note)
    when = _when_from(pending)
    if str(chosen.get("kind") or "") == "event" or note.rel.startswith(CALENDAR_REL + "/"):
        return _preview_event_move(note, when)
    return _preview_due(note, when)


_WHEN_WORDS = {
    "tonight",
    "today",
    "tomorrow",
    "next",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "jan",
    "feb",
    "mar",
    "apr",
    "jun",
    "jul",
    "aug",
    "sep",
    "sept",
    "oct",
    "nov",
    "dec",
}


def _is_when_word(word: str) -> bool:
    token = word.lower().strip(".,")
    if token in _WHEN_WORDS or re.fullmatch(r"20\d{2}-\d{2}-\d{2}", token):
        return True
    return bool(re.fullmatch(r"\d{1,2}(?::\d{2})?(?:am|pm)", token))


def _split_when(body: str) -> tuple[str, Optional[When]]:
    words = [part for part in re.sub(r"\s+", " ", (body or "").strip()).split(" ") if part]
    for index, word in enumerate(words):
        if index == 0 or not _is_when_word(word):
            continue
        found = parse_when(" ".join(words[index:]), now=now_ct())
        if not found:
            continue
        title = " ".join(words[:index])
        title = re.sub(r"\s+(?:for|on|at|by)$", "", title, flags=re.I)
        title = re.sub(r"^(?:the|a|an)\s+", "", title, flags=re.I)
        title = _tidy(title)
        if title:
            return title, found
    return "", None


def _shifted(current: Optional[When], target: When, current_end: str = "") -> tuple[When, str]:
    """Keep the clock when William names a day but not a time."""
    if target.clock is None and current and current.clock:
        return When(target.day, current.clock), current_end
    if target.clock is None:
        return When(target.day), ""
    return When(target.day, target.clock), end_after(target.clock).strftime("%H:%M")


def _event_meta(when: When, end: str) -> Dict[str, Any]:
    meta: Dict[str, Any] = {"type": "event", "allDay": when.all_day, "date": when.iso_date}
    if when.clock:
        meta["startTime"] = when.hhmm
        meta["endTime"] = end or end_after(when.clock).strftime("%H:%M")
    return meta


def _event_updates(when: When, end: str) -> Dict[str, Any]:
    updates: Dict[str, Any] = {
        "date": when.iso_date,
        "allDay": when.all_day,
        "cancelled": None,
        "cancelledDate": None,
    }
    if when.clock:
        updates["startTime"] = when.hhmm
        updates["endTime"] = end or end_after(when.clock).strftime("%H:%M")
    else:
        updates["startTime"] = None
        updates["endTime"] = None
    return updates


def _payload(kind: str, *, title: str, when: When, end: str, spoken: str, rel: str = "") -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "kind": kind,
        "title": title,
        "date": when.iso_date,
        "start": when.hhmm,
        "end": end if when.clock else "",
        "allDay": when.all_day,
        "spoken": spoken,
    }
    if rel:
        payload["rel"] = rel
    return payload


def _when_from(pending: Dict[str, Any]) -> When:
    year, month, day = (int(part) for part in str(pending.get("date") or "").split("-"))
    start = str(pending.get("start") or "")
    clock = None
    if start and not pending.get("allDay"):
        hour, minute = (int(part) for part in start.split(":"))
        clock = time(hour, minute)
    return When(date(year, month, day), clock)


def _note_when(note: VaultNote) -> Optional[When]:
    raw = str(note.frontmatter.get("date") or "")
    if not raw:
        return None
    try:
        year, month, day = (int(part) for part in raw.split("-"))
        day_value = date(year, month, day)
    except ValueError:
        return None
    start = str(note.frontmatter.get("startTime") or "")
    clock = None
    if start:
        try:
            hour, minute = (int(part) for part in start.split(":"))
            clock = time(hour, minute)
        except ValueError:
            clock = None
    return When(day_value, clock)


def _speak_span(when: When, end: str) -> str:
    if when.clock is None:
        return speak_when(when) + ", all day"
    spoken = speak_when(when)
    if not end:
        return spoken
    hour, minute = (int(part) for part in end.split(":"))
    end_when = When(when.day, time(hour, minute))
    end_clock = speak_when(end_when).split(", ", 1)[1]
    return spoken.replace(" CT", "") + " to " + end_clock


def _speak_pending(pending: Dict[str, Any]) -> str:
    return speak_when(_when_from({**pending, "allDay": True, "start": ""}))


def _speak_iso(iso: str) -> str:
    try:
        year, month, day = (int(part) for part in iso.split("-"))
    except ValueError:
        return iso
    return speak_when(When(date(year, month, day)))


def _tasks(store: VaultStore) -> List[VaultNote]:
    return [
        note
        for note in store.list_notes()
        if note.kind == "task" or note.rel.startswith(TASKS_REL + "/")
    ]


def _match(notes: List[VaultNote], title: str) -> List[VaultNote]:
    query = re.sub(r"\s+", " ", (title or "").strip()).lower()
    query = re.sub(r"^(?:the|a|an)\s+", "", query)
    if query in {"it", "that", "this"}:
        rels = {str(row.get("rel") or "") for row in _last_rels()}
        picked = [note for note in notes if note.rel in rels]
        return picked
    exact = [note for note in notes if note.title.lower() == query or note.title.lower() == title.strip().lower()]
    if exact:
        return exact
    return [
        note
        for note in notes
        if query and query in note.title.lower() and note.path.name != CALENDAR_INDEX_NAME
    ]


def _last_rels() -> List[Dict[str, Any]]:
    from modules.Vault_Filing import load_memory

    rows = load_memory().get("last") or []
    return list(rows) if isinstance(rows, list) else []


def _tidy(title: str) -> str:
    text = re.sub(r"\s+", " ", (title or "").strip()).strip(" .\"'")
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text


register_applier("event", apply_event)
register_applier("event-move", apply_event_move)
register_applier("due", apply_due)
register_applier("cancel-event", apply_cancel)
