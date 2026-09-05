#!/usr/bin/env python3
"""
modules/Intent_Router.py — Lightweight natural-language intent router for Bolt
==============================================================================
Maps plain spoken/typed phrases to existing Bolt actions so conversation
feels fluid without requiring exact CLI commands.

Design goals:
  - Fast, local, no extra LLM call for routing
  - Prefer high-value, low-risk actions (status, next, morning, queue)
  - Return a short spoken-friendly string the conversation layer can use
  - Fall through (return None) when the message is just normal chat
  - Write intents (ready / week set / shipped / mission check-in) call the
    same Week_Card and Command_Center functions as the CLI — conversation
    is a front-end, not a second brain

Usage from Bolt_Conversation:
  from modules.Intent_Router import try_handle_intent
  handled = try_handle_intent(user_text)
  if handled is not None:
      return handled   # already a ready-to-speak reply
  # else: normal ask_llm path
"""

from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Tuple


def _normalize(text: str) -> str:
    t = (text or "").lower().strip()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _match_any(text: str, phrases: Tuple[str, ...]) -> bool:
    return any(p in text for p in phrases)


def _action_morning() -> str:
    try:
        from modules.Content_Manager import morning, is_good_morning_phrase

        # morning() already speaks; we still return the spoken text for history
        result = morning(speak_aloud=True)
        return result.get("spoken") or "Good morning briefing is ready."
    except Exception as exc:
        return f"I tried to run the morning briefing but hit a snag: {exc}"


def _action_day() -> str:
    """Real bolt day kickoff — queue + peak + a short plan from real data (not LLM fiction)."""
    try:
        from modules.Peak_Hour_Notifier import (
            queue_summary,
            _actionable_clips,
            _is_peak_now,
            _clip_display_name,
        )

        is_peak, peak_info = _is_peak_now()
        s = queue_summary()
        clips = _actionable_clips()
        n = len(clips)
        peak_bit = (
            "Peak posting window is open right now."
            if is_peak
            else f"Off peak. {peak_info}."
        )

        # Cheerful mini-plan grounded in real queue (Billy liked the "plan" energy)
        if not clips:
            week_bit = ""
            try:
                from modules.Week_Card import spoken_line

                week_bit = spoken_line() + " "
            except Exception:
                week_bit = ""
            plan = (
                "Today's plan: process a recording or add a hand-edited vertical, "
                "then review and post when peak opens."
            )
            return (
                f"It's Bolt day! {peak_bit} {week_bit}"
                f"No postable clips yet. {plan} "
                f"Try bolt recordings, or bolt queue add in the terminal."
            )

        top = clips[0]
        title = top.get("title") or _clip_display_name(top) or "untitled"
        approved = int(s.get("approved") or 0)
        week_bit = ""
        try:
            from modules.Week_Card import spoken_line

            week_bit = spoken_line() + " "
        except Exception:
            week_bit = ""
        # Build a 3-step plan from reality
        if is_peak and approved > 0:
            plan = (
                f"Today's plan: one, open queue decide and polish titles if needed. "
                f"Two, post now on {title} or the next approved clip while peak is live. "
                f"Three, log how it does later."
            )
        elif approved > 0:
            plan = (
                f"Today's plan: one, review with queue decide. "
                f"Two, keep your {approved} approved clips ready for peak. "
                f"Three, post when the window opens — next in line is {title}."
            )
        else:
            plan = (
                f"Today's plan: one, queue decide and approve the keepers. "
                f"Two, hold anything weak with a reason. "
                f"Three, post the best one at peak. Next up is {title}."
            )

        return (
            f"It's Bolt day! {peak_bit} {week_bit}"
            f"You have {n} postable clips, {approved} already approved. "
            f"{plan} "
            f"Say approve next, hold next, post next, or queue decide."
        )
    except Exception as exc:
        return f"Bolt day hit a snag: {exc}. Try bolt day in the terminal."


def _action_next() -> str:
    try:
        from modules.Week_Card import spoken_line

        week = spoken_line()
    except Exception:
        week = ""
    try:
        from modules.Content_Manager import next_actions

        actions = next_actions(limit=3)
        if not actions:
            return (week + " Nothing urgent in the manager queue.").strip()
        lines = []
        for a in actions:
            lines.append(f"{a['title']}.")
        prefix = (week + " ") if week else ""
        return prefix + "Here's what I'd focus on next: " + " ".join(lines)
    except Exception as exc:
        return f"I couldn't load next actions: {exc}"


def _action_week() -> str:
    try:
        from modules.Week_Card import spoken_line

        return spoken_line()
    except Exception as exc:
        return f"Week card is unavailable: {exc}"


def _action_status() -> str:
    try:
        from modules.Content_Manager import (
            list_items,
            store_summary,
            shipped_summary,
            sponsors_pipeline,
            social_queue,
        )

        items = list_items()
        testing = [i for i in items if i.get("status") == "testing"]
        store = store_summary()
        ship = shipped_summary()
        sp = sponsors_pipeline()
        queue_len = len(social_queue())

        parts = [
            f"You have {len(items)} catalog items, {len(testing)} currently testing.",
            f"Storefront has {store['total']} items ({store['with_asin']} with ASINs).",
            f"Shipped reviews: {ship['total']}.",
            f"Sponsor pipeline: {sp['active']} active of {sp['total']}.",
            f"Social queue entries: {queue_len}.",
        ]
        return " ".join(parts)
    except Exception as exc:
        return f"Status check failed: {exc}"


def _action_queue() -> str:
    try:
        from modules.Peak_Hour_Notifier import queue_summary, _actionable_clips

        s = queue_summary()
        actionable = _actionable_clips()
        n = len(actionable)
        parts = [
            f"You have {n} postable clip{'s' if n != 1 else ''}.",
            f"{s.get('awaiting_approval', 0)} awaiting approval, "
            f"{s.get('approved', 0)} approved for peak.",
        ]
        if s.get("missing"):
            parts.append(
                f"{s['missing']} ghost rows with missing files — say clean queue or run bolt queue clean."
            )
        if actionable:
            top = actionable[0]
            parts.append(
                f"Next up: {top.get('title') or 'untitled'} "
                f"(score {top.get('score')}). "
                f"Run bolt queue decide to review."
            )
        else:
            parts.append("Nothing postable right now.")
        return " ".join(parts)
    except Exception:
        try:
            from modules.Bolt_Chat import format_queue_status

            return format_queue_status()
        except Exception as exc:
            return f"Couldn't read the queue: {exc}"


def _action_queue_clean() -> str:
    try:
        from modules.Peak_Hour_Notifier import clean_missing_clips, queue_summary

        before = queue_summary().get("missing") or 0
        if before == 0:
            return "No ghost queue rows — nothing to clean."
        result = clean_missing_clips(dry_run=False)
        return (
            f"Cleaned {result.get('cleaned', 0)} ghost ready row(s) "
            f"with missing video files. Media was not deleted."
        )
    except Exception as exc:
        return f"Could not clean queue: {exc}"


def _action_queue_decide() -> str:
    """Voice-friendly next-clip brief (full interactive decide needs the terminal)."""
    try:
        from modules.Peak_Hour_Notifier import _actionable_clips, _clip_display_name

        clips = _actionable_clips()
        if not clips:
            return (
                "Nothing postable right now. "
                "Add clips with bolt queue add, or clean ghosts with clean queue."
            )
        c = clips[0]
        title = c.get("title") or _clip_display_name(c) or "untitled"
        score = c.get("score")
        plan = (c.get("auto_post") or {}).get("status") or c.get("status")
        n = len(clips)
        return (
            f"Queue decide: {n} postable clip{'s' if n != 1 else ''}. "
            f"Next is {title}, score {score}, plan {plan}. "
            f"Say approve next, hold next, or post next. "
            f"For full interactive review with the video player, run bolt queue decide in the terminal."
        )
    except Exception as exc:
        return f"Could not start queue decide: {exc}"


def _action_approve_next() -> str:
    try:
        from modules.Peak_Hour_Notifier import approve_next_clip

        clip = approve_next_clip()
        if not clip:
            return "No postable clip to approve."
        return (
            f"Approved {clip.get('title') or clip.get('id')} for the next peak post."
        )
    except Exception as exc:
        return f"Approve failed: {exc}"


def _action_hold_next() -> str:
    try:
        from modules.Peak_Hour_Notifier import reject_next_clip

        clip = reject_next_clip("held by voice command")
        if not clip:
            return "No postable clip to hold."
        return f"Held {clip.get('title') or clip.get('id')}."
    except Exception as exc:
        return f"Hold failed: {exc}"


def _action_post_next() -> str:
    try:
        from modules.Peak_Hour_Notifier import post_now

        result = post_now()
        clip = result.get("clip") or {}
        publish = result.get("result") or {}
        if publish.get("success"):
            return f"Posted {clip.get('title') or clip.get('id')}."
        err = publish.get("error") or "unknown error"
        if not clip:
            return f"Could not post: {err}"
        return f"Tried to post {clip.get('id')} but failed: {err}"
    except Exception as exc:
        return f"Post failed: {exc}"


def _action_research() -> str:
    try:
        from modules.Researcher import summary as research_summary

        s = research_summary()
        return (
            f"Research: {s.get('candidates_total', 0)} candidates, "
            f"{s.get('candidates_pending_c5', 0)} pending C5, "
            f"{s.get('candidates_kept', 0)} kept. "
            f"Next: {s.get('next_action', 'check bolt research status.')}"
        )
    except Exception:
        try:
            # Fallback: read research log lightly if helper missing
            from pathlib import Path
            import json

            log_path = Path("Data/memory/research_log.jsonl")
            if not log_path.exists():
                return "Research log is empty so far. Want to add a candidate?"
            lines = log_path.read_text(encoding="utf-8").strip().splitlines()
            return f"Research log has {len(lines)} entries. Run bolt research status for details."
        except Exception as exc:
            return f"Research status unavailable: {exc}"


def _action_stats() -> str:
    try:
        from modules.Social_Stats import readiness_summary, tiktok_ready, youtube_ready

        t, y = tiktok_ready(), youtube_ready()
        if t.get("paused"):
            return (
                f"Social stats: {readiness_summary()}. "
                f"YouTube: {y['next_step']}. "
                f"TikTok API is paused — post in the app, then bolt log_perf."
            )
        return (
            f"Social stats: {readiness_summary()}. "
            f"TikTok: {t['next_step']}. YouTube: {y['next_step']}. "
            f"When ready, run bolt stats --dry-run in the terminal."
        )
    except Exception as exc:
        return f"Social stats status unavailable: {exc}"


def _action_budget() -> str:
    try:
        from modules.LLM_Budget import describe_policy, briefing_provider_preference
        from modules.XAI_Usage import status_dict

        s = status_dict()
        cap = s.get("cap_usd")
        spent = s.get("spend_usd", 0)
        rem = s.get("remaining_usd")
        parts = [describe_policy()]
        parts.append(f"Briefing provider preference: {briefing_provider_preference()}.")
        if cap:
            parts.append(
                f"This month estimated API spend is {spent:.2f} dollars "
                f"of {cap:.0f} dollar soft cap"
                + (
                    f", about {rem:.2f} remaining."
                    if rem is not None
                    else "."
                )
            )
            if s.get("cap_exceeded"):
                parts.append("Cap reached — Bolt is forcing local models.")
        else:
            parts.append(f"Estimated API spend this month: {spent:.2f} dollars. No cap set.")
        return " ".join(parts)
    except Exception as exc:
        return f"Budget status unavailable: {exc}"


def _action_storage() -> str:
    """Spoken-friendly storage snapshot for media/ + disk free."""
    try:
        import shutil
        import subprocess
        from pathlib import Path

        repo = Path(__file__).resolve().parents[2]
        media = repo / "media"
        recordings = media / "Recordings"
        clips = media / "clips"

        def _gb(path: Path) -> float:
            if not path.exists():
                return 0.0
            try:
                out = subprocess.check_output(["du", "-sk", str(path)], text=True)
                kb = float(out.split()[0])
                return kb / (1024 * 1024)
            except Exception:
                return 0.0

        usage = shutil.disk_usage(str(repo))
        free_gb = usage.free / (1024 ** 3)
        used_pct = int(round(100 * usage.used / usage.total)) if usage.total else 0
        rec_gb = _gb(recordings)
        clip_gb = _gb(clips)
        return (
            f"Storage: disk is {used_pct} percent full with {free_gb:.0f} gigabytes free. "
            f"Recordings are {rec_gb:.1f} gigabytes. Clips are {clip_gb:.1f} gigabytes."
        )
    except Exception as exc:
        return f"Could not read storage status: {exc}"


def _action_mission() -> str:
    try:
        from modules.Command_Center import mission_status  # type: ignore

        return mission_status()
    except Exception:
        return (
            "Mission system is available via bolt mission status. "
            "Want me to start a new mission for a goal?"
        )


# ── Write intents (item 12) — same functions the CLI uses ────────────────────

_QUESTION_HEAD = re.compile(
    r"^(what|whats|what's|how|how's|hows|tell me|can you|could you)\b",
    re.I,
)

_READY_RE = re.compile(
    r"^(?:"
    r"i(?:'m| am|m)? ready to continue"
    r"|ready to continue"
    r"|i(?:'m| am|m)? ready"
    r"|i(?:'m| am|m)? back"
    r"|un-?pause"
    r"|let'?s continue"
    r")(?:\s+(?:with|on)\s+(?P<topic>.+))?$",
    re.I,
)

_WEEK_SET_RE = re.compile(
    r"^(?:this week is|set this week(?: to)?|week set)\s+(?P<topic>.+)$",
    re.I,
)

_WEEK_SET_LETS_RE = re.compile(
    r"^let'?s do\s+(?P<topic>.+?)(?:\s+this week)?$",
    re.I,
)

_WEEK_DONE_RE = re.compile(
    r"^(?:this shipped|i shipped|week done|mark done|that(?:'s|s) done|done)"
    r"(?:\s*[:\-]\s*|\s+)(?P<item>.+)$",
    re.I,
)

_WEEK_DONE_DID_RE = re.compile(
    r"^i (?:posted|filmed|shipped|finished)\s+(?P<item>.+)$",
    re.I,
)

_REMEMBER_RE = re.compile(
    r"^(?:remember|note for tomorrow|leave a note)\s*[:\-]\s*(?P<note>.+)$",
    re.I,
)

_CHECKIN_HOURS_LABELED = re.compile(
    r"(?:^|\b)(?:mission\s+)?(?:hours|time available)\s*[:=]\s*(?P<val>[^\n,;]+)",
    re.I,
)
_CHECKIN_HOURS_HAVE = re.compile(
    r"^i have\s+(?P<val>\d+(?:\.\d+)?)\s*(?:hours?|hrs?)\b",
    re.I,
)
_CHECKIN_BUDGET = re.compile(
    r"(?:^|\b)(?:mission\s+)?(?:max\s+)?budget\s*[:=]?\s*(?P<val>\$?\d+(?:\.\d+)?(?:\s*dollars?)?)",
    re.I,
)
_CHECKIN_ASSETS = re.compile(
    r"(?:^|\b)(?:mission\s+)?(?:assets|already own(?:ed)?|already have)\s*[:=]\s*(?P<val>.+)$",
    re.I,
)
_CHECKIN_ASSETS_HAVE = re.compile(
    r"^already (?:own|have)\s+(?P<val>.+)$",
    re.I,
)
_CHECKIN_BORROW = re.compile(
    r"(?:^|\b)(?:mission\s+)?(?:borrow(?:\/free)?|free \/ cheap|borrow free)\s*[:=]\s*(?P<val>.+)$",
    re.I,
)
_CHECKIN_RESTRICT = re.compile(
    r"(?:^|\b)(?:mission\s+)?(?:restrictions|deal-?breakers?)\s*[:=]\s*(?P<val>.+)$",
    re.I,
)
_CHECKIN_DEADLINE = re.compile(
    r"(?:^|\b)(?:mission\s+)?deadline\s*[:=]\s*(?P<val>.+)$",
    re.I,
)


def _soft(text: str) -> str:
    t = (text or "").strip()
    t = t.replace("\u2019", "'").replace("\u2018", "'").replace("`", "'")
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _payload(value: str) -> str:
    v = (value or "").strip().strip("\"'")
    v = re.sub(r"[.!?]+$", "", v).strip()
    return v


def _is_question(text: str) -> bool:
    return bool(_QUESTION_HEAD.match(text or ""))


def _save_memory_note(fact: str) -> None:
    try:
        from modules.Bolt_Memory import remember

        remember(fact, section="Recent Notes")
    except Exception:
        pass


def _write_ready(topic_extra: str = "") -> str:
    from modules.Week_Card import is_paused, load, set_week, spoken_line

    data = load()
    current = (data["this_week"].get("topic") or "").strip()
    topic = _payload(topic_extra) or current
    if not topic:
        return (
            "You're back. Which week topic should I set — games, tech, "
            "beauty, or general product?"
        )
    was_paused = is_paused(data)
    set_week(topic, note="ready to continue")
    line = spoken_line()
    if was_paused:
        return f"Unpaused. {line}"
    return f"Ready. {line}"


def _write_week_set(topic: str) -> str:
    from modules.Week_Card import set_week, spoken_line

    topic = _payload(topic)
    if not topic:
        return "Which week topic? Games, tech, beauty, or general product."
    set_week(topic)
    return spoken_line()


def _write_week_done(item: str) -> str:
    from modules.Week_Card import load, mark_done, spoken_line

    item = _payload(item)
    if not item:
        return "What shipped? Say this shipped, then the thing."
    data = load()
    if not (data["this_week"].get("topic") or "").strip():
        mark_done(item)
        return (
            f"Logged: {item}. This week still has no topic — "
            "set one when you can so we stay on it."
        )
    mark_done(item)
    return spoken_line()


def _write_remember(note: str) -> str:
    note = _payload(note)
    if not note:
        return "What should I remember?"
    _save_memory_note(note)
    return "Saved that note for tomorrow."


def _parse_checkin_fields(soft: str) -> Dict[str, str]:
    fields: Dict[str, str] = {}
    m = _CHECKIN_HOURS_LABELED.search(soft) or _CHECKIN_HOURS_HAVE.search(soft)
    if m:
        fields["hours"] = _payload(m.group("val"))
    m = _CHECKIN_BUDGET.search(soft)
    if m:
        fields["budget"] = _payload(m.group("val"))
    m = _CHECKIN_ASSETS.search(soft) or _CHECKIN_ASSETS_HAVE.search(soft)
    if m:
        fields["assets"] = _payload(m.group("val"))
    m = _CHECKIN_BORROW.search(soft)
    if m:
        fields["borrow_free"] = _payload(m.group("val"))
    m = _CHECKIN_RESTRICT.search(soft)
    if m:
        fields["restrictions"] = _payload(m.group("val"))
    m = _CHECKIN_DEADLINE.search(soft)
    if m:
        fields["deadline"] = _payload(m.group("val"))
    return {k: v for k, v in fields.items() if v}


def _write_checkin(soft: str) -> Optional[str]:
    if _is_question(soft):
        return None
    fields = _parse_checkin_fields(soft)
    if not fields:
        return None
    from modules.Command_Center import latest_mission, update_mission_checkin

    path = latest_mission()
    if path is None:
        return (
            "No mission file yet. Start one with bolt mission start, "
            "then I can save those answers."
        )
    update_mission_checkin(path, **fields)
    bits = ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in fields.items())
    return f"Saved {bits} on the latest mission."


def _try_write_intent(user_text: str) -> Optional[str]:
    """Map a single reply onto week set / done / mission check-in / remember."""
    soft = _soft(user_text)
    if not soft or _is_question(soft):
        return None

    m = _READY_RE.match(soft)
    if m:
        return _write_ready(m.group("topic") or "")

    m = _WEEK_SET_RE.match(soft) or _WEEK_SET_LETS_RE.match(soft)
    if m:
        return _write_week_set(m.group("topic"))

    m = _WEEK_DONE_RE.match(soft) or _WEEK_DONE_DID_RE.match(soft)
    if m:
        return _write_week_done(m.group("item"))

    m = _REMEMBER_RE.match(soft)
    if m:
        return _write_remember(m.group("note"))

    return _write_checkin(soft)


def _iter_reply_lines(block: str) -> List[str]:
    lines: List[str] = []
    for raw in (block or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("Write below this line") or line.startswith("*Generated"):
            continue
        if line.startswith("#"):
            continue
        line = re.sub(r"^[-*•]\s+", "", line)
        if line:
            lines.append(line)
    return lines


def apply_reply_block(block: str) -> Dict[str, List[str]]:
    """Run each line through write intents. CLI functions stay the source of truth.

    Returns ``{"replies": [...], "leftover": [...]}``. Leftover lines did not
    match a write and should stay as a note (briefing) or fall through to chat.
    """
    replies: List[str] = []
    leftover: List[str] = []
    for line in _iter_reply_lines(block):
        try:
            handled = _try_write_intent(line)
        except Exception as exc:
            replies.append(f"I recognized that but failed while saving it: {exc}")
            continue
        if handled is None:
            leftover.append(line)
        else:
            replies.append(handled)
    return {"replies": replies, "leftover": leftover}


# Order matters: more specific patterns first.
_INTENT_TABLE: Tuple[Tuple[Tuple[str, ...], Callable[[], str]], ...] = (
    (
        (
            "bolt day",
            "play bolt day",
            "start bolt day",
            "run bolt day",
            "start my day",
            "start the day",
            "kickoff",
            "kick off",
            "daily kickoff",
            "content kickoff",
        ),
        _action_day,
    ),
    (
        (
            "good morning bolt",
            "morning bolt",
            "good morning",
            "hey bolt good morning",
            "bolt good morning",
            "give me the morning briefing",
            "run morning briefing",
            "daily briefing",
        ),
        _action_morning,
    ),
    (
        (
            "what should i do",
            "what should i work on",
            "what's next",
            "whats next",
            "next action",
            "next actions",
            "what do you recommend",
            "give me next steps",
            "what needs attention",
        ),
        _action_next,
    ),
    (
        (
            "how are things",
            "status report",
            "give me a status",
            "manager status",
            "catalog status",
            "how is everything",
            "system status",
        ),
        _action_status,
    ),
    (
        (
            "clean the queue",
            "clean queue",
            "clear ghost",
            "clear ghosts",
            "remove missing clips",
            "prune queue",
        ),
        _action_queue_clean,
    ),
    (
        (
            "queue decide",
            "bolt queue decide",
            "bolt q decide",
            "bolt cue decide",  # common STT mis-hear of "queue"
            "q decide",
            "cue decide",
            "review the queue",
            "review queue",
            "decide queue",
            "triage queue",
            "walk the queue",
        ),
        _action_queue_decide,
    ),
    (
        (
            "approve next",
            "approve the next clip",
            "approve clip",
            "approve for peak",
            "bolt approve",
        ),
        _action_approve_next,
    ),
    (
        (
            "hold next",
            "hold the next clip",
            "dont post",
            "don't post",
            "reject next",
            "skip this clip",
        ),
        _action_hold_next,
    ),
    (
        (
            "post next",
            "post now",
            "post the next clip",
            "bolt post now",
            "postnow",
        ),
        _action_post_next,
    ),
    (
        (
            "posting queue",
            "queue status",
            "what's in the queue",
            "whats in the queue",
            "show the queue",
            "social queue",
            "clip queue",
            "ready to post",
            "what can i post",
        ),
        _action_queue,
    ),
    (
        (
            "this week",
            "what's this week",
            "whats this week",
            "week card",
            "what are we doing this week",
            "current week",
            "weekly topic",
        ),
        _action_week,
    ),
    (
        (
            "research status",
            "research update",
            "any research",
            "research candidates",
            "pending research",
        ),
        _action_research,
    ),
    (
        (
            "mission status",
            "command center",
            "any missions",
            "current mission",
        ),
        _action_mission,
    ),
    (
        (
            "storage status",
            "disk space",
            "how much storage",
            "storage report",
            "disk usage",
            "free space",
            "how full is the disk",
        ),
        _action_storage,
    ),
    (
        (
            "api budget",
            "api usage",
            "how much have i spent",
            "grok api cost",
            "budget status",
            "monthly cap",
            "api spend",
        ),
        _action_budget,
    ),
    (
        (
            "social stats",
            "sync stats",
            "tiktok stats",
            "youtube stats",
            "pull stats",
            "performance sync",
            "how did my posts do",
        ),
        _action_stats,
    ),
)


def try_handle_intent(user_text: str) -> Optional[str]:
    """
    If user_text matches a known intent, run the action and return a
    spoken-friendly reply string. Otherwise return None so the caller
    can fall through to free-form LLM chat.

    Write intents (week / mission / remember) run first and call the same
    functions as ``bolt week`` / ``bolt mission update``.
    """
    raw = (user_text or "").strip()
    if not raw:
        return None

    if "\n" in raw:
        applied = apply_reply_block(raw)
        if applied["replies"]:
            parts = list(applied["replies"])
            if applied["leftover"]:
                _save_memory_note(" ".join(applied["leftover"]))
                parts.append("Saved the rest as a note.")
            return " ".join(parts)
        # No writes in the block — let chat handle the whole message.
        raw = _soft(raw)

    try:
        write_reply = _try_write_intent(raw)
    except Exception as exc:
        return f"I recognized that request but failed while saving it: {exc}"
    if write_reply is not None:
        return write_reply

    text = _normalize(raw)
    if not text:
        return None

    for phrases, action in _INTENT_TABLE:
        if _match_any(text, phrases):
            try:
                return action()
            except Exception as exc:
                return f"I recognized that request but failed while running it: {exc}"
    return None


if __name__ == "__main__":
    samples = [
        "Good morning Bolt",
        "What should I do next?",
        "How are things looking?",
        "Show me the posting queue",
        "Research status",
        "Just chatting about games",
    ]
    for s in samples:
        result = try_handle_intent(s)
        print(f"IN:  {s}")
        print(f"OUT: {result!r}\n")
