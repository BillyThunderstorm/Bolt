"""Briefing focus switch (2026-10-11): single-lane, calm briefings.

Config: Core/config.json -> "briefing_focus".
  enabled: false  -> old full briefing behavior everywhere.
  lane: catalog lane whose `testing` items drive the one daily step.
  hide: sections to drop (queue, clip_actions, week_text, storefront,
        sponsors, do_not_suggest, gmail, research_c5, nexus, memory_notes).
  storage_warn_pct: only mention disk when usage is above this.
Env BOLT_NO_DRIVE_PUSH=1 skips the Drive Daily Log push (dry runs).
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG = REPO_ROOT / "Core" / "config.json"
CATALOG = REPO_ROOT / "Data" / "content" / "catalog.json"
JOURNAL_DAYS = 7  # plan: ~1 week of daily notes, then write the assessment


def settings() -> Dict[str, Any]:
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        bf = cfg.get("briefing_focus") or {}
    except Exception:
        bf = {}
    return bf


def enabled() -> bool:
    # BOLT_BRIEFING_FOCUS=0 forces the legacy full briefing (tests, debugging).
    if os.getenv("BOLT_BRIEFING_FOCUS", "").strip().lower() in ("0", "off", "false"):
        return False
    return bool(settings().get("enabled"))


def hidden(section: str) -> bool:
    bf = settings()
    return bool(bf.get("enabled")) and section in (bf.get("hide") or [])


def lane() -> str:
    return str(settings().get("lane") or "product")


def drive_push_allowed() -> bool:
    return os.getenv("BOLT_NO_DRIVE_PUSH", "").strip() not in ("1", "true", "yes")


def storage_warning() -> str:
    """Return a warning line only when disk use exceeds the threshold."""
    try:
        pct_limit = float(settings().get("storage_warn_pct", 95))
        du = shutil.disk_usage(str(REPO_ROOT))
        pct = du.used / du.total * 100
        if pct > pct_limit:
            return f"Disk is {pct:.0f}% full — archive old recordings when you can."
    except Exception:
        pass
    return ""


def testing_items() -> List[Dict[str, Any]]:
    try:
        data = json.loads(CATALOG.read_text(encoding="utf-8"))
    except Exception:
        return []
    want = lane()
    return [
        i for i in data.get("items", [])
        if isinstance(i, dict) and i.get("lane") == want and i.get("status") == "testing"
    ]


ACTIVE_STATUSES = ("testing", "drafting")


def active_items() -> List[Dict[str, Any]]:
    """Lane items still in progress: testing (journaling) or drafting (short not posted)."""
    try:
        data = json.loads(CATALOG.read_text(encoding="utf-8"))
    except Exception:
        return []
    want = lane()
    return [
        i for i in data.get("items", [])
        if isinstance(i, dict) and i.get("lane") == want and i.get("status") in ACTIVE_STATUSES
    ]


def _draft(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    draft = item.get("last_draft")
    return draft if isinstance(draft, dict) and draft else None


def next_step(item: Dict[str, Any]) -> str:
    """One next action. A draft that already exists is reviewed or posted."""
    notes = item.get("notes_log") or []
    n = len(notes) if isinstance(notes, list) else 0
    name = item.get("name") or "your test item"
    draft = _draft(item)
    if draft:
        posted = f'bolt manage posted "{name}"'
        needs = [str(x).strip() for x in (draft.get("needs") or []) if str(x).strip()]
        if draft.get("approved_at"):
            if needs:
                return (
                    f"Post {name} tonight. Open piece: {needs[0]}. "
                    f"If that piece slips, post the cut already approved. Then `{posted}`."
                )
            return f"Post the approved short for {name} by hand, then `{posted}`."
        return f"Review the draft for {name} and approve it, or say what to change."
    if item.get("verdict"):
        return f"Draft the short for {name} and send it for your OK."
    if n < JOURNAL_DAYS:
        return f"Day {n + 1} journal note on {name} (`bolt manage note \"{name}\" --text \"...\"`)."
    return f"Write the detailed assessment and verdict for {name}."


def todays_steps() -> List[str]:
    """Today's list. `briefing_focus.focus_item` keeps the list to one product."""
    items = active_items()
    if not items:
        return [
            f'Pick your next {lane()} product to test and add it: '
            f'bolt manage add "Item" --lane {lane()} --status testing'
        ]
    focus = str(settings().get("focus_item") or "").strip()
    if focus:
        chosen = [
            i for i in items
            if str(i.get("id") or "") == focus or str(i.get("name") or "") == focus
        ]
        if chosen:
            items = chosen[:1]
    return [next_step(i) for i in items]
