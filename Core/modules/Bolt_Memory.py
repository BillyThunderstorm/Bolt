#!/usr/bin/env python3
"""
modules/Bolt_Memory.py — Bolt's long-term memory system (Phase 4)
=================================================================
Gives Bolt the ability to remember things across sessions and recall
them when needed. No LangChain, no vector database — just Bolt's LLM
providers + the Data/ memory tree you already have.

How it works:
  - Data/MEMORY.md     → hot cache (most important stuff, always loaded)
  - Data/people/       → notes on people Billy works with or talks about
  - Data/projects/     → project-specific notes (Bolt, ClipBot, etc.)
  - Data/context/      → creator setup, stream notes, brand context
  - Data/glossary.md   → decoder ring for Billy's shorthand
  - Data/memory/       → user_profile, research_log, phase checklists

`recall()` answers a question from this memory (plus live state: today's
date and the current game in Core/config.json) through LLM_Handler, so it
follows Bolt's budget mode and provider order (Grok → Ollama → OpenAI). Grok
gets the whole memory tree; Ollama gets word-matched memsearch hits + a trimmed
core so it fits a small context window.

`remember()` adds a dated fact under a MEMORY.md section (no same-day
duplicates; keeps the file's Finder tag) and refreshes the memory index.

Usage anywhere in Bolt:
    from modules.Bolt_Memory import recall, remember, load_all_memory

    answer = recall("What platforms is Billy focusing on right now?")
    remember("Billy switched from Marvel Rivals to Fortnite on 2026-04-27")
    context = load_all_memory()

CLI (READY via ``bolt memory``, 19 Oct 2026):
  status [--json] [--probe]
  list   [--json]
  remember "fact" [--section "Recent Notes"]
  recall "question" [--provider xai|ollama|openai] [--no-search] [--json]
  load   [--json]

Soft-fail prefix: ``Bolt memory unavailable:``. Distinct from READY
``bolt memsearch`` (local word search, no LLM) and READY
``bolt refresh-memory`` (index rebuild).
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


def _memory_sections() -> List[tuple]:
    """(title, text) blocks in priority order — hot cache first."""
    out: List[tuple] = []
    for title, text in (
        ("Core Memory (MEMORY.md)", _read_file(MEMORY_FILE)),
        ("Glossary", _read_file(GLOSSARY)),
        ("People", _read_folder(PEOPLE_DIR)),
        ("Projects", _read_folder(PROJECTS_DIR)),
        ("Context", _read_folder(CONTEXT_DIR)),
        ("Content Memory", _read_folder(CONTENT_DIR)),
    ):
        if text:
            out.append((title, text))
    return out


def load_all_memory() -> str:
    """
    Load the full memory context into a single string (local, no LLM).

    Order: MEMORY.md hot cache, glossary, people, projects, context, content.
    ``recall`` trims this per provider; other callers get all of it.
    """
    sections = [f"## {title}\n{text}" for title, text in _memory_sections()]
    if not sections:
        return "(no memory files found — memory/ folder may be empty)"
    return "\n\n---\n\n".join(sections)


# ── Retrieval ─────────────────────────────────────────────────────────────────


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



# ── Recall — answer from memory via LLM_Handler (Grok → Ollama → OpenAI) ──────
# READY (19 Oct 2026). Used to call OpenAI directly (gpt-4o-mini) and died when
# that account ran out of credits. Now routes through LLM_Handler so it follows
# Bolt's budget mode + provider order, and sizes the prompt per provider:
# Grok/OpenAI get the whole memory tree; Ollama's default context window is
# small, so local recall gets live state + word-matched hits + trimmed core.

CONFIG_FILE = PROJECT_ROOT / "Core" / "config.json"


def _env_int(name: str, default: int) -> int:
    try:
        return max(2000, int(os.getenv(name, "") or default))
    except ValueError:
        return default


CLOUD_PROMPT_CHARS = _env_int("BOLT_MEMORY_CLOUD_CHARS", 60000)
LOCAL_PROMPT_CHARS = _env_int("BOLT_MEMORY_LOCAL_CHARS", 9000)

_RECALL_RULES = """You are Bolt, William (Billy) Carter's personal AI producer.
Answer the question concisely and accurately using only the memory below.
Prefer LIVE STATE and newer dated notes when they conflict with older notes.
If memory does not say, say you don't know — never make things up."""


def _live_state() -> str:
    """Facts that change faster than MEMORY.md (today + current game)."""
    lines = [f"- Today: {datetime.now().strftime('%A %Y-%m-%d')}"]
    try:
        import json as _json

        cfg = _json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        game = str(cfg.get("game") or "").strip()
        if game and game != "__twitch__":
            lines.append(
                "- Current game (Core/config.json; follows the Twitch category): "
                f"{game}"
            )
    except Exception:
        pass
    return "\n".join(lines)


def _search_context(question: str, limit: int = 6) -> str:
    """Word-matched hits from READY Memory_Search (rebuilds a stale index)."""
    try:
        from modules import Memory_Search as _ms
    except Exception:
        _ms = None
    if _ms is not None:
        try:
            res = _ms.try_run(question, limit=limit)
            if res.get("ok") and res.get("hit_count"):
                return str(res.get("context") or "").strip()
            return ""
        except Exception:
            return ""
    try:
        ctx = retrieve_context(question, limit=limit)
        return "" if ctx.startswith("(memory retrieval index") else ctx
    except Exception:
        return ""


def build_recall_prompt(
    question: str,
    *,
    budget_chars: int = CLOUD_PROMPT_CHARS,
    relevant: Optional[str] = None,
    use_retrieval: bool = True,
) -> Dict[str, Any]:
    """System prompt for recall, capped at ``budget_chars``. Never raises."""
    if relevant is None:
        relevant = _search_context(question) if use_retrieval else ""
    parts = [_RECALL_RULES, "LIVE STATE:\n" + _live_state()]
    if relevant:
        cap = max(1500, budget_chars // 3)
        rel = relevant if len(relevant) <= cap else relevant[:cap] + "\n… [trimmed]"
        parts.append("MOST RELEVANT MEMORY (entries containing your words):\n" + rel)
    remaining = budget_chars - sum(len(p) + 7 for p in parts)
    included: List[str] = []
    dropped: List[str] = []
    for title, text in _memory_sections():
        block = f"## {title}\n{text}"
        if len(block) + 7 <= remaining:
            parts.append(block)
            included.append(title)
            remaining -= len(block) + 7
        elif remaining > 1500:
            parts.append(block[: remaining - 40].rstrip() + "\n… [trimmed]")
            included.append(f"{title} (trimmed)")
            remaining = 0
        else:
            dropped.append(title)
    system = "\n\n---\n\n".join(parts)
    return {
        "system": system,
        "chars": len(system),
        "budget_chars": budget_chars,
        "relevant_hits": bool(relevant),
        "included": included,
        "dropped": dropped,
    }


def _norm_provider(name: Optional[str]) -> str:
    n = (name or "").strip().lower()
    return "xai" if n == "grok" else n


def recall_providers(preferred: Optional[str] = None) -> List[str]:
    """Provider order recall will try (budget mode aware). Never raises."""
    try:
        from modules.LLM_Handler import _resolve_providers

        order = list(_resolve_providers(preferred or None, task_type="memory"))
    except Exception:
        order = []
    pref = _norm_provider(preferred)
    if pref:
        order = [p for p in order if p == pref] or [pref]
    return order


def recall_detailed(
    question: str,
    *,
    provider: Optional[str] = None,
    use_retrieval: bool = True,
    max_tokens: int = 512,
) -> Dict[str, Any]:
    """Answer ``question`` from memory. Returns a dict; never raises."""
    import contextlib
    import io

    out: Dict[str, Any] = {
        "ok": False,
        "question": question,
        "answer": "",
        "provider": "",
        "model": "",
        "prompt_chars": 0,
        "relevant_hits": False,
        "included": [],
        "dropped": [],
        "attempts": [],
        "error": "",
    }
    q = (question or "").strip()
    if not q:
        out["error"] = "empty question"
        return out
    try:
        from modules.LLM_Handler import _default_model, ask_llm
    except Exception as exc:
        out["error"] = f"LLM_Handler unavailable ({exc})"
        return out

    order = recall_providers(provider)
    if not order:
        out["error"] = "no LLM providers allowed (check BOLT_LLM_MODE / keys / Ollama)"
        return out

    relevant = _search_context(q) if use_retrieval else ""
    for prov in order:
        budget = LOCAL_PROMPT_CHARS if prov == "ollama" else CLOUD_PROMPT_CHARS
        built = build_recall_prompt(
            q, budget_chars=budget, relevant=relevant, use_retrieval=use_retrieval
        )
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                reply = ask_llm(
                    q,
                    system=built["system"],
                    provider=prov,
                    fallback=False,
                    max_tokens=max_tokens,
                    temperature=0.2,
                    task_type="memory",
                )
        except Exception as exc:
            reply = f"LLM unavailable: {prov}: {exc}"
        reply = (reply or "").strip()
        if reply and not reply.startswith("LLM unavailable:"):
            out.update(
                ok=True,
                answer=reply,
                provider=prov,
                model=_default_model(prov, "memory", "medium"),
                prompt_chars=built["chars"],
                relevant_hits=built["relevant_hits"],
                included=built["included"],
                dropped=built["dropped"],
            )
            return out
        detail = reply or "empty reply"
        noise = " ".join(buf.getvalue().split())
        if noise and noise not in detail:
            detail = f"{detail} ({noise[:160]})"
        out["attempts"].append({"provider": prov, "error": detail[:300]})

    tried = "; ".join(f"{a['provider']}: {a['error'][:140]}" for a in out["attempts"])
    out["error"] = f"no LLM answered — {tried}"
    return out


def recall(question: str, quiet: bool = False, use_retrieval: bool = True) -> str:
    """
    Ask Bolt a question; it answers from Data/ memory (plus live game/date).

    Examples:
        recall("What game is Billy streaming right now?")
        recall("What was decided about ElevenLabs?")

    Returns the answer, or a string starting with ``Recall failed:``.
    """
    res = recall_detailed(question, use_retrieval=use_retrieval)
    if not res.get("ok"):
        return f"Recall failed: {res.get('error') or 'unknown error'}"
    answer = res["answer"]
    if not quiet:
        notify(
            f"Memory recall: {answer[:100]}{'...' if len(answer) > 100 else ''}",
            level="info",
        )
    return answer


# ── Remember — save a new fact to MEMORY.md ───────────────────────────────────

_LAST_REMEMBER: Dict[str, Any] = {"duplicate": False}


def _write_keep_tags(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` safely without dropping Finder tags.

    The new content goes to a temp file first and is read back; only then is it
    copied into the existing file (same inode), so MEMORY.md keeps any
    Finder tag. An os.replace swap would silently drop the tag xattrs on macOS.
    """
    import shutil
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".MEMORY.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        if Path(tmp).read_text(encoding="utf-8") != text:
            raise IOError("temp write verify failed")
        if path.exists():
            shutil.copyfile(tmp, path)
        else:
            os.replace(tmp, path)
            tmp = ""
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


def remember(fact: str, section: str = "Recent Notes") -> bool:
    """
    Save a new fact to MEMORY.md so it persists across sessions.

    The fact is dated and added at the top of its ``## section`` (exact header
    line match; created at the end when missing). The same fact on the same
    day is not added twice. Returns True when the fact is in MEMORY.md.
    """
    _LAST_REMEMBER["duplicate"] = False
    fact = " ".join(str(fact or "").split())
    if not fact:
        return False
    section = " ".join(str(section or "Recent Notes").split()) or "Recent Notes"
    header = f"## {section}"
    entry = f"- [{datetime.now().strftime('%Y-%m-%d')}] {fact}"

    try:
        existing = MEMORY_FILE.read_text(encoding="utf-8") if MEMORY_FILE.exists() else ""
        lines = existing.splitlines()
        if entry in (ln.strip() for ln in lines):
            _LAST_REMEMBER["duplicate"] = True
            return True

        idx = next((i for i, ln in enumerate(lines) if ln.strip() == header), None)
        if idx is None:
            body = existing.rstrip("\n")
            updated = (body + "\n\n" if body else "") + f"{header}\n{entry}\n"
        else:
            lines.insert(idx + 1, entry)
            updated = "\n".join(lines) + "\n"

        _write_keep_tags(MEMORY_FILE, updated)
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


# ── CLI (READY — bolt memory) ─────────────────────────────────────────────────
# Soft-fail prefix for status/list/remember/recall/load. The recall / remember /
# load_all_memory APIs above stay the same for in-process callers.

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


def _key_meta(var: str) -> Dict[str, Any]:
    raw = (os.getenv(var, "") or "").strip()
    if not raw:
        return {"present": False, "redacted": ""}
    redacted = f"{raw[:4]}…{raw[-2:]}" if len(raw) >= 10 else "***"
    return {"present": True, "redacted": redacted}


def _openai_key_meta() -> Dict[str, Any]:
    return _key_meta("OPENAI_API_KEY")


def _ollama_up() -> bool:
    try:
        from modules.LLM_Handler import _ollama_healthy

        return bool(_ollama_healthy())
    except Exception:
        return False


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


def _llm_mode() -> str:
    try:
        from modules.LLM_Budget import llm_mode

        return llm_mode()
    except Exception:
        return "unknown"


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Never raises. ready=True when a memory store exists and recall has a provider."""
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

    openai_meta = _key_meta("OPENAI_API_KEY")
    xai_meta = _key_meta("XAI_API_KEY")
    ollama_up = _ollama_up()
    openai_pkg = _openai_pkg_present()
    order = recall_providers() if openai_pkg else []
    usable = [
        p
        for p in order
        if (p == "xai" and xai_meta["present"])
        or (p == "openai" and openai_meta["present"])
        or (p == "ollama" and ollama_up)
    ]
    recall_ready = bool(openai_pkg and usable)

    info: Dict[str, Any] = {
        "checked_at": _iso(),
        "ready": bool(any_store),
        "partial": False,
        "readiness": "READY",
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
        "openai_api_key_present": openai_meta["present"],
        "openai_api_key_redacted": openai_meta["redacted"],
        "xai_api_key_present": xai_meta["present"],
        "ollama_up": ollama_up,
        "llm_mode": _llm_mode(),
        "recall_providers": order,
        "recall_usable_providers": usable,
        "recall_ready": recall_ready,
        "cloud_prompt_chars": CLOUD_PROMPT_CHARS,
        "local_prompt_chars": LOCAL_PROMPT_CHARS,
        "memory_index_import": retrieve_memory is not None,
        "probe": bool(probe),
        "probe_ok": None,
        "probe_load_chars": None,
        "error": "",
        "hint": (
            "remember/load are local · recall answers from Data/ memory + live game "
            "via LLM_Handler (Grok → Ollama → OpenAI, budget-mode aware) · "
            "--provider xai|ollama|openai to pin one"
        ),
        "is_stranger_ready": False,
    }

    if not any_store:
        info["error"] = _soft(
            "no local memory store yet (Data/MEMORY.md or people|projects|"
            "context|glossary|memory|content) — run: bolt memory remember \"first fact\""
        )
        info["ready"] = False
    elif not recall_ready:
        info["error"] = _soft(
            "recall has no LLM: set XAI_API_KEY in .env, or start Ollama "
            "(`ollama serve` + `ollama pull llama3.1:8b`), or set OPENAI_API_KEY"
            + ("" if openai_pkg else " — and install the openai package (uv sync)")
            + " · remember/load still work"
        )

    if probe:
        try:
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
            "id": "xai_api_key",
            "ok": bool(st.get("xai_api_key_present")),
            "detail": "XAI_API_KEY " + ("present" if st.get("xai_api_key_present") else "missing"),
        }
    )
    rows.append(
        {
            "id": "ollama",
            "ok": bool(st.get("ollama_up")),
            "detail": "Ollama " + ("reachable" if st.get("ollama_up") else "not reachable"),
        }
    )
    rows.append(
        {
            "id": "openai_api_key",
            "ok": bool(st.get("openai_api_key_present")),
            "detail": (
                f"OPENAI_API_KEY present ({st.get('openai_api_key_redacted')})"
                if st.get("openai_api_key_present")
                else "OPENAI_API_KEY missing (optional fallback)"
            ),
        }
    )
    rows.append(
        {
            "id": "recall_providers",
            "ok": bool(st.get("recall_ready")),
            "detail": "recall order ("
            + str(st.get("llm_mode"))
            + " mode): "
            + (" → ".join(st.get("recall_providers") or []) or "none"),
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
        "duplicate": False,
    }
    if not (fact or "").strip():
        out["error"] = _soft("empty fact — bolt memory remember \"what to keep\"")
        return out
    try:
        ok = bool(remember(fact.strip(), section=section or "Recent Notes"))
        out["ok"] = ok
        out["duplicate"] = bool(_LAST_REMEMBER.get("duplicate"))
        if not ok:
            out["error"] = _soft("write failed")
        return out
    except Exception as exc:
        out["ok"] = False
        out["error"] = _soft(str(exc) or type(exc).__name__)
        return out


def try_recall(
    question: str,
    *,
    quiet: bool = True,
    provider: Optional[str] = None,
    use_retrieval: bool = True,
) -> Dict[str, Any]:
    """Wrap recall_detailed(); soft-fail with guidance. Never raises."""
    if not (question or "").strip():
        return {
            "ok": False,
            "question": question,
            "answer": "",
            "error": _soft("empty question — bolt memory recall \"what did I decide about X?\""),
        }
    if not _openai_pkg_present():
        return {
            "ok": False,
            "question": question,
            "answer": "",
            "error": _soft("openai package not installed (LLM client) — run: uv sync"),
        }
    try:
        res = recall_detailed(
            question.strip(), provider=provider, use_retrieval=use_retrieval
        )
    except Exception as exc:
        res = {"ok": False, "question": question, "answer": "", "error": str(exc)}
    if not res.get("ok"):
        res["error"] = _soft(
            (res.get("error") or "recall failed")
            + " · check: bolt memory status (XAI_API_KEY / Ollama / OPENAI_API_KEY)"
        )
    elif not quiet:
        notify(f"Memory recall: {res['answer'][:100]}", level="info")
    return res


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
        return 0
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
        extra = f" md={meta['md_count']}" if meta.get("md_count") else ""
        print(f"  {label}: present={bool(present)}{extra}")
    order = " → ".join(info.get("recall_providers") or []) or "none"
    print(
        f"  recall: ready={info.get('recall_ready')}  mode={info.get('llm_mode')}  "
        f"order={order}"
    )
    print(
        f"  XAI_API_KEY={info.get('xai_api_key_present')}  "
        f"ollama={info.get('ollama_up')}  "
        f"OPENAI_API_KEY={info.get('openai_api_key_present')}"
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
            print(
                _soft(
                    f"legacy flag {argv[0]!r} retired here — "
                    "use bolt refresh-memory / bolt memsearch"
                )
            )
            return 0
        elif not argv[0].startswith("-"):
            # Bare question → recall (legacy default)
            argv = ["recall"] + argv

    parser = argparse.ArgumentParser(
        prog="bolt memory",
        description="Bolt long-term memory: remember facts, recall answers (READY).",
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
        help="status only: also load all memory and report its size",
    )
    parser.add_argument("--fact", default="", help="remember: fact text (alt to positional)")
    parser.add_argument(
        "--section",
        default="Recent Notes",
        help="remember: MEMORY.md section (default: Recent Notes)",
    )
    parser.add_argument(
        "--provider",
        default="",
        help="recall: pin one provider (xai | grok | ollama | openai)",
    )
    parser.add_argument(
        "--no-search",
        action="store_true",
        help="recall: skip the word-matched memsearch hits",
    )
    parser.add_argument(
        "--truncate",
        type=int,
        default=4000,
        help="load: max chars to print (0 = full; default 4000)",
    )
    parser.add_argument("rest", nargs="*", help="remember/recall: fact or question text")
    # intermixed: allow `recall --provider ollama "question"` (flags before the text)
    args = parser.parse_intermixed_args(argv)

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
        return 0

    if args.action == "remember":
        fact = (args.fact or "").strip() or " ".join(args.rest).strip()
        result = try_remember(fact, section=args.section)
        if args.json:
            print(_json.dumps(result, indent=2))
        elif result.get("ok"):
            what = "Already saved today" if result.get("duplicate") else "✓ Saved"
            print(f"{what} → {result.get('path')} [{args.section}]: {fact[:120]}")
        else:
            print(result.get("error") or _soft("remember failed"))
        return 0

    if args.action == "recall":
        question = " ".join(args.rest).strip()
        result = try_recall(
            question,
            quiet=True,
            provider=args.provider or None,
            use_retrieval=not args.no_search,
        )
        if args.json:
            print(_json.dumps(result, indent=2, default=str))
        elif result.get("ok"):
            print(result.get("answer") or "")
            hits = "yes" if result.get("relevant_hits") else "no"
            print(
                f"\n(via {result.get('provider')}/{result.get('model')} · "
                f"{result.get('prompt_chars')} chars of memory · word-matched hits: {hits})"
            )
        else:
            print(result.get("error"))
        return 0

    if args.action == "load":
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
