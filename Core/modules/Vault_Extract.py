#!/usr/bin/env python3
"""Turn the recent conversation into tasks or a page. A separate, longer model call.

Light budget stays on Ollama unless planning is allowed. William approves the
whole list, some numbers, or none.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from modules.Vault_Capture import choose_area
from modules.Vault_Dates import When, now_ct, parse_when, speak_when
from modules.Vault_Pending import clear_pending, register_applier, save_pending
from modules.Vault_Store import VaultError, VaultStore, resolve_area, vault_exists

_TASKS = re.compile(
    r"^(?:please\s+)?(?:turn|make|pull|convert)\s+(?:this|that|our chat|the conversation)\s+into\s+tasks\b",
    re.I,
)
_PAGE = re.compile(
    r"^(?:please\s+)?(?:make|write|create)\s+(?:a\s+)?page\s+from\s+(?:this|that|our chat|the conversation)\b",
    re.I,
)

_REPO = Path(__file__).resolve().parents[2]
_DEFAULT_HISTORY = _REPO / "Data" / "conversations" / "voice_history.json"
Ask = Callable[..., str]


def history_path() -> Path:
    raw = (os.getenv("BOLT_CHAT_HISTORY_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return _DEFAULT_HISTORY


def try_extract(text: str) -> Optional[str]:
    soft = re.sub(r"\s+", " ", (text or "").strip())
    want_tasks = bool(_TASKS.search(soft))
    want_page = bool(_PAGE.search(soft))
    if not want_tasks and not want_page:
        return None
    if not vault_exists():
        return (
            "I can't see the vault yet, so I didn't make those notes. "
            "Set BOLT_VAULT_PATH and ask again."
        )
    turns = _load_turns(history_path())
    usable = [
        turn
        for turn in turns
        if str(turn.get("content") or "").strip()
        and str(turn.get("content") or "").strip() != soft
    ]
    if not usable:
        return "I don't have a recent conversation to read yet. Talk a bit, then ask again."
    raw = _ask_model(usable[-16:], want_tasks=want_tasks, want_page=want_page)
    if raw.startswith("LLM unavailable"):
        return "I couldn't reach a model to read that conversation, so I didn't save anything."
    try:
        items = _items_from_model(raw, want_tasks=want_tasks, want_page=want_page)
    except VaultError as exc:
        return str(exc)
    if not items:
        return "I didn't find tasks or a page in that conversation, so I didn't save anything."
    spoken = speak_batch(items)
    save_pending({"kind": "batch", "items": items, "spoken": spoken})
    return spoken


def speak_batch(items: List[Dict[str, Any]]) -> str:
    bits = []
    for index, item in enumerate(items, start=1):
        kind = "page" if item.get("type") == "page" else "task"
        due = item.get("due") or ""
        when = f", due {_speak_due(str(due))}" if due else ""
        bits.append(f"{index}, {item.get('title')}, {kind} in {item.get('area')}{when}")
    listed = ". ".join(bits)
    return (
        f"I found {len(items)}. {listed}. "
        "Say yes for all of them, only 1 and 3 to keep some, or no."
    )


def apply_batch(pending: Dict[str, Any]) -> str:
    items = list(pending.get("items") or [])
    picked = pending.get("picked") or list(range(1, len(items) + 1))
    chosen = [items[num - 1] for num in picked if 1 <= num <= len(items)]
    if not chosen:
        clear_pending()
        return "Okay, I won't save those."
    if not vault_exists():
        raise VaultError("I can't see the vault yet, so I didn't save those.")
    specs = []
    for item in chosen:
        specs.append(
            {
                "title": item["title"],
                "kind": item.get("type") or "task",
                "area": item.get("area") or "",
                "due": item.get("due") or "",
                "body": item.get("body") or "",
                "source": "chat",
                "status": "inbox",
            }
        )
    notes = VaultStore().add_many(specs)
    clear_pending()
    names = ", ".join(note.title for note in notes)
    return f"Saved {len(notes)}: {names}."


def _ask_model(turns: List[Dict[str, Any]], *, want_tasks: bool, want_page: bool) -> str:
    # Imported here so a missing model stack cannot block vault routing.
    from modules.LLM_Handler import ask_llm

    transcript = "\n".join(
        f"{turn.get('role', 'user')}: {str(turn.get('content') or '')[:500]}" for turn in turns
    )
    want = []
    if want_tasks:
        want.append("tasks")
    if want_page:
        want.append("one page")
    prompt = (
        "Read this conversation with William and pull out "
        + " and ".join(want)
        + ". Reply with JSON only, no markdown:\n"
        '{"tasks":[{"title":"","due":"Friday or YYYY-MM-DD or empty","area":"folder name or empty"}],'
        '"page":{"title":"","area":"","body":""} or null}\n'
        "Use his words for titles. Leave area empty if you are unsure. "
        "Do not invent tasks he did not talk about.\n\n"
        + transcript
    )
    return ask_llm(
        prompt,
        system="You extract notes for William's vault. JSON only.",
        max_tokens=900,
        temperature=0.2,
        task_type="planning",
        complexity="high",
    )


def _items_from_model(raw: str, *, want_tasks: bool, want_page: bool) -> List[Dict[str, Any]]:
    data = _parse_json(raw)
    items: List[Dict[str, Any]] = []
    if want_tasks:
        for row in data.get("tasks") or []:
            if not isinstance(row, dict):
                continue
            title = _tidy(str(row.get("title") or ""))
            if not title:
                continue
            items.append(
                {
                    "type": "task",
                    "title": title,
                    "due": _due(str(row.get("due") or "")),
                    "area": _area(str(row.get("area") or ""), title),
                    "body": "",
                }
            )
    if want_page and isinstance(data.get("page"), dict):
        page = data["page"]
        title = _tidy(str(page.get("title") or ""))
        body = str(page.get("body") or "").strip()
        if title:
            items.append(
                {
                    "type": "page",
                    "title": title,
                    "due": "",
                    "area": _area(str(page.get("area") or ""), title + " " + body),
                    "body": body,
                }
            )
    return items


def _parse_json(raw: str) -> Dict[str, Any]:
    text = (raw or "").strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise VaultError("I couldn't read a task list from the model, so I didn't save anything.")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise VaultError("I couldn't read a task list from the model, so I didn't save anything.") from exc
    if not isinstance(data, dict):
        raise VaultError("I couldn't read a task list from the model, so I didn't save anything.")
    return data


def _due(raw: str) -> str:
    text = (raw or "").strip()
    if not text or text.lower() in ("null", "none", "empty"):
        return ""
    if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", text):
        return text
    found = parse_when(text, now=now_ct())
    return found.iso_date if found else ""


def _area(raw: str, fallback_text: str) -> str:
    text = (raw or "").strip()
    if text and text.lower() not in ("null", "none", "empty"):
        try:
            return resolve_area(text)
        except VaultError:
            pass
    return choose_area(fallback_text)


def _speak_due(iso: str) -> str:
    try:
        year, month, day = (int(part) for part in iso.split("-"))
        return speak_when(When(date(year, month, day)))
    except ValueError:
        return iso


def _tidy(title: str) -> str:
    text = re.sub(r"\s+", " ", (title or "").strip()).strip(" .\"'")
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text


def _load_turns(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


register_applier("batch", apply_batch)
