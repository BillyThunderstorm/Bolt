#!/usr/bin/env python3
"""Vault_Store — the only module that reads and writes William's Obsidian vault.

Safety:
  - Writes stay inside the vault root. Symlinks and ``..`` paths are refused.
  - Nothing is deleted. Undoing a new note parks it under ``.bolt/undone/``.
  - A backup is copied to ``.bolt/backups/`` before an existing note is modified.
  - Every user-facing change appends a row to ``10 Bolt/Bolt Activity Log.md``.

The vault root is ``BOLT_VAULT_PATH``, then ``vault_path`` in ``Core/config.json``,
then ``/Users/carter/Documents/Obsidian/Bolt Vault``. A missing root is reported.
This module does not create that default folder.

Phase 0 names (already in the real vault — update these files, never replace them):
  - ``10 Bolt/Bolt Board.md`` — Kanban 2.0.51 (``kanban-plugin: board``)
  - ``10 Bolt/Plan Timeline.md`` — Mermaid between bolt:timeline markers
  - ``10 Bolt/Bolt Activity Log.md`` — table When (CT) | Action | Note | Details
  - ``10 Bolt/Tasks/`` — task notes
  - ``10 Bolt/Calendar/`` — Full Calendar Remastered full-note events
  - ``10 Bolt/Bolt Calendar.md`` — index note, not an event
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
DEFAULT_VAULT = Path("/Users/carter/Documents/Obsidian/Bolt Vault")

AREAS: tuple[str, ...] = (
    "00 Inbox",
    "10 Bolt",
    "20 Creator HQ & Content",
    "30 Product Testing",
    "40 Career & Creator Plan",
    "50 Personal",
)

BOARD_REL = "10 Bolt/Bolt Board.md"
TIMELINE_REL = "10 Bolt/Plan Timeline.md"
ACTIVITY_REL = "10 Bolt/Bolt Activity Log.md"
TASKS_REL = "10 Bolt/Tasks"
CALENDAR_REL = "10 Bolt/Calendar"
CALENDAR_INDEX_REL = "10 Bolt/Bolt Calendar.md"
CALENDAR_INDEX_NAME = "Bolt Calendar.md"

TIMELINE_START = "bolt:timeline:start"
TIMELINE_END = "bolt:timeline:end"

LANES: tuple[str, ...] = ("Inbox", "This Week", "Doing", "Done")
STATUS_FOR_LANE = {
    "Inbox": "inbox",
    "This Week": "this-week",
    "Doing": "doing",
    "Done": "done",
}
LANE_FOR_STATUS = {v: k for k, v in STATUS_FOR_LANE.items()}

_AREA_ALIASES = {
    "inbox": "00 Inbox",
    "bolt": "10 Bolt",
    "creator": "20 Creator HQ & Content",
    "creator hq": "20 Creator HQ & Content",
    "content": "20 Creator HQ & Content",
    "creator hq & content": "20 Creator HQ & Content",
    "product": "30 Product Testing",
    "product testing": "30 Product Testing",
    "testing": "30 Product Testing",
    "career": "40 Career & Creator Plan",
    "career & creator plan": "40 Career & Creator Plan",
    "personal": "50 Personal",
}

_SKIP_DIR_NAMES = {".obsidian", ".bolt", ".git", ".trash"}


class VaultError(Exception):
    """A vault read or write that Bolt should say out loud, not crash on."""


@dataclass
class VaultNote:
    rel: str
    title: str
    frontmatter: Dict[str, Any]
    body: str
    path: Path

    @property
    def area(self) -> str:
        raw = self.frontmatter.get("area")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        for area in AREAS:
            if self.rel == area or self.rel.startswith(area + "/"):
                return area
        return ""

    @property
    def kind(self) -> str:
        raw = self.frontmatter.get("type") or self.frontmatter.get("kind") or ""
        return str(raw).strip().lower()


@dataclass
class _FileSnap:
    rel: str
    existed: bool
    original: Optional[str]
    backup_rel: Optional[str] = None


@dataclass
class _Txn:
    summary: str
    files: Dict[str, _FileSnap] = field(default_factory=dict)


def now_ct() -> datetime:
    return datetime.now(CT)


def resolve_vault_path() -> Path:
    """Env, then config ``vault_path``, then the Mac default. Does not create it."""
    env = (os.getenv("BOLT_VAULT_PATH") or "").strip()
    if env:
        return Path(env).expanduser()
    configured = _config_vault_path()
    if configured:
        return Path(configured).expanduser()
    return DEFAULT_VAULT


def vault_exists(root: Optional[Path] = None) -> bool:
    path = root if root is not None else resolve_vault_path()
    return path.is_dir()


def resolve_area(name: str, *, default: str = "00 Inbox") -> str:
    """Map a spoken or typed area onto a vault folder name."""
    raw = (name or "").strip()
    if not raw:
        return default
    folded = re.sub(r"\s+", " ", raw).strip().lower()
    for area in AREAS:
        if folded == area.lower():
            return area
        short = area.split(" ", 1)[1].lower()
        if folded == short:
            return area
    if folded in _AREA_ALIASES:
        return _AREA_ALIASES[folded]
    raise VaultError(f"I don't know an area called {raw}.")


def safe_note_filename(title: str) -> str:
    cleaned = (title or "").strip()
    cleaned = cleaned.replace("/", " - ").replace("\\", " - ").replace(":", " - ")
    cleaned = re.sub(r'[<>"|?*\n\r\t]', " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if not cleaned:
        cleaned = "Untitled"
    if len(cleaned) > 80:
        cleaned = cleaned[:80].rstrip()
    return cleaned + ".md"


def parse_frontmatter(text: str) -> tuple[Dict[str, Any], str]:
    """Split a note into frontmatter and body. Missing frontmatter is fine."""
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, text
    meta: Dict[str, Any] = {}
    for line in lines[1:end]:
        if not line.strip() or line.strip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, raw_val = line.split(":", 1)
        key = _unquote(key.strip())
        meta[key] = _parse_scalar(raw_val.strip())
    body = "\n".join(lines[end + 1 :])
    if body.startswith("\n"):
        body = body[1:]
    return meta, body


def dump_frontmatter(meta: Dict[str, Any], body: str) -> str:
    lines = ["---"]
    for key, value in meta.items():
        if value is None:
            continue
        lines.append(f"{_dump_key(key)}: {_dump_scalar(value)}")
    lines.append("---")
    body = body if body.startswith("\n") or body == "" else "\n" + body
    if body and not body.endswith("\n"):
        body += "\n"
    return "\n".join(lines) + body


def note_from_text(rel: str, text: str, path: Path) -> VaultNote:
    meta, body = parse_frontmatter(text)
    title = meta.get("title")
    if not isinstance(title, str) or not title.strip():
        heading = _first_heading(body)
        title = heading or Path(rel).stem
    return VaultNote(
        rel=rel.replace("\\", "/"),
        title=str(title).strip(),
        frontmatter=meta,
        body=body,
        path=path,
    )


def _config_vault_path() -> str:
    config = Path(__file__).resolve().parents[1] / "config.json"
    if not config.is_file():
        return ""
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    raw = data.get("vault_path") or data.get("obsidian_vault") or ""
    return str(raw).strip()


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        inner = value[1:-1]
        return inner.replace('\\"', '"').replace("\\'", "'")
    return value


def _parse_scalar(raw: str) -> Any:
    if raw == "" or raw in ("null", "~", "Null", "NULL"):
        return ""
    if raw in ("true", "True", "TRUE"):
        return True
    if raw in ("false", "False", "FALSE"):
        return False
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        parts = [_parse_scalar(part.strip()) for part in _split_flow(inner)]
        return parts
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
        return _unquote(raw)
    return raw


def _split_flow(inner: str) -> List[str]:
    parts: List[str] = []
    buf: List[str] = []
    quote: Optional[str] = None
    for ch in inner:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            continue
        if ch == ",":
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return parts


def _dump_key(key: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]+", key):
        return key
    return json.dumps(key)


def _dump_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_dump_scalar(item) for item in value) + "]"
    text = str(value)
    if text == "" or re.search(r'[:#\[\]{},&*!|>%@`]|^\s|\s$', text) or text.lower() in {
        "true",
        "false",
        "null",
    }:
        return json.dumps(text)
    return json.dumps(text) if any(ch in text for ch in ('"', "'")) else text if _safe_plain(text) else json.dumps(text)


def _safe_plain(text: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _./+-]*", text))


def _first_heading(body: str) -> str:
    for line in body.splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return ""


def _ct_stamp() -> str:
    """Clock time in America/Chicago, 12-hour, labeled later as CT in speech."""
    moment = now_ct()
    hour = moment.strftime("%I").lstrip("0") or "12"
    return moment.strftime(f"%Y-%m-%d {hour}:%M %p")


def _cell(value: str) -> str:
    return (value or "").replace("|", "\\|").replace("\n", " ").strip()


def board_template() -> str:
    lanes = []
    for lane in LANES:
        lanes.append(f"## {lane}")
        lanes.append("")
        if lane == "Done":
            lanes.append("**Complete**")
            lanes.append("")
    settings = json.dumps(
        {
            "kanban-plugin": "board",
            "list-collapse": [False, False, False, False],
            "show-checkboxes": True,
            "new-note-folder": TASKS_REL,
        },
        separators=(",", ":"),
    )
    return (
        "---\n\nkanban-plugin: board\n\n---\n\n"
        + "\n".join(lanes)
        + "\n%% kanban:settings\n```\n"
        + settings
        + "\n```\n%%\n"
    )


def timeline_template() -> str:
    return (
        "---\n"
        'title: "Plan Timeline"\n'
        "tags: [bolt, timeline]\n"
        "---\n"
        "# Plan Timeline\n\n"
        "Bolt fills the chart between the markers. Drag events on the calendar "
        "and cards on the board; this picture is rebuilt from those notes.\n\n"
        f"%% {TIMELINE_START} %%\n"
        "```mermaid\n"
        "gantt\n"
        "    title Coming up\n"
        "    dateFormat YYYY-MM-DD\n"
        "    section Plan\n"
        "    Timeline ready :milestone, 2026-10-19, 0d\n"
        "```\n"
        f"%% {TIMELINE_END} %%\n"
    )


def activity_template() -> str:
    return (
        "---\n"
        'title: "Bolt Activity Log"\n'
        "tags: [bolt, log]\n"
        "---\n"
        "# Bolt Activity Log\n\n"
        "Every vault change Bolt makes is a row here.\n\n"
        "| When (CT) | Action | Note | Details |\n"
        "| --- | --- | --- | --- |\n"
    )


class VaultStore:
    def __init__(self, root: Optional[Path] = None):
        self.root = (root if root is not None else resolve_vault_path()).expanduser()
        self._txn: Optional[_Txn] = None

    def require_root(self) -> None:
        if not self.root.exists():
            raise VaultError(
                f"Vault folder is not there yet: {self.root}. "
                "Set BOLT_VAULT_PATH to the Obsidian vault."
            )
        if not self.root.is_dir():
            raise VaultError(f"Vault path is not a folder: {self.root}")

    def rel_of(self, path: Path) -> str:
        root = self.root.resolve()
        resolved = path.resolve() if path.exists() else path
        try:
            rel = resolved.relative_to(root)
        except ValueError as exc:
            raise VaultError("That path leaves the vault.") from exc
        return rel.as_posix()

    def checked(self, rel: str) -> Path:
        """Absolute path inside the vault, or VaultError."""
        self.require_root()
        normal = _norm_rel(rel)
        root = self.root.resolve()
        candidate = root / normal
        if candidate.exists() and candidate.is_symlink():
            raise VaultError("Refusing to follow a symlink inside the vault.")
        probe = candidate
        while not probe.exists() and probe != root:
            probe = probe.parent
        try:
            probe.resolve().relative_to(root)
        except ValueError as exc:
            raise VaultError("That path leaves the vault.") from exc
        if candidate.exists():
            resolved = candidate.resolve()
        else:
            resolved = probe.resolve() / candidate.relative_to(probe)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise VaultError("That path leaves the vault.") from exc
        return resolved

    @contextmanager
    def changing(self, summary: str) -> Iterator[None]:
        """Group writes so one undo restores all of them."""
        if self._txn is not None:
            raise VaultError("A vault change is already open.")
        self.require_root()
        self._txn = _Txn(summary=summary)
        try:
            yield
        except Exception:
            self._rollback()
            raise
        else:
            self._commit()

    def read_text(self, rel: str) -> str:
        path = self.checked(rel)
        if not path.is_file():
            raise VaultError(f"No note at {rel}.")
        return path.read_text(encoding="utf-8")

    def read_note(self, rel: str) -> VaultNote:
        path = self.checked(rel)
        return note_from_text(rel, self.read_text(rel), path)

    def write_text(self, rel: str, text: str) -> None:
        """Write a file. Must run inside ``changing``."""
        if self._txn is None:
            raise VaultError("Refusing to write outside a vault change.")
        normal = _norm_rel(rel)
        path = self.checked(normal)
        if normal not in self._txn.files:
            existed = path.exists()
            original = path.read_text(encoding="utf-8") if existed else None
            backup_rel = self._backup(normal, original) if existed and original is not None else None
            self._txn.files[normal] = _FileSnap(
                rel=normal,
                existed=existed,
                original=original,
                backup_rel=backup_rel,
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def ensure_scaffold(self) -> List[str]:
        """Create missing Tasks, Calendar, board, timeline, and activity log.

        Existing files are left byte-for-byte alone.
        """
        self.require_root()
        created: List[str] = []
        for folder in (TASKS_REL, CALENDAR_REL):
            path = self.checked(folder)
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
                created.append(folder + "/")
        templates = (
            (BOARD_REL, board_template()),
            (TIMELINE_REL, timeline_template()),
            (ACTIVITY_REL, activity_template()),
        )
        for rel, content in templates:
            path = self.checked(rel)
            if path.exists():
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            created.append(rel)
        return created

    def status(self) -> Dict[str, Any]:
        info: Dict[str, Any] = {
            "path": str(self.root),
            "exists": self.root.is_dir(),
            "notes": 0,
            "tasks": 0,
            "events": 0,
            "scaffold_created": [],
            "last_activity": "",
        }
        if not info["exists"]:
            return info
        info["scaffold_created"] = self.ensure_scaffold()
        notes = self.list_notes()
        info["notes"] = len(notes)
        info["tasks"] = sum(1 for note in notes if note.kind == "task" or note.rel.startswith(TASKS_REL + "/"))
        info["events"] = len(self.list_events())
        info["last_activity"] = self.last_activity()
        return info

    def list_notes(self, area: str = "", kind: str = "") -> List[VaultNote]:
        if not self.root.is_dir():
            return []
        want_area = resolve_area(area, default="") if area else ""
        want_kind = (kind or "").strip().lower()
        found: List[VaultNote] = []
        for rel, path in self._markdown_files():
            note = note_from_text(rel, path.read_text(encoding="utf-8"), path)
            if want_area and note.area != want_area and not rel.startswith(want_area + "/"):
                continue
            if want_kind and note.kind != want_kind:
                if not (want_kind == "task" and rel.startswith(TASKS_REL + "/")):
                    continue
            found.append(note)
        found.sort(key=lambda note: note.rel.lower())
        return found

    def list_events(self) -> List[VaultNote]:
        """Full-note events under ``10 Bolt/Calendar``. The index note is not an event."""
        if not self.root.is_dir():
            return []
        events: List[VaultNote] = []
        folder = self.root / CALENDAR_REL
        if not folder.is_dir():
            return []
        for path in sorted(folder.rglob("*.md")):
            if not path.is_file() or path.is_symlink():
                continue
            if path.name == CALENDAR_INDEX_NAME:
                continue
            rel = path.resolve().relative_to(self.root.resolve()).as_posix()
            note = note_from_text(rel, path.read_text(encoding="utf-8"), path)
            if note.frontmatter.get("cancelled") is True:
                continue
            if not str(note.frontmatter.get("date") or "").strip():
                continue
            events.append(note)
        return events

    def find(self, query: str, limit: int = 20) -> List[VaultNote]:
        tokens = [tok for tok in re.findall(r"[a-z0-9&+]+", (query or "").lower()) if len(tok) > 1]
        if not tokens or not self.root.is_dir():
            return []
        ranked: List[tuple[int, VaultNote]] = []
        for note in self.list_notes():
            title = note.title.lower()
            hay = f"{title}\n{note.body.lower()}\n{note.area.lower()}\n{note.rel.lower()}"
            hits = sum(1 for tok in tokens if tok in hay)
            if hits == 0:
                continue
            title_hits = sum(2 for tok in tokens if tok in title)
            ranked.append((hits + title_hits, note))
        ranked.sort(key=lambda item: (-item[0], item[1].rel.lower()))
        return [note for _score, note in ranked[: max(1, limit)]]

    def add_note(
        self,
        title: str,
        *,
        kind: str = "task",
        area: str = "",
        due: str = "",
        body: str = "",
        status: str = "inbox",
        source: str = "cli",
        extra: Optional[Dict[str, Any]] = None,
        folder_rel: str = "",
        grouped: bool = True,
    ) -> VaultNote:
        """Create a task, note, or page. Existing files are not overwritten.

        ``grouped=False`` writes inside a change the caller already opened,
        so several notes undo as one step.
        """
        self.require_root()
        self.ensure_scaffold()
        kind = (kind or "task").strip().lower()
        if kind not in ("task", "note", "page"):
            raise VaultError("Kind must be task, note, or page.")
        title = re.sub(r"\s+", " ", (title or "").strip())
        if not title:
            raise VaultError("A note needs a title.")
        area_name = resolve_area(area) if area else ("10 Bolt" if kind == "task" else "00 Inbox")
        if kind == "task":
            folder = TASKS_REL
        else:
            folder = folder_rel.strip("/") if folder_rel else area_name
        rel = self._unique_rel(f"{folder}/{safe_note_filename(title)}")
        created = now_ct().isoformat(timespec="seconds")
        meta: Dict[str, Any] = {
            "title": title,
            "type": kind,
            "status": (status or "inbox").strip().lower(),
            "area": area_name,
            "source": source,
            "created": created,
        }
        if due:
            meta["due"] = due
        if extra:
            for key, value in extra.items():
                if value is not None and value != "":
                    meta[key] = value
        note_body = f"# {title}\n"
        if body.strip():
            note_body += "\n" + body.strip() + "\n"
        text = dump_frontmatter(meta, note_body)

        def _write() -> None:
            self.write_text(rel, text)
            self.append_activity(
                f"add {kind}",
                title,
                f"{rel}; area {area_name}" + (f"; due {due}" if due else ""),
            )

        if grouped:
            with self.changing(f"add {kind} {title}"):
                _write()
                if kind == "task":
                    self._push_board()
        else:
            _write()
            if kind == "task":
                self._push_board()
        return self.read_note(rel) if grouped else VaultNote(rel, title, meta, note_body, self.checked(rel))

    def add_many(self, specs: List[Dict[str, Any]]) -> List[VaultNote]:
        """Create several notes in one undo step."""
        self.require_root()
        self.ensure_scaffold()
        if not specs:
            return []
        made: List[str] = []
        with self.changing("add notes from chat"):
            for spec in specs:
                note = self.add_note(grouped=False, **spec)
                made.append(note.rel)
            self._push_board()
        return [self.read_note(rel) for rel in made]

    def refile_many(self, moves: List[tuple[str, str]]) -> List[VaultNote]:
        """Set area on each note. Tasks stay in ``10 Bolt/Tasks``. Notes move.

        The old note bytes are parked under ``.bolt/undone/`` when a note moves.
        """
        self.require_root()
        if not moves:
            return []
        made: List[str] = []
        with self.changing("refile notes"):
            for rel, area in moves:
                made.append(self._refile_inside(rel, area))
            self._push_board()
        return [self.read_note(rel) for rel in made]

    def _refile_inside(self, rel: str, area: str) -> str:
        """Caller already opened ``changing``."""
        note = self.read_note(rel)
        area_name = resolve_area(area)
        meta = dict(note.frontmatter)
        meta["area"] = area_name
        body = note.body if note.body.startswith("\n") or note.body == "" else "\n" + note.body
        text = dump_frontmatter(meta, body)
        task = note.kind == "task" or rel.startswith(TASKS_REL + "/")
        if task or rel.startswith(area_name + "/"):
            self.write_text(rel, text)
            self.append_activity("refile", note.title, f"area {area_name}; stayed {rel}")
            return rel
        new_rel = self._unique_rel(f"{area_name}/{Path(rel).name}")
        self.write_text(new_rel, text)
        self.write_text(rel, self.read_text(rel))
        self._park(self.checked(rel), rel)
        self.append_activity("refile", note.title, f"{rel} -> {new_rel}")
        return new_rel

    def update_frontmatter(self, rel: str, updates: Dict[str, Any], *, summary: str) -> VaultNote:
        note = self.read_note(rel)
        meta = dict(note.frontmatter)
        for key, value in updates.items():
            if value is None:
                meta.pop(key, None)
            else:
                meta[key] = value
        text = dump_frontmatter(meta, note.body if note.body.startswith("\n") else "\n" + note.body)
        with self.changing(summary):
            self.write_text(rel, text)
            self.append_activity("update", note.title, summary)
            self._push_board()
        return self.read_note(rel)

    def _push_board(self) -> None:
        """Refresh kanban cards inside the open change. A bad board module must not block writes."""
        if self._txn is None:
            return
        try:
            from modules.Vault_Board import push_inside
        except Exception:
            return
        push_inside(self)

    def append_activity(self, action: str, note: str, details: str) -> None:
        """Add one activity-log row. Call inside ``changing``."""
        path = self.checked(ACTIVITY_REL)
        current = path.read_text(encoding="utf-8") if path.exists() else activity_template()
        row = f"| {_cell(_ct_stamp())} | {_cell(action)} | {_cell(note)} | {_cell(details)} |"
        self.write_text(ACTIVITY_REL, _insert_activity_row(current, row))

    def last_activity(self) -> str:
        path = self.root / ACTIVITY_REL
        if not path.is_file():
            return ""
        rows = [line for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("|")]
        data = [line for line in rows if "---" not in line and "When (CT)" not in line]
        return data[-1] if data else ""

    def undo(self) -> str:
        """Restore the last change. Created notes are parked, not deleted."""
        self.require_root()
        stack = self._load_undo()
        if not stack:
            return "Nothing to undo."
        record = stack.pop()
        self._save_undo(stack)
        restored: List[str] = []
        for item in record.get("files") or []:
            rel = str(item.get("rel") or "")
            if not rel or rel == ".bolt/undo.json":
                continue
            path = self.checked(rel)
            if item.get("existed"):
                backup_rel = item.get("backup")
                if backup_rel:
                    original = self.checked(str(backup_rel)).read_text(encoding="utf-8")
                else:
                    original = item.get("original")
                    if original is None:
                        continue
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(str(original), encoding="utf-8")
            elif path.exists() and not path.is_symlink():
                self._park(path, rel)
            restored.append(rel)
        summary = str(record.get("summary") or "the last change")
        self._append_undo_row(summary)
        names = ", ".join(restored) if restored else summary
        return f"Undid {summary}. Restored {names}."

    def _append_undo_row(self, summary: str) -> None:
        """Log the undo itself without pushing another undo record."""
        path = self.checked(ACTIVITY_REL)
        if not path.exists():
            return
        current = path.read_text(encoding="utf-8")
        backup_name = self._backup(ACTIVITY_REL, current)
        row = f"| {_cell(_ct_stamp())} | undo | {_cell(summary)} | backup {backup_name} |"
        path.write_text(_insert_activity_row(current, row), encoding="utf-8")

    def _unique_rel(self, rel: str) -> str:
        normal = _norm_rel(rel)
        path = self.checked(normal)
        if not path.exists():
            return normal
        stem = Path(normal).stem
        parent = Path(normal).parent.as_posix()
        if parent == ".":
            parent = ""
        for n in range(2, 50):
            name = f"{stem} {n}.md"
            candidate = f"{parent}/{name}" if parent else name
            if not self.checked(candidate).exists():
                return candidate
        raise VaultError(f"Too many notes already named {stem}.")

    def _markdown_files(self) -> Iterator[tuple[str, Path]]:
        root = self.root.resolve()
        for path in sorted(root.rglob("*.md")):
            if not path.is_file() or path.is_symlink():
                continue
            if any(part in _SKIP_DIR_NAMES for part in path.relative_to(root).parts):
                continue
            rel = path.relative_to(root).as_posix()
            yield rel, path

    def _backup(self, rel: str, original: str) -> str:
        stamp = now_ct().strftime("%Y%m%dT%H%M%S%f")
        flat = rel.replace("/", "__")
        backup_rel = f".bolt/backups/{stamp}__{flat}"
        dest = self.checked(backup_rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(original, encoding="utf-8")
        return backup_rel

    def _park(self, path: Path, rel: str) -> str:
        stamp = now_ct().strftime("%Y%m%dT%H%M%S%f")
        parked = f".bolt/undone/{stamp}/{rel}"
        dest = self.checked(parked)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(dest))
        return parked

    def _commit(self) -> None:
        txn = self._txn
        self._txn = None
        if txn is None or not txn.files:
            return
        stack = self._load_undo()
        stack.append(
            {
                "summary": txn.summary,
                "at": now_ct().isoformat(timespec="seconds"),
                "files": [
                    {
                        "rel": snap.rel,
                        "existed": snap.existed,
                        "backup": snap.backup_rel,
                        "original": None if snap.backup_rel else snap.original,
                    }
                    for snap in txn.files.values()
                ],
            }
        )
        self._save_undo(stack[-20:])

    def _rollback(self) -> None:
        txn = self._txn
        self._txn = None
        if txn is None:
            return
        for snap in reversed(list(txn.files.values())):
            path = self.checked(snap.rel)
            if snap.existed and snap.original is not None:
                path.write_text(snap.original, encoding="utf-8")
            elif not snap.existed and path.exists() and not path.is_symlink():
                self._park(path, snap.rel)

    def _undo_path(self) -> Path:
        return self.checked(".bolt/undo.json")

    def _load_undo(self) -> List[Dict[str, Any]]:
        path = self.root / ".bolt" / "undo.json"
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        if isinstance(data, list):
            return data
        return []

    def _save_undo(self, stack: List[Dict[str, Any]]) -> None:
        path = self._undo_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(stack, indent=2), encoding="utf-8")


def _norm_rel(rel: str) -> str:
    raw = (rel or "").replace("\\", "/").strip()
    if not raw:
        raise VaultError("Empty vault path.")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise VaultError("Vault paths stay relative to the vault.")
    parts = [part for part in raw.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise VaultError("That path leaves the vault.")
    return "/".join(parts)


def _insert_activity_row(current: str, row: str) -> str:
    lines = current.splitlines()
    header_at = None
    for i, line in enumerate(lines):
        if line.strip().startswith("|") and "When (CT)" in line and "Action" in line:
            header_at = i
            break
    if header_at is None:
        extra = (
            "\n\n| When (CT) | Action | Note | Details |\n"
            "| --- | --- | --- | --- |\n"
            f"{row}\n"
        )
        return current.rstrip() + extra
    end = header_at + 1
    while end < len(lines) and lines[end].strip().startswith("|"):
        end += 1
    lines.insert(end, row)
    text = "\n".join(lines)
    if not text.endswith("\n"):
        text += "\n"
    return text


def _print_status(info: Dict[str, Any]) -> None:
    print(f"Vault: {info['path']}")
    if not info["exists"]:
        print("The vault folder is not there. Set BOLT_VAULT_PATH and try again.")
        return
    print(f"Notes: {info['notes']}    Tasks: {info['tasks']}    Events: {info['events']}")
    if info["scaffold_created"]:
        print("Created missing pieces: " + ", ".join(info["scaffold_created"]))
    if info["last_activity"]:
        print("Last change: " + info["last_activity"])


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="bolt vault", description="Read and write the Obsidian vault.")
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("status", help="Show the vault path and counts")

    list_p = sub.add_parser("list", help="List notes")
    list_p.add_argument("--area", default="")
    list_p.add_argument("--kind", default="")

    find_p = sub.add_parser("find", help="Find notes by words in the title or body")
    find_p.add_argument("query", nargs="+")

    add_p = sub.add_parser("add", help="Add a task, note, or page")
    add_p.add_argument("title")
    add_p.add_argument("--kind", choices=("task", "note", "page"), default="task")
    add_p.add_argument("--area", default="")
    add_p.add_argument("--due", default="")
    add_p.add_argument("--body", default="")
    add_p.add_argument("--status", default="inbox")

    sub.add_parser("undo", help="Undo the last vault change")

    args = parser.parse_args(argv)
    cmd = args.cmd or "status"
    store = VaultStore()
    try:
        if cmd == "status":
            info = store.status()
            if args.json:
                print(json.dumps(info, indent=2))
            else:
                _print_status(info)
            return 0
        if cmd == "list":
            notes = store.list_notes(area=args.area, kind=args.kind)
            if args.json:
                print(json.dumps([{"title": n.title, "rel": n.rel, "area": n.area, "kind": n.kind} for n in notes], indent=2))
            elif not notes:
                print("No matching notes.")
            else:
                for note in notes:
                    print(f"{note.rel}  —  {note.title}")
            return 0
        if cmd == "find":
            notes = store.find(" ".join(args.query))
            if args.json:
                print(json.dumps([{"title": n.title, "rel": n.rel, "area": n.area} for n in notes], indent=2))
            elif not notes:
                print("No notes matched.")
            else:
                for note in notes:
                    print(f"{note.title}  ({note.rel})")
            return 0
        if cmd == "add":
            note = store.add_note(
                args.title,
                kind=args.kind,
                area=args.area,
                due=args.due,
                body=args.body,
                status=args.status,
                source="cli",
            )
            print(f"Added {note.kind}: {note.title}")
            print(note.rel)
            return 0
        if cmd == "undo":
            print(store.undo())
            return 0
    except VaultError as exc:
        print(f"bolt vault: {exc}")
        return 1
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
