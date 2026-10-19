#!/usr/bin/env python3
"""Quick capture: add a task or a note, then wait for yes.

No model call on the capture itself. Area comes from rules, saved corrections, and note titles. Unsure means 00 Inbox.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, Optional

from modules.Vault_Dates import When, now_ct, parse_when, speak_when
from modules.Vault_Filing import pick_area, remember_saved, with_related_body
from modules.Vault_Pending import clear_pending, register_applier, save_pending
from modules.Vault_Store import VaultError, VaultStore, vault_exists

_ADD_TASK = re.compile(
    r"^(?:please\s+)?(?:add|create|new|make)\s+(?:a\s+)?task\s*[:\-]?\s*(?P<body>.+)$",
    re.I,
)
_NOTE = re.compile(
    r"^(?:please\s+)?(?:quick note|jot|note)\s*:\s*(?P<body>.+)$",
    re.I,
)
_DUE_TAIL = re.compile(
    r"^(?P<title>.+?)\s+(?:by|due|on|for)\s+(?P<when>.+)$",
    re.I,
)



def try_capture(text: str) -> Optional[str]:
    soft = re.sub(r"\s+", " ", (text or "").strip())
    task = _ADD_TASK.match(soft)
    note = _NOTE.match(soft)
    if not task and not note:
        return None
    if not vault_exists():
        return (
            "I can't see the vault yet, so I didn't save anything. "
            "Set BOLT_VAULT_PATH to the Obsidian vault and say it again."
        )
    if task:
        item = _task_item(task.group("body"))
    else:
        item = _note_item(note.group("body") if note else "")
    spoken = speak_capture(item)
    save_pending({"kind": "capture", "item": item, "spoken": spoken})
    return spoken


def speak_capture(item: Dict[str, Any]) -> str:
    kind = "task" if item.get("type") == "task" else "note"
    title = item.get("title") or "Untitled"
    area = item.get("area") or "00 Inbox"
    due = item.get("due") or ""
    when_bit = ""
    if due:
        try:
            year, month, day_num = (int(part) for part in str(due).split("-"))
            when_bit = f", due {speak_when(When(date(year, month, day_num)))}"
        except ValueError:
            when_bit = f", due {due}"
    else:
        when_bit = ", with no due date"
    related = item.get("related") or []
    related_bit = ""
    if related:
        names = ", ".join(f"[[{name}]]" for name in related)
        related_bit = f" Related: {names}."
    return (
        f"I'll add a {kind}, {title}, in {area}{when_bit}.{related_bit} "
        "Say yes to save or no to cancel."
    )


def apply_capture(pending: Dict[str, Any]) -> str:
    item = pending.get("item") or {}
    if not vault_exists():
        raise VaultError(
            "I can't see the vault yet, so I didn't save that. "
            "Set BOLT_VAULT_PATH and say yes again."
        )
    store = VaultStore()
    note = store.add_note(
        str(item.get("title") or "Untitled"),
        kind=str(item.get("type") or "task"),
        area=str(item.get("area") or ""),
        due=str(item.get("due") or ""),
        body=with_related_body(str(item.get("body") or ""), list(item.get("related") or [])),
        status="inbox",
        source="chat",
    )
    remember_saved([{"rel": note.rel, "title": note.title, "type": note.kind or "note"}])
    clear_pending()
    return f"Saved {note.title}. It's in {note.rel}."


def choose_area(text: str) -> str:
    """Rules, then corrections and note titles, else Inbox."""
    return pick_area(text).area


def _task_item(body: str) -> Dict[str, Any]:
    title, when = _split_due(body)
    title = _tidy(title)
    if not title:
        raise VaultError("What should the task be called?")
    decision = pick_area(body)
    item: Dict[str, Any] = {
        "type": "task",
        "title": title,
        "area": decision.area,
        "due": when.iso_date if when else "",
        "body": "",
        "related": decision.related,
        "source": "chat",
    }
    return item


def _note_item(body: str) -> Dict[str, Any]:
    text = _tidy(body)
    if not text:
        raise VaultError("What should the note say?")
    title = text if len(text) <= 80 else text[:77].rsplit(" ", 1)[0] + "…"
    decision = pick_area(body)
    return {
        "type": "note",
        "title": title,
        "area": decision.area,
        "due": "",
        "body": text,
        "related": decision.related,
        "source": "chat",
    }


def _split_due(body: str) -> tuple[str, Optional[When]]:
    match = _DUE_TAIL.match(body.strip())
    if match:
        found = parse_when(match.group("when"), now=now_ct())
        if found:
            return match.group("title"), found
    found = parse_when(body, now=now_ct())
    if found and _DUE_TAIL.match(body.strip()):
        return _DUE_TAIL.match(body.strip()).group("title"), found  # type: ignore[union-attr]
    return body, None


def _tidy(title: str) -> str:
    text = re.sub(r"\s+", " ", (title or "").strip()).strip(" .\"'")
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text


register_applier("capture", apply_capture)
