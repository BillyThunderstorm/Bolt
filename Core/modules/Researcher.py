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
- Data/memory/research_log.jsonl (one JSON per finding, append-only)
- Apple Reminders via the assistant role (when wired)

Read-only access to:
- Data/memory/user_profile.json

Designed for night-shift work: research runs async, surfaces in evening
briefings, never blocks Billy's other work.
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
    return entries[-limit:]


# ──────────────────────────────────────────────────────────────────────────────
# Summary builders — what to show Billy
# ──────────────────────────────────────────────────────────────────────────────

def summary(profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build the researcher role summary: who Billy is + what we're working on.

    This is what the assistant/manager roles will surface in briefings.
    """
    if profile is None:
        profile = load_profile()

    vision = get_vision(profile)
    aspirations = get_named_aspirations(profile)
    questions = get_research_questions(profile)

    recent = read_log(limit=10000)  # Read all; surface total in summary

    candidates_total = sum(1 for r in recent if r.get("finding_type") == "candidate_creator")
    candidates_cleared = sum(
        1 for r in recent
        if r.get("finding_type") == "candidate_creator"
        and r.get("gate", {}).get("verdict") == "cleared"
    )
    candidates_blocked = sum(
        1 for r in recent
        if r.get("finding_type") == "candidate_creator"
        and r.get("gate", {}).get("verdict") == "blocked_c7"
    )
    candidates_flagged = sum(
        1 for r in recent
        if r.get("finding_type") == "candidate_creator"
        and r.get("gate", {}).get("verdict") == "flagged_c6"
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
        "next_action": (
            "Review the cleared candidates in research_log.jsonl and answer "
            "the C5 user test ('Would I want to be known for this?') for each. "
            "Bolt cannot answer this for you."
        ),
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


def _print_candidates(limit: int = 20) -> None:
    entries = [
        e for e in read_log(limit=10000)
        if e.get("finding_type") == "candidate_creator"
    ]
    # Newest last in the log; show newest first for review.
    entries = list(reversed(entries))[:limit]
    print("═" * 70)
    print(f"  CANDIDATE CREATORS (showing {len(entries)}, newest first)")
    print("═" * 70)
    if not entries:
        print("\n  (no candidate_creator findings yet)")
        print("  Log findings with Researcher.log_finding(... finding_type='candidate_creator')")
        print()
        return
    for e in entries:
        gate = e.get("gate") or {}
        name = e.get("name") or e.get("creator") or "(unnamed)"
        platform = e.get("platform") or "?"
        verdict = gate.get("verdict", "ungated")
        print(f"\n• {name}  [{platform}]  verdict={verdict}")
        if e.get("summary"):
            print(f"    {e['summary']}")
        if e.get("why_match"):
            print(f"    Why: {e['why_match']}")
        if gate.get("c5_user_decision_required"):
            print(f"    C5: {gate.get('user_test', 'Would you want to be known for this?')}")
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
    cleared = s.get("candidates_cleared", 0)
    if total == 0 and not s.get("named_aspirations"):
        return ""

    lines.append(
        f"- Log: **{total}** findings · "
        f"**{cleared}** candidates cleared for C5 review · "
        f"**{s.get('candidates_blocked_c7', 0)}** blocked (C7) · "
        f"**{s.get('candidates_flagged_c6', 0)}** flagged (C6)"
    )

    # Surface recent cleared candidates that still need Billy's C5 call.
    try:
        recent = [
            e for e in reversed(read_log(limit=100))
            if e.get("finding_type") == "candidate_creator"
            and (e.get("gate") or {}).get("verdict") == "cleared"
            and not e.get("c5_verdict")
        ][:limit]
    except Exception:
        recent = []

    if recent:
        lines.append(
            "- Cleared candidates awaiting your C5 call "
            "(\"Would I want to be known for this?\"):"
        )
        for e in recent:
            name = e.get("name") or e.get("creator") or "(unnamed)"
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

    parser = argparse.ArgumentParser(
        prog="bolt research",
        description="Direction-finding researcher role (profile + C5/C6/C7 gates + log).",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="status",
        choices=["status", "questions", "candidates", "log", "help"],
        help="What to show (default: status)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Max entries for candidates/log (default: 20)",
    )
    args = parser.parse_args(argv)

    if args.command == "help":
        parser.print_help()
        print(
            "\nExamples:\n"
            "  bolt research                 # status summary\n"
            "  bolt research questions       # standing research questions\n"
            "  bolt research candidates      # gated candidate creators\n"
            "  bolt research log --limit 10  # recent findings\n"
        )
        return 0
    if args.command == "status":
        _print_summary()
        return 0
    if args.command == "questions":
        _print_questions()
        return 0
    if args.command == "candidates":
        _print_candidates(limit=args.limit)
        return 0
    if args.command == "log":
        _print_log(limit=args.limit)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
