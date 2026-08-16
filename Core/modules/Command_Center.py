#!/usr/bin/env python3
"""
modules/Command_Center.py — B.O.L.T. Creator Command Center
===========================================================
Turns a broad creator/career/funding goal into a printable mission
briefing Billy can follow without guessing the next step.

This is the `bin/bolt` home for the skill that used to live only as
`bolt-creator-command-center/SKILL.md` (now Core/skills/creator-command-center/).

What it does:
  - Loads the skill playbook (check-in rules + 13-section mission shape)
  - Pulls profile constraints + researcher status + catalog snapshot
  - Scaffolds a mission markdown file under Data/memory/missions/
  - Optionally asks Nexus for a strategy fill-in (best-effort)
  - Never sends mail, posts, or spends money — planning only

CLI (`bolt mission` / `bolt command-center` / `bolt ccc`):
  status | checkin | playbook | list | show | start | next
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from modules.notifier import notify
except ImportError:

    def notify(msg, level="info", reason=None):
        prefix = {"info": "ℹ", "success": "✓", "warning": "⚠", "error": "✗"}.get(
            level, "•"
        )
        print(f"  {prefix}  {msg}")
        if reason:
            print(f"     → {reason}")


# ──────────────────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = PROJECT_ROOT / "Core" / "skills" / "creator-command-center"
SKILL_FILE = SKILL_DIR / "SKILL.md"
MISSIONS_DIR = PROJECT_ROOT / "Data" / "memory" / "missions"
USER_PROFILE = PROJECT_ROOT / "Data" / "memory" / "user_profile.json"
CATALOG_FILE = PROJECT_ROOT / "Data" / "content" / "catalog.json"
STOREFRONT_FILE = PROJECT_ROOT / "Data" / "content" / "storefront.json"

CHECKIN_QUESTIONS = [
    {
        "id": "time",
        "prompt": "Time available (hours this week / deadline)?",
        "why": "Caps how ambitious the mission can be without burnout.",
    },
    {
        "id": "budget",
        "prompt": "Maximum budget for this mission ($)?",
        "why": "Keeps upgrades optional; free/owned assets first.",
    },
    {
        "id": "assets",
        "prompt": "What do you already have (gear, accounts, skills, usable clips)?",
        "why": "Missions start from owned inventory, not shopping lists.",
    },
    {
        "id": "borrow_free",
        "prompt": "What can you borrow, get free, or get cheaply?",
        "why": "Lowers cost without pretending free gear is mandatory.",
    },
    {
        "id": "restrictions",
        "prompt": "Restrictions / deal-breakers / comfort limits right now?",
        "why": "Honors C5/C6 and real-life constraints before planning.",
    },
]

MISSION_SECTIONS = [
    ("Mission title and objective", "State the measurable result and target date."),
    ("Commander's pitch", "Why this fits Billy now and what success unlocks."),
    ("Situation report", "Inputs + current evidence (profile, research, catalog)."),
    ("Options comparison", "Shortlist scored 1–5 on speed, growth, cost, upgrades, fit."),
    ("Mission strategy", "Offer, audience, platform, positioning, path to income."),
    ("Resources and cost", "Owned / free / low-cost / optional upgrades + total budget."),
    ("Step-by-step operation", "Numbered actions with where/what/done looks like."),
    ("Printable checklist", "Short `- [ ]` boxes grouped by phase."),
    ("Timeline and checkpoints", "Dates or time blocks + go/no-go reviews."),
    ("Success dashboard", "Trackable measures, baselines, targets, review date."),
    ("Risks and safeguards", "Scams, costs, disclosure, policies, backup plan."),
    ("Sources checked", "Direct links + date checked (fill after live research)."),
    ("Next command", "The single first action Billy should take."),
]


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _slugify(text: str, max_len: int = 48) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return (s or "mission")[:max_len].rstrip("-")


def _ensure_missions_dir() -> None:
    MISSIONS_DIR.mkdir(parents=True, exist_ok=True)


def skill_path() -> Path:
    return SKILL_FILE


def load_playbook() -> str:
    """Return the full skill markdown (empty string if missing)."""
    if not SKILL_FILE.exists():
        return ""
    try:
        return SKILL_FILE.read_text(encoding="utf-8")
    except OSError:
        return ""


def load_profile() -> Dict[str, Any]:
    if not USER_PROFILE.exists():
        return {}
    try:
        return json.loads(USER_PROFILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _catalog_snapshot() -> Dict[str, Any]:
    out: Dict[str, Any] = {"items": [], "storefront": []}
    try:
        if CATALOG_FILE.exists():
            data = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
            out["items"] = [
                {
                    "name": i.get("name"),
                    "lane": i.get("lane"),
                    "status": i.get("status"),
                    "asin": i.get("asin") or "",
                }
                for i in (data.get("items") or [])
                if isinstance(i, dict)
            ]
    except (json.JSONDecodeError, OSError):
        pass
    try:
        if STOREFRONT_FILE.exists():
            data = json.loads(STOREFRONT_FILE.read_text(encoding="utf-8"))
            out["storefront"] = [
                {
                    "name": i.get("name"),
                    "asin": i.get("asin") or "",
                    "status": i.get("status"),
                }
                for i in (data.get("items") or [])
                if isinstance(i, dict)
            ]
    except (json.JSONDecodeError, OSError):
        pass
    return out


def _research_snapshot() -> Dict[str, Any]:
    try:
        from modules.Researcher import summary as research_summary

        return research_summary()
    except Exception:
        return {}


def checkin_questions() -> List[Dict[str, str]]:
    return list(CHECKIN_QUESTIONS)


def format_checkin() -> str:
    lines = [
        "═" * 70,
        "  CREATOR COMMAND CENTER — MISSION CHECK-IN",
        "═" * 70,
        "",
        "Answer these before finalizing a mission (skill rule: limits first).",
        "",
    ]
    for i, q in enumerate(CHECKIN_QUESTIONS, 1):
        lines.append(f"{i}. {q['prompt']}")
        lines.append(f"   Why it matters: {q['why']}")
        lines.append("")
    lines.append("Pass answers into start with flags:")
    lines.append(
        '  bolt mission start "your goal" --hours 8 --budget 40 '
        '--assets "OBS, mic, Mouse ASIN" --restrictions "no gimmick posts"'
    )
    lines.append("═" * 70)
    return "\n".join(lines)


def list_missions(limit: int = 20) -> List[Path]:
    _ensure_missions_dir()
    files = sorted(MISSIONS_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


def latest_mission() -> Optional[Path]:
    files = list_missions(limit=1)
    return files[0] if files else None


def resolve_mission(ref: str = "latest") -> Optional[Path]:
    if not ref or ref in ("latest", "last", "."):
        return latest_mission()
    path = Path(ref)
    if path.exists():
        return path
    candidate = MISSIONS_DIR / ref
    if candidate.exists():
        return candidate
    if not ref.endswith(".md"):
        candidate = MISSIONS_DIR / f"{ref}.md"
        if candidate.exists():
            return candidate
    # substring match on filename
    for p in list_missions(limit=100):
        if ref.lower() in p.name.lower():
            return p
    return None


def _nexus_blurb(goal: str) -> str:
    try:
        from modules.Nexus_Creator import NexusCreator

        nexus = NexusCreator()
        result = nexus.consult(
            f"Mission planning for creator goal: {goal}",
            context=(
                "Billy is a local-first creator. Prefer honest reviews, owned gear, "
                "Amazon tag billycarter-20, no gimmick content, direction before execution."
            ),
            task_type="strategy",
            complexity="high",
        )
        advice = (result or {}).get("advice") or ""
        provider = (result or {}).get("provider") or "unknown"
        if advice:
            return f"{advice.strip()}\n\n_Provider: {provider}_"
    except Exception:
        pass
    return (
        "_(Nexus unavailable — fill this section after live research. "
        "Prefer official program pages; never invent earnings or approvals.)_"
    )


def build_mission_markdown(
    goal: str,
    *,
    hours: str = "",
    budget: str = "",
    assets: str = "",
    borrow_free: str = "",
    restrictions: str = "",
    deadline: str = "",
    use_nexus: bool = True,
) -> str:
    """Scaffold a full 13-section mission briefing."""
    profile = load_profile()
    vision = profile.get("vision") or {}
    constraints = profile.get("hard_constraints") or []
    research = _research_snapshot()
    catalog = _catalog_snapshot()
    created = _now_iso()
    date_label = datetime.now().strftime("%Y-%m-%d")

    constraint_lines = []
    for c in constraints[:7]:
        if isinstance(c, dict):
            constraint_lines.append(f"- **{c.get('id', '?')}**: {c.get('text', '')}")
        else:
            constraint_lines.append(f"- {c}")
    if not constraint_lines:
        constraint_lines = ["- (no profile constraints loaded)"]

    catalog_lines = [
        f"- {i.get('name')} [{i.get('lane')}/{i.get('status')}]"
        + (f" ASIN={i.get('asin')}" if i.get("asin") else " (no ASIN)")
        for i in catalog.get("items") or []
    ] or ["- (catalog empty — add real products with `bolt manage add`)"]

    research_line = (
        f"Research log: {research.get('research_log_total', 0)} findings · "
        f"{research.get('candidates_pending_c5', 0)} pending C5 · "
        f"{research.get('candidates_kept', 0)} kept"
    )
    career = (vision.get("career_goal") or research.get("user_career_goal") or "").strip()
    nexus_text = _nexus_blurb(goal) if use_nexus else "_(Nexus skipped.)_"

    hours_s = hours or "_(not set — run check-in)_"
    budget_s = budget or "_(not set — run check-in)_"
    assets_s = assets or "_(not set — run check-in)_"
    borrow_s = borrow_free or "_(not set)_"
    restrict_s = restrictions or "_(none listed — still honor C1–C7)_"
    deadline_s = deadline or "_(set a target date)_"

    body = f"""# Mission Briefing — Creator Command Center

**Created:** {created}  
**Date:** {date_label}  
**Status:** draft (planning only — no external sends without Billy's approval)

---

## 1. Mission title and objective

**Goal:** {goal}

**Measurable result:** _(define one clear outcome)_  
**Target date:** {deadline_s}

---

## 2. Commander's pitch

{nexus_text}

**North star (from profile):**  
{career or "_(fill from Data/memory/user_profile.json)_"}

---

## 3. Situation report

### Check-in (limits first)

| Input | Answer |
|-------|--------|
| Time available | {hours_s} |
| Max budget | {budget_s} |
| Already owned / usable | {assets_s} |
| Borrow / free / cheap | {borrow_s} |
| Restrictions | {restrict_s} |

### Hard constraints (never cross)

{chr(10).join(constraint_lines)}

### Catalog / storefront

{chr(10).join(catalog_lines)}

### Research pulse

- {research_line}
- Next research action: {research.get("next_action") or "bolt research pending"}
- Commands: `bolt research pending` · `bolt research c5 keep|drop "Name"`

---

## 4. Options comparison

Score each shortlisted option 1–5 (higher is better). Do not invent precision.

| Option | Speed to income | Long-term growth | Low cost | Useful upgrades | Fit with Billy | Notes |
|--------|-----------------|------------------|----------|-----------------|----------------|-------|
| A — _(primary)_ |  |  |  |  |  |  |
| B — _(fallback)_ |  |  |  |  |  |  |
| C — _(optional)_ |  |  |  |  |  |  |

**Primary pick:** _(A/B/C + one sentence why)_  
**Fallback:** _(if primary fails checkpoint)_

Income paths to consider (from playbook): Amazon affiliate reviews · sponsorships · freelance creator services · digital products · legitimate product testing / gigs.  
Exclude: gimmick content, undisclosed ads, fake engagement, pay-to-play “jobs”.

---

## 5. Mission strategy

- **Offer:**  
- **Audience / customer:**  
- **Platform(s):**  
- **Positioning (honest-take voice):**  
- **Path to income:**  

---

## 6. Resources and cost

| Bucket | Items | Est. cost |
|--------|-------|-----------|
| Already owned | {assets_s} | $0 |
| Free / borrowed | {borrow_s} | $0–low |
| Low-cost essentials |  |  |
| Optional upgrades |  |  |
| **Total** |  | **≤ {budget_s}** |

---

## 7. Step-by-step operation

1. _(Where · what to enter/create · what “done” looks like)_
2.  
3.  
4.  
5.  

Copy-ready drafts / scripts / shot lists go here when they remove guesswork.

---

## 8. Printable checklist

### Phase 1 — Setup
- [ ] Confirm check-in answers still true
- [ ] Clear blocking C5 reviews if research is part of this mission (`bolt research pending`)
- [ ]  

### Phase 2 — Execute
- [ ]  
- [ ]  
- [ ]  

### Phase 3 — Ship / review
- [ ]  
- [ ] Log outcome for Bolt (`bolt manage mark-posted` / `bolt log_perf` when relevant)
- [ ]  

---

## 9. Timeline and checkpoints

| Block | When | Go / no-go |
|-------|------|------------|
| Start |  |  
| Mid checkpoint |  | If blocked → pivot to fallback option |
| Ship | {deadline_s} |  

---

## 10. Success dashboard

| Metric | Baseline | Target | Review date |
|--------|----------|--------|-------------|
|  |  |  |  |
|  |  |  |  |

---

## 11. Risks and safeguards

- **Scams / fees:** never pay to “get approved”; verify official pages
- **Disclosure:** affiliate / gifted products always disclosed
- **C6 authenticity:** reject deals you would not stand behind
- **C7:** no Trump/MAGA/insulting associations
- **Approval gate:** drafts OK; Billy approves before send/post/purchase
- **Backup plan:**  

---

## 12. Sources checked

| Source | URL | Date checked |
|--------|-----|--------------|
|  |  | {date_label} |

---

## 13. Next command

**Do this first:**

```bash
bolt research pending
# or the single concrete action you filled in section 7 step 1
```

Then: open this file, tick Phase 1, and only then expand scope.

---

*Generated by `bolt mission` · playbook: `Core/skills/creator-command-center/SKILL.md`*
"""
    return body


def start_mission(
    goal: str,
    *,
    hours: str = "",
    budget: str = "",
    assets: str = "",
    borrow_free: str = "",
    restrictions: str = "",
    deadline: str = "",
    use_nexus: bool = True,
) -> Path:
    """Create and save a new mission briefing. Returns the file path."""
    goal = (goal or "").strip()
    if not goal:
        raise ValueError("Goal is required. Example: bolt mission start \"fund a new mic\"")

    _ensure_missions_dir()
    stamp = datetime.now().strftime("%Y-%m-%d")
    slug = _slugify(goal)
    path = MISSIONS_DIR / f"{stamp}_{slug}.md"
    # avoid clobber
    n = 2
    while path.exists():
        path = MISSIONS_DIR / f"{stamp}_{slug}-{n}.md"
        n += 1

    md = build_mission_markdown(
        goal,
        hours=hours,
        budget=budget,
        assets=assets,
        borrow_free=borrow_free,
        restrictions=restrictions,
        deadline=deadline,
        use_nexus=use_nexus,
    )
    path.write_text(md, encoding="utf-8")
    notify(
        f"Mission saved: {path}",
        level="success",
        reason="Planning only — nothing was posted or purchased.",
    )
    return path


def extract_next_command(mission_text: str) -> str:
    """Best-effort: pull the 'Next command' section body."""
    m = re.search(
        r"##\s*13\.\s*Next command\s*(.+?)(?:\n---|\n\*Generated|\Z)",
        mission_text,
        re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return "Open the latest mission and fill section 13."
    return m.group(1).strip()


def _rel_or_abs(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def status() -> Dict[str, Any]:
    missions = list_missions(limit=5)
    latest = missions[0] if missions else None
    profile = load_profile()
    research = _research_snapshot()
    return {
        "skill_present": SKILL_FILE.exists(),
        "skill_path": _rel_or_abs(SKILL_FILE) if SKILL_FILE.exists() else "",
        "missions_dir": _rel_or_abs(MISSIONS_DIR),
        "mission_count": len(list_missions(limit=1000)),
        "latest": latest.name if latest else None,
        "career_goal": (profile.get("vision") or {}).get("career_goal", "")[:160],
        "research_pending_c5": research.get("candidates_pending_c5", 0),
    }


def _print_status() -> None:
    s = status()
    print("═" * 70)
    print("  CREATOR COMMAND CENTER")
    print("═" * 70)
    print(f"\nPlaybook: {'✓ ' + s['skill_path'] if s['skill_present'] else '✗ missing'}")
    print(f"Missions: {s['mission_count']} under {s['missions_dir']}")
    print(f"Latest:   {s['latest'] or '(none yet)'}")
    if s.get("career_goal"):
        print(f"\nCareer goal: {s['career_goal'][:200]}…")
    print(f"Research pending C5: {s.get('research_pending_c5', 0)}")
    try:
        from modules.Week_Card import format_card

        print()
        print(format_card())
    except Exception:
        pass
    print(
        "\nCommands:\n"
        "  bolt mission checkin\n"
        "  bolt mission start \"your goal\" --hours 8 --budget 40\n"
        "  bolt mission list\n"
        "  bolt mission show latest\n"
        "  bolt mission next\n"
        "  bolt mission playbook\n"
    )
    print("Aliases: bolt command-center · bolt ccc")
    print("═" * 70)


def _print_list(limit: int = 20) -> None:
    files = list_missions(limit=limit)
    print("═" * 70)
    print(f"  MISSIONS (newest first, {len(files)})")
    print("═" * 70)
    if not files:
        print("\n  (none yet)  →  bolt mission start \"your goal\"\n")
        return
    for p in files:
        print(f"  • {p.name}")
    print()


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="bolt mission",
        description="Creator Command Center — turn goals into printable missions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  bolt mission\n"
            "  bolt mission checkin\n"
            '  bolt mission start "fund a new mic this month" --hours 6 --budget 50\n'
            "  bolt mission list\n"
            "  bolt mission show latest\n"
            "  bolt mission next\n"
            "  bolt ccc start \"first Amazon review from owned gear\"\n"
        ),
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="status",
        help="status|checkin|playbook|list|show|start|next|help",
    )
    parser.add_argument("rest", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    cmd = (args.command or "status").lower()
    rest = list(args.rest or [])
    if rest and rest[0] == "--":
        rest = rest[1:]

    if cmd in ("help", "-h", "--help"):
        parser.print_help()
        return 0

    if cmd in ("status", "home"):
        _print_status()
        return 0

    if cmd == "checkin":
        print(format_checkin())
        return 0

    if cmd == "playbook":
        text = load_playbook()
        if not text:
            print(f"error: playbook missing at {SKILL_FILE}", flush=True)
            return 1
        print(text)
        print(f"\n— playbook path: {SKILL_FILE}")
        return 0

    if cmd == "list":
        limit = 20
        if "--limit" in rest:
            i = rest.index("--limit")
            if i + 1 < len(rest):
                try:
                    limit = int(rest[i + 1])
                except ValueError:
                    pass
        _print_list(limit=limit)
        return 0

    if cmd == "show":
        ref = rest[0] if rest else "latest"
        path = resolve_mission(ref)
        if not path:
            print(f"error: no mission matching '{ref}'", flush=True)
            return 1
        print(path.read_text(encoding="utf-8"))
        print(f"\n— file: {path}")
        return 0

    if cmd == "next":
        path = resolve_mission(rest[0] if rest else "latest")
        if not path:
            print("No missions yet. Start one:")
            print('  bolt mission start "your goal"')
            return 1
        text = path.read_text(encoding="utf-8")
        print("═" * 70)
        print(f"  NEXT COMMAND — {path.name}")
        print("═" * 70)
        print()
        print(extract_next_command(text))
        print()
        return 0

    if cmd == "start":
        start_parser = argparse.ArgumentParser(prog="bolt mission start")
        start_parser.add_argument("goal", nargs="+", help="Mission goal text")
        start_parser.add_argument("--hours", default="", help="Time available")
        start_parser.add_argument("--budget", default="", help="Max budget")
        start_parser.add_argument("--assets", default="", help="What you already have")
        start_parser.add_argument(
            "--borrow",
            default="",
            dest="borrow_free",
            help="Borrow / free / cheap options",
        )
        start_parser.add_argument(
            "--restrictions",
            default="",
            help="Deal-breakers / comfort limits",
        )
        start_parser.add_argument("--deadline", default="", help="Target date")
        start_parser.add_argument(
            "--no-nexus",
            action="store_true",
            help="Skip Nexus strategy fill-in",
        )
        try:
            start_args = start_parser.parse_args(rest)
        except SystemExit:
            return 2
        goal = " ".join(start_args.goal).strip()
        try:
            path = start_mission(
                goal,
                hours=start_args.hours,
                budget=start_args.budget,
                assets=start_args.assets,
                borrow_free=start_args.borrow_free,
                restrictions=start_args.restrictions,
                deadline=start_args.deadline,
                use_nexus=not start_args.no_nexus,
            )
        except ValueError as e:
            print(f"error: {e}", flush=True)
            return 1
        print(f"\n✓ Mission created: {path}")
        print("\nOpen it:")
        print(f"  bolt mission show {path.name}")
        print("  # or open the markdown in your editor / print it")
        missing = []
        if not start_args.hours:
            missing.append("time (--hours)")
        if not start_args.budget:
            missing.append("budget (--budget)")
        if not start_args.assets:
            missing.append("assets (--assets)")
        if missing:
            print("\nCheck-in incomplete (still drafted): " + ", ".join(missing))
            print("  bolt mission checkin")
        return 0

    print(f"bolt mission: unknown command '{cmd}'", flush=True)
    print("  Try: status | checkin | playbook | list | show | start | next | help")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
