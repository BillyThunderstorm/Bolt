#!/usr/bin/env python3
"""
modules/Researcher.py — Direction-finding research for Billy's creator career
===============================================================================
The Researcher role exists because Billy's bottleneck (per user_profile.json
Q2) is "no roadmap, no example to follow." This module:

1. Finds the through-line in Billy's existing work/interests that points to
   the authentic version of the career.
2. Surfaces 3-5 creators doing adjacent work, extracts their patterns.
3. Runs every recommendation through the user's C5/C6 hard constraints:
   - C5: "Would I want to be known for this?"
   - C6: "Believe in / stand behind / trust it?"
   - C7: No Trump/MAGA/insulting intelligence.

The Researcher does NOT:
- Pick a creator for Billy to copy (Billy picks; C5/C6 gate).
- Reach out to anyone (C2 risk tolerance).
- Build content calendars (Producer role).
- Predict revenue (covered in revenue_scenario block of profile).

Output goes to:
- Data/memory/research_log.jsonl (findings + C5 decisions)
- Daily briefing Research Notes (`bolt briefing` / `bolt morning`)

CLI (`bolt research`):
- status | questions | candidates | pending | log
- add | note | c5 keep|drop|maybe

Read-only access to:
- Data/memory/user_profile.json

Designed for night-shift work: research runs async, surfaces in evening
briefings, never blocks Billy's other work. Apple Reminders delivery is
still a future channel (profile priority #1) — not wired in this phase.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from modules.notifier import notify
except ImportError:
    def notify(msg, level="info", reason=None):
        prefix = {"info": "ℹ", "success": "✓", "warning": "⚠", "error": "✗"}.get(level, "•")
        print(f"  {prefix}  {msg}")
        if reason:
            print(f"     → {reason}")


# ──────────────────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # Bolt/ (repo root)
USER_PROFILE = PROJECT_ROOT / "Data" / "memory" / "user_profile.json"
RESEARCH_LOG = PROJECT_ROOT / "Data" / "memory" / "research_log.jsonl"


# ──────────────────────────────────────────────────────────────────────────────
# Constants — hard constraints from the user profile
# ──────────────────────────────────────────────────────────────────────────────

# Patterns that match C7 ("No Trump / MAGA / insulting intelligence").
# Used as a soft filter on candidate creators: never recommend a creator
# whose public persona is associated with these patterns.
C7_BLOCK_PATTERNS = [
    r"\btrump\b",
    r"\bmaga\b",
    r"\bmaga[- ]?adjacent\b",
    r"\b(make america great again)\b",
]

# Phrases that signal C6 violation in a creator's output
# ("Believe in / stand behind / trust it"). These are heuristics, not
# absolute rules — they're red flags, not deal-breakers.
C6_RED_FLAG_PHRASES = [
    "dropshipped",
    "paid promotion not disclosed",
    "shills",
    "fake review",
]


# ──────────────────────────────────────────────────────────────────────────────
# Profile loading
# ──────────────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_profile() -> Dict[str, Any]:
    """Load the user profile. Returns empty dict if missing or malformed."""
    if not USER_PROFILE.exists():
        return {}
    try:
        with USER_PROFILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def get_hard_constraints(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract the user's hard_constraints list from the profile."""
    return profile.get("hard_constraints", [])


def get_vision(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the user's vision block from the profile."""
    return profile.get("vision", {})


def get_lane_mix(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the user's lane_mix block."""
    return profile.get("lane_mix", {})


def get_named_aspirations(profile: Dict[str, Any]) -> List[str]:
    """Extract the user's named_aspirations list."""
    return profile.get("vision", {}).get("named_aspirations", [])


def get_career_goal(profile: Dict[str, Any]) -> str:
    """Extract the user's career_goal string."""
    return profile.get("vision", {}).get("career_goal", "")


# ──────────────────────────────────────────────────────────────────────────────
# Constraint checks (C5, C6, C7)
# ──────────────────────────────────────────────────────────────────────────────

def check_c7(text: str) -> Dict[str, Any]:
    """Check text against C7 (no Trump/MAGA/insulting content).

    Returns: {"passes": bool, "matches": [list of matched patterns]}
    """
    text_lower = text.lower()
    matches = []
    for pattern in C7_BLOCK_PATTERNS:
        if re.search(pattern, text_lower):
            matches.append(pattern)
    return {"passes": len(matches) == 0, "matches": matches}


def check_c6_flags(text: str) -> Dict[str, Any]:
    """Soft check for C6 red flags in creator output. Heuristic only.

    Returns: {"flagged": bool, "matches": [list of flagged phrases]}
    """
    text_lower = text.lower()
    matches = [p for p in C6_RED_FLAG_PHRASES if p in text_lower]
    return {"flagged": len(matches) > 0, "matches": matches}


def gate_candidate(
    candidate: Dict[str, Any],
    profile: Dict[str, Any],
) -> Dict[str, Any]:
    """Run a candidate creator through the C5/C6/C7 gates.

    Args:
        candidate: {
            "name": str,
            "platform": str,
            "summary": str (one-line description),
            "why_match": str (why we think they're relevant),
            "public_signal": str (sample of their content/speech to check),
        }
        profile: full user profile

    Returns the candidate dict with an added "gate" key containing:
        {
            "c7_passes": bool,
            "c7_matches": [list],
            "c6_flagged": bool,
            "c6_matches": [list],
            "c5_user_decision_required": True (always — only Billy decides),
            "user_test": "Would Billy want to be known for this? Does Billy believe in / stand behind / trust it?",
            "verdict": "cleared" | "blocked_c7" | "flagged_c6",
        }
    """
    c7 = check_c7(candidate.get("public_signal", "") + " " + candidate.get("summary", ""))
    c6 = check_c6_flags(candidate.get("public_signal", ""))

    if not c7["passes"]:
        verdict = "blocked_c7"
    elif c6["flagged"]:
        verdict = "flagged_c6"
    else:
        verdict = "cleared"

    gate = {
        "c7_passes": c7["passes"],
        "c7_matches": c7["matches"],
        "c6_flagged": c6["flagged"],
        "c6_matches": c6["matches"],
        "c5_user_decision_required": True,
        "user_test": (
            "Would Billy want to be known for this? "
            "Does Billy believe in / stand behind / trust it? "
            "(Only Billy can answer — surfaced for review.)"
        ),
        "verdict": verdict,
    }
    candidate["gate"] = gate
    return candidate


# ──────────────────────────────────────────────────────────────────────────────
# Research questions — surfaced to Billy
# ──────────────────────────────────────────────────────────────────────────────

def get_research_questions(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build the standing research questions based on the user's profile.

    These are the things Bolt should be investigating. Each one is a
    sub-question of the larger "no roadmap" problem. They update as the
    profile updates.
    """
    vision = get_vision(profile)
    aspirations = get_named_aspirations(profile)
    lanes = get_lane_mix(profile).get("target", {})

    questions = [
        {
            "id": "through_line",
            "question": (
                "What is the through-line in Billy's existing work, interests, "
                "and history that points to the authentic version of this "
                "career? (Per Q2 — no roadmap, no example to model after.)"
            ),
            "why": "Direction-finding is the bottleneck. Without a through-line, "
                   "every recommendation is guesswork.",
            "method": "Pattern-extract from Twitch history, existing content, "
                     "the Skin Care test folder, the Marvel counter project, "
                     "any other artifacts of Billy's interests.",
            "status": "open",
        },
        {
            "id": "creator_examples",
            "question": (
                "Which 3-5 creators are doing adjacent work — product reviews "
                "with company-travel, gaming-to-brand-partnership paths, "
                "event-hosting tiers — and what patterns do they share?"
            ),
            "why": "Per C2, we look for direction before charging into a list. "
                   "External examples give us reference points (not templates).",
            "method": "Surface candidates, run each through C7/C6 gates, present "
                     "for Billy's C5 review.",
            "status": "open",
        },
        {
            "id": "aspirations_research",
            "question": (
                f"How do creators reach the tier represented by these "
                f"aspirations: {aspirations}?"
            ),
            "why": "These represent the tier of recognition Billy's aiming for. "
                   "The path from 'starting out' to 'Dream Con / Marvel tier' "
                   "is not well-documented. We need to map it.",
            "method": "Find creators who've reached this tier, trace their "
                     "0-to-there journey, identify the inflection points.",
            "status": "open",
            "aspirations": aspirations,
        },
        {
            "id": "lane_fit_trials",
            "question": (
                f"How does Billy evaluate whether each of the four parallel-trial "
                f"lanes ({list(lanes.keys())}) actually fits? What signals indicate "
                f"'keep going' vs 'shelve'?"
            ),
            "why": "C5/C6 require ongoing evaluation. We need observable signals "
                   "(not just feelings) that say 'this lane is working' or 'this "
                   "lane isn't.'",
            "method": "Define per-lane fitness signals: audience growth, sponsor "
                     "inbound, user engagement with content, personal satisfaction "
                     "in making it.",
            "status": "open",
        },
        {
            "id": "honest_take_moat",
            "question": (
                "How do honest-take creators build defensibility against "
                "the 'next gimmick' content cycle? What patterns sustain "
                "trust over 3-5 years?"
            ),
            "why": "C6 (authenticity outranks profitability) is the moat. We "
                   "need to understand HOW the moat works, not just that it "
                   "should.",
            "method": "Long-tail case studies. Creators who've maintained "
                     "honest-take positioning for 5+ years and what they did "
                     "differently from those who burned out.",
            "status": "open",
        },
    ]
    return questions


# ──────────────────────────────────────────────────────────────────────────────
# Research log (append-only)
# ──────────────────────────────────────────────────────────────────────────────

def _ensure_log_exists() -> None:
    """Make sure the research log file exists. Creates parent dirs as needed."""
    RESEARCH_LOG.parent.mkdir(parents=True, exist_ok=True)
    if not RESEARCH_LOG.exists():
        RESEARCH_LOG.touch()
        # Set restrictive permissions on creation
        try:
            os.chmod(RESEARCH_LOG, 0o600)
        except OSError:
            pass


def log_finding(
    finding: Dict[str, Any],
    finding_type: str = "candidate_creator",
    profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Append a research finding to the log. Returns the finding as logged.

    Args:
        finding: the finding payload (creator candidate, pattern note, etc.)
        finding_type: "candidate_creator" | "pattern_note" | "lane_signal" | "general"
        profile: optional — if provided, runs C7/C6 gates on the finding

    Returns:
        The finding dict with added fields: timestamp, finding_type, and (if
        profile provided) gate results.
    """
    _ensure_log_exists()

    entry = dict(finding)
    entry["timestamp"] = _now_iso()
    entry["finding_type"] = finding_type

    if profile is not None and finding_type == "candidate_creator":
        entry = gate_candidate(entry, profile)

    with RESEARCH_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return entry


def read_log(limit: int = 50) -> List[Dict[str, Any]]:
    """Read the most recent findings from the log (newest last)."""
    return _read_all_entries()[-limit:]


def _read_all_entries() -> List[Dict[str, Any]]:
    """Read every valid JSONL entry (oldest first)."""
    _ensure_log_exists()
    entries: List[Dict[str, Any]] = []
    with RESEARCH_LOG.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _write_all_entries(entries: List[Dict[str, Any]]) -> None:
    """Rewrite the research log (used for in-place C5 updates)."""
    _ensure_log_exists()
    with RESEARCH_LOG.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _candidate_name(entry: Dict[str, Any]) -> str:
    return (entry.get("name") or entry.get("creator") or "").strip()


def _name_matches(entry: Dict[str, Any], query: str) -> bool:
    """Case-insensitive exact or substring match on name/creator."""
    q = (query or "").strip().lower()
    if not q:
        return False
    name = _candidate_name(entry).lower()
    if not name:
        return False
    return name == q or q in name or name in q


def list_candidates(
    *,
    pending_c5_only: bool = False,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Return candidate_creator entries, newest first."""
    entries = [
        e for e in _read_all_entries()
        if e.get("finding_type") == "candidate_creator"
    ]
    if pending_c5_only:
        entries = [
            e for e in entries
            if (e.get("gate") or {}).get("verdict") == "cleared"
            and not e.get("c5_verdict")
        ]
    entries = list(reversed(entries))
    return entries[:limit]


def add_candidate(
    name: str,
    *,
    platform: str = "",
    summary: str = "",
    why_match: str = "",
    public_signal: str = "",
    profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Log a new candidate creator (auto-gated with profile)."""
    if profile is None:
        profile = load_profile()
    finding = {
        "name": name.strip(),
        "platform": (platform or "").strip() or "unknown",
        "summary": (summary or "").strip(),
        "why_match": (why_match or "").strip(),
        "public_signal": (public_signal or summary or "").strip(),
    }
    return log_finding(finding, finding_type="candidate_creator", profile=profile or None)


def add_note(
    text: str,
    *,
    finding_type: str = "general",
    title: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Log a free-form research note (pattern, lane signal, general)."""
    allowed = {"general", "pattern_note", "lane_signal"}
    if finding_type not in allowed:
        raise ValueError(f"finding_type must be one of {sorted(allowed)}")
    finding: Dict[str, Any] = {"text": text.strip(), "summary": text.strip()}
    if title:
        finding["title"] = title.strip()
        finding["name"] = title.strip()
    if extra:
        finding.update(extra)
    return log_finding(finding, finding_type=finding_type)


# Normalize operator-facing C5 verbs to stored verdicts
C5_VERDICT_ALIASES = {
    "keep": "fits",
    "fits": "fits",
    "yes": "fits",
    "y": "fits",
    "pass": "fits",
    "drop": "no",
    "no": "no",
    "n": "no",
    "reject": "no",
    "skip": "no",
    "maybe": "maybe",
    "later": "maybe",
    "hold": "maybe",
}


def set_c5_verdict(
    name: str,
    verdict: str,
    *,
    why: str = "",
    only_pending: bool = True,
) -> Dict[str, Any]:
    """Record Billy's C5 decision on a candidate creator.

    Updates the matching candidate_creator row(s) in the log and appends a
    short audit entry so the decision is searchable later.

    Args:
        name: creator name (exact or unique substring)
        verdict: keep|drop|fits|no|maybe (aliases accepted)
        why: optional free-text reason in Billy's words
        only_pending: if True, only update candidates without c5_verdict

    Returns:
        {
          "updated": [names...],
          "verdict": normalized,
          "why": why,
          "matches": int,
        }

    Raises:
        ValueError on unknown verdict, no matches, or ambiguous multi-match
        when more than one distinct name matches.
    """
    normalized = C5_VERDICT_ALIASES.get((verdict or "").strip().lower())
    if not normalized:
        raise ValueError(
            f"Unknown C5 verdict '{verdict}'. Use: keep, drop, fits, no, maybe."
        )

    entries = _read_all_entries()
    matches_idx: List[int] = []
    matched_names: List[str] = []
    for i, e in enumerate(entries):
        if e.get("finding_type") != "candidate_creator":
            continue
        if not _name_matches(e, name):
            continue
        if only_pending and e.get("c5_verdict"):
            continue
        matches_idx.append(i)
        matched_names.append(_candidate_name(e) or f"entry-{i}")

    if not matches_idx:
        raise ValueError(
            f"No matching candidate for '{name}'"
            + (" that still needs a C5 decision" if only_pending else "")
            + ". Try: bolt research pending"
        )

    # Disambiguation: prefer exact (case-insensitive) matches over substring
    # matches. Substring-only searches report ambiguity and refuse. This lets
    # callers approve "Unbox Therapy (generalist mode)" verbatim even when a
    # shorter "Unbox Therapy" also exists in the log.
    q_lower = name.strip().lower()
    exact_idx = [i for i in matches_idx if _candidate_name(entries[i]).lower() == q_lower]
    substring_idx = [i for i in matches_idx if i not in exact_idx]
    if exact_idx and len({_candidate_name(entries[i]).lower() for i in exact_idx}) == 1:
        matches_idx = exact_idx
        matched_names = [_candidate_name(entries[i]) for i in exact_idx]
    elif substring_idx:
        unique_names = sorted({_candidate_name(entries[i]).lower() for i in substring_idx})
        if len(unique_names) > 1:
            raise ValueError(
                f"Ambiguous name '{name}' matches: {', '.join(sorted({_candidate_name(entries[i]) for i in matches_idx}))}. "
                "Use a more specific name."
            )
        # Substring search disambiguated to exactly one pending candidate — proceed.

    decided_at = _now_iso()
    for i in matches_idx:
        entries[i]["c5_verdict"] = normalized
        entries[i]["c5_decided_at"] = decided_at
        if why:
            entries[i]["c5_user_words"] = why.strip()

    # Audit trail as a separate finding (keeps history even if candidate re-added)
    display = matched_names[0]
    audit = {
        "timestamp": decided_at,
        "finding_type": "c5_decision",
        "name": display,
        "creator": display,
        "c5_verdict": normalized,
        "c5_user_words": (why or "").strip(),
        "summary": f"C5 {normalized}: {display}"
        + (f" — {why.strip()}" if why else ""),
    }
    entries.append(audit)
    _write_all_entries(entries)

    notify(
        f"C5 recorded: {display} → {normalized}",
        level="success",
        reason=why.strip() if why else "Billy's call saved to research_log.jsonl",
    )
    return {
        "updated": matched_names,
        "verdict": normalized,
        "why": (why or "").strip(),
        "matches": len(matches_idx),
        "decided_at": decided_at,
    }


def pending_c5_count() -> int:
    return len(list_candidates(pending_c5_only=True, limit=10000))


# ──────────────────────────────────────────────────────────────────────────────
# Summary builders — what to show Billy
# ──────────────────────────────────────────────────────────────────────────────

def summary(profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build the researcher role summary: who Billy is + what we're working on.

    This is what the assistant/manager roles will surface in briefings.
    """
    if profile is None:
        profile = load_profile()

    aspirations = get_named_aspirations(profile)
    questions = get_research_questions(profile)

    recent = _read_all_entries()

    candidates = [r for r in recent if r.get("finding_type") == "candidate_creator"]
    candidates_total = len(candidates)
    candidates_cleared = sum(
        1 for r in candidates
        if (r.get("gate") or {}).get("verdict") == "cleared"
    )
    candidates_blocked = sum(
        1 for r in candidates
        if (r.get("gate") or {}).get("verdict") == "blocked_c7"
    )
    candidates_flagged = sum(
        1 for r in candidates
        if (r.get("gate") or {}).get("verdict") == "flagged_c6"
    )
    candidates_pending_c5 = sum(
        1 for r in candidates
        if (r.get("gate") or {}).get("verdict") == "cleared" and not r.get("c5_verdict")
    )
    candidates_kept = sum(1 for r in candidates if r.get("c5_verdict") == "fits")
    candidates_dropped = sum(1 for r in candidates if r.get("c5_verdict") == "no")

    if candidates_pending_c5 > 0:
        next_action = (
            f"{candidates_pending_c5} candidate(s) need your C5 call. "
            "Run `bolt research pending`, then "
            "`bolt research c5 keep \"Name\"` or `bolt research c5 drop \"Name\"`. "
            "Bolt cannot answer C5 for you."
        )
    elif candidates_total == 0:
        next_action = (
            "No candidates yet. Add one with "
            "`bolt research add \"Name\" --platform YouTube --summary \"...\" --why \"...\"`."
        )
    else:
        next_action = (
            "All gated candidates have a C5 decision. "
            "Add new candidates or dig into open research questions "
            "(`bolt research questions`)."
        )

    return {
        "role": "researcher",
        "user_career_goal": get_career_goal(profile),
        "named_aspirations": aspirations,
        "open_questions": [q["id"] for q in questions],
        "research_log_total": len(recent),
        "candidates_total": candidates_total,
        "candidates_cleared": candidates_cleared,
        "candidates_blocked_c7": candidates_blocked,
        "candidates_flagged_c6": candidates_flagged,
        "candidates_pending_c5": candidates_pending_c5,
        "candidates_kept": candidates_kept,
        "candidates_dropped": candidates_dropped,
        "next_action": next_action,
    }


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def _print_summary() -> None:
    """CLI helper: print a human-readable summary."""
    s = summary()
    goal = s["user_career_goal"] or "(no career goal in profile yet)"
    print("═" * 70)
    print("  RESEARCHER ROLE — STATUS")
    print("═" * 70)
    print(f"\nCareer goal: {goal[:200]}{'...' if len(goal) > 200 else ''}")
    print("\nNamed aspirations:")
    for a in s["named_aspirations"]:
        print(f"  • {a}")
    if not s["named_aspirations"]:
        print("  (none yet — fill Data/memory/user_profile.json)")
    print(f"\nOpen research questions: {len(s['open_questions'])}")
    for q in s["open_questions"]:
        print(f"  • {q}")
    print(f"\nResearch log: {s['research_log_total']} total findings")
    print("  Candidate creators:")
    print(f"    Total:        {s['candidates_total']}")
    print(f"    Cleared:      {s['candidates_cleared']}")
    print(f"    Pending C5:   {s['candidates_pending_c5']}")
    print(f"    Kept (fits):  {s['candidates_kept']}")
    print(f"    Dropped:      {s['candidates_dropped']}")
    print(f"    Blocked (C7): {s['candidates_blocked_c7']}")
    print(f"    Flagged (C6): {s['candidates_flagged_c6']}")
    print(f"\nNext action: {s['next_action']}")
    print("═" * 70)


def _print_questions() -> None:
    profile = load_profile()
    questions = get_research_questions(profile)
    print("═" * 70)
    print("  RESEARCH QUESTIONS")
    print("═" * 70)
    for q in questions:
        print(f"\n[{q['id']}]  status={q.get('status', 'open')}")
        print(f"  Q: {q['question']}")
        print(f"  Why: {q.get('why', '')}")
        print(f"  Method: {q.get('method', '')}")
    print()


def _format_candidate_line(e: Dict[str, Any]) -> None:
    gate = e.get("gate") or {}
    name = _candidate_name(e) or "(unnamed)"
    platform = e.get("platform") or "?"
    gate_verdict = gate.get("verdict", "ungated")
    c5 = e.get("c5_verdict") or "pending"
    print(f"\n• {name}  [{platform}]  gate={gate_verdict}  c5={c5}")
    if e.get("summary"):
        print(f"    {e['summary']}")
    if e.get("why_match"):
        print(f"    Why: {e['why_match']}")
    if e.get("c5_user_words"):
        print(f"    Your words: {e['c5_user_words']}")
    elif not e.get("c5_verdict") and gate.get("c5_user_decision_required"):
        print(f"    C5: {gate.get('user_test', 'Would you want to be known for this?')}")
        print(f"    → bolt research c5 keep \"{name}\"")
        print(f"    → bolt research c5 drop \"{name}\"")


def _print_candidates(limit: int = 20, pending_only: bool = False) -> None:
    entries = list_candidates(pending_c5_only=pending_only, limit=limit)
    title = "PENDING C5 REVIEW" if pending_only else "CANDIDATE CREATORS"
    print("═" * 70)
    print(f"  {title} (showing {len(entries)}, newest first)")
    print("═" * 70)
    if not entries:
        if pending_only:
            print("\n  (none pending — all cleared candidates have a C5 decision)")
            print("  Add more: bolt research add \"Name\" --platform YouTube --summary \"...\"")
        else:
            print("\n  (no candidate_creator findings yet)")
            print("  Add one: bolt research add \"Name\" --platform YouTube --summary \"...\" --why \"...\"")
        print()
        return
    for e in entries:
        _format_candidate_line(e)
    print()


def _print_log(limit: int = 15) -> None:
    entries = list(reversed(read_log(limit=limit)))
    print("═" * 70)
    print(f"  RESEARCH LOG (last {len(entries)})")
    print("═" * 70)
    if not entries:
        print("\n  (empty)")
        print()
        return
    for e in entries:
        ts = e.get("timestamp", "?")
        kind = e.get("finding_type", "finding")
        label = e.get("name") or e.get("creator") or e.get("title") or kind
        print(f"\n[{ts}] {kind}: {label}")
        summary_text = e.get("summary") or e.get("why_this_creator") or e.get("text") or ""
        if summary_text:
            print(f"  {summary_text[:240]}")
        if e.get("c5_verdict"):
            print(f"  c5={e['c5_verdict']}")
    print()


def briefing_snippet(limit: int = 3) -> str:
    """Short markdown block for inclusion in the daily briefing.

    Best-effort: never raises. Returns empty string if nothing useful.
    """
    try:
        s = summary()
    except Exception:
        return ""

    lines = ["## Research Notes", ""]
    total = s.get("research_log_total", 0)
    pending = s.get("candidates_pending_c5", 0)
    if total == 0 and not s.get("named_aspirations"):
        return ""

    lines.append(
        f"- Log: **{total}** findings · "
        f"**{pending}** pending C5 · "
        f"**{s.get('candidates_kept', 0)}** kept · "
        f"**{s.get('candidates_dropped', 0)}** dropped · "
        f"**{s.get('candidates_blocked_c7', 0)}** blocked (C7)"
    )

    try:
        recent = list_candidates(pending_c5_only=True, limit=limit)
    except Exception:
        recent = []

    if recent:
        lines.append(
            "- Cleared candidates awaiting your C5 call "
            "(`bolt research c5 keep|drop \"Name\"`):"
        )
        for e in recent:
            name = _candidate_name(e) or "(unnamed)"
            platform = e.get("platform") or "?"
            why = (e.get("why_match") or e.get("summary") or "").strip()
            if why:
                lines.append(f"  - **{name}** ({platform}) — {why[:140]}")
            else:
                lines.append(f"  - **{name}** ({platform})")
    else:
        next_action = s.get("next_action") or ""
        if next_action:
            lines.append(f"- Next: {next_action}")

    lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry for `python -m modules.Researcher` / `bolt research`."""
    import argparse
    import shlex

    raw = list(argv) if argv is not None else None
    # Allow: bolt research c5 keep "Name"  → command=c5, rest handled below
    parser = argparse.ArgumentParser(
        prog="bolt research",
        description="Direction-finding researcher (profile + C5/C6/C7 gates + log).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  bolt research\n"
            "  bolt research pending\n"
            "  bolt research add \"iJustine\" --platform YouTube "
            "--summary \"Tech reviews + events\" --why \"Industry insider path\"\n"
            "  bolt research c5 keep \"iJustine\" --why \"Want that event path\"\n"
            "  bolt research c5 drop \"Someone\" --why \"Not my voice\"\n"
            "  bolt research note \"Through-line idea: honest tangent reviews\"\n"
        ),
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="status",
        help="status|questions|candidates|pending|log|add|note|c5|help",
    )
    parser.add_argument("rest", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
    parser.add_argument("--limit", type=int, default=20, help="Max entries for list commands")
    # Shared flags for add / note / c5 (parsed from rest when needed)
    args, _unknown = parser.parse_known_args(raw)

    cmd = (args.command or "status").lower()
    rest = list(args.rest or [])
    # argparse.REMAINDER keeps a leading -- sometimes; strip empty
    if rest and rest[0] == "--":
        rest = rest[1:]

    # --limit may land in rest because REMAINDER swallows trailing flags
    limit = args.limit
    cleaned_rest: List[str] = []
    i = 0
    while i < len(rest):
        if rest[i] == "--limit" and i + 1 < len(rest):
            try:
                limit = int(rest[i + 1])
            except ValueError:
                pass
            i += 2
            continue
        if rest[i].startswith("--limit="):
            try:
                limit = int(rest[i].split("=", 1)[1])
            except ValueError:
                pass
            i += 1
            continue
        cleaned_rest.append(rest[i])
        i += 1
    rest = cleaned_rest

    if cmd in ("help", "-h", "--help"):
        parser.print_help()
        return 0

    if cmd == "status":
        _print_summary()
        return 0

    if cmd == "questions":
        _print_questions()
        return 0

    if cmd == "candidates":
        _print_candidates(limit=limit, pending_only=False)
        return 0

    if cmd == "pending":
        _print_candidates(limit=limit, pending_only=True)
        return 0

    if cmd == "log":
        _print_log(limit=limit)
        return 0

    if cmd == "add":
        add_parser = argparse.ArgumentParser(prog="bolt research add")
        add_parser.add_argument("name", help="Creator name")
        add_parser.add_argument("--platform", default="", help="YouTube, TikTok, Twitch, …")
        add_parser.add_argument("--summary", default="", help="One-line description")
        add_parser.add_argument("--why", default="", dest="why_match", help="Why they match Billy")
        add_parser.add_argument(
            "--signal",
            default="",
            dest="public_signal",
            help="Public content sample for C6/C7 gating",
        )
        try:
            add_args = add_parser.parse_args(rest)
        except SystemExit:
            return 2
        if not add_args.name.strip():
            print("error: name is required", flush=True)
            return 2
        entry = add_candidate(
            add_args.name,
            platform=add_args.platform,
            summary=add_args.summary,
            why_match=add_args.why_match,
            public_signal=add_args.public_signal,
        )
        gate = (entry.get("gate") or {}).get("verdict", "ungated")
        print(f"✓ Logged candidate: {entry.get('name')}  gate={gate}")
        if gate == "cleared":
            print(f"  C5 still needed: bolt research c5 keep \"{entry.get('name')}\"")
        return 0

    if cmd == "note":
        note_parser = argparse.ArgumentParser(prog="bolt research note")
        note_parser.add_argument("text", nargs="+", help="Note text")
        note_parser.add_argument(
            "--type",
            default="general",
            dest="finding_type",
            choices=["general", "pattern_note", "lane_signal"],
        )
        note_parser.add_argument("--title", default="")
        try:
            note_args = note_parser.parse_args(rest)
        except SystemExit:
            return 2
        text = " ".join(note_args.text).strip()
        entry = add_note(text, finding_type=note_args.finding_type, title=note_args.title)
        print(f"✓ Logged {entry.get('finding_type')}: {text[:80]}")
        return 0

    if cmd == "c5":
        c5_parser = argparse.ArgumentParser(prog="bolt research c5")
        c5_parser.add_argument(
            "verdict",
            help="keep|drop|fits|no|maybe",
        )
        c5_parser.add_argument("name", help="Creator name (substring OK if unique)")
        c5_parser.add_argument("--why", default="", help="Your words — why keep or drop")
        c5_parser.add_argument(
            "--all",
            action="store_true",
            help="Also update candidates that already have a C5 verdict",
        )
        try:
            c5_args = c5_parser.parse_args(rest)
        except SystemExit:
            return 2
        try:
            result = set_c5_verdict(
                c5_args.name,
                c5_args.verdict,
                why=c5_args.why,
                only_pending=not c5_args.all,
            )
        except ValueError as e:
            print(f"error: {e}", flush=True)
            return 1
        names = ", ".join(result["updated"])
        print(f"✓ C5 {result['verdict']}: {names}")
        if result.get("why"):
            print(f"  Why: {result['why']}")
        print(f"  Pending remaining: {pending_c5_count()}")
        return 0

    print(f"bolt research: unknown command '{cmd}'", flush=True)
    print("  Try: status | questions | candidates | pending | log | add | note | c5 | help")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
