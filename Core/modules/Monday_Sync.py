#!/usr/bin/env python3
"""Two-way sync between the Obsidian vault and William's Monday board.

The vault stays the source of truth. Monday is the phone view: the same
lanes as ``10 Bolt/Bolt Board.md`` (Inbox, This Week, Doing, Done), plus
calendar events and pages. Bolt pushes when it saves a task, event, or page.
``bolt monday sync`` also pulls phone edits. The newest edit wins. When both
sides changed at the same second, the vault wins.

Nothing here deletes a vault note. A missing Monday card is logged and left
alone. The feature stays off until ``MONDAY_API_TOKEN`` is set, and a down
or rate-limited Monday is logged without stopping Bolt.

Column ids, status indexes, and group ids live in ``BOARD`` below.
"""

from __future__ import annotations

import sys
from pathlib import Path

_CORE = Path(__file__).resolve().parents[1]
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

import argparse
import hashlib
import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import quote

import requests

from modules.Vault_Filing import pick_area
from modules.Vault_Store import (
    ACTIVITY_REL,
    BOARD_REL,
    CALENDAR_INDEX_REL,
    CALENDAR_REL,
    LANE_FOR_STATUS,
    STATUS_FOR_LANE,
    TASKS_REL,
    TIMELINE_REL,
    VaultError,
    VaultNote,
    VaultStore,
    dump_frontmatter,
    now_ct,
)

logger = logging.getLogger("bolt.monday")

API_URL = "https://api.monday.com/v2"
API_VERSION = "2024-10"
_SOFT = "Monday unavailable:"
_STATE_REL = ".bolt/monday_sync.json"
_REPO = Path(__file__).resolve().parents[2]

# One map for the live board. Indexes are Monday's label indexes, not positions.
BOARD: Dict[str, Any] = {
    "id": "18436882096",
    "groups": {
        "Inbox": "group_mm8eyqj0",
        "This Week": "group_mm8em8sq",
        "Doing": "group_mm8epgcj",
        "Done": "group_mm8ep1be",
    },
    "columns": {
        "status": "status",
        "area": "area",
        "type": "type",
        "due": "due",
        "event_time": "event_time",
        "vault_note": "vault_note",
        "vault_link": "vault_link",
        "last_synced": "last_synced",
    },
    "status": {"To do": 17, "Working on it": 0, "Done": 1},
    "area": {
        "Bolt": 9,
        "Creator HQ & Content": 4,
        "Product Testing": 1,
        "Career & Creator Plan": 7,
        "Personal": 0,
        "Inbox": 17,
    },
    "type": {"Task": 3, "Event": 11, "Page": 8},
    "folder_area": {
        "00 Inbox": "Inbox",
        "10 Bolt": "Bolt",
        "20 Creator HQ & Content": "Creator HQ & Content",
        "30 Product Testing": "Product Testing",
        "40 Career & Creator Plan": "Career & Creator Plan",
        "50 Personal": "Personal",
    },
}

_GROUP_LANE = {group: lane for lane, group in BOARD["groups"].items()}
_STATUS_LABEL = {index: label for label, index in BOARD["status"].items()}
_AREA_LABEL = {index: label for label, index in BOARD["area"].items()}
_TYPE_LABEL = {index: label for label, index in BOARD["type"].items()}
_AREA_FOLDER = {label: folder for folder, label in BOARD["folder_area"].items()}
_SKIP_RELS = {BOARD_REL, TIMELINE_REL, ACTIVITY_REL, CALENDAR_INDEX_REL}

_lock = threading.Lock()
_local = threading.local()
_dotenv_loaded = False
_watch_thread: Optional[threading.Thread] = None


class MondayOffline(Exception):
    """Monday did not answer. Callers log this and keep going."""


@dataclass
class Item:
    id: str
    name: str
    updated_at: str
    group_id: str
    columns: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def text(self, column: str) -> str:
        raw = self.columns.get(BOARD["columns"][column]) or {}
        text = str(raw.get("text") or "").strip()
        if text:
            return text
        value = _parse_value(raw.get("value"))
        if isinstance(value, str):
            return value.strip()
        return ""

    def value(self, column: str) -> Any:
        raw = self.columns.get(BOARD["columns"][column]) or {}
        return _parse_value(raw.get("value"))

    @property
    def vault_note(self) -> str:
        return self.text("vault_note").replace("\\", "/")

    @property
    def status_label(self) -> str:
        label = self.text("status")
        if label:
            return label
        value = self.value("status")
        if isinstance(value, dict) and "index" in value:
            return _STATUS_LABEL.get(value.get("index"), "")
        return ""

    @property
    def area_label(self) -> str:
        label = self.text("area")
        if label:
            return label
        value = self.value("area")
        if isinstance(value, dict) and "index" in value:
            return _AREA_LABEL.get(value.get("index"), "")
        return ""

    @property
    def type_label(self) -> str:
        label = self.text("type")
        if label:
            return label
        value = self.value("type")
        if isinstance(value, dict) and "index" in value:
            return _TYPE_LABEL.get(value.get("index"), "")
        return ""

    @property
    def due(self) -> str:
        value = self.value("due")
        if isinstance(value, dict) and value.get("date"):
            return str(value["date"])[:10]
        text = self.text("due")
        return text[:10] if len(text) >= 10 and text[4:5] == "-" else ""

    @property
    def timeline(self) -> tuple[str, str]:
        value = self.value("event_time")
        if not isinstance(value, dict):
            return "", ""
        return str(value.get("from") or ""), str(value.get("to") or "")


def board_id() -> str:
    return (os.getenv("MONDAY_BOARD_ID") or str(BOARD["id"])).strip()


def sync_interval() -> int:
    raw = (os.getenv("MONDAY_SYNC_INTERVAL") or _env_value("MONDAY_SYNC_INTERVAL") or "300").strip()
    try:
        value = int(float(raw))
    except ValueError:
        value = 300
    return max(15, value)


def enabled() -> bool:
    """True only when the process already has a token. Does not read .env."""
    if (os.getenv("MONDAY_SYNC") or "").strip().lower() in {"0", "off", "false", "no"}:
        return False
    return bool((os.getenv("MONDAY_API_TOKEN") or "").strip())


def token_configured() -> bool:
    """Token in the environment or in .env / .env.local, without loading them."""
    if (os.getenv("MONDAY_API_TOKEN") or "").strip():
        return True
    return bool(_env_value("MONDAY_API_TOKEN"))


def cron_expression() -> str:
    minutes = max(1, round(sync_interval() / 60))
    if minutes <= 1:
        return "* * * * *"
    if minutes < 60:
        return f"*/{minutes} * * * *"
    return "0 * * * *"


def desired_cron_entry(python: str, repo: Path, log_dir: Path) -> Optional[Dict[str, str]]:
    """Cron line for mac-auto install. Omitted until a token exists."""
    if not token_configured():
        return None
    script = repo / "Core" / "modules" / "Monday_Sync.py"
    log = log_dir / "monday_sync.log"
    return {
        "key": "Monday_Sync",
        "comment": "# Monday board: keep the phone board in step with the vault",
        "line": f"{cron_expression()} cd {repo} && {python} {script} sync >> {log} 2>&1",
    }


def push_after_commit(store: VaultStore, rels: List[str]) -> None:
    """Push notes Bolt just saved. Never raises. Pull stays on sync and watch."""
    if not rels or _busy():
        return
    _load_dotenv()
    if not enabled():
        return
    if not _lock.acquire(blocking=False):
        logger.info("Monday sync is already running; this save waits for the next pass.")
        return
    try:
        with _hold():
            _push_rels(store, rels)
    except Exception as exc:
        logger.warning("%s", _down_text(str(exc)))
    finally:
        _lock.release()


def sync(*, store: Optional[VaultStore] = None, dry_run: bool = False) -> Dict[str, Any]:
    """Push vault notes and pull phone edits. Returns a result dict. Never raises."""
    _load_dotenv()
    result = _empty_result(dry_run)
    if not enabled():
        result["disabled"] = True
        result["message"] = "Monday sync is off until MONDAY_API_TOKEN is set in .env."
        return result
    if not _lock.acquire(blocking=False):
        result["message"] = "A Monday sync is already running."
        return result
    try:
        with _hold():
            return _sync_body(store or VaultStore(), dry_run, result)
    except MondayOffline as exc:
        text = _down_text(str(exc))
        logger.warning("%s", text)
        result["ok"] = False
        result["error"] = text
        result["message"] = text
        return result
    except VaultError as exc:
        logger.warning("Monday sync left the vault unchanged: %s", exc)
        result["ok"] = False
        result["error"] = str(exc)
        result["message"] = str(exc)
        return result
    except Exception as exc:
        text = _down_text(str(exc))
        logger.warning("%s", text)
        result["ok"] = False
        result["error"] = text
        result["message"] = text
        return result
    finally:
        _lock.release()


def start_background_watch() -> bool:
    """Daemon thread for live Bolt. No-op without a token. Returns whether it is running."""
    global _watch_thread
    _load_dotenv()
    if not enabled():
        return False
    if _watch_thread is not None and _watch_thread.is_alive():
        return True

    def _loop() -> None:
        while True:
            try:
                sync()
            except Exception as exc:
                logger.warning("%s", _down_text(str(exc)))
            time.sleep(sync_interval())

    _watch_thread = threading.Thread(target=_loop, name="monday-sync", daemon=True)
    _watch_thread.start()
    logger.info("Monday watch started, every %s seconds.", sync_interval())
    return True


def maybe_sync_from_scheduler() -> None:
    """One pass from briefing or another scheduled job. Never raises."""
    try:
        _load_dotenv()
        if not enabled():
            return
        sync()
    except Exception as exc:
        logger.warning("%s", _down_text(str(exc)))


def lane_from_monday(group_id: str, status_label: str) -> str:
    """Group is the lane. Done forces Done. Working on it forces Doing from Inbox."""
    group_lane = _GROUP_LANE.get(group_id or "", "Inbox")
    label = (status_label or "").strip().lower()
    if label == "done" or group_lane == "Done":
        return "Done"
    if group_lane == "Doing":
        return "Doing"
    if label == "working on it" and group_lane == "Inbox":
        return "Doing"
    return group_lane


def fingerprint(note: VaultNote) -> str:
    raw = json.dumps(_describe(note), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def vault_clock(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).replace(microsecond=0)


def save_state(store: VaultStore, state: Dict[str, Any]) -> None:
    path = store.root / _STATE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def load_state(store: VaultStore) -> Dict[str, Any]:
    path = store.root / _STATE_REL
    if not path.is_file():
        return {"version": 1, "items": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "items": {}}
    if not isinstance(data, dict):
        return {"version": 1, "items": {}}
    items = data.get("items")
    if not isinstance(items, dict):
        data["items"] = {}
    data["version"] = 1
    return data


def main(argv: Optional[List[str]] = None) -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(
        prog="bolt monday",
        description="Keep the Monday phone board in step with the Obsidian vault.",
    )
    sub = parser.add_subparsers(dest="cmd")

    status_p = sub.add_parser("status", help="Say whether Monday sync is on")
    status_p.add_argument("--json", action="store_true")

    sync_p = sub.add_parser("sync", help="Push the vault and pull phone edits")
    sync_p.add_argument("--dry-run", action="store_true")
    sync_p.add_argument("--json", action="store_true")

    sub.add_parser("watch", help="Keep syncing until Ctrl+C")

    args = parser.parse_args(argv)
    cmd = args.cmd or "status"
    try:
        if cmd == "watch":
            return _watch_cli()
        if cmd == "sync":
            result = sync(dry_run=bool(args.dry_run))
            _emit(result, as_json=bool(args.json))
            return 0
        info = _status_info()
        if bool(getattr(args, "json", False)):
            print(json.dumps(info, indent=2))
        else:
            print(info["message"])
        return 0
    except KeyboardInterrupt:
        print("Stopped.")
        return 0


def _watch_cli() -> int:
    if not enabled():
        print("Monday sync is off until MONDAY_API_TOKEN is set in .env.")
        return 0
    interval = sync_interval()
    print(f"Watching the Monday board every {interval} seconds. Ctrl+C stops it.")
    while True:
        _emit(sync(), as_json=False)
        time.sleep(interval)


def _status_info() -> Dict[str, Any]:
    _load_dotenv()
    on = enabled()
    vault = VaultStore()
    message = (
        f"Monday sync is on. Board {board_id()}. Phone check every {sync_interval()} seconds."
        if on
        else "Monday sync is off until MONDAY_API_TOKEN is set in .env."
    )
    if on:
        message += f" Vault: {vault.root}"
    return {
        "on": on,
        "board_id": board_id() if on else "",
        "interval": sync_interval(),
        "vault": str(vault.root),
        "vault_exists": vault.root.is_dir(),
        "message": message,
    }


def _emit(result: Dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2))
        return
    print(result.get("message") or "Monday sync unchanged.")


def _sync_body(store: VaultStore, dry_run: bool, result: Dict[str, Any]) -> Dict[str, Any]:
    if not store.root.is_dir():
        result["ok"] = False
        result["error"] = f"Vault folder is not there yet: {store.root}"
        result["message"] = result["error"]
        return result
    client = MondayClient(board_id(), _token())
    items = client.fetch_items()
    by_path: Dict[str, Item] = {}
    for item in items:
        if item.vault_note and item.vault_note not in by_path:
            by_path[item.vault_note] = item
    state = load_state(store)
    saved_items: Dict[str, Dict[str, Any]] = state.setdefault("items", {})
    notes = _collect(store)
    by_rel = {note.rel: note for note in notes}
    pushes: List[tuple[VaultNote, Optional[Item]]] = []
    pulls: List[tuple[VaultNote, Item]] = []
    creates: List[Item] = []
    writebacks: List[tuple[str, Item]] = []

    for note in notes:
        item = by_path.get(note.rel)
        saved = saved_items.get(note.rel) or {}
        if item is None and saved.get("item_id"):
            if not saved.get("missing_on_monday"):
                saved["missing_on_monday"] = True
                result["kept"].append({"rel": note.rel, "title": note.title})
                logger.warning(
                    "Monday card for %s is gone. Left the vault note in place.",
                    note.rel,
                )
            continue
        if item is None:
            pushes.append((note, None))
            continue
        if saved.get("missing_on_monday"):
            saved["missing_on_monday"] = False
        winner = _winner(note, item, saved)
        if winner == "pull":
            pulls.append((note, item))
        elif winner == "push":
            pushes.append((note, item))

    known_ids = {str(row.get("item_id") or "") for row in saved_items.values()}
    for item in items:
        if item.vault_note:
            if item.vault_note not in by_rel and item.vault_note not in _SKIP_RELS:
                logger.warning(
                    "Monday card %s points at %s, and that note is not in the vault. Left it alone.",
                    item.name or item.id,
                    item.vault_note,
                )
            continue
        rel = _rel_for_item(saved_items, item.id)
        if rel and rel in by_rel:
            writebacks.append((rel, item))
            continue
        if item.id in known_ids and rel:
            continue
        creates.append(item)

    if dry_run:
        for note, item in pushes:
            result["pushed"].append(
                {"rel": note.rel, "title": note.title, "action": "would-create" if item is None else "would-update"}
            )
        for note, item in pulls:
            result["pulled"].append({"rel": note.rel, "title": item.name or note.title, "lane": _incoming_lane(item)})
        for item in creates:
            result["created"].append({"title": item.name or "Untitled", "lane": _incoming_lane(item)})
        result["message"] = _summary(result, dry_run=True)
        return result

    created_notes: List[tuple[VaultNote, Item]] = []
    if pulls or creates:
        with store.changing("monday sync"):
            for note, item in pulls:
                _apply_pull(store, note, item)
                result["pulled"].append({"rel": note.rel, "title": item.name or note.title, "lane": _incoming_lane(item)})
            for item in creates:
                note = _create_from_phone(store, item)
                created_notes.append((note, item))
                result["created"].append({"rel": note.rel, "title": note.title, "lane": _incoming_lane(item)})
            store._push_board()

    try:
        for note, item in pushes:
            fresh = store.read_note(note.rel)
            pushed = client.push(fresh, item)
            _remember(saved_items, fresh, pushed)
            result["pushed"].append(
                {"rel": fresh.rel, "title": fresh.title, "item_id": pushed["item_id"], "action": pushed["action"]}
            )
        for note, item in created_notes:
            fresh = store.read_note(note.rel)
            try:
                pushed = client.push(fresh, item)
            except MondayOffline:
                row = _remember(
                    saved_items,
                    fresh,
                    {"item_id": item.id, "updated_at": item.updated_at, "action": "link"},
                )
                row["needs_link"] = True
                raise
            row = _remember(saved_items, fresh, pushed)
            row["needs_link"] = False
        for rel, item in writebacks:
            note = store.read_note(rel)
            pushed = client.push(note, item)
            row = _remember(saved_items, note, pushed)
            row["needs_link"] = False
        for note, _item in pulls:
            fresh = store.read_note(note.rel)
            item = by_path.get(note.rel)
            if item is None:
                continue
            row = saved_items.setdefault(note.rel, {})
            row.update(_snapshot(fresh, item.id, item.updated_at))
            row["needs_link"] = False
            row["missing_on_monday"] = False
    finally:
        if result["pushed"] or result["pulled"] or result["created"] or result["kept"]:
            save_state(store, state)
    result["message"] = _summary(result, dry_run=False)
    return result


def _push_rels(store: VaultStore, rels: List[str]) -> None:
    if not store.root.is_dir():
        return
    notes: List[VaultNote] = []
    for rel in rels:
        if rel in _SKIP_RELS or rel.startswith(".bolt/"):
            continue
        try:
            note = store.read_note(rel)
        except VaultError:
            continue
        if _sync_kind(note):
            notes.append(note)
    if not notes:
        return
    client = MondayClient(board_id(), _token())
    items = client.fetch_items()
    by_path = {item.vault_note: item for item in items if item.vault_note}
    state = load_state(store)
    saved = state.setdefault("items", {})
    changed = False
    for note in notes:
        fresh = store.read_note(note.rel)
        item = by_path.get(fresh.rel)
        pushed = client.push(fresh, item)
        _remember(saved, fresh, pushed)
        if item is None:
            by_path[fresh.rel] = Item(
                id=pushed["item_id"],
                name=fresh.title,
                updated_at=pushed.get("updated_at") or "",
                group_id=pushed.get("group_id") or "",
            )
        changed = True
    if changed:
        save_state(store, state)


def _winner(note: VaultNote, item: Item, saved: Dict[str, Any]) -> str:
    current = fingerprint(note)
    if not saved or not saved.get("fingerprint"):
        vault_changed = True
        monday_changed = True
    else:
        vault_changed = current != saved.get("fingerprint")
        monday_changed = not _same_time(item.updated_at, str(saved.get("monday_updated_at") or ""))
    if vault_changed and monday_changed:
        vault_dt = vault_clock(note.path)
        monday_dt = _parse_time(item.updated_at)
        if monday_dt and monday_dt > vault_dt:
            return "pull"
        return "push"
    if monday_changed and not vault_changed:
        return "pull"
    if vault_changed and not monday_changed:
        return "push"
    return "skip"


def _apply_pull(store: VaultStore, note: VaultNote, item: Item) -> None:
    kind = _sync_kind(note)
    lane = _incoming_lane(item)
    title = (item.name or "").strip() or note.title
    meta = dict(note.frontmatter)
    meta["title"] = title
    meta["status"] = STATUS_FOR_LANE[lane]
    clock = _clock_from_item(item)
    if kind == "event":
        meta["type"] = "event"
        if clock["date"]:
            meta["date"] = clock["date"]
            meta["allDay"] = clock["all_day"]
            if clock["start"]:
                meta["startTime"] = clock["start"]
                meta["endTime"] = clock["end"]
            else:
                meta.pop("startTime", None)
                meta.pop("endTime", None)
            meta.pop("cancelled", None)
        else:
            for key in ("date", "startTime", "endTime", "allDay"):
                meta.pop(key, None)
    else:
        due = item.due or (clock["date"] if kind == "task" else "")
        if due:
            meta["due"] = due
        else:
            meta.pop("due", None)
    body = _retitle(note.body, note.title, title)
    if not body.startswith("\n"):
        body = "\n" + body
    store.write_text(note.rel, dump_frontmatter(meta, body))
    store.append_activity("monday", title, f"from phone, lane {lane}")


def _create_from_phone(store: VaultStore, item: Item) -> VaultNote:
    title = (item.name or "").strip() or "Untitled"
    kind, folder, area = _place_new(item)
    lane = _incoming_lane(item)
    status = STATUS_FOR_LANE[lane]
    if kind == "event":
        clock = _clock_from_item(item)
        return store.add_note(
            title,
            kind="page",
            area=area,
            status=status,
            source="monday",
            folder_rel=folder,
            grouped=False,
            extra={
                "type": "event",
                "allDay": clock["all_day"],
                "date": clock["date"] or None,
                "startTime": clock["start"] or None,
                "endTime": clock["end"] or None,
            },
        )
    return store.add_note(
        title,
        kind="task" if kind == "task" else "page",
        area=area,
        due=item.due,
        status=status,
        source="monday",
        folder_rel=folder,
        grouped=False,
    )


def _place_new(item: Item) -> tuple[str, str, str]:
    label = (item.type_label or "Task").strip().lower()
    if label == "event":
        return "event", CALENDAR_REL, "10 Bolt"
    area = _area_folder(item)
    if label == "page":
        return "page", area, area
    if area == "10 Bolt":
        return "task", TASKS_REL, area
    return "task", area, area


def _area_folder(item: Item) -> str:
    chosen = _AREA_FOLDER.get(item.area_label or "")
    if chosen and item.area_label != "Inbox":
        return chosen
    filed = pick_area(item.name or "").area
    return filed or "00 Inbox"


def _incoming_lane(item: Item) -> str:
    lane = lane_from_monday(item.group_id, item.status_label)
    return lane if lane in STATUS_FOR_LANE else "Inbox"


def _clock_from_item(item: Item) -> Dict[str, Any]:
    start_raw, end_raw = item.timeline
    start_day, start_clock = _split_stamp(start_raw)
    _end_day, end_clock = _split_stamp(end_raw)
    if start_day and start_clock:
        return {"date": start_day, "start": start_clock, "end": end_clock or _hour_later(start_clock), "all_day": False}
    if start_day:
        return {"date": start_day, "start": "", "end": "", "all_day": True}
    if item.due:
        return {"date": item.due, "start": "", "end": "", "all_day": True}
    return {"date": "", "start": "", "end": "", "all_day": True}


def _describe(note: VaultNote) -> Dict[str, Any]:
    kind = _sync_kind(note)
    clock = _event_clock(note) if kind == "event" else {"date": "", "start": "", "end": "", "all_day": True}
    due = str(note.frontmatter.get("due") or "")[:10]
    return {
        "title": note.title,
        "kind": kind,
        "lane": _lane_of(note, kind),
        "area": _folder_area(note.rel),
        "due": "" if kind == "event" else due,
        "date": clock["date"],
        "start": clock["start"],
        "end": clock["end"],
        "all_day": clock["all_day"] if kind == "event" else False,
        "body": note.body.strip(),
    }


def _sync_kind(note: VaultNote) -> str:
    rel = note.rel.replace("\\", "/")
    if rel in _SKIP_RELS or rel.startswith("90 ") or rel.startswith("90/"):
        return ""
    top = rel.split("/", 1)[0]
    if top.startswith("90 "):
        return ""
    if rel.startswith(CALENDAR_REL + "/") and Path(rel).name != Path(CALENDAR_INDEX_REL).name:
        return "event"
    kind = note.kind
    if kind == "event":
        return "event"
    if kind == "task" or rel.startswith(TASKS_REL + "/"):
        return "task"
    if kind == "page":
        return "page"
    return ""


def _lane_of(note: VaultNote, kind: str) -> str:
    if kind == "event" and note.frontmatter.get("cancelled") is True:
        return "Done"
    status = str(note.frontmatter.get("status") or "inbox").strip().lower()
    return LANE_FOR_STATUS.get(status, "Inbox")


def _folder_area(rel: str) -> str:
    top = rel.split("/", 1)[0]
    return BOARD["folder_area"].get(top, "Bolt")


def _event_clock(note: VaultNote) -> Dict[str, Any]:
    date = str(note.frontmatter.get("date") or "")[:10]
    start = str(note.frontmatter.get("startTime") or "")[:5]
    end = str(note.frontmatter.get("endTime") or "")[:5]
    if not date:
        return {"date": "", "start": "", "end": "", "all_day": True}
    if start:
        return {"date": date, "start": start, "end": end or _hour_later(start), "all_day": False}
    return {"date": date, "start": "", "end": "", "all_day": True}


def _column_values(note: VaultNote) -> Dict[str, Any]:
    kind = _sync_kind(note)
    lane = _lane_of(note, kind)
    status_label = {"Done": "Done", "Doing": "Working on it"}.get(lane, "To do")
    type_label = {"event": "Event", "page": "Page"}.get(kind, "Task")
    columns = BOARD["columns"]
    values: Dict[str, Any] = {
        columns["status"]: {"index": BOARD["status"][status_label]},
        columns["area"]: {"index": BOARD["area"].get(_folder_area(note.rel), BOARD["area"]["Bolt"])},
        columns["type"]: {"index": BOARD["type"][type_label]},
        columns["vault_note"]: note.rel,
        columns["vault_link"]: {"url": _obsidian_url(note), "text": note.title},
        columns["last_synced"]: {"date": now_ct().date().isoformat()},
    }
    clock = _event_clock(note) if kind == "event" else None
    due = clock["date"] if clock else str(note.frontmatter.get("due") or "")[:10]
    # null clears a date or timeline the phone still has.
    values[columns["due"]] = {"date": due or None}
    if kind == "event":
        if clock and clock["date"] and not clock["all_day"]:
            values[columns["event_time"]] = {
                "from": f"{clock['date']} {clock['start']}:00",
                "to": f"{clock['date']} {clock['end']}:00",
            }
        elif clock and clock["date"]:
            values[columns["event_time"]] = {"from": clock["date"], "to": clock["date"]}
        else:
            values[columns["event_time"]] = {"from": None, "to": None}
    return values


def _obsidian_url(note: VaultNote) -> str:
    """Obsidian open link. The vault name is the folder name, normally Bolt Vault."""
    return (
        f"obsidian://open?vault={quote(_vault_name(note), safe='')}"
        f"&file={quote(note.rel, safe='')}"
    )


def _vault_name(note: VaultNote) -> str:
    try:
        root = note.path
        for _part in Path(note.rel).parts:
            root = root.parent
        return root.name or "Bolt Vault"
    except (OSError, ValueError):
        return "Bolt Vault"


def _snapshot(note: VaultNote, item_id: str, updated_at: str) -> Dict[str, Any]:
    return {
        "item_id": str(item_id),
        "monday_updated_at": updated_at or "",
        "fingerprint": fingerprint(note),
        "vault_mtime": int(vault_clock(note.path).timestamp()),
        "group_id": BOARD["groups"].get(_lane_of(note, _sync_kind(note)), ""),
        "missing_on_monday": False,
    }


def _remember(saved: Dict[str, Dict[str, Any]], note: VaultNote, pushed: Dict[str, str]) -> Dict[str, Any]:
    row = _snapshot(note, pushed.get("item_id") or "", pushed.get("updated_at") or "")
    row["group_id"] = pushed.get("group_id") or row["group_id"]
    saved[note.rel] = {**saved.get(note.rel, {}), **row}
    return saved[note.rel]


def _rel_for_item(saved: Dict[str, Dict[str, Any]], item_id: str) -> str:
    for rel, row in saved.items():
        if str(row.get("item_id") or "") == str(item_id):
            return rel
    return ""


def _collect(store: VaultStore) -> List[VaultNote]:
    found = [note for note in store.list_notes() if _sync_kind(note)]
    found.sort(key=lambda note: note.rel.lower())
    return found


def _empty_result(dry_run: bool) -> Dict[str, Any]:
    return {
        "ok": True,
        "dry_run": dry_run,
        "disabled": False,
        "error": "",
        "message": "",
        "pushed": [],
        "pulled": [],
        "created": [],
        "kept": [],
    }


def _summary(result: Dict[str, Any], *, dry_run: bool) -> str:
    pushed = len(result["pushed"])
    pulled = len(result["pulled"])
    created = len(result["created"])
    kept = len(result["kept"])
    if not any((pushed, pulled, created, kept)):
        return "Monday sync dry run: unchanged." if dry_run else "Monday sync unchanged."
    verb = "would push" if dry_run else "pushed"
    pull_verb = "would pull" if dry_run else "pulled"
    add_verb = "would add" if dry_run else "added"
    bits = []
    if pushed:
        bits.append(f"{verb} {pushed}")
    if pulled:
        bits.append(f"{pull_verb} {pulled}")
    if created:
        names = ", ".join(str(row.get("title") or "Untitled") for row in result["created"])
        bits.append(f"{add_verb} {created} from your phone ({names})")
    text = "Monday sync" + (" dry run: " if dry_run else ": ") + ", ".join(bits) + "."
    if kept:
        text += f" Left {kept} vault note{'s' if kept != 1 else ''} in place (Monday card gone)."
    return text


def _retitle(body: str, old: str, new: str) -> str:
    if not new or new == old:
        return body
    lines = body.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("#"):
            current = line.lstrip("#").strip()
            if current == old or not current:
                lines[index] = f"# {new}"
            break
    text = "\n".join(lines)
    if body.endswith("\n"):
        text += "\n"
    return text


def _split_stamp(value: str) -> tuple[str, str]:
    raw = (value or "").strip()
    if not raw:
        return "", ""
    day = raw[:10]
    if len(day) != 10 or day[4] != "-" or day[7] != "-":
        return "", ""
    rest = raw[10:].strip()
    if not rest:
        return day, ""
    clock = rest[:5]
    if len(clock) == 5 and clock[2] == ":":
        return day, clock
    return day, ""


def _hour_later(clock: str) -> str:
    try:
        hour, minute = (int(part) for part in clock.split(":", 1))
    except ValueError:
        return ""
    start = datetime(2000, 1, 1, hour, minute) + timedelta(hours=1)
    return start.strftime("%H:%M")


def _parse_time(value: str) -> Optional[datetime]:
    raw = (value or "").strip()
    if not raw:
        return None
    raw = raw.replace("Z", "+00:00")
    if " " in raw and "T" not in raw:
        raw = raw.replace(" ", "T", 1)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def _same_time(left: str, right: str) -> bool:
    a = _parse_time(left)
    b = _parse_time(right)
    if a and b:
        return a == b
    return (left or "") == (right or "")


def _parse_value(raw: Any) -> Any:
    if raw is None or isinstance(raw, (dict, list)):
        return raw
    text = str(raw).strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _parse_items(rows: List[Dict[str, Any]]) -> Iterator[Item]:
    for row in rows or []:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        columns = {}
        for column in row.get("column_values") or []:
            if isinstance(column, dict) and column.get("id"):
                columns[str(column["id"])] = column
        group = row.get("group") or {}
        yield Item(
            id=str(row["id"]),
            name=str(row.get("name") or ""),
            updated_at=str(row.get("updated_at") or ""),
            group_id=str(group.get("id") or ""),
            columns=columns,
        )


class MondayClient:
    def __init__(self, board: str, token: str):
        self.board = board
        self.token = token

    def fetch_items(self) -> List[Item]:
        data = self._graphql(
            """
            query ($board: [ID!]!) {
              boards(ids: $board) {
                items_page(limit: 100) {
                  cursor
                  items {
                    id
                    name
                    updated_at
                    group { id }
                    column_values { id text value }
                  }
                }
              }
            }
            """,
            {"board": [self.board]},
        )
        boards = data.get("boards") or []
        if not boards or not isinstance(boards[0], dict):
            raise MondayOffline(f"{_SOFT} board not found")
        page = boards[0].get("items_page") or {}
        items = list(_parse_items(page.get("items") or []))
        cursor = page.get("cursor")
        hops = 0
        while cursor and hops < 50:
            hops += 1
            data = self._graphql(
                """
                query ($cursor: String!) {
                  next_items_page(cursor: $cursor, limit: 100) {
                    cursor
                    items {
                      id
                      name
                      updated_at
                      group { id }
                      column_values { id text value }
                    }
                  }
                }
                """,
                {"cursor": cursor},
            )
            page = data.get("next_items_page") or {}
            items.extend(_parse_items(page.get("items") or []))
            cursor = page.get("cursor")
        return items

    def push(self, note: VaultNote, item: Optional[Item]) -> Dict[str, str]:
        kind = _sync_kind(note)
        lane = _lane_of(note, kind)
        group_id = BOARD["groups"].get(lane, BOARD["groups"]["Inbox"])
        values = json.dumps(_column_values(note))
        name = note.title[:255]
        if item is None:
            created = self._graphql(
                """
                mutation ($board: ID!, $group: String!, $name: String!, $values: JSON!) {
                  create_item(
                    board_id: $board
                    group_id: $group
                    item_name: $name
                    column_values: $values
                  ) { id updated_at }
                }
                """,
                {"board": self.board, "group": group_id, "name": name, "values": values},
            ).get("create_item") or {}
            if not created.get("id"):
                raise MondayOffline(f"{_SOFT} create failed")
            return {
                "item_id": str(created["id"]),
                "updated_at": str(created.get("updated_at") or ""),
                "group_id": group_id,
                "action": "create",
            }
        updated_at = item.updated_at
        if item.group_id != group_id:
            moved = self._graphql(
                """
                mutation ($item: ID!, $group: String!) {
                  move_item_to_group(item_id: $item, group_id: $group) { id updated_at }
                }
                """,
                {"item": item.id, "group": group_id},
            ).get("move_item_to_group") or {}
            updated_at = str(moved.get("updated_at") or updated_at)
        changed = self._graphql(
            """
            mutation ($board: ID!, $item: ID!, $values: JSON!) {
              change_multiple_column_values(board_id: $board, item_id: $item, column_values: $values) {
                id
                updated_at
              }
            }
            """,
            {"board": self.board, "item": item.id, "values": values},
        ).get("change_multiple_column_values") or {}
        updated_at = str(changed.get("updated_at") or updated_at)
        if (item.name or "").strip() != name:
            renamed = self._graphql(
                """
                mutation ($board: ID!, $item: ID!, $value: String!) {
                  change_simple_column_value(
                    board_id: $board
                    item_id: $item
                    column_id: "name"
                    value: $value
                  ) { id updated_at }
                }
                """,
                {"board": self.board, "item": item.id, "value": name},
            ).get("change_simple_column_value") or {}
            updated_at = str(renamed.get("updated_at") or updated_at)
        return {"item_id": item.id, "updated_at": updated_at, "group_id": group_id, "action": "update"}

    def _graphql(self, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        if not self.token:
            raise MondayOffline(f"{_SOFT} token missing")
        try:
            response = requests.post(
                API_URL,
                json={"query": query, "variables": variables},
                headers={
                    "Authorization": self.token,
                    "Content-Type": "application/json",
                    "API-Version": API_VERSION,
                },
                timeout=(3.05, 20),
            )
        except requests.RequestException as exc:
            raise MondayOffline(f"{_SOFT} {exc}") from exc
        if response.status_code == 429 or response.status_code >= 500:
            raise MondayOffline(f"{_SOFT} HTTP {response.status_code}")
        if response.status_code >= 400:
            raise MondayOffline(f"{_SOFT} HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise MondayOffline(f"{_SOFT} bad JSON") from exc
        if not isinstance(payload, dict):
            raise MondayOffline(f"{_SOFT} bad JSON")
        errors = payload.get("errors") or []
        if errors:
            message = ""
            if isinstance(errors[0], dict):
                message = str(errors[0].get("message") or "request failed")
            raise MondayOffline(f"{_SOFT} {message or 'request failed'}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise MondayOffline(f"{_SOFT} empty response")
        return data


def _token() -> str:
    raw = (os.getenv("MONDAY_API_TOKEN") or "").strip()
    if raw.lower().startswith("bearer "):
        raw = raw[7:].strip()
    return raw


def _down_text(message: str) -> str:
    text = (message or "").strip() or "request failed"
    if text.startswith(_SOFT):
        return text
    return f"{_SOFT} {text}"


def _env_value(key: str) -> str:
    for name in (".env.local", ".env"):
        path = _REPO / name
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            found, raw = stripped.split("=", 1)
            if found.strip() != key:
                continue
            value = raw.strip().strip('"').strip("'")
            if value:
                return value
    return ""


def _load_dotenv() -> None:
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    _dotenv_loaded = True
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    load_dotenv(_REPO / ".env.local", override=False)
    load_dotenv(_REPO / ".env", override=False)


def _busy() -> bool:
    return getattr(_local, "depth", 0) > 0


@contextmanager
def _hold() -> Iterator[None]:
    _local.depth = getattr(_local, "depth", 0) + 1
    try:
        yield
    finally:
        _local.depth -= 1


if __name__ == "__main__":
    raise SystemExit(main())
