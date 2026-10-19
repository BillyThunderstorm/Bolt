#!/usr/bin/env python3
"""Preview waiting for yes / no / edit. Survives a restart.

The file is ``BOLT_PENDING_VAULT_PATH`` or ``Data/memory/pending_vault_changes.json``.
Tests point the env var at a temp file so tracked Data/ is left alone.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from modules.Vault_Dates import now_ct, parse_when
from modules.Vault_Store import VaultError, resolve_area

_REPO = Path(__file__).resolve().parents[2]
PENDING_NAME = _REPO / "Data" / "memory" / "pending_vault_changes.json"

_YES = re.compile(
    r"^(?:yes|yeah|yep|yup|save|do it|confirm|go ahead|ok|okay|sure)[.!]?$",
    re.I,
)
_NO = re.compile(
    r"^(?:no|nope|cancel|never mind|nevermind|stop|don'?t)[.!]?$",
    re.I,
)
_TITLE = re.compile(r"^change (?:the )?title to\s+(?P<title>.+)$", re.I)
_AREA = re.compile(
    r"^(?:put|file|move) (?:it|that) (?:in|into|under|to)\s+(?P<area>.+)$",
    re.I,
)
_UNDO = re.compile(r"^undo (?:that|it|the last change|the last vault change)[.!]?$", re.I)

Applier = Callable[[Dict[str, Any]], str]
_APPLIERS: Dict[str, Applier] = {}


def pending_path() -> Path:
    raw = (os.getenv("BOLT_PENDING_VAULT_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return PENDING_NAME


def register_applier(kind: str, fn: Applier) -> None:
    _APPLIERS[kind] = fn


def load_pending() -> Optional[Dict[str, Any]]:
    path = pending_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not data.get("kind"):
        return None
    return data


def save_pending(payload: Dict[str, Any]) -> None:
    path = pending_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def clear_pending() -> None:
    path = pending_path()
    if path.is_file():
        path.unlink()


def try_pending(text: str) -> Optional[str]:
    """Confirm, cancel, edit, or undo. None when this message is not about a preview."""
    soft = re.sub(r"\s+", " ", (text or "").strip())
    if _UNDO.match(soft):
        clear_pending()
        from modules.Vault_Store import VaultStore, vault_exists

        store = VaultStore()
        if not vault_exists(store.root):
            return "Nothing to undo. I can't see the vault."
        try:
            return store.undo()
        except VaultError as exc:
            return str(exc)

    # Before a bare "no", so "no, put that in Product Testing" files instead of canceling.
    # Imported here: Vault_Filing registers an applier and imports this module.
    from modules.Vault_Filing import try_correction

    corrected = try_correction(soft)
    if corrected is not None:
        return corrected

    pending = load_pending()
    if not pending:
        return None
    if _YES.match(soft):
        return _apply(pending)
    if _NO.match(soft):
        clear_pending()
        return "Okay, I won't save that."
    picked = _picked_numbers(soft, pending)
    if picked is not None:
        if not picked:
            clear_pending()
            return "Okay, I won't save those."
        chosen = dict(pending)
        chosen["picked"] = picked
        return _apply(chosen)
    edited = _edit(pending, soft)
    if edited is not None:
        save_pending(edited)
        return str(edited.get("spoken") or "Updated the preview. Say yes to save or no to cancel.")
    if re.match(r"^(?:change|make it|put it|move it|due)\b", soft, re.I):
        return (
            "I still have that preview. Say yes, no, or tell me the new title, "
            "date, or area."
        )
    return None


def _picked_numbers(text: str, pending: Dict[str, Any]) -> Optional[list]:
    """1-based item numbers for a batch preview, or None if this isn't a choice."""
    if str(pending.get("kind") or "") != "batch":
        return None
    count = len(pending.get("items") or [])
    if count == 0:
        return None
    if re.match(r"^(?:all|all of them|save them|save all)[.!]?$", text, re.I):
        return list(range(1, count + 1))
    if re.match(r"^(?:none|nothing)[.!]?$", text, re.I):
        return []
    if not re.search(r"\d", text):
        return None
    if not re.match(r"^(?:only|just|save|numbers?)?\s*[\d\s,and&]+[.!]?$", text, re.I):
        return None
    nums = [int(piece) for piece in re.findall(r"\d+", text)]
    if not nums:
        return None
    if any(num < 1 or num > count for num in nums):
        raise VaultError(f"I numbered {count} things. Say yes, only 1, or no.")
    return nums


def _apply(pending: Dict[str, Any]) -> str:
    kind = str(pending.get("kind") or "")
    fn = _APPLIERS.get(kind)
    if fn is None:
        clear_pending()
        return "I lost track of how to save that preview, so I dropped it."
    try:
        return fn(pending)
    except VaultError as exc:
        return str(exc)


def _edit(pending: Dict[str, Any], text: str) -> Optional[Dict[str, Any]]:
    """Return a new preview, or None if this isn't an edit of the one we have."""
    kind = str(pending.get("kind") or "")
    if kind != "capture":
        return None
    item = dict(pending.get("item") or {})
    title_match = _TITLE.match(text)
    if title_match:
        item["title"] = _tidy(title_match.group("title"))
        return _with_spoken(pending, item)
    area_match = _AREA.match(text)
    if area_match:
        raw_area = area_match.group("area").strip(" .")
        if raw_area.lower() in {"doing", "done", "this week"} or parse_when(raw_area, now=now_ct()):
            area_match = None
    if area_match:
        try:
            item["area"] = resolve_area(area_match.group("area"))
        except VaultError as exc:
            pending = dict(pending)
            pending["spoken"] = str(exc) + " The preview is unchanged. Say yes or no."
            return pending
        return _with_spoken(pending, item)
    when_text = re.sub(
        r"^(?:change it to|make it|due|move it to|put it on)\s+",
        "",
        text,
        flags=re.I,
    )
    if when_text != text or parse_when(text, now=now_ct()):
        found = parse_when(when_text, now=now_ct())
        if found:
            item["due"] = found.iso_date
            if found.clock:
                item["time"] = found.hhmm
            return _with_spoken(pending, item)
    return None


def _with_spoken(pending: Dict[str, Any], item: Dict[str, Any]) -> Dict[str, Any]:
    from modules.Vault_Capture import speak_capture

    updated = dict(pending)
    updated["item"] = item
    updated["spoken"] = speak_capture(item)
    return updated


def _tidy(title: str) -> str:
    text = re.sub(r"\s+", " ", (title or "").strip()).strip(" .\"'")
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text
