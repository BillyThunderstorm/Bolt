#!/usr/bin/env python3
"""
modules/Bolt_Memory.py — Bolt's long-term memory system (Phase 4)
=================================================================
Gives Bolt the ability to remember things across sessions and recall
them when needed. No LangChain, no vector database, no OpenAI key.
Just OpenAI + the Data/ memory tree you already have.

How it works:
  - Data/MEMORY.md     → hot cache (most important stuff, always loaded)
  - Data/people/       → notes on people Billy works with or talks about
  - Data/projects/     → project-specific notes (Bolt, ClipBot, etc.)
  - Data/context/      → creator setup, stream notes, brand context
  - Data/glossary.md   → decoder ring for Billy's shorthand
  - Data/memory/       → user_profile, research_log, phase checklists

The `recall()` function loads all of this and asks OpenAI a question
using the memory as context. This is Phase 4's "self-awareness" — Bolt
can now answer things like "what game am I playing this week?" or
"what did I decide about ElevenLabs?" correctly.

The `remember()` function saves new facts to MEMORY.md so they persist
across sessions. This is how Bolt "learns" over time.

Usage anywhere in Bolt:
    from modules.Bolt_Memory import recall, remember, load_all_memory

    # Ask Bolt something based on its memory
    answer = recall("What platforms is Billy focusing on right now?")

    # Save a new fact
    remember("Billy switched from Marvel Rivals to Fortnite on 2026-04-27")

    # Just load the full memory context (for injecting into other prompts)
    context = load_all_memory()

CLI (PARTIAL soft-fail via ``bolt memory``):
  status [--json] [--probe]
  list   [--json]
  remember "fact" [--section "Recent Notes"]
  recall "question"
  load   [--json]

Soft-fail prefix: ``Bolt memory unavailable:``. Stay PARTIAL — LLM-gated
recall; Phase 4 incomplete. Distinct from READY briefing retrieve and
PARTIAL ``bolt refresh-memory`` (index rebuild).
"""

import os
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

try:
    from modules.notifier import notify
except ImportError:

    def notify(msg, level="info", reason=None):
        print(f"  [{level.upper()}] {msg}")


# ── Paths ──────────────────────────────────────────────────────────────────────
# Core/modules/Bolt_Memory.py → parents[2] is the repo root (Bolt/).
# After the Jul 2026 reorg, creator memory lives under Data/, not Core/memory/.

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MEMORY_ROOT = PROJECT_ROOT / "Data"
MEMORY_FILE = MEMORY_ROOT / "MEMORY.md"
GLOSSARY = MEMORY_ROOT / "glossary.md"
PEOPLE_DIR = MEMORY_ROOT / "people"
PROJECTS_DIR = MEMORY_ROOT / "projects"
CONTEXT_DIR = MEMORY_ROOT / "context"
CONTENT_DIR = MEMORY_ROOT / "content"
MEMORY_DIR = MEMORY_ROOT / "memory"

try:
    from modules.Memory_Index import (
        format_retrieved_context,
        refresh_memory_index,
        retrieve_memory,
    )
except ImportError:
    refresh_memory_index = None
    retrieve_memory = None
    format_retrieved_context = None


# ── Load memory ────────────────────────────────────────────────────────────────


def _read_file(path: Path) -> str:
    """Safely read a file, return empty string if missing."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _read_folder(folder: Path) -> str:
    """
    Read all .md files in a folder and combine them.
    Each file gets a header so memory is organized.
    """
    if not folder.exists():
        return ""
    chunks = []
    for md_file in sorted(folder.glob("*.md")):
        content = _read_file(md_file)
        if content:
            chunks.append(f"### {md_file.stem}\n{content}")
    return "\n\n".join(chunks)


def load_all_memory() -> str:
    """
    Load the full memory context into a single string.

    This is what gets injected into OpenAI's context so it knows
    who Billy is, what he's working on, and what's been decided.

    Why one big string?
    The memory/ folder is small enough (a few KB) that loading all of it
    is faster and simpler than building a vector search index. For a solo
    creator's personal assistant, this approach works perfectly.
    """
    sections = []

    # Hot cache first — highest priority facts
    hot = _read_file(MEMORY_FILE)
    if hot:
        sections.append(f"## Core Memory (MEMORY.md)\n{hot}")

    # Glossary — decoder ring for Billy's shorthand
    glossary = _read_file(GLOSSARY)
    if glossary:
        sections.append(f"## Glossary\n{glossary}")

    # People notes
    people = _read_folder(PEOPLE_DIR)
    if people:
        sections.append(f"## People\n{people}")

    # Project notes
    projects = _read_folder(PROJECTS_DIR)
    if projects:
        sections.append(f"## Projects\n{projects}")

    # Creator context
    context = _read_folder(CONTEXT_DIR)
    if context:
        sections.append(f"## Context\n{context}")

    # Content creation memory — reviews, ideas, scripts, posting lessons
    content = _read_folder(CONTENT_DIR)
    if content:
        sections.append(f"## Content Memory\n{content}")

    if not sections:
        return "(no memory files found — memory/ folder may be empty)"

    return "\n\n---\n\n".join(sections)


# ── Recall — ask OpenAI something using memory as context ─────────────────────


def retrieve_context(question: str, limit: int = 5) -> str:
    """
    Retrieve the most relevant local memory snippets for a question.

    This uses data/memory_index.json when it exists, and creates it on demand
    when possible. It is deliberately local-only so Bolt can remember past
    clips and decisions without needing a cloud vector database first.
    """
    if retrieve_memory is None or format_retrieved_context is None:
        return "(memory retrieval index is not available)"
    hits = retrieve_memory(question, limit=limit)
    return format_retrieved_context(hits)


def recall(question: str, quiet: bool = False, use_retrieval: bool = True) -> str:
    """
    Ask Bolt a question. It will answer using everything in memory/.

    This is what makes Phase 4 work — Bolt can now remember decisions,
    preferences, and context across sessions without you repeating yourself.

    Examples:
        recall("What game is Billy streaming right now?")
        recall("What was decided about ElevenLabs?")
        recall("Who is ChaoticallyRobotical?")

    Returns the answer as a string.
    """
    try:
        from openai import OpenAI
    except ImportError:
        return "openai package not installed — run: pip3 install openai --break-system-packages"

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return "OPENAI_API_KEY not set in .env"

    memory_context = load_all_memory()
    retrieved_context = (
        retrieve_context(question) if use_retrieval else "(retrieval disabled)"
    )

    client = OpenAI(api_key=api_key)

    system_prompt = f"""You are Bolt, Billy Carter's personal AI producer.
You have access to Billy's memory files below — this is everything you know about him,
his projects, his preferences, and his decisions.

Answer the question concisely and accurately based on what's in memory.
If you don't know something, say so — don't make things up.

MEMORY:
{memory_context}

RELEVANT RETRIEVED MEMORY:
{retrieved_context}"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # fast + cheap for quick recalls
            max_tokens=512,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
        )
        answer = response.choices[0].message.content.strip()
        if not quiet:
            notify(
                f"Memory recall: {answer[:100]}{'...' if len(answer) > 100 else ''}",
                level="info",
            )
        return answer
    except Exception as e:
        return f"Recall failed: {e}"


# ── Remember — save a new fact to MEMORY.md ───────────────────────────────────


def remember(fact: str, section: str = "Recent Notes") -> bool:
    """
    Save a new fact to MEMORY.md so it persists across sessions.

    This is how Bolt learns over time. Call this when something important
    happens or is decided during a session.

    Examples:
        remember("Switched from Marvel Rivals to Fortnite")
        remember("ChaoticallyRobotical confirmed as Bolt's Twitch bot account")
        remember("Phase 3 complete — Bolt_Chat and Bolt_Voice both working")

    The fact is timestamped and appended under the given section header.
    Returns True if saved successfully.
    """
    MEMORY_ROOT.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d")
    entry = f"\n- [{timestamp}] {fact}"

    try:
        existing = _read_file(MEMORY_FILE)

        # If the section already exists, append to it
        if f"## {section}" in existing:
            updated = existing.replace(
                f"## {section}",
                f"## {section}{entry}",
                1,  # only replace the first occurrence
            )
        else:
            # Add a new section at the end
            updated = existing + f"\n\n## {section}{entry}\n"

        MEMORY_FILE.write_text(updated, encoding="utf-8")
        if refresh_memory_index is not None:
            try:
                refresh_memory_index()
            except Exception:
                pass
        notify(
            f"Memory saved: {fact[:80]}{'...' if len(fact) > 80 else ''}",
            level="success",
            reason="Added to Data/MEMORY.md — next retrieve will see it.",
        )
        return True

    except Exception as e:
        notify(f"Failed to save memory: {e}", level="warning")
        return False


# ── Auto-remember key session events ──────────────────────────────────────────


def remember_session_event(event_type: str, **kwargs):
    """
    Convenience wrapper for common session events worth remembering.

    Usage:
        remember_session_event("phase_complete", phase=3)
        remember_session_event("game_change", game="Fortnite")
        remember_session_event("clips_posted", count=2, titles=["clip1", "clip2"])
    """
    templates = {
        "phase_complete": "Phase {phase} marked complete",
        "game_change": "Game switched to {game}",
        "clips_posted": "{count} clip(s) posted — {titles}",
        "bot_connected": "Twitch bot ({account}) confirmed connected",
        "setting_changed": "{setting} changed to {value} in config.json",
    }
    template = templates.get(event_type, f"{event_type}: {kwargs}")
    try:
        fact = template.format(**kwargs)
    except KeyError:
        fact = f"{event_type}: {kwargs}"
    remember(fact)


# ── Briefing memory retrieval ─────────────────────────────────────────────────
# Tests patch `scripts.<module>._retrieve_briefing_memory` so this function
# needs to be importable from the scripts layer. We define it here in the
# canonical place, then re-export it from the scripts via a thin wrapper.


def _retrieve_briefing_memory(query: str = "", limit: int = 5) -> list:
    """Return ranked memory hits for a briefing query.

    Designed to be called from scripts/daily_briefing.py and
    scripts/weekly_analysis.py. Returns [] if no memory is available — never
    crashes the caller. Hits are ranked by score (highest first), capped at
    `limit` (default 5).

    Hit shape:
        {
            "kind": str,        # "creator_note" | "decision_event" | "performance_outcome" | "constraint" | etc.
            "text": str,        # human-readable summary
            "score": float,     # 0.0-1.0 relevance/confidence
            "source": str,      # where this hit came from
            "timestamp": str,   # ISO timestamp
        }

    Sources, in priority order:
        1. Memory_Index.retrieve_memory (vector-style, against content/* .md)
        2. Data/unified_memory.jsonl (decision events from past sessions)
        3. Data/memory/user_profile.json (hard constraints surfaced as reminders)
    """
    hits: list = []

    # Source 1: Memory_Index vector retrieval (preferred)
    if retrieve_memory is not None:
        try:
            indexed = retrieve_memory(query=query, limit=limit) or []
            for h in indexed:
                hits.append({
                    "kind": h.get("kind", "memory_index"),
                    "text": h.get("text", "") or h.get("title", ""),
                    "score": float(h.get("score", 0.5)),
                    "source": h.get("source", "memory_index"),
                    "timestamp": h.get("updated_at", ""),
                })
        except Exception:
            pass  # fall through to next source

    # Source 2: unified_memory.jsonl recent decision events
    try:
        unified_path = PROJECT_ROOT / "Data" / "unified_memory.jsonl"
        if unified_path.exists():
            recent_events: list = []
            with unified_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        import json as _json
                        evt = _json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(evt, dict):
                        continue
                    action = str(evt.get("action") or "?").strip() or "?"
                    result = str(evt.get("result") or "").strip()
                    feedback = str(evt.get("feedback") or "").strip()
                    reason = str(evt.get("reason") or "").strip()
                    detail = feedback or (
                        reason if result in {"rejected", "failed", "held", "error"} else ""
                    )
                    if detail:
                        detail = " ".join(detail.split())
                        if len(detail) > 120:
                            detail = detail[:117].rstrip() + "…"
                    if result and detail:
                        title = f"{action} · {result} — {detail}"
                    elif result:
                        title = f"{action} · {result}"
                    else:
                        title = f"{action}: {reason}" if reason else action
                    actionable = bool(
                        result in {"rejected", "failed", "held", "error"} or feedback
                    )
                    score = 0.9 if actionable else (
                        0.35 if result in {"started", "completed", "ok", "success"} else 0.7
                    )
                    recent_events.append({
                        "kind": "decision_event",
                        "action": action,
                        "result": result,
                        "feedback": feedback,
                        "text": title,
                        "title": title,
                        "score": score,
                        "source": "unified_memory",
                        "timestamp": evt.get("timestamp", ""),
                        "needs_follow_up": actionable,
                    })
            # Prefer actionable rejections over pipeline audit noise
            actionable_hits = [h for h in recent_events if h.get("needs_follow_up")]
            hits.extend((actionable_hits or recent_events)[-3:])
    except Exception:
        pass

    # Source 3: user_profile.json hard constraints (lowest priority)
    try:
        profile_path = PROJECT_ROOT / "Data" / "memory" / "user_profile.json"
        if profile_path.exists():
            import json as _json
            with profile_path.open("r", encoding="utf-8") as f:
                profile = _json.load(f)
            constraints = profile.get("hard_constraints", []) or []
            for c in constraints[:2]:  # top 2 constraints
                hits.append({
                    "kind": "constraint",
                    "text": f"Reminder: {c.get('text', '')}",
                    "score": 0.5,
                    "source": "user_profile",
                    "timestamp": "",
                })
    except Exception:
        pass

    # Sort by score desc, cap at limit
    hits.sort(key=lambda h: h.get("score", 0), reverse=True)
    return hits[:limit]


# ── Soft-fail CLI (PARTIAL — bolt memory) ─────────────────────────────────────
# Soft-fail prefix for status/list/remember/recall/load. Existing recall /
# remember / load_all_memory APIs above stay unchanged for in-process callers.

_SOFT = "Bolt memory unavailable:"


def _soft(msg: str) -> str:
    if msg.startswith(_SOFT):
        return msg
    return f"{_SOFT} {msg}"


def _iso() -> str:
    from datetime import timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _openai_pkg_present() -> bool:
    try:
        import openai  # noqa: F401

        return True
    except ImportError:
        return False


def _openai_key_meta() -> Dict[str, Any]:
    raw = os.getenv("OPENAI_API_KEY", "") or ""
    present = bool(raw.strip())
    if not present:
        return {"present": False, "redacted": ""}
    # Redact: show first 4 + last 2 if long enough, else ***
    s = raw.strip()
    if len(s) >= 10:
        redacted = f"{s[:4]}…{s[-2:]}"
    else:
        redacted = "***"
    return {"present": True, "redacted": redacted}


def _dir_meta(path: Path) -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "is_dir": path.is_dir() if path.exists() else False,
        "md_count": 0,
        "size_hint": 0,
    }
    if path.is_dir():
        try:
            mds = list(path.glob("*.md"))
            meta["md_count"] = len(mds)
            meta["size_hint"] = sum(f.stat().st_size for f in mds if f.is_file())
        except Exception:
            pass
    elif path.is_file():
        try:
            meta["size_hint"] = int(path.stat().st_size)
        except Exception:
            pass
    return meta


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Never raises. ready=True when hot cache or any memory dir exists."""
    hot = _dir_meta(MEMORY_FILE)
    hot["exists"] = MEMORY_FILE.is_file()
    people = _dir_meta(PEOPLE_DIR)
    projects = _dir_meta(PROJECTS_DIR)
    context = _dir_meta(CONTEXT_DIR)
    glossary = _dir_meta(GLOSSARY)
    glossary["exists"] = GLOSSARY.is_file()
    mem_dir = _dir_meta(MEMORY_DIR)
    content = _dir_meta(CONTENT_DIR)

    any_store = bool(
        hot["exists"]
        or people.get("is_dir")
        or projects.get("is_dir")
        or context.get("is_dir")
        or glossary["exists"]
        or mem_dir.get("is_dir")
        or content.get("is_dir")
    )

    key_meta = _openai_key_meta()
    openai_pkg = _openai_pkg_present()
    mi_ok = retrieve_memory is not None

    info: Dict[str, Any] = {
        "checked_at": _iso(),
        "ready": bool(any_store),
        "partial": True,
        "readiness": "PARTIAL",
        "soft_fail_prefix": _SOFT,
        "cli": "bolt memory",
        "module": str(Path(__file__).resolve()),
        "memory_root": str(MEMORY_ROOT),
        "hot_cache": hot,
        "people": people,
        "projects": projects,
        "context": context,
        "glossary": glossary,
        "memory_dir": mem_dir,
        "content": content,
        "any_store": any_store,
        "openai_pkg": openai_pkg,
        "openai_api_key_present": key_meta["present"],
        "openai_api_key_redacted": key_meta["redacted"],
        "memory_index_import": mi_ok,
        "probe": bool(probe),
        "probe_ok": None,
        "probe_load_chars": None,
        "error": "",
        "hint": (
            "local Data/MEMORY.md + people/projects/context/glossary/memory · "
            "recall is LLM-gated (OPENAI_API_KEY) · distinct from READY "
            "briefing retrieve + PARTIAL bolt refresh-memory · stay PARTIAL"
        ),
        "is_stranger_ready": False,
    }

    if not any_store:
        info["error"] = _soft(
            "no local memory store yet (Data/MEMORY.md or people|projects|"
            "context|glossary|memory|content)"
        )
        info["ready"] = False

    if probe:
        try:
            # Optional import openai (does not require key for import)
            if openai_pkg:
                import openai  # noqa: F401

            blob = load_all_memory()
            info["probe_load_chars"] = len(blob or "")
            info["probe_ok"] = True
        except Exception as exc:
            info["probe_ok"] = False
            info["error"] = _soft(str(exc) or type(exc).__name__)
    return info


def list_items() -> List[Dict[str, Any]]:
    st = status(probe=False)
    rows: List[Dict[str, Any]] = []
    for key in (
        "hot_cache",
        "people",
        "projects",
        "context",
        "glossary",
        "memory_dir",
        "content",
    ):
        meta = st.get(key) or {}
        ok = bool(meta.get("exists") or meta.get("is_dir"))
        detail = meta.get("path") or key
        if meta.get("md_count"):
            detail = f"{detail} md={meta['md_count']}"
        elif meta.get("size_hint"):
            detail = f"{detail} bytes={meta['size_hint']}"
        rows.append({"id": key, "ok": ok, "detail": detail})
    rows.append(
        {
            "id": "openai_pkg",
            "ok": bool(st.get("openai_pkg")),
            "detail": "openai package" + (" installed" if st.get("openai_pkg") else " missing"),
        }
    )
    rows.append(
        {
            "id": "openai_api_key",
            "ok": bool(st.get("openai_api_key_present")),
            "detail": (
                f"OPENAI_API_KEY present ({st.get('openai_api_key_redacted')})"
                if st.get("openai_api_key_present")
                else "OPENAI_API_KEY missing"
            ),
        }
    )
    rows.append(
        {
            "id": "memory_index_import",
            "ok": bool(st.get("memory_index_import")),
            "detail": "Memory_Index import "
            + ("ok" if st.get("memory_index_import") else "unavailable"),
        }
    )
    rows.append(
        {
            "id": "soft_fail",
            "ok": True,
            "detail": (
                f"prefix {_SOFT!r}; stay PARTIAL; distinct from READY "
                "briefing retrieve + PARTIAL bolt refresh-memory"
            ),
        }
    )
    return rows


def try_remember(
    fact: str,
    section: str = "Recent Notes",
) -> Dict[str, Any]:
    """Wrap remember(); soft-fail on write failure. Never raises."""
    out: Dict[str, Any] = {
        "ok": False,
        "error": "",
        "fact": fact,
        "section": section,
        "path": str(MEMORY_FILE),
    }
    if not (fact or "").strip():
        out["error"] = _soft("empty fact")
        return out
    try:
        ok = bool(remember(fact.strip(), section=section or "Recent Notes"))
        out["ok"] = ok
        if not ok:
            out["error"] = _soft("write failed")
        return out
    except Exception as exc:
        out["ok"] = False
        out["error"] = _soft(str(exc) or type(exc).__name__)
        return out


def try_recall(question: str, *, quiet: bool = True) -> Dict[str, Any]:
    """Wrap recall(); soft-fail when openai/key/API missing. Never raises."""
    out: Dict[str, Any] = {
        "ok": False,
        "error": "",
        "question": question,
        "answer": "",
    }
    if not (question or "").strip():
        out["error"] = _soft("empty question")
        print(out["error"])
        return out

    if not _openai_pkg_present():
        out["error"] = _soft("openai package not installed")
        print(out["error"])
        return out

    if not (os.getenv("OPENAI_API_KEY", "") or "").strip():
        out["error"] = _soft("OPENAI_API_KEY not set in .env")
        print(out["error"])
        return out

    try:
        answer = recall(question.strip(), quiet=quiet)
        # Existing recall() returns error strings instead of raising
        if isinstance(answer, str) and (
            answer.startswith("openai package")
            or answer.startswith("OPENAI_API_KEY")
            or answer.startswith("Recall failed:")
        ):
            out["error"] = _soft(answer)
            print(out["error"])
            return out
        out["ok"] = True
        out["answer"] = answer or ""
        return out
    except Exception as exc:
        out["error"] = _soft(str(exc) or type(exc).__name__)
        print(out["error"])
        return out


def try_load(*, truncate: int = 0) -> Dict[str, Any]:
    """Dump load_all_memory summary. Local, no LLM. Never raises."""
    out: Dict[str, Any] = {
        "ok": False,
        "error": "",
        "chars": 0,
        "text": "",
        "truncated": False,
    }
    try:
        blob = load_all_memory() or ""
        out["chars"] = len(blob)
        if truncate and truncate > 0 and len(blob) > truncate:
            out["text"] = blob[:truncate] + "\n… [truncated]"
            out["truncated"] = True
        else:
            out["text"] = blob
        out["ok"] = True
        return out
    except Exception as exc:
        out["error"] = _soft(str(exc) or type(exc).__name__)
        return out


def _print_status(info: Dict[str, Any], as_json: bool) -> int:
    import json as _json

    if as_json:
        print(_json.dumps(info, indent=2))
    else:
        ready = "yes" if info.get("ready") else "no"
        print(f"bolt-memory readiness: {info.get('readiness')}  ready={ready}")
        print(f"  root:    {info.get('memory_root')}")
        hot = info.get("hot_cache") or {}
        print(f"  MEMORY.md: present={hot.get('exists')}  path={hot.get('path')}")
        for label, key in (
            ("people", "people"),
            ("projects", "projects"),
            ("context", "context"),
            ("glossary", "glossary"),
            ("memory/", "memory_dir"),
            ("content", "content"),
        ):
            meta = info.get(key) or {}
            present = meta.get("exists") or meta.get("is_dir")
            extra = ""
            if meta.get("md_count"):
                extra = f" md={meta['md_count']}"
            print(f"  {label}: present={bool(present)}{extra}")
        print(f"  openai pkg: {info.get('openai_pkg')}")
        print(
            f"  OPENAI_API_KEY: present={info.get('openai_api_key_present')}"
            + (
                f" ({info.get('openai_api_key_redacted')})"
                if info.get("openai_api_key_present")
                else ""
            )
        )
        print(f"  Memory_Index import: {info.get('memory_index_import')}")
        if info.get("probe"):
            print(
                f"  probe_ok: {info.get('probe_ok')}  "
                f"load_chars={info.get('probe_load_chars')}"
            )
        if info.get("error"):
            print(f"  {info['error']}")
        else:
            print(f"  hint: {info.get('hint')}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import json as _json
    import sys as _sys

    argv = list(_sys.argv[1:] if argv is None else argv)

    # Back-compat: legacy flags → new actions
    if argv and argv[0] not in (
        "status",
        "list",
        "remember",
        "recall",
        "load",
        "-h",
        "--help",
    ):
        if argv[0] == "--load":
            argv = ["load"] + argv[1:]
        elif argv[0] == "--remember":
            argv = ["remember"] + argv[1:]
        elif argv[0] in ("--refresh-index", "--search"):
            # Legacy ops kept as soft messages — use bolt refresh-memory / search
            print(
                _soft(
                    f"legacy flag {argv[0]!r} retired here — "
                    "use bolt refresh-memory / bolt search"
                )
            )
            return 0
        elif argv[0].startswith("-") and argv[0] not in ("--json", "--probe"):
            # Unknown bare flag
            pass
        elif not argv[0].startswith("-"):
            # Bare question → recall (legacy default)
            argv = ["recall"] + argv

    parser = argparse.ArgumentParser(
        prog="bolt memory",
        description="Bolt long-term memory store (PARTIAL; soft-fail).",
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["status", "list", "remember", "recall", "load"],
        help="status (default) | list | remember | recall | load",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="status only: import openai + load_all_memory length",
    )
    parser.add_argument(
        "--fact",
        default="",
        help="remember: fact text (alt to positional)",
    )
    parser.add_argument(
        "--section",
        default="Recent Notes",
        help="remember: MEMORY.md section (default: Recent Notes)",
    )
    parser.add_argument(
        "--truncate",
        type=int,
        default=4000,
        help="load: max chars to print (0 = full; default 4000)",
    )
    parser.add_argument(
        "rest",
        nargs="*",
        help="remember/recall: fact or question text",
    )
    args = parser.parse_args(argv)

    if args.action == "status":
        return _print_status(status(probe=args.probe), args.json)

    if args.action == "list":
        rows = list_items()
        if args.json:
            print(_json.dumps({"items": rows, "soft_fail_note": _SOFT}, indent=2))
        else:
            for r in rows:
                mark = "OK" if r["ok"] else "NO"
                print(f"[{mark}] {r['id']}: {r['detail']}")
            print(f"(soft-fail prefix: {_SOFT!r})")
        return 0

    if args.action == "remember":
        fact = (args.fact or "").strip()
        if not fact:
            fact = " ".join(args.rest).strip()
        result = try_remember(fact, section=args.section)
        if args.json:
            print(_json.dumps(result, indent=2))
        else:
            if result.get("ok"):
                print(f"✓ Saved to {result.get('path')}: {fact[:120]}")
            else:
                print(result.get("error") or _soft("remember failed"))
        return 0

    if args.action == "recall":
        question = " ".join(args.rest).strip()
        result = try_recall(question, quiet=True)
        if args.json:
            print(_json.dumps(result, indent=2))
        else:
            if result.get("ok"):
                print(result.get("answer") or "")
            # error already printed by try_recall
        return 0

    if args.action == "load":
        trunc = 0 if args.json and args.truncate == 4000 else args.truncate
        # For --json default to full text unless --truncate explicitly set;
        # keep truncate for human print.
        if args.json:
            result = try_load(truncate=0)
            payload = {
                "ok": result.get("ok"),
                "chars": result.get("chars"),
                "error": result.get("error"),
                "text": result.get("text"),
            }
            print(_json.dumps(payload, indent=2))
        else:
            result = try_load(truncate=args.truncate)
            if result.get("error") and not result.get("ok"):
                print(result["error"])
                return 0
            trunc_note = " truncated" if result.get("truncated") else ""
            print(f"(chars={result.get('chars')}{trunc_note})")
            print(result.get("text") or "")
        return 0

    print(_soft(f"unknown action {args.action!r}"))
    return 0


if __name__ == "__main__":
    import sys as _sys

    _sys.exit(main())
