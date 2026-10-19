#!/usr/bin/env python3
"""Pick an area from rules, corrections William already taught, and note titles.

The model is optional (``BOLT_VAULT_FILING_AI``). ``auto`` asks only when a
provider can answer quickly. ``on`` always asks. ``off`` stays local.
"""

from __future__ import annotations

import json
import os
import re
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from modules.Vault_Dates import now_ct, parse_when
from modules.Vault_Pending import clear_pending, load_pending, register_applier, save_pending
from modules.Vault_Store import (
    ACTIVITY_REL,
    BOARD_REL,
    CALENDAR_INDEX_REL,
    TIMELINE_REL,
    VaultError,
    VaultStore,
    resolve_area,
    vault_exists,
)

_REPO = Path(__file__).resolve().parents[2]
_DEFAULT_PATH = _REPO / "Data" / "memory" / "vault_filing_memory.json"

_AREA_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("30 Product Testing", ("assessment", "product test", "unboxing", "review")),
    ("20 Creator HQ & Content", ("podcast", "pitch", "content idea", "content")),
    ("40 Career & Creator Plan", ("sprint", "portfolio", "career", "goal")),
    ("50 Personal", ("habit", "personal")),
    ("10 Bolt", ("clip", "queue", "post")),
)
_GENERIC = {word for _area, words in _AREA_RULES for word in words}
_STOP = {
    "the", "and", "for", "with", "from", "this", "that", "into", "onto", "your",
    "about", "after", "before", "film", "short", "note", "task", "page", "idea",
    "today", "week", "next", "make", "need", "want", "just", "only", "please",
}
_SKIP_RELS = {BOARD_REL, TIMELINE_REL, ACTIVITY_REL, CALENDAR_INDEX_REL}
_CORRECTION = re.compile(
    r"^(?:no[, ]+)?(?:put|file|move) (?:it|that|them|those) (?:in|into|under|to) (?P<area>.+)$",
    re.I,
)
_THATS = re.compile(r"^(?:no[, ]+)?that(?:'s| is) (?P<area>.+)$", re.I)


@dataclass
class Filing:
    area: str
    related: List[str]


def filing_path() -> Path:
    raw = (os.getenv("BOLT_VAULT_FILING_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return _DEFAULT_PATH


def load_memory() -> Dict[str, Any]:
    path = filing_path()
    if not path.is_file():
        return {"phrases": [], "last": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"phrases": [], "last": []}
    if not isinstance(data, dict):
        return {"phrases": [], "last": []}
    data.setdefault("phrases", [])
    data.setdefault("last", [])
    return data


def save_memory(data: Dict[str, Any]) -> None:
    path = filing_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def pick_area(text: str) -> Filing:
    """Area plus up to two related note titles. Inbox when nothing is clear."""
    folded = (text or "").lower()
    related = _related_titles(folded)
    learned = _learned_area(folded)
    if learned:
        return Filing(learned, related)
    keyword = _keyword_area(folded)
    if keyword:
        return Filing(keyword, related)
    titled = _title_area(folded)
    if titled:
        return Filing(titled, related)
    modeled = _model_area(text)
    if modeled:
        return Filing(modeled, related)
    return Filing("00 Inbox", related)


def remember_phrase(title: str, area: str) -> None:
    phrase = _best_token(title)
    if not phrase:
        return
    data = load_memory()
    phrases = [row for row in data.get("phrases") or [] if str(row.get("phrase")) != phrase]
    phrases.append({"phrase": phrase, "area": area})
    data["phrases"] = phrases[-200:]
    save_memory(data)


def remember_saved(notes: List[Dict[str, str]]) -> None:
    data = load_memory()
    data["last"] = [
        {"rel": row["rel"], "title": row["title"], "type": row.get("type") or "note"}
        for row in notes
        if row.get("rel") and row.get("title")
    ][-20:]
    save_memory(data)


def with_related_body(body: str, related: List[str]) -> str:
    if not related:
        return body or ""
    line = "Related: " + ", ".join(f"[[{name}]]" for name in related)
    if line in (body or ""):
        return body or ""
    base = (body or "").rstrip()
    return f"{base}\n\n{line}".strip() if base else line


def correction_area(text: str) -> Optional[str]:
    """Spoken area from a correction, or None if this is not one.

    "move it to Friday" is a date. "move it to Doing" is a board lane.
    Both fall through so those handlers can take them.
    """
    soft = re.sub(r"\s+", " ", (text or "").strip())
    match = _CORRECTION.match(soft) or _THATS.match(soft)
    if not match:
        return None
    raw = match.group("area").strip(" .")
    if raw.lower() in {"doing", "done", "this week"}:
        return None
    if soft.lower().startswith("move") and parse_when(raw, now=now_ct()):
        return None
    return raw


def try_correction(text: str) -> Optional[str]:
    """Retarget the open preview, or preview a refile of the last save."""
    raw = correction_area(text)
    if raw is None:
        return None
    try:
        area = resolve_area(raw)
    except VaultError as exc:
        if parse_when(raw, now=now_ct()):
            return None
        return str(exc) + " The preview is unchanged."
    pending = load_pending()
    if pending and pending.get("kind") in ("capture", "batch"):
        updated = _retarget(pending, area)
        save_pending(updated)
        return str(updated.get("spoken") or "Updated the preview. Say yes to save or no to cancel.")
    if pending:
        return "I still have a different preview open. Say yes or no first."
    last = list(load_memory().get("last") or [])
    if not last:
        return "I don't have a saved note to refile."
    if not vault_exists():
        return "I can't see the vault yet, so I didn't move that."
    spoken = _speak_refile(last, area)
    save_pending({"kind": "refile", "area": area, "notes": last, "spoken": spoken})
    return spoken


def apply_refile(pending: Dict[str, Any]) -> str:
    notes = list(pending.get("notes") or [])
    area = str(pending.get("area") or "")
    if not notes or not area:
        clear_pending()
        return "Okay, I won't move that."
    if not vault_exists():
        raise VaultError("I can't see the vault yet, so I didn't move that.")
    moved = VaultStore().refile_many([(str(row["rel"]), area) for row in notes if row.get("rel")])
    remember_saved(
        [{"rel": note.rel, "title": note.title, "type": note.kind or "note"} for note in moved]
    )
    for note in moved:
        remember_phrase(note.title, area)
    clear_pending()
    names = ", ".join(note.title for note in moved)
    return f"Filed {len(moved)} in {area}: {names}."


def _retarget(pending: Dict[str, Any], area: str) -> Dict[str, Any]:
    updated = dict(pending)
    if pending.get("kind") == "capture":
        item = dict(pending.get("item") or {})
        item["area"] = area
        item["related"] = _related_titles(str(item.get("title") or "").lower(), limit=2)
        remember_phrase(str(item.get("title") or ""), area)
        updated["item"] = item
        from modules.Vault_Capture import speak_capture

        updated["spoken"] = speak_capture(item)
        return updated
    items = []
    for item in pending.get("items") or []:
        row = dict(item)
        row["area"] = area
        remember_phrase(str(row.get("title") or ""), area)
        items.append(row)
    updated["items"] = items
    from modules.Vault_Extract import speak_batch

    updated["spoken"] = speak_batch(items)
    return updated


def _speak_refile(notes: List[Dict[str, Any]], area: str) -> str:
    bits = []
    for row in notes:
        title = row.get("title") or "that note"
        kind = str(row.get("type") or "")
        if kind == "task":
            bits.append(f"{title} stays in 10 Bolt/Tasks and its area becomes {area}")
        else:
            bits.append(f"{title} moves to {area}")
    return "I'll refile " + "; ".join(bits) + ". Say yes to save or no to cancel."


def _learned_area(folded: str) -> str:
    hits: List[tuple[int, str]] = []
    for row in load_memory().get("phrases") or []:
        phrase = str(row.get("phrase") or "")
        area = str(row.get("area") or "")
        if phrase and area and phrase in folded:
            hits.append((len(phrase), area))
    if not hits:
        return ""
    hits.sort(key=lambda item: -item[0])
    top = hits[0][0]
    areas = {area for length, area in hits if length == top}
    if len(areas) == 1:
        return hits[0][1]
    return ""


def _keyword_area(folded: str) -> str:
    hits = []
    for area, words in _AREA_RULES:
        if any(re.search(rf"\b{re.escape(word)}\b", folded) for word in words):
            hits.append(area)
    if len(hits) == 1:
        return hits[0]
    return ""


def _title_area(folded: str) -> str:
    if not vault_exists():
        return ""
    query = set(_tokens(folded))
    if not query:
        return ""
    areas = set()
    for note in _candidate_notes():
        if query & set(_tokens(note.title.lower())):
            if note.area:
                areas.add(note.area)
    if len(areas) == 1:
        return next(iter(areas))
    return ""


def _related_titles(folded: str, limit: int = 2) -> List[str]:
    if not vault_exists():
        return []
    query = set(_tokens(folded))
    if not query:
        return []
    ranked: List[tuple[int, str]] = []
    for note in _candidate_notes():
        overlap = query & set(_tokens(note.title.lower()))
        if overlap:
            ranked.append((len(overlap), note.title))
    ranked.sort(key=lambda item: (-item[0], item[1].lower()))
    seen = []
    for _score, title in ranked:
        if title not in seen:
            seen.append(title)
        if len(seen) >= limit:
            break
    return seen


def _candidate_notes():
    notes = []
    for note in VaultStore().list_notes():
        if note.rel in _SKIP_RELS or note.rel.startswith("90 Archive"):
            continue
        notes.append(note)
    return notes


def _tokens(text: str) -> List[str]:
    found = re.findall(r"[a-z0-9]+(?:&[a-z0-9]+)*", (text or "").lower())
    return [tok for tok in found if len(tok) >= 3 and tok not in _STOP and tok not in _GENERIC]


def _best_token(title: str) -> str:
    toks = _tokens(title)
    if not toks:
        return ""
    return max(toks, key=len)


def _model_allowed() -> bool:
    mode = (os.getenv("BOLT_VAULT_FILING_AI") or "auto").strip().lower()
    if mode in ("0", "off", "false", "no"):
        return False
    if mode in ("1", "on", "true", "yes"):
        return True
    provider = (os.getenv("BOLT_LLM_PROVIDER") or "ollama").strip().lower()
    if provider == "openai":
        return bool((os.getenv("OPENAI_API_KEY") or "").strip())
    if provider in ("xai", "grok"):
        return bool((os.getenv("XAI_API_KEY") or "").strip())
    return _ollama_up()


def _ollama_up() -> bool:
    raw = (os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434/v1").strip()
    parsed = urlparse(raw)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 11434)
    try:
        with socket.create_connection((host, port), timeout=0.2):
            return True
    except OSError:
        return False


def _model_area(text: str) -> str:
    if not (text or "").strip() or not _model_allowed():
        return ""
    # Imported here so filing stays usable when the model stack is missing.
    from modules.LLM_Handler import ask_llm

    raw = ask_llm(
        "Which single area fits this note for William? "
        "Reply with only one of: Inbox, Bolt, Creator HQ & Content, "
        "Product Testing, Career & Creator Plan, Personal.\n\n"
        + text.strip()[:800],
        system="You file notes into William's vault. One area name only.",
        max_tokens=30,
        temperature=0,
        task_type="planning",
        complexity="medium",
    )
    if not raw or raw.startswith("LLM unavailable"):
        return ""
    try:
        return resolve_area(raw.strip().splitlines()[0].strip(" .\"'"))
    except VaultError:
        return ""


register_applier("refile", apply_refile)
