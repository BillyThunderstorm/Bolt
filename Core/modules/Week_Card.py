#!/usr/bin/env python3
"""
Week_Card — this week / last week / do not suggest again
=======================================================
A small current-season pointer so bolt day, research, Nexus, and voice
cannot pretend it is week one.

William picks the topic. Bolt keeps the floor marked.

  bolt week
  bolt week set "skincare first-use" --note "already filmed AM"
  bolt week done "posted the AM routine clip"
  bolt week paper [--open]            # one-page fridge sheet (not the mission)
  bolt week rotate
  bolt week ban "Hyram-style education" --why "C5 no"
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEEK_FILE = PROJECT_ROOT / "Data" / "memory" / "week_card.json"
RESEARCH_LOG = PROJECT_ROOT / "Data" / "memory" / "research_log.jsonl"
USER_PROFILE = PROJECT_ROOT / "Data" / "memory" / "user_profile.json"
PAPER_FILE = PROJECT_ROOT / "Data" / "memory" / "this_week_paper.txt"

_EMPTY_WEEK = {"topic": "", "note": "", "started": "", "done": []}

# William's four content topics (2026-08-24). Gaming and tech are one lane.
CONTENT_LANES = (
    "pop culture / TV and film",
    "gaming / tech",
    "beauty / skincare",
    "general product review / Amazon storefront",
)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _blank() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "updated_at": "",
        "this_week": dict(_EMPTY_WEEK),
        "last_week": dict(_EMPTY_WEEK),
        "do_not_suggest": [],
    }


def load() -> Dict[str, Any]:
    data = _blank()
    if WEEK_FILE.is_file():
        try:
            raw = json.loads(WEEK_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data.update(raw)
        except Exception:
            pass
    data.setdefault("this_week", dict(_EMPTY_WEEK))
    data.setdefault("last_week", dict(_EMPTY_WEEK))
    data.setdefault("do_not_suggest", [])
    for key in ("this_week", "last_week"):
        slot = data[key] if isinstance(data.get(key), dict) else {}
        merged = dict(_EMPTY_WEEK)
        merged.update({k: slot.get(k, merged[k]) for k in _EMPTY_WEEK})
        if not isinstance(merged.get("done"), list):
            merged["done"] = []
        data[key] = merged
    if not isinstance(data.get("do_not_suggest"), list):
        data["do_not_suggest"] = []
    return data


def save(data: Dict[str, Any]) -> Dict[str, Any]:
    data["updated_at"] = _now_iso()
    WEEK_FILE.parent.mkdir(parents=True, exist_ok=True)
    WEEK_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data


def _remember(fact: str) -> None:
    try:
        from modules.Bolt_Memory import remember

        remember(fact, section="Recent Notes")
    except Exception:
        pass


def c5_dropped_names() -> List[str]:
    names: List[str] = []
    if not RESEARCH_LOG.is_file():
        return names
    try:
        for line in RESEARCH_LOG.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if str(row.get("c5_verdict") or "").lower() != "no":
                continue
            name = (row.get("name") or row.get("creator") or "").strip()
            if name and name not in names:
                names.append(name)
    except Exception:
        return names
    return names


def blocked_suggestions(data: Optional[Dict[str, Any]] = None) -> List[str]:
    card = data or load()
    out: List[str] = []
    for item in card.get("do_not_suggest") or []:
        if isinstance(item, dict):
            text = str(item.get("text") or "").strip()
        else:
            text = str(item).strip()
        if text and text not in out:
            out.append(text)
    for name in c5_dropped_names():
        if name not in out:
            out.append(name)
    return out


def is_blocked(text: str, data: Optional[Dict[str, Any]] = None) -> Optional[str]:
    needle = (text or "").strip().lower()
    if not needle:
        return None
    words = set(needle.replace("-", " ").replace("(", " ").replace(")", " ").split())
    for item in blocked_suggestions(data):
        il = item.lower()
        if il in needle or needle in il:
            return item
        token = il.replace("(", " ").replace(")", " ").split()[0] if il else ""
        if len(token) >= 4 and token in words:
            return item
    return None


def set_week(topic: str, note: str = "") -> Dict[str, Any]:
    topic = (topic or "").strip()
    if not topic:
        raise ValueError("topic is required")
    data = load()
    current = (data["this_week"].get("topic") or "").strip()
    if current and current.lower() != topic.lower():
        data["last_week"] = dict(data["this_week"])
    data["this_week"] = {
        "topic": topic,
        "note": (note or "").strip(),
        "started": date.today().isoformat(),
        "done": list(data["this_week"].get("done") or [])
        if current.lower() == topic.lower()
        else [],
    }
    save(data)
    _remember(f"This week is: {topic}" + (f" — {note}" if note else ""))
    return data


def mark_done(item: str) -> Dict[str, Any]:
    item = (item or "").strip()
    if not item:
        raise ValueError("done item is required")
    data = load()
    done = list(data["this_week"].get("done") or [])
    if item not in done:
        done.append(item)
    data["this_week"]["done"] = done
    save(data)
    topic = data["this_week"].get("topic") or "(no topic yet)"
    _remember(f"This week ({topic}) done: {item}")
    return data


def rotate() -> Dict[str, Any]:
    data = load()
    topic = (data["this_week"].get("topic") or "").strip()
    data["last_week"] = dict(data["this_week"])
    data["this_week"] = dict(_EMPTY_WEEK)
    save(data)
    if topic:
        _remember(f"Rotated week. Last week was: {topic}. This week is unset.")
    return data


def ban(text: str, why: str = "") -> Dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("ban text is required")
    data = load()
    existing = blocked_suggestions(data)
    if any(text.lower() == e.lower() for e in existing):
        return data
    data["do_not_suggest"].append(
        {"text": text, "why": (why or "").strip(), "added": _now_iso()}
    )
    save(data)
    _remember(f"Do not suggest again: {text}" + (f" ({why})" if why else ""))
    return data


def unban(text: str) -> Dict[str, Any]:
    needle = (text or "").strip().lower()
    data = load()
    data["do_not_suggest"] = [
        item
        for item in data.get("do_not_suggest") or []
        if str(item.get("text") if isinstance(item, dict) else item).strip().lower()
        != needle
    ]
    save(data)
    return data


def is_paused(data: Optional[Dict[str, Any]] = None) -> bool:
    """True when this week's note is a pause (do not invent a post)."""
    card = data or load()
    note = str((card.get("this_week") or {}).get("note") or "")
    head = note.strip().upper()
    return head.startswith("PAUSE") or "stepping away" in note.lower()


def is_stale_skincare_leftover(text: str, week_topic: str = "") -> bool:
    """True when retrieved text is last-week snail/steamer advice on a non-beauty week."""
    topic = (week_topic or "").lower()
    if "skincare" in topic or "beauty" in topic or "snail" in topic:
        return False
    low = (text or "").lower()
    return "snail" in low or "facial steamer" in low or "steamer kit" in low


def days_old(data: Optional[Dict[str, Any]] = None) -> Optional[int]:
    card = data or load()
    started = (card.get("this_week") or {}).get("started") or ""
    if not started:
        return None
    try:
        return (date.today() - date.fromisoformat(started[:10])).days
    except Exception:
        return None


def format_card(data: Optional[Dict[str, Any]] = None) -> str:
    card = data or load()
    this = card["this_week"]
    last = card["last_week"]
    topic = (this.get("topic") or "").strip() or "(not set — pick a topic today)"
    lines = [
        "THIS WEEK",
        f"  Topic: {topic}",
    ]
    if this.get("started"):
        age = days_old(card)
        extra = f"  ·  {age}d ago" if age is not None else ""
        lines.append(f"  Started: {this['started']}{extra}")
    if this.get("note"):
        lines.append(f"  Note: {this['note']}")
    done = this.get("done") or []
    if done:
        lines.append("  Already done:")
        for item in done:
            lines.append(f"    • {item}")
    else:
        lines.append("  Already done: (nothing logged yet)")
    last_topic = (last.get("topic") or "").strip()
    lines.append("LAST WEEK")
    if last_topic:
        lines.append(f"  Topic: {last_topic}")
        if last.get("note"):
            lines.append(f"  Note: {last['note']}")
        for item in last.get("done") or []:
            lines.append(f"    • {item}")
    else:
        lines.append("  (none yet)")
    blocked = blocked_suggestions(card)
    lines.append("DO NOT SUGGEST")
    if blocked:
        for item in blocked[:12]:
            lines.append(f"  • {item}")
        if len(blocked) > 12:
            lines.append(f"  … +{len(blocked) - 12} more (C5 drops + bans)")
    else:
        lines.append("  (empty)")
    age = days_old(card)
    if topic.startswith("(") is False and age is not None and age >= 8:
        lines.append("  ⚠  Card is 8+ days old. Rotate or set a new topic.")
    return "\n".join(lines)


def format_prompt(data: Optional[Dict[str, Any]] = None) -> str:
    """Hard constraints for any plan-making LLM or briefing."""
    card = data or load()
    this = card["this_week"]
    last = card["last_week"]
    topic = (this.get("topic") or "").strip()
    today = date.today()
    lines = [
        "WEEK CARD (read this before inventing a plan).",
        f"Today is {today.strftime('%A, %Y-%m-%d')}. Use this date. Notes from a prior week are history, not today's to-do.",
        "Do not restart the career. Do not open a new research project unless William asks.",
        "Do not suggest anything listed under DO NOT SUGGEST.",
        "The only four content topics: "
        + "; ".join(CONTENT_LANES)
        + ". Gaming and tech are one lane. Amazon is the shelf for general product reviews, not a fifth topic.",
        "Retrieved memory is often stale. The WEEK CARD beats old Nexus notes.",
    ]
    if topic:
        lines.append(f"This week is: {topic}.")
        if this.get("started"):
            lines.append(f"This week's card started {this['started']}.")
        if this.get("note"):
            lines.append(f"Note: {this['note']}")
        done = this.get("done") or []
        if done:
            lines.append("Already done this week: " + "; ".join(done))
            lines.append(
                "Already-done items are finished. Do not tell William to film, "
                "post, pick, or start them again. The original week-start note "
                "was a plan, not an open to-do — if something from it is in "
                "Already done, treat it as shipped."
            )
        if is_paused(card):
            lines.append(
                "This week is PAUSED. Do not invent a film, post, reapply, or "
                "product-review next step. Acknowledge the pause. Wait until William returns."
            )
        else:
            lines.append("Continue this week. One next step only. Do not repeat a finished step.")
    else:
        lines.append(
            "This week has no topic yet. Ask William to pick one "
            "(`bolt week set \"…\"`). Do not invent a new lane mix. "
            "Do not fill the gap with last week's leftovers."
        )
    last_topic = (last.get("topic") or "").strip()
    if last_topic:
        lines.append(f"Last week was: {last_topic}. Do not assign it again as if new.")
        if last.get("note"):
            lines.append(f"Last week's note: {last['note']}")
        last_done = last.get("done") or []
        if last_done:
            lines.append("Last week already shipped: " + "; ".join(last_done))
        lines.append(
            "Last week's leftovers are closed. Do not tell William to film or post "
            "snail care, the facial steamer, or any optional leftover from last week "
            "unless this week's topic is beauty/skincare AND William asks."
        )
    blocked = blocked_suggestions(card)
    if blocked:
        lines.append("Do not suggest: " + "; ".join(blocked[:20]))
    return "\n".join(lines)


def _horizon() -> Dict[str, Any]:
    """Year-end bar from the profile. Empty dict if the profile is missing."""
    try:
        raw = json.loads(USER_PROFILE.read_text(encoding="utf-8"))
        h = (raw or {}).get("near_term_horizon") or {}
        return h if isinstance(h, dict) else {}
    except Exception:
        return {}


def format_paper(data: Optional[Dict[str, Any]] = None) -> str:
    """One-page fridge sheet: goal, status, checkboxes. Plain English.

    For William and anyone in the house. Not the 13-section mission.
    Tick a box when something actually ships; log it later with
    `bolt week done`.
    """
    card = data or load()
    this = card["this_week"]
    last = card["last_week"]
    horizon = _horizon()
    topic = (this.get("topic") or "").strip() or "(not picked yet)"
    paused = is_paused(card)
    today = date.today().strftime("%A, %Y-%m-%d")

    goal_date = horizon.get("target_date") or "2026-12-31"
    goal_text = horizon.get("success_is") or (
        "Know what success looks like in this kind of work, or have a "
        "written roadmap plus proof the work is leading somewhere."
    )

    status = "PAUSED — stepping back. Not behind. Not a skipped plan."
    if not paused:
        if topic.startswith("("):
            status = "No topic yet. Pick one when work starts again."
        else:
            status = "In progress. Stay on this week's topic."

    lines = [
        "WILLIAM — THIS WEEK",
        "(one page for the fridge — not a computer briefing)",
        f"Printed: {today}",
        "",
        f"THE BIG GOAL  (by {goal_date})",
    ]
    for wrap in _wrap(str(goal_text), 72):
        lines.append(wrap)
    lines.extend(
        [
            "This is figuring out the map. It is not a finished career plan.",
            "",
            "THIS WEEK",
            f"  Topic:  {topic}",
            f"  Status: {status}",
        ]
    )
    if this.get("started"):
        lines.append(f"  Started: {this['started']}")
    note = (this.get("note") or "").strip()
    if note and not paused:
        lines.append(f"  Note: {note}")
    lines.extend(["", "DONE (tick when it actually happened)"])
    done = [str(x).strip() for x in (this.get("done") or []) if str(x).strip()]
    if done:
        for item in done:
            lines.append(f"  [x] {item}")
    else:
        lines.append("  (nothing logged on the computer yet)")
    lines.extend(
        [
            "  [ ] ________________________________",
            "  [ ] ________________________________",
            "  [ ] ________________________________",
            "",
            "LAST WEEK (already happened — not this week's job)",
        ]
    )
    last_topic = (last.get("topic") or "").strip()
    if last_topic:
        lines.append(f"  Topic: {last_topic}")
        last_done = [str(x).strip() for x in (last.get("done") or []) if str(x).strip()]
        if last_done:
            for item in last_done:
                lines.append(f"  [x] {item}")
        else:
            lines.append("  (nothing logged)")
    else:
        lines.append("  (none yet)")
    lines.extend(
        [
            "",
            "HOW TO READ THIS",
            "  A blank week is not failure. Daily computer work does not",
            "  require this sheet to be full. Tick a box when something",
            "  ships. At the computer later:  bolt week done \"what shipped\"",
            "",
        ]
    )
    return "\n".join(lines)


def _wrap(text: str, width: int) -> List[str]:
    words = (text or "").split()
    if not words:
        return [""]
    out: List[str] = []
    buf = words[0]
    for w in words[1:]:
        if len(buf) + 1 + len(w) <= width:
            buf = f"{buf} {w}"
        else:
            out.append(buf)
            buf = w
    out.append(buf)
    return out


def write_paper(data: Optional[Dict[str, Any]] = None) -> Path:
    PAPER_FILE.parent.mkdir(parents=True, exist_ok=True)
    PAPER_FILE.write_text(format_paper(data), encoding="utf-8")
    return PAPER_FILE


def spoken_line(data: Optional[Dict[str, Any]] = None) -> str:
    card = data or load()
    topic = (card["this_week"].get("topic") or "").strip()
    if is_paused(card):
        return (
            f"This week is {topic or 'set'} and it is paused. "
            "Do not start a new post. Snail care is not this week's job."
        )
    if topic:
        done = card["this_week"].get("done") or []
        extra = f" Already done: {done[-1]}." if done else ""
        return f"This week is {topic}.{extra} Stay on that. Do not start a new plan."
    return (
        "This week has no topic yet. Pick one today with bolt week set, "
        "then we stay on it. Do not suggest last week's leftovers."
    )


def _cli(argv: List[str]) -> int:
    args = list(argv)
    cmd = (args[0] if args else "show").lower()
    rest = args[1:]

    def _opt(flag: str) -> str:
        if flag in rest:
            i = rest.index(flag)
            if i + 1 < len(rest):
                return rest[i + 1]
        return ""

    try:
        if cmd in ("show", "status", "card"):
            print(format_card())
            return 0
        if cmd == "set":
            note = _opt("--note")
            topic_parts = [a for a in rest if a != "--note" and a != note]
            # drop the value that belongs to --note
            if "--note" in rest:
                i = rest.index("--note")
                topic_parts = [a for j, a in enumerate(rest) if j != i and j != i + 1]
            topic = " ".join(topic_parts).strip().strip('"')
            set_week(topic, note=note)
            print(format_card())
            return 0
        if cmd == "done":
            mark_done(" ".join(rest).strip().strip('"'))
            print(format_card())
            return 0
        if cmd in ("paper", "print", "fridge"):
            path = write_paper()
            print(path.read_text(encoding="utf-8"))
            print(f"Saved: {path}")
            if "--open" in rest:
                import subprocess

                subprocess.run(["open", str(path)], check=False)
            return 0
        if cmd == "rotate":
            rotate()
            print(format_card())
            return 0
        if cmd == "ban":
            why = _opt("--why")
            parts = rest
            if "--why" in rest:
                i = rest.index("--why")
                parts = [a for j, a in enumerate(rest) if j != i and j != i + 1]
            ban(" ".join(parts).strip().strip('"'), why=why)
            print(format_card())
            return 0
        if cmd == "unban":
            unban(" ".join(rest).strip().strip('"'))
            print(format_card())
            return 0
        if cmd in ("help", "-h", "--help"):
            print(__doc__)
            return 0
        print(
            "usage: bolt week [show|set|done|paper|rotate|ban|unban]",
            file=sys.stderr,
        )
        return 2
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
