#!/usr/bin/env python3
"""Keep ``10 Bolt/Bolt Board.md`` in step with task notes.

Obsidian is the source of truth when a card has been dragged. Bolt's own
status change wins when William says "move X to Doing". Unknown cards and the
kanban settings block stay put. A note that is not a kanban board is left alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from modules.Vault_Filing import load_memory
from modules.Vault_Pending import clear_pending, load_pending, register_applier, save_pending
from modules.Vault_Store import (
    BOARD_REL,
    LANES,
    LANE_FOR_STATUS,
    STATUS_FOR_LANE,
    TASKS_REL,
    VaultError,
    VaultNote,
    VaultStore,
    dump_frontmatter,
    vault_exists,
)

_SHOW = re.compile(
    r"^(?:please\s+)?(?:what(?:'s| is) on my board|show (?:me )?(?:my |the )?board)[.!?]*$",
    re.I,
)
_MOVE = re.compile(
    r"^(?:please\s+)?move (?P<title>.+?) to (?P<lane>inbox|this week|doing|done)[.!?]*$",
    re.I,
)
_LINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
_CARD = re.compile(r"^- \[([ xX])\] (.+)$")
_LANE_NAMES = {name.lower(): name for name in LANES}


@dataclass
class ParsedBoard:
    head: str
    complete: bool
    cards: Dict[str, List[str]]
    tail: str
    kanban: bool


@dataclass
class _Plan:
    board_text: str
    status_writes: List[tuple[str, str, str]] = field(default_factory=list)
    changed: bool = False


def try_board(text: str) -> Optional[str]:
    soft = re.sub(r"\s+", " ", (text or "").strip())
    if _SHOW.match(soft):
        return show_board()
    pending = load_pending()
    if pending and pending.get("kind") == "choose":
        return _answer_choice(pending, soft)
    match = _MOVE.match(soft)
    if not match:
        return None
    if not vault_exists():
        return "I can't see the vault yet, so I didn't move that card."
    lane = _LANE_NAMES[match.group("lane").lower()]
    store = VaultStore()
    store.ensure_scaffold()
    _pull(store)
    matches = _match_tasks(store, match.group("title"))
    if not matches:
        return f"I don't see a task called {match.group('title').strip()}."
    if len(matches) > 1:
        options = [{"rel": note.rel, "title": note.title} for note in matches]
        spoken = _speak_choice(options, lane)
        save_pending(
            {
                "kind": "choose",
                "options": options,
                "lane": lane,
                "status": STATUS_FOR_LANE[lane],
                "spoken": spoken,
            }
        )
        return spoken
    return _preview_move(matches[0], lane)


def show_board() -> str:
    if not vault_exists():
        return "I can't see the vault yet, so I can't read the board."
    store = VaultStore()
    store.ensure_scaffold()
    _pull(store)
    text = (store.root / BOARD_REL).read_text(encoding="utf-8")
    if "kanban-plugin: board" not in text:
        return "The board note is not a kanban board, so I left it alone."
    parsed = parse_board(text)
    bits = []
    for lane in LANES:
        titles = []
        for raw in parsed.cards.get(lane) or []:
            link = _wikilink(raw)
            titles.append(link or raw)
        bits.append(f"{lane}: " + (", ".join(titles) if titles else "nothing"))
    return "On your board. " + ". ".join(bits) + "."


def apply_move(pending: Dict[str, str]) -> str:
    rel = str(pending.get("rel") or "")
    lane = str(pending.get("lane") or "")
    status = str(pending.get("status") or STATUS_FOR_LANE.get(lane, "inbox"))
    if not rel or lane not in LANES:
        clear_pending()
        return "Okay, I won't move that."
    if not vault_exists():
        raise VaultError("I can't see the vault yet, so I didn't move that card.")
    store = VaultStore()
    note = store.read_note(rel)
    current = str(note.frontmatter.get("status") or "inbox").lower()
    if current == status:
        clear_pending()
        return f"{note.title} is already in {lane}."
    meta = dict(note.frontmatter)
    meta["status"] = status
    body = note.body if note.body.startswith("\n") or note.body == "" else "\n" + note.body
    with store.changing(f"move {note.title} to {lane}"):
        store.write_text(rel, dump_frontmatter(meta, body))
        store.append_activity("move", note.title, f"to {lane}")
        push_inside(store)
    clear_pending()
    return f"Moved {note.title} to {lane}."


def push_inside(store: VaultStore) -> None:
    """Rebuild cards from task status. Caller holds the vault change."""
    plan = _plan(store, prefer="tasks")
    if plan.changed:
        store.write_text(BOARD_REL, plan.board_text)


def parse_board(text: str) -> ParsedBoard:
    kanban = "kanban-plugin: board" in (text or "")
    marker = "%% kanban:settings"
    idx = text.find(marker)
    if idx == -1:
        middle, tail = text, ""
    elif idx > 0 and text[idx - 1] == "\n":
        middle, tail = text[: idx - 1], text[idx - 1 :]
    else:
        middle, tail = text[:idx], text[idx:]
    cards: Dict[str, List[str]] = {lane: [] for lane in LANES}
    lane_at = re.search(r"^## (?:Inbox|This Week|Doing|Done)\s*$", middle, re.M)
    if lane_at is None:
        head = middle if middle.endswith("\n") or not middle else middle + "\n"
        return ParsedBoard(head=head, complete=False, cards=cards, tail=tail, kanban=kanban)
    head = middle[: lane_at.start()]
    if head and not head.endswith("\n"):
        head += "\n"
    lane = ""
    complete = False
    for line in middle[lane_at.start() :].split("\n"):
        header = re.match(r"^## (.+?)\s*$", line)
        if header and header.group(1) in LANES:
            lane = header.group(1)
            continue
        if line.strip() == "**Complete**" and lane == "Done":
            complete = True
            continue
        if lane and _CARD.match(line):
            cards[lane].append(line)
    return ParsedBoard(head=head, complete=complete, cards=cards, tail=tail, kanban=kanban)


def render_board(parsed: ParsedBoard, cards: Dict[str, List[str]]) -> str:
    sections: List[str] = []
    for lane in LANES:
        block = [f"## {lane}", ""]
        if lane == "Done" and parsed.complete:
            block.extend(["**Complete**", ""])
        block.extend(cards.get(lane) or [])
        sections.append("\n".join(block))
    body = parsed.head + "\n".join(sections)
    if not body.endswith("\n"):
        body += "\n"
    return body + parsed.tail


def _pull(store: VaultStore) -> None:
    plan = _plan(store, prefer="board")
    if not plan.changed:
        return
    with store.changing("read board"):
        for rel, _old, status in plan.status_writes:
            _write_status(store, rel, status)
        if plan.board_text:
            fresh = _plan(store, prefer="tasks")
            store.write_text(BOARD_REL, fresh.board_text)
        for rel, old, status in plan.status_writes:
            note = store.read_note(rel)
            store.append_activity("status", note.title, f"{old} -> {status}")


def _plan(store: VaultStore, *, prefer: str) -> _Plan:
    path = store.root / BOARD_REL
    if not path.is_file():
        return _Plan(board_text="")
    current = path.read_text(encoding="utf-8")
    if "kanban-plugin: board" not in current:
        return _Plan(board_text=current)
    parsed = parse_board(current)
    tasks = _tasks(store)
    by_title: Dict[str, List[VaultNote]] = {}
    for note in tasks:
        by_title.setdefault(note.title.lower(), []).append(note)
    status_writes: List[tuple[str, str, str]] = []
    statuses: Dict[str, str] = {}
    for note in tasks:
        statuses[note.rel] = str(note.frontmatter.get("status") or "inbox").lower()
    if prefer == "board":
        for lane in LANES:
            status = STATUS_FOR_LANE[lane]
            for raw in parsed.cards.get(lane) or []:
                title = _wikilink(raw)
                if not title:
                    continue
                matches = by_title.get(title.lower()) or []
                if len(matches) != 1:
                    continue
                note = matches[0]
                old = statuses.get(note.rel, "inbox")
                if old != status:
                    statuses[note.rel] = status
                    status_writes.append((note.rel, old, status))
    linked = {note.title.lower() for note in tasks}
    cards: Dict[str, List[str]] = {lane: [] for lane in LANES}
    for note in tasks:
        status = statuses.get(note.rel, "inbox")
        lane = LANE_FOR_STATUS.get(status, "Inbox")
        mark = "x" if lane == "Done" else " "
        cards[lane].append(f"- [{mark}] [[{note.title}]]")
    for lane in LANES:
        for raw in parsed.cards.get(lane) or []:
            title = _wikilink(raw)
            if title and title.lower() in linked:
                continue
            cards[lane].append(raw)
    rendered = render_board(parsed, cards)
    changed = rendered != current or bool(status_writes)
    return _Plan(board_text=rendered, status_writes=status_writes, changed=changed)


def _write_status(store: VaultStore, rel: str, status: str) -> None:
    note = store.read_note(rel)
    meta = dict(note.frontmatter)
    meta["status"] = status
    body = note.body if note.body.startswith("\n") or note.body == "" else "\n" + note.body
    store.write_text(rel, dump_frontmatter(meta, body))


def _tasks(store: VaultStore) -> List[VaultNote]:
    found = []
    for note in store.list_notes():
        if note.kind == "task" or note.rel.startswith(TASKS_REL + "/"):
            found.append(note)
    return found


def _match_tasks(store: VaultStore, title: str) -> List[VaultNote]:
    query = re.sub(r"\s+", " ", (title or "").strip()).lower()
    tasks = _tasks(store)
    if query in {"it", "that", "this"}:
        rels = {str(row.get("rel") or "") for row in load_memory().get("last") or []}
        picked = [note for note in tasks if note.rel in rels]
        return picked or tasks[:1]
    exact = [note for note in tasks if note.title.lower() == query]
    if exact:
        return exact
    return [note for note in tasks if query and query in note.title.lower()]


def _preview_move(note: VaultNote, lane: str) -> str:
    current = str(note.frontmatter.get("status") or "inbox").lower()
    status = STATUS_FOR_LANE[lane]
    if current == status:
        return f"{note.title} is already in {lane}."
    spoken = f"I'll move {note.title} to {lane}. Say yes to save or no to cancel."
    save_pending(
        {
            "kind": "move",
            "rel": note.rel,
            "title": note.title,
            "lane": lane,
            "status": status,
            "spoken": spoken,
        }
    )
    return spoken


def _speak_choice(options: List[Dict[str, str]], lane: str) -> str:
    bits = [f"{index}, {row['title']}" for index, row in enumerate(options, start=1)]
    return f"Which one should move to {lane}: " + "; ".join(bits) + "? Say the number."


def _answer_choice(pending: Dict[str, object], text: str) -> Optional[str]:
    options = list(pending.get("options") or [])
    lane = str(pending.get("lane") or "")
    if not options or lane not in LANES:
        return None
    number = re.fullmatch(r"(?:number\s+)?(\d+)[.!]?", text.strip(), re.I)
    if number:
        index = int(number.group(1))
        if index < 1 or index > len(options):
            raise VaultError(f"I numbered {len(options)} tasks. Say a number or no.")
        chosen = options[index - 1]
    else:
        query = text.lower()
        hits = [row for row in options if query and query in str(row.get("title") or "").lower()]
        if len(hits) != 1:
            return None
        chosen = hits[0]
    if not vault_exists():
        return "I can't see the vault yet, so I didn't move that card."
    note = VaultStore().read_note(str(chosen.get("rel") or ""))
    return _preview_move(note, lane)


def _wikilink(raw: str) -> str:
    match = _LINK.search(raw or "")
    return match.group(1).strip() if match else ""


register_applier("move", apply_move)
