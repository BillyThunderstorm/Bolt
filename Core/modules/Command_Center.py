#!/usr/bin/env python3
"""
modules/Command_Center.py — B.O.L.T. Creator Command Center
===========================================================
Turns a broad creator/career/funding goal into a printable mission
briefing Billy can follow without guessing the next step.

This is the `bin/bolt` home for the mission playbook at
`Core/skills/creator-command-center/SKILL.md`.

What it does:
  - Loads the skill playbook (check-in rules + 13-section mission shape)
  - Pulls profile constraints + week card + researcher status + catalog
  - Writes a filled mission markdown file under Data/memory/missions/
  - Optionally asks Nexus for a strategy overlay (best-effort JSON)
  - Never sends mail, posts, or spends money — planning only

CLI (`bolt mission` / `bolt command-center` / `bolt ccc`):
  status | checkin | playbook | list | show | start | fill | update | next
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

_PLACEHOLDER_ANSWERS = (
    "",
    "_(not set)_",
    "_(not set — run check-in)_",
    "_(none listed — still honor C1–C7)_",
)

_CATALOG_LANES = {
    "gaming_tech": ("game", "tech"),
    "pop_culture": ("game", "product"),
    "beauty_skincare": ("skincare",),
    "product": ("product",),
    "general_product_amazon": ("product",),
}


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
    lines.append("Or patch the latest file:")
    lines.append(
        '  bolt mission update latest --hours 8 --budget 40 --assets "OBS, mic"'
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


def _blank_answer(value: str) -> bool:
    v = (value or "").strip()
    if not v:
        return True
    if v in _PLACEHOLDER_ANSWERS:
        return True
    if v.startswith("_(") and "not set" in v:
        return True
    return False


def _week_snapshot() -> Dict[str, Any]:
    try:
        from modules.Week_Card import load as load_week

        data = load_week()
    except Exception:
        return {
            "this_week": "",
            "this_week_note": "",
            "this_week_done": [],
            "last_week": "",
            "last_week_note": "",
            "bans": [],
        }
    tw = data.get("this_week") if isinstance(data.get("this_week"), dict) else {}
    lw = data.get("last_week") if isinstance(data.get("last_week"), dict) else {}
    bans = data.get("do_not_suggest") or []
    ban_text = []
    for b in bans:
        if isinstance(b, dict):
            t = (b.get("text") or "").strip()
            if t:
                ban_text.append(t)
        elif str(b).strip():
            ban_text.append(str(b).strip())
    done = tw.get("done") or []
    if not isinstance(done, list):
        done = []
    return {
        "this_week": (tw.get("topic") or "").strip(),
        "this_week_note": (tw.get("note") or "").strip(),
        "this_week_done": [str(x) for x in done if str(x).strip()],
        "last_week": (lw.get("topic") or "").strip(),
        "last_week_note": (lw.get("note") or "").strip(),
        "bans": ban_text[:8],
    }


def _kept_candidates(limit: int = 6) -> List[Dict[str, str]]:
    try:
        from modules.Researcher import list_candidates

        kept = [
            c
            for c in list_candidates(limit=100)
            if isinstance(c, dict) and c.get("c5_verdict") == "fits"
        ]
    except Exception:
        return []
    out: List[Dict[str, str]] = []
    for c in kept[:limit]:
        out.append(
            {
                "name": str(c.get("name") or "").strip(),
                "platform": str(c.get("platform") or "").strip(),
                "why": str(c.get("why_match") or c.get("summary") or "").strip()[:180],
            }
        )
    return [x for x in out if x["name"]]


def _lane_for_topic(topic: str) -> str:
    try:
        from modules.Researcher import lane_from_topic

        return lane_from_topic(topic) or ""
    except Exception:
        return ""


def _catalog_for_week(items: List[Dict[str, Any]], topic: str) -> List[Dict[str, Any]]:
    lane = _lane_for_topic(topic)
    wanted = _CATALOG_LANES.get(lane, ())
    if wanted:
        matched = [i for i in items if (i.get("lane") or "") in wanted]
        if matched:
            return matched
    return list(items)


def _item_shipped(item: Dict[str, Any]) -> bool:
    return str(item.get("status") or "").lower() in {
        "posted",
        "done",
        "shipped",
        "complete",
    }


def _evidence_pack() -> Dict[str, Any]:
    profile = load_profile()
    vision = profile.get("vision") or {}
    catalog = _catalog_snapshot()
    research = _research_snapshot()
    week = _week_snapshot()
    return {
        "profile": profile,
        "career_goal": (vision.get("career_goal") or research.get("user_career_goal") or "").strip(),
        "constraints": profile.get("hard_constraints") or [],
        "horizon": profile.get("near_term_horizon") or {},
        "catalog_items": catalog.get("items") or [],
        "storefront": catalog.get("storefront") or [],
        "research": research,
        "week": week,
        "kept": _kept_candidates(),
    }


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*```$", "", t)
    start = t.find("{")
    end = t.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(t[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _names(items: List[Dict[str, Any]], limit: int = 4) -> str:
    names = [str(i.get("name") or "").strip() for i in items if i.get("name")]
    names = [n for n in names if n]
    if not names:
        return ""
    return ", ".join(names[:limit])


def _goal_kind(goal: str, topic: str = "") -> str:
    """Classify the mission so the plan follows the goal, not a generic template."""
    g = (goal or "").lower()
    if any(
        w in g
        for w in (
            "career",
            "roadmap",
            "direction",
            "thin air",
            "what success",
            "from scratch",
        )
    ):
        return "direction"
    if any(
        w in g
        for w in (
            "sponsor",
            "brand deal",
            "freelance",
            "digital product",
            "affiliate program",
        )
    ):
        return "income_path"
    if any(
        w in g
        for w in (
            "fund",
            "upgrade",
            "buy ",
            "mic",
            "camera",
            "light",
            "gear",
            "audio",
            "tripod",
        )
    ):
        return "upgrade"
    if any(w in g for w in ("review", "post", "film", "clip", "this week", "content")):
        return "content"
    return "content" if (topic or "").strip() else "direction"


def _default_next_command(
    goal: str,
    checkin: Dict[str, str],
    evidence: Dict[str, Any],
) -> str:
    missing = []
    if _blank_answer(checkin.get("hours", "")):
        missing.append("--hours")
    if _blank_answer(checkin.get("budget", "")):
        missing.append("--budget")
    if _blank_answer(checkin.get("assets", "")):
        missing.append("--assets")
    if missing:
        flags = " ".join(f'{f} "…"' for f in missing)
        return (
            "Check-in is incomplete. Limits first — do not expand the plan yet.\n\n"
            f"```bash\nbolt mission update latest {flags}\n```"
        )

    week = evidence.get("week") or {}
    topic = (week.get("this_week") or "").strip()
    kind = _goal_kind(goal, topic)
    pending = int((evidence.get("research") or {}).get("candidates_pending_c5") or 0)

    if kind == "direction" and pending:
        return (
            f"{pending} candidate(s) still need your C5 call. "
            "Bolt cannot answer C5 for you.\n\n"
            "```bash\nbolt research pending\n```"
        )

    if kind == "upgrade":
        budget = checkin.get("budget") or "the stated budget"
        assets = checkin.get("assets") or "owned gear"
        return (
            f"Test whether current gear ({assets}) actually blocks this week's work. "
            f"If it does not, do not buy. If it does, list one used/cheap option "
            f"within {budget} — draft only, no purchase.\n\n"
            "```bash\nbolt week\n```"
        )

    if kind == "income_path":
        return (
            "Do not apply or pitch yet. Verify one live official program page, "
            "then stop for approval.\n\n"
            "```bash\nbolt research find\nbolt sponsors next\n```"
        )

    if topic:
        return (
            f"Stay on this week ({topic}). One owned-gear step, then log it.\n\n"
            "```bash\nbolt week\nbolt manage next\n```"
        )

    return (
        "No week topic yet. Pick one of the four lanes, then research that lane — "
        "do not start a new career plan.\n\n"
        "```bash\n"
        'bolt week set "gaming / tech" --note "why this week"\n'
        "bolt research find\n"
        "```"
    )


def _local_strategy(
    goal: str,
    evidence: Dict[str, Any],
    checkin: Dict[str, str],
) -> Dict[str, Any]:
    week = evidence.get("week") or {}
    topic = (week.get("this_week") or "").strip()
    kind = _goal_kind(goal, topic)
    items = list(evidence.get("catalog_items") or [])
    lane_items = _catalog_for_week(items, topic or goal)
    unposted = [i for i in lane_items if not _item_shipped(i)]
    posted = [i for i in lane_items if _item_shipped(i)]
    kept = evidence.get("kept") or []
    research = evidence.get("research") or {}
    career = evidence.get("career_goal") or ""
    bans = week.get("bans") or []
    done = week.get("this_week_done") or []
    pending = int(research.get("candidates_pending_c5") or 0)
    hours = checkin.get("hours") or "unset"
    budget = checkin.get("budget") or "unset"
    assets = checkin.get("assets") or "owned gear"

    unposted_names = _names(unposted) or "nothing unposted in this lane"
    posted_names = _names(posted, 3)
    kept_names = ", ".join(k["name"] for k in kept[:4] if k.get("name")) or "(none kept yet)"

    if kind == "upgrade":
        opt_a = {
            "label": f"A — Justify the upgrade against this week ({topic or 'current work'})",
            "speed": "est. 3",
            "growth": "est. 3",
            "low_cost": "est. 5",
            "upgrades": "est. 4",
            "fit": "est. 5",
            "notes": (
                f"Assets already listed: {assets}. "
                "Treat new gear as optional and justified, not a prerequisite. "
                f"Budget cap {budget}."
            ),
        }
        opt_b = {
            "label": "B — Ship this week's owned-gear work with what you already have",
            "speed": "est. 4",
            "growth": "est. 3",
            "low_cost": "est. 5",
            "upgrades": "est. 1",
            "fit": "est. 5",
            "notes": (
                f"Unposted in-lane: {unposted_names}. "
                + (
                    f"Already shipped (do not reassign): {posted_names}."
                    if posted_names
                    else ""
                )
            ),
        }
        opt_c = {
            "label": f"C — Buy used/cheap within {budget} only if A proves the blocker",
            "speed": "est. 2",
            "growth": "est. 2",
            "low_cost": "est. 3",
            "upgrades": "est. 5",
            "fit": "est. 3",
            "notes": "Draft a shopping shortlist. No purchase without approval. No invented product links.",
        }
        primary = opt_a["label"]
        fallback = opt_b["label"]
        offer = (
            f"Optional upgrade for `{goal}` only if current gear ({assets}) "
            f"blocks this week's `{topic or 'work'}`. Cap {budget}."
        )
        execute_1 = (
            f"Desk · test current gear ({assets}) on this week's work · "
            "done = a yes/no: is this the blocker? If no, do not buy."
        )
        path = (
            "Do not spend to start. Earn toward the cap from owned ASINs if you still "
            "want the upgrade after the test. Affiliate tag billycarter-20 on real ASINs."
        )
    elif kind == "direction":
        opt_a = {
            "label": "A — Direction research on C5-kept examples (study, do not copy)",
            "speed": "est. 2",
            "growth": "est. 5",
            "low_cost": "est. 5",
            "upgrades": "est. 1",
            "fit": "est. 5",
            "notes": f"Kept: {kept_names}. Year-end job is a roadmap + proof, not a posting streak.",
        }
        opt_b = {
            "label": f"B — Stay on this week ({topic or 'set a lane'}) and capture proof",
            "speed": "est. 4",
            "growth": "est. 3",
            "low_cost": "est. 5",
            "upgrades": "est. 2",
            "fit": "est. 5",
            "notes": f"Unposted in-lane: {unposted_names}. Proof goes on the week card.",
        }
        opt_c = {
            "label": "C — Income-path scouting (sponsors / freelance) after C5/C6",
            "speed": "est. 1",
            "growth": "est. 4",
            "low_cost": "est. 4",
            "upgrades": "est. 2",
            "fit": "est. 3",
            "notes": "Do not invent rates, approvals, or open programs. Verify live before outreach.",
        }
        primary = opt_a["label"]
        fallback = opt_b["label"]
        offer = (
            "A written picture of what success looks like in this profession, "
            "or a roadmap plus proof the current work leads somewhere — by the year-end horizon."
        )
        execute_1 = (
            "Research log · read C5-kept examples · done = one sentence of what to copy "
            "as a *process*, never as a persona."
        )
        path = (
            "No new income path until the direction sentence exists. "
            "Owned-ASIN affiliate is allowed meanwhile; sponsorships wait on C5/C6."
        )
    elif kind == "income_path":
        opt_a = {
            "label": "A — Verify one live official program (no outreach yet)",
            "speed": "est. 2",
            "growth": "est. 4",
            "low_cost": "est. 5",
            "upgrades": "est. 1",
            "fit": "est. 4",
            "notes": "Official pages only. Label estimates. Stop for approval before apply/pitch.",
        }
        opt_b = {
            "label": "B — Owned-ASIN affiliate reviews on this week's lane",
            "speed": "est. 4",
            "growth": "est. 3",
            "low_cost": "est. 5",
            "upgrades": "est. 2",
            "fit": "est. 5",
            "notes": f"Unposted: {unposted_names}. Tag billycarter-20 when the ASIN is real.",
        }
        opt_c = {
            "label": "C — Pause income scouting; stay on this week's proof",
            "speed": "est. 3",
            "growth": "est. 3",
            "low_cost": "est. 5",
            "upgrades": "est. 1",
            "fit": "est. 5",
            "notes": f"This week is `{topic or 'unset'}`. Proof beats a cold pitch.",
        }
        primary = opt_a["label"]
        fallback = opt_b["label"]
        offer = f"A verified, current path toward `{goal}` — not a guessed application."
        execute_1 = (
            "Browser · official program page only · done = eligibility + URL logged in section 12, "
            "or the path is marked unverified and dropped."
        )
        path = "Verify live → draft → approval → then send. Never pay to get approved."
    else:
        if topic:
            opt_a = {
                "label": f"A — This week: {topic} from owned gear",
                "speed": "est. 4",
                "growth": "est. 3",
                "low_cost": "est. 5",
                "upgrades": "est. 2",
                "fit": "est. 5",
                "notes": (
                    f"Unposted in-lane: {unposted_names}. "
                    + (
                        f"Already shipped (do not reassign as new work): {posted_names}."
                        if posted_names
                        else "No posted in-lane items."
                    )
                ),
            }
        else:
            opt_a = {
                "label": "A — One owned-catalog honest review (affiliate tag billycarter-20)",
                "speed": "est. 4",
                "growth": "est. 3",
                "low_cost": "est. 5",
                "upgrades": "est. 2",
                "fit": "est. 4",
                "notes": (
                    f"Start from owned inventory ({_names(items) or 'catalog empty'}). "
                    "Do not shop for a new hero product."
                ),
            }
        opt_b = {
            "label": "B — Direction research on C5-kept examples (study, do not copy)",
            "speed": "est. 2",
            "growth": "est. 5",
            "low_cost": "est. 5",
            "upgrades": "est. 1",
            "fit": "est. 5",
            "notes": f"Kept: {kept_names}. Year-end job is a roadmap + proof, not a posting streak.",
        }
        opt_c = {
            "label": "C — Sponsor / freelance / digital-product path (only if it passes C5/C6)",
            "speed": "est. 1",
            "growth": "est. 4",
            "low_cost": "est. 4",
            "upgrades": "est. 3",
            "fit": "est. 3",
            "notes": "Do not invent rates, approvals, or open programs. Verify live before outreach.",
        }
        primary = opt_a["label"] + (" — already on the week card" if topic else "")
        fallback = opt_b["label"]
        offer = (
            f"Honest {topic or 'owned-product'} take using gear already on the shelf; "
            "Amazon tag billycarter-20 when a real ASIN exists."
        )
        if unposted:
            first_item = unposted[0].get("name") or "the unposted in-lane item"
            execute_1 = (
                f"Catalog · pick `{first_item}` · done = one honest-take note in the catalog, "
                "not a new purchase."
            )
        elif topic:
            execute_1 = (
                f"Week card · stay on `{topic}` · done = one next action from "
                "`bolt manage next`, not a new career plan."
            )
        else:
            execute_1 = (
                "Terminal · `bolt week set` to one of the four lanes · done = this_week.topic is set."
            )
        path = (
            "Affiliate on owned ASINs now. Sponsorships only after a C5-kept example "
            "shows the path and William says the deal is something he would stand behind."
        )

    audience = "People who want an honest first-use, not a hype recap."
    platforms = "William's existing socials + Amazon written review when he actually bought it."
    positioning = (
        (career.split(".")[0] + ".")
        if career
        else "Honest-take voice; never sell the next gimmick."
    )

    steps = [
        f"Terminal · confirm check-in still true (hours {hours}, budget {budget}, assets {assets}) · done = limits match reality.",
        "Terminal · `bolt week` · done = this week is the floor; do not restart the career.",
        execute_1,
        (
            f"Terminal · `bolt research pending` · done = {pending} C5 call(s) cleared "
            "or confirmed none waiting."
            if pending and kind == "direction"
            else "Keep C5 calls on the setup list; they do not replace this mission's first action."
        ),
        "Terminal · `bolt week done \"what shipped\"` · done = the week card records the proof.",
    ]
    if done:
        steps.insert(
            2,
            "Week card · treat already-done items as shipped · done = do not tell William to re-film them.",
        )

    checklist_setup = [
        "Confirm check-in answers still true",
        "Read `bolt week` — stay on this week; do not invent a fifth topic",
    ]
    if pending:
        checklist_setup.append(
            "Clear blocking C5 reviews (`bolt research pending`) — William's call, not Bolt's"
        )
    if bans:
        checklist_setup.append("Honor do-not-suggest: " + "; ".join(bans[:3]))

    checklist_execute = [
        execute_1,
        "Use owned gear / listed assets before any purchase",
        "Drafts only — no post, email, apply, or buy without approval",
    ]
    checklist_review = [
        'Log what shipped (`bolt week done "…"` / `bolt log_perf` when relevant)',
        "If a checkpoint fails, pivot to the fallback option",
    ]

    metrics = [
        {
            "metric": "Week card proof (something actually shipped or learned)",
            "baseline": "; ".join(done) if done else "none logged this week",
            "target": "One dated proof line on the week card",
            "review": "end of this week",
        },
        {
            "metric": "Direction (year-end horizon)",
            "baseline": "roadmap incomplete on purpose",
            "target": "Know what success looks like, or a written path with proof",
            "review": str((evidence.get("horizon") or {}).get("target_date") or "2026-12-31"),
        },
    ]

    sources: List[Dict[str, str]] = [
        {
            "name": "Creator Command Center playbook",
            "url": "Core/skills/creator-command-center/SKILL.md",
        },
        {"name": "User profile (C1–C7 + horizon)", "url": "Data/memory/user_profile.json"},
        {"name": "Week card", "url": "Data/memory/week_card.json"},
    ]
    for item in lane_items[:6]:
        asin = (item.get("asin") or "").strip()
        if asin:
            sources.append(
                {
                    "name": f"{item.get('name')} (owned ASIN)",
                    "url": f"https://www.amazon.com/dp/{asin}?tag=billycarter-20",
                }
            )

    pitch_bits = [
        f"Goal: {goal}.",
        "This is a plan from what is already true — week card, owned catalog, C5-kept examples — not a shopping list.",
    ]
    if topic:
        pitch_bits.append(f"This week is already `{topic}`. Do not replace it with a new career.")
    if week.get("last_week_note"):
        pitch_bits.append("Last week's note still stands as history; do not reopen closed paths unless William sets them.")
    if kind == "upgrade":
        pitch_bits.append(
            "New gear is an optional, justified upgrade — only if current assets actually block this week's work."
        )
    if pending and kind == "direction":
        pitch_bits.append(f"{pending} C5 decision(s) are blocking — those are William's, not Bolt's.")
    elif pending:
        pitch_bits.append(
            f"{pending} C5 decision(s) are waiting on the setup list; they are not this mission's first step."
        )
    pitch_bits.append(
        "Scores below are estimates from owned-gear and research state, not predicted earnings. "
        "No sends, posts, or purchases without approval."
    )

    return {
        "pitch": " ".join(pitch_bits),
        "options": [opt_a, opt_b, opt_c],
        "primary": primary,
        "fallback": fallback,
        "offer": offer,
        "audience": audience,
        "platforms": platforms,
        "positioning": positioning,
        "path_to_income": path,
        "low_cost_essentials": "None required if owned gear covers the week. Confirm before buying.",
        "optional_upgrades": "Only if it unblocks the week and fits the stated budget — never a prerequisite.",
        "steps": steps,
        "checklist_setup": checklist_setup,
        "checklist_execute": checklist_execute,
        "checklist_review": checklist_review,
        "timeline_start": "This wake-period (see C4): harder task first, finish it.",
        "timeline_mid": "If blocked or the week card already lists it as done → pivot to option B.",
        "timeline_ship": "Before the week rotates — one proof line, not a finished career.",
        "metrics": metrics,
        "backup": "Stop execution. Run `bolt week` and `bolt research pending`. Do not invent a new lane.",
        "next_command": _default_next_command(goal, checkin, evidence),
        "sources": sources,
        "_provider": "local-evidence",
    }


def _strategy_prompt(
    goal: str,
    evidence: Dict[str, Any],
    checkin: Dict[str, str],
    local: Dict[str, Any],
) -> str:
    slim = {
        "goal": goal,
        "checkin": checkin,
        "career_goal": evidence.get("career_goal"),
        "horizon": evidence.get("horizon"),
        "week": evidence.get("week"),
        "research_counts": {
            k: (evidence.get("research") or {}).get(k)
            for k in (
                "research_log_total",
                "candidates_pending_c5",
                "candidates_kept",
                "next_action",
            )
        },
        "kept_candidates": evidence.get("kept"),
        "catalog": evidence.get("catalog_items"),
        "constraints": [
            c.get("id", "?") + ": " + c.get("text", "")
            if isinstance(c, dict)
            else str(c)
            for c in (evidence.get("constraints") or [])[:7]
        ],
        "local_draft": {
            "options": local.get("options"),
            "primary": local.get("primary"),
            "next_command": local.get("next_command"),
        },
    }
    return (
        "Fill a Creator Command Center mission as compact JSON only (no markdown). "
        "Honor C1–C7. Stay on the week card. Do not restart the career. "
        "Do not invent earnings, approval odds, contacts, or program availability. "
        "Do not invent URLs — omit a source rather than guess. "
        "Owned catalog first; upgrades optional. Planning only — no send/post/purchase. "
        "Scores are 1–5 estimates; say est. and keep notes honest.\n\n"
        "JSON keys: pitch, options (list of {label,speed,growth,low_cost,upgrades,fit,notes}), "
        "primary, fallback, offer, audience, platforms, positioning, path_to_income, "
        "low_cost_essentials, optional_upgrades, steps (list of 5 strings: Where · what · done), "
        "checklist_setup, checklist_execute, checklist_review, timeline_start, timeline_mid, "
        "timeline_ship, metrics (list of {metric,baseline,target,review}), backup, "
        "next_command (one first action; bash fence ok), sources (list of {name,url}).\n\n"
        f"Evidence:\n{json.dumps(slim, ensure_ascii=False, indent=2)[:8000]}"
    )


def _sanitize_sources(
    sources: Any, evidence: Dict[str, Any]
) -> List[Dict[str, str]]:
    asins = {
        str(i.get("asin") or "").strip()
        for i in (evidence.get("catalog_items") or [])
        if i.get("asin")
    }
    allowed_local = (
        "Core/skills/creator-command-center/SKILL.md",
        "Data/memory/user_profile.json",
        "Data/memory/week_card.json",
        "Data/memory/research_log.jsonl",
        "Data/content/catalog.json",
    )
    out: List[Dict[str, str]] = []
    for s in sources or []:
        if not isinstance(s, dict):
            continue
        name = str(s.get("name") or "").strip()
        url = str(s.get("url") or "").strip()
        if not name and not url:
            continue
        if not url:
            out.append({"name": name, "url": ""})
            continue
        if url in allowed_local:
            out.append({"name": name, "url": url})
            continue
        if url.startswith("https://www.amazon.com/dp/") and any(
            a and a in url for a in asins
        ):
            out.append({"name": name, "url": url})
            continue
        if url.startswith("http://") or url.startswith("https://"):
            # Live URL not in evidence — keep the name, drop the unverified link.
            out.append({"name": f"{name} (URL omitted — not in evidence)", "url": ""})
            continue
        if url.startswith("Data/") or url.startswith("Core/"):
            out.append({"name": name, "url": url})
            continue
        out.append({"name": name, "url": ""})
    return out[:12]


def _nexus_strategy(
    goal: str,
    evidence: Dict[str, Any],
    checkin: Dict[str, str],
) -> Dict[str, Any]:
    local = _local_strategy(goal, evidence, checkin)
    try:
        from modules.Nexus_Creator import NexusCreator

        nexus = NexusCreator()
        result = nexus.consult(
            f"Mission planning JSON for creator goal: {goal}",
            context=_strategy_prompt(goal, evidence, checkin, local),
            task_type="strategy",
            complexity="high",
        )
        advice = (result or {}).get("advice") or ""
        provider = (result or {}).get("provider") or "unknown"
        parsed = _extract_json(advice)
        if parsed:
            merged = dict(local)
            for key, val in parsed.items():
                if key.startswith("_"):
                    continue
                if val in (None, "", [], {}):
                    continue
                merged[key] = val
            merged["sources"] = _sanitize_sources(
                merged.get("sources") or local.get("sources"), evidence
            )
            merged["_provider"] = provider
            pitch = str(merged.get("pitch") or "").strip()
            if pitch and "_Provider:" not in pitch:
                merged["pitch"] = f"{pitch}\n\n_Provider: {provider}_"
            return merged
        if advice.strip():
            local["pitch"] = f"{advice.strip()}\n\n_Provider: {provider}_"
            local["_provider"] = provider
    except Exception:
        pass
    return local


def _as_str_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _render_options(options: Any) -> str:
    rows = options if isinstance(options, list) else []
    if len(rows) < 3:
        rows = list(rows) + [
            {"label": "A — _(primary)_"},
            {"label": "B — _(fallback)_"},
            {"label": "C — _(optional)_"},
        ]
        rows = rows[:3]
    lines = [
        "| Option | Speed to income | Long-term growth | Low cost | Useful upgrades | Fit with Billy | Notes |",
        "|--------|-----------------|------------------|----------|-----------------|----------------|-------|",
    ]
    for opt in rows[:5]:
        if not isinstance(opt, dict):
            continue
        lines.append(
            "| {label} | {speed} | {growth} | {low_cost} | {upgrades} | {fit} | {notes} |".format(
                label=str(opt.get("label") or "").replace("|", "/"),
                speed=str(opt.get("speed") or ""),
                growth=str(opt.get("growth") or ""),
                low_cost=str(opt.get("low_cost") or ""),
                upgrades=str(opt.get("upgrades") or ""),
                fit=str(opt.get("fit") or ""),
                notes=str(opt.get("notes") or "").replace("|", "/"),
            )
        )
    return "\n".join(lines)


def _render_steps(steps: Any) -> str:
    items = _as_str_list(steps)
    if not items:
        items = ["_(Where · what to enter/create · what “done” looks like)_"]
    lines = []
    for i, step in enumerate(items, 1):
        lines.append(f"{i}. {step}")
    return "\n".join(lines)


def _render_checklist(items: Any) -> str:
    lines = []
    for item in _as_str_list(items) or ["_"]:
        box = item if item.startswith("- [ ]") else f"- [ ] {item}"
        lines.append(box)
    return "\n".join(lines)


def _render_metrics(metrics: Any) -> str:
    lines = [
        "| Metric | Baseline | Target | Review date |",
        "|--------|----------|--------|-------------|",
    ]
    rows = metrics if isinstance(metrics, list) else []
    if not rows:
        rows = [{"metric": "", "baseline": "", "target": "", "review": ""}]
    for m in rows[:6]:
        if not isinstance(m, dict):
            continue
        lines.append(
            "| {metric} | {baseline} | {target} | {review} |".format(
                metric=str(m.get("metric") or "").replace("|", "/"),
                baseline=str(m.get("baseline") or "").replace("|", "/"),
                target=str(m.get("target") or "").replace("|", "/"),
                review=str(m.get("review") or "").replace("|", "/"),
            )
        )
    return "\n".join(lines)


def _render_sources(sources: Any, date_label: str) -> str:
    lines = [
        "| Source | URL | Date checked |",
        "|--------|-----|--------------|",
    ]
    rows = sources if isinstance(sources, list) else []
    if not rows:
        rows = [{"name": "", "url": ""}]
    for s in rows[:12]:
        if not isinstance(s, dict):
            continue
        lines.append(
            f"| {str(s.get('name') or '').replace('|', '/')} | "
            f"{str(s.get('url') or '').replace('|', '/')} | {date_label} |"
        )
    return "\n".join(lines)


def _parse_labeled(text: str, label: str) -> str:
    m = re.search(rf"\*\*{re.escape(label)}:\*\*\s*(.+)", text)
    if not m:
        return ""
    val = m.group(1).strip()
    if _blank_answer(val):
        return ""
    return val


def parse_mission_fields(text: str) -> Dict[str, str]:
    """Pull goal + check-in answers back out of a mission markdown file."""
    fields = {
        "goal": _parse_labeled(text, "Goal"),
        "deadline": _parse_labeled(text, "Target date"),
        "hours": "",
        "budget": "",
        "assets": "",
        "borrow_free": "",
        "restrictions": "",
    }
    mapping = {
        "Time available": "hours",
        "Max budget": "budget",
        "Already owned / usable": "assets",
        "Borrow / free / cheap": "borrow_free",
        "Restrictions": "restrictions",
    }
    for label, key in mapping.items():
        m = re.search(rf"\| {re.escape(label)} \| ([^|\n]+)\|", text)
        if not m:
            continue
        val = m.group(1).strip()
        if not _blank_answer(val):
            fields[key] = val
    deadline = fields.get("deadline") or ""
    if "research horizon" in deadline or deadline.startswith("_("):
        fields["deadline"] = ""
    return fields


def _replace_table_cell(text: str, label: str, value: str) -> str:
    return re.sub(
        rf"\| {re.escape(label)} \| [^|\n]+\|",
        f"| {label} | {value} |",
        text,
        count=1,
    )


def update_mission_checkin(
    path: Path,
    *,
    hours: str = "",
    budget: str = "",
    assets: str = "",
    borrow_free: str = "",
    restrictions: str = "",
    deadline: str = "",
) -> Path:
    """Patch check-in cells in an existing mission. Does not regenerate strategy."""
    text = path.read_text(encoding="utf-8")
    if hours:
        text = _replace_table_cell(text, "Time available", hours)
    if budget:
        text = _replace_table_cell(text, "Max budget", budget)
        text = re.sub(
            r"(\*\*Total\*\* \|  \| )\*\*≤ [^|*]+\*\*",
            r"\1**≤ " + budget + "**",
            text,
            count=1,
        )
    if assets:
        text = _replace_table_cell(text, "Already owned / usable", assets)
        text = re.sub(
            r"\| Already owned \| [^|\n]+\| [^|\n]+\|",
            f"| Already owned | {assets} | $0 |",
            text,
            count=1,
        )
    if borrow_free:
        text = _replace_table_cell(text, "Borrow / free / cheap", borrow_free)
        text = re.sub(
            r"\| Free / borrowed \| [^|\n]+\| [^|\n]+\|",
            f"| Free / borrowed | {borrow_free} | $0–low |",
            text,
            count=1,
        )
    if restrictions:
        text = _replace_table_cell(text, "Restrictions", restrictions)
    if deadline:
        text = re.sub(
            r"(\*\*Target date:\*\*\s*).+",
            r"\1" + deadline,
            text,
            count=1,
        )
    path.write_text(text, encoding="utf-8")
    notify(
        f"Check-in updated: {path}",
        level="success",
        reason="Planning only — strategy sections were not regenerated. Run fill to rebuild them.",
    )
    return path


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
    created: str = "",
) -> str:
    """Build a filled 13-section mission briefing from current evidence."""
    evidence = _evidence_pack()
    profile = evidence.get("profile") or {}
    vision = profile.get("vision") or {}
    constraints = evidence.get("constraints") or []
    research = evidence.get("research") or {}
    catalog_items = evidence.get("catalog_items") or []
    week = evidence.get("week") or {}
    created = created or _now_iso()
    date_label = created[:10] if len(created) >= 10 else datetime.now().strftime("%Y-%m-%d")

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
        for i in catalog_items
    ] or ["- (catalog empty — add real products with `bolt manage add`)"]

    research_line = (
        f"Research log: {research.get('research_log_total', 0)} findings · "
        f"{research.get('candidates_pending_c5', 0)} pending C5 · "
        f"{research.get('candidates_kept', 0)} kept"
    )
    kept = evidence.get("kept") or []
    kept_lines = [
        f"- {k.get('name')} ({k.get('platform') or 'unknown'}) — {k.get('why')}"
        for k in kept
        if k.get("name")
    ] or ["- (no C5-kept examples yet)"]

    career = (vision.get("career_goal") or research.get("user_career_goal") or "").strip()
    checkin = {
        "hours": hours,
        "budget": budget,
        "assets": assets,
        "borrow_free": borrow_free,
        "restrictions": restrictions,
        "deadline": deadline,
    }
    strategy = (
        _nexus_strategy(goal, evidence, checkin)
        if use_nexus
        else _local_strategy(goal, evidence, checkin)
    )

    hours_s = hours or "_(not set — run check-in)_"
    budget_s = budget or "_(not set — run check-in)_"
    assets_s = assets or "_(not set — run check-in)_"
    borrow_s = borrow_free or "_(not set)_"
    restrict_s = restrictions or "_(none listed — still honor C1–C7)_"
    horizon = evidence.get("horizon") or {}
    deadline_s = (
        deadline
        or horizon.get("target_date")
        or "_(research horizon — not a ship date)_"
    )
    measurable_s = horizon.get("success_is") or (
        "Unknown on purpose until research answers it. "
        "Do not invent a career outcome to fill this line."
    )

    week_lines = [
        f"- **This week:** {week.get('this_week') or '(not set — `bolt week set`)'}",
    ]
    if week.get("this_week_note"):
        week_lines.append(f"- Note: {week.get('this_week_note')}")
    if week.get("this_week_done"):
        week_lines.append("- Already done: " + "; ".join(week["this_week_done"]))
    if week.get("last_week"):
        week_lines.append(f"- Last week: {week.get('last_week')}")
    if week.get("last_week_note"):
        week_lines.append(f"- Last week note: {week.get('last_week_note')}")
    if week.get("bans"):
        week_lines.append("- Do not suggest: " + "; ".join(week["bans"]))

    pitch = str(strategy.get("pitch") or "").strip() or "_(fill after live research)_"
    provider = strategy.get("_provider") or "local-evidence"

    options_table = _render_options(strategy.get("options"))
    steps_block = _render_steps(strategy.get("steps"))
    metrics_table = _render_metrics(strategy.get("metrics"))
    sources_table = _render_sources(strategy.get("sources"), date_label)
    next_block = str(strategy.get("next_command") or _default_next_command(goal, checkin, evidence)).strip()

    body = f"""# Mission Briefing — Creator Command Center

**Created:** {created}  
**Date:** {date_label}  
**Status:** draft (planning only — no external sends without Billy's approval)  
**Fill:** {provider}

---

## 1. Mission title and objective

**Goal:** {goal}

**Measurable result:** {measurable_s}  
**Target date:** {deadline_s}

---

## 2. Commander's pitch

{pitch}

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

### This week / last week

{chr(10).join(week_lines)}

### Catalog / storefront

{chr(10).join(catalog_lines)}

### Research pulse

- {research_line}
- Next research action: {research.get("next_action") or "bolt research pending"}
- Commands: `bolt research pending` · `bolt research c5 keep|drop "Name"`

### C5-kept examples (study, do not copy)

{chr(10).join(kept_lines)}

---

## 4. Options comparison

Score each shortlisted option 1–5 (higher is better). Labels marked **est.** are reasoned guesses from current evidence, not predicted income.

{options_table}

**Primary pick:** {strategy.get("primary") or "_(A/B/C + one sentence why)_"}  
**Fallback:** {strategy.get("fallback") or "_(if primary fails checkpoint)_"}

Income paths in play: Amazon affiliate reviews · sponsorships · freelance creator services · digital products · legitimate product testing / gigs.  
Exclude: gimmick content, undisclosed ads, fake engagement, pay-to-play “jobs”.

---

## 5. Mission strategy

- **Offer:** {strategy.get("offer") or ""}
- **Audience / customer:** {strategy.get("audience") or ""}
- **Platform(s):** {strategy.get("platforms") or ""}
- **Positioning (honest-take voice):** {strategy.get("positioning") or ""}
- **Path to income:** {strategy.get("path_to_income") or ""}

---

## 6. Resources and cost

| Bucket | Items | Est. cost |
|--------|-------|-----------|
| Already owned | {assets_s} | $0 |
| Free / borrowed | {borrow_s} | $0–low |
| Low-cost essentials | {strategy.get("low_cost_essentials") or ""} |  |
| Optional upgrades | {strategy.get("optional_upgrades") or ""} |  |
| **Total** |  | **≤ {budget_s}** |

---

## 7. Step-by-step operation

{steps_block}

Copy-ready drafts / scripts / shot lists go here when they remove guesswork.

---

## 8. Printable checklist

### Phase 1 — Setup
{_render_checklist(strategy.get("checklist_setup"))}

### Phase 2 — Execute
{_render_checklist(strategy.get("checklist_execute"))}

### Phase 3 — Ship / review
{_render_checklist(strategy.get("checklist_review"))}

---

## 9. Timeline and checkpoints

| Block | When | Go / no-go |
|-------|------|------------|
| Start | {strategy.get("timeline_start") or ""} | Limits still true |
| Mid checkpoint | {strategy.get("timeline_mid") or ""} | If blocked → pivot to fallback option |
| Ship | {strategy.get("timeline_ship") or deadline_s} | One proof line on the week card |

---

## 10. Success dashboard

{metrics_table}

---

## 11. Risks and safeguards

- **Scams / fees:** never pay to “get approved”; verify official pages
- **Disclosure:** affiliate / gifted products always disclosed
- **C6 authenticity:** reject deals you would not stand behind
- **C7:** no Trump/MAGA/insulting associations
- **Approval gate:** drafts OK; Billy approves before send/post/purchase
- **Backup plan:** {strategy.get("backup") or ""}

---

## 12. Sources checked

{sources_table}

Live program pages, rates, and deadlines were **not** fetched automatically (C5: Bolt does not pick). Run `bolt research find` before treating any outside offer as current.

---

## 13. Next command

**Do this first:**

{next_block}

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


def fill_mission(path: Path, *, use_nexus: bool = True) -> Path:
    """Rebuild strategy sections from current evidence, keeping goal + check-in."""
    text = path.read_text(encoding="utf-8")
    fields = parse_mission_fields(text)
    goal = fields.get("goal") or path.stem
    created_m = re.search(r"\*\*Created:\*\*\s*(.+)", text)
    created = created_m.group(1).strip() if created_m else _now_iso()
    md = build_mission_markdown(
        goal,
        hours=fields.get("hours") or "",
        budget=fields.get("budget") or "",
        assets=fields.get("assets") or "",
        borrow_free=fields.get("borrow_free") or "",
        restrictions=fields.get("restrictions") or "",
        deadline=fields.get("deadline") or "",
        use_nexus=use_nexus,
        created=created,
    )
    path.write_text(md, encoding="utf-8")
    notify(
        f"Mission filled: {path}",
        level="success",
        reason="Rebuilt from current week card / research / catalog. Planning only.",
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


def mission_status() -> str:
    """Spoken-friendly snapshot for voice / conversation (Intent_Router)."""
    s = status()
    latest = latest_mission()
    if not latest:
        return (
            "No missions on file yet. Start one with bolt mission start "
            "and pass hours, budget, and assets so the plan is real. "
            "Planning only — nothing gets posted."
        )
    try:
        text = latest.read_text(encoding="utf-8")
    except OSError:
        return f"Latest mission file {latest.name} could not be read."
    goal = parse_mission_fields(text).get("goal") or latest.stem
    nxt = extract_next_command(text)
    nxt = re.sub(r"```(?:bash)?", "", nxt)
    nxt = " ".join(nxt.split())[:280]
    pending = s.get("research_pending_c5") or 0
    extra = (
        f" {pending} research candidates still need your C5 call."
        if pending
        else ""
    )
    return (
        f"Latest mission: {goal}. File {latest.name}. "
        f"Next command: {nxt}.{extra} Planning only."
    )


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
        "  bolt mission fill latest\n"
        "  bolt mission update latest --hours 8 --budget 40\n"
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


def _start_parser() -> "argparse.ArgumentParser":
    import argparse

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
        help="Skip Nexus strategy overlay (local evidence only)",
    )
    return start_parser


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
            "  bolt mission fill latest\n"
            '  bolt mission update latest --hours 6 --budget 50 --assets "OBS, mic"\n'
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
        help="status|checkin|playbook|list|show|start|fill|update|next|help",
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
        start_parser = _start_parser()
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
            print("  bolt mission update latest --hours … --budget … --assets …")
        print("\nNext command:")
        print(extract_next_command(path.read_text(encoding="utf-8")))
        return 0

    if cmd == "fill":
        fill_parser = argparse.ArgumentParser(prog="bolt mission fill")
        fill_parser.add_argument(
            "ref",
            nargs="?",
            default="latest",
            help="Mission file, name, or 'latest'",
        )
        fill_parser.add_argument(
            "--no-nexus",
            action="store_true",
            help="Rebuild from local evidence only",
        )
        try:
            fill_args = fill_parser.parse_args(rest)
        except SystemExit:
            return 2
        path = resolve_mission(fill_args.ref)
        if not path:
            print(f"error: no mission matching '{fill_args.ref}'", flush=True)
            return 1
        path = fill_mission(path, use_nexus=not fill_args.no_nexus)
        print(f"\n✓ Mission filled: {path}")
        print("\nNext command:")
        print(extract_next_command(path.read_text(encoding="utf-8")))
        return 0

    if cmd == "update":
        upd_parser = argparse.ArgumentParser(prog="bolt mission update")
        upd_parser.add_argument(
            "ref",
            nargs="?",
            default="latest",
            help="Mission file, name, or 'latest'",
        )
        upd_parser.add_argument("--hours", default="", help="Time available")
        upd_parser.add_argument("--budget", default="", help="Max budget")
        upd_parser.add_argument("--assets", default="", help="What you already have")
        upd_parser.add_argument(
            "--borrow",
            default="",
            dest="borrow_free",
            help="Borrow / free / cheap options",
        )
        upd_parser.add_argument(
            "--restrictions",
            default="",
            help="Deal-breakers / comfort limits",
        )
        upd_parser.add_argument("--deadline", default="", help="Target date")
        try:
            upd_args = upd_parser.parse_args(rest)
        except SystemExit:
            return 2
        path = resolve_mission(upd_args.ref)
        if not path:
            print(f"error: no mission matching '{upd_args.ref}'", flush=True)
            return 1
        if not any(
            [
                upd_args.hours,
                upd_args.budget,
                upd_args.assets,
                upd_args.borrow_free,
                upd_args.restrictions,
                upd_args.deadline,
            ]
        ):
            print("error: pass at least one of --hours --budget --assets --borrow --restrictions --deadline")
            return 2
        path = update_mission_checkin(
            path,
            hours=upd_args.hours,
            budget=upd_args.budget,
            assets=upd_args.assets,
            borrow_free=upd_args.borrow_free,
            restrictions=upd_args.restrictions,
            deadline=upd_args.deadline,
        )
        print(f"\n✓ Check-in updated: {path}")
        print("  Rebuild the plan from these limits: bolt mission fill latest --no-nexus")
        return 0

    print(f"bolt mission: unknown command '{cmd}'", flush=True)
    print("  Try: status | checkin | playbook | list | show | start | fill | update | next | help")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
