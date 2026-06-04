#!/usr/bin/env python3
"""
modules/Bolt_Memory.py — Bolt's long-term memory system (Phase 4)
=================================================================
Gives Bolt the ability to remember things across sessions and recall
them when needed. No LangChain, no vector database, no OpenAI key.
Just OpenAI + the memory/ folder you already have.

How it works:
  - memory/MEMORY.md  → hot cache (most important stuff, always loaded)
  - memory/people/    → notes on people Billy works with or talks about
  - memory/projects/  → project-specific notes (Bolt, ClipBot, etc.)
  - memory/context/   → creator setup, stream notes, brand context
  - memory/glossary.md → decoder ring for Billy's shorthand

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
"""

import os
from pathlib import Path
from datetime import datetime
from typing import Optional

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

MEMORY_ROOT  = Path(__file__).parent.parent / "memory"
MEMORY_FILE  = MEMORY_ROOT / "MEMORY.md"
GLOSSARY     = MEMORY_ROOT / "glossary.md"
PEOPLE_DIR   = MEMORY_ROOT / "people"
PROJECTS_DIR = MEMORY_ROOT / "projects"
CONTEXT_DIR  = MEMORY_ROOT / "context"
CONTENT_DIR  = MEMORY_ROOT / "content"

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
    retrieved_context = retrieve_context(question) if use_retrieval else "(retrieval disabled)"

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
            model="gpt-4o-mini",   # fast + cheap for quick recalls
            max_tokens=512,
            
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": question}]
        )
        answer = response.choices[0].message.content.strip()
        if not quiet:
            notify(f"Memory recall: {answer[:100]}{'...' if len(answer) > 100 else ''}", level="info")
        return answer
    except Exception as e:
        return f"Recall failed: {e}"


# ── Remember — save a new fact to MEMORY.md ───────────────────────────────────

def remember(fact: str, section: str = "Session Notes") -> bool:
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
                1  # only replace the first occurrence
            )
        else:
            # Add a new section at the end
            updated = existing + f"\n\n## {section}{entry}\n"

        MEMORY_FILE.write_text(updated, encoding="utf-8")
        notify(f"Memory saved: {fact[:80]}{'...' if len(fact) > 80 else ''}", level="success",
               reason="Added to memory/MEMORY.md — Bolt will remember this next session.")
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
        "game_change":    "Game switched to {game}",
        "clips_posted":   "{count} clip(s) posted — {titles}",
        "bot_connected":  "Twitch bot ({account}) confirmed connected",
        "setting_changed":"{setting} changed to {value} in config.json",
    }
    template = templates.get(event_type, f"{event_type}: {kwargs}")
    try:
        fact = template.format(**kwargs)
    except KeyError:
        fact = f"{event_type}: {kwargs}"
    remember(fact)


# ── CLI — test from terminal ───────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    print("\n  🤖  Bolt Memory System")
    print(f"  Memory root: {MEMORY_ROOT}")
    print(f"  MEMORY.md exists: {MEMORY_FILE.exists()}")
    print()

    if "--load" in sys.argv:
        print("  Full memory context:\n")
        print(load_all_memory())
        sys.exit(0)

    if "--refresh-index" in sys.argv:
        if refresh_memory_index is None:
            print("  Memory index module is not available")
            sys.exit(1)
        payload = refresh_memory_index()
        print(f"  Indexed {payload['entry_count']} memory entries")
        sys.exit(0)

    if "--search" in sys.argv:
        idx = sys.argv.index("--search")
        query = " ".join(sys.argv[idx + 1:]).strip()
        if not query:
            print("  Usage: python -m modules.Bolt_Memory --search 'your query'")
            sys.exit(1)
        print(retrieve_context(query))
        sys.exit(0)

    if "--remember" in sys.argv:
        idx = sys.argv.index("--remember")
        if idx + 1 < len(sys.argv):
            fact = sys.argv[idx + 1]
            success = remember(fact)
            print(f"  {'✓ Saved' if success else '✗ Failed'}: {fact}")
        else:
            print("  Usage: python -m modules.Bolt_Memory --remember 'your fact here'")
        sys.exit(0)

    # Default: ask a question
    question = " ".join(a for a in sys.argv[1:] if not a.startswith("--"))
    if question:
        print(f"  Question: {question}")
        print(f"  Answer:   {recall(question)}")
    else:
        print("  Usage:")
        print("    python -m modules.Bolt_Memory 'What game is Billy playing?'")
        print("    python -m modules.Bolt_Memory --load")
        print("    python -m modules.Bolt_Memory --refresh-index")
        print("    python -m modules.Bolt_Memory --search 'best Marvel Rivals clips'")
        print("    python -m modules.Bolt_Memory --remember 'Phase 3 is complete'")
    print()
