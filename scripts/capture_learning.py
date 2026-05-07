#!/usr/bin/env python3
"""
scripts/capture_learning.py — Save a learning note to Bolt's memory
====================================================================
Run this after any learning session — a chapter, a video, an experiment,
a conversation. It saves a structured note to memory/learning/ so Bolt
knows what you know.

Usage:
    python3 scripts/capture_learning.py
    python3 scripts/capture_learning.py --list
    python3 scripts/capture_learning.py --read ch03

What it does:
    - Prompts you for the chapter/topic and what you learned
    - Asks how it connects to Bolt
    - Saves a timestamped note to memory/learning/
    - Optionally uses Claude to help structure your notes if you ramble

Why this exists:
    Bolt learns by reading files in memory/. The learning/ folder is where
    YOUR knowledge goes — so Bolt can reference it, build on it, and help
    you apply it. This script makes adding to that folder a 2-minute habit
    instead of a chore.
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT         = Path(__file__).parent.parent
LEARNING_DIR = ROOT / "memory" / "learning"
TEMPLATE     = LEARNING_DIR / "_TEMPLATE.md"

LEARNING_DIR.mkdir(parents=True, exist_ok=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    """Convert a title to a safe filename."""
    import re
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:60]


def list_notes():
    """Print all existing learning notes."""
    notes = sorted(LEARNING_DIR.glob("*.md"))
    notes = [n for n in notes if not n.name.startswith("_")]
    if not notes:
        print("\n  No learning notes yet. Run the script to add your first one.\n")
        return
    print(f"\n  {'─'*50}")
    print(f"  Learning notes in memory/learning/")
    print(f"  {'─'*50}")
    for note in notes:
        # Try to read the first non-empty, non-# line as a description
        try:
            lines = note.read_text().splitlines()
            title = next((l.lstrip("# ") for l in lines if l.strip() and not l.startswith("#")), "")
            captured = next((l for l in lines if "Captured:" in l), "")
            date = captured.split("Captured:")[1].split("|")[0].strip() if captured else ""
        except Exception:
            title = ""
            date = ""
        print(f"  {note.stem:<35} {date}")
    print()


def read_note(slug: str):
    """Print a specific note by partial name match."""
    matches = list(LEARNING_DIR.glob(f"*{slug}*.md"))
    matches = [m for m in matches if not m.name.startswith("_")]
    if not matches:
        print(f"\n  No note found matching '{slug}'\n")
        return
    for match in matches:
        print(f"\n  {'─'*50}")
        print(f"  {match.name}")
        print(f"  {'─'*50}")
        print(match.read_text())


def use_claude_to_structure(raw_notes: str, topic: str) -> str:
    """
    Optional: ask Claude to turn messy notes into a structured learning note.
    Only runs if ANTHROPIC_API_KEY is set.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return ""

    try:
        import anthropic
    except ImportError:
        return ""

    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""Billy is building Bolt — a personal AI streaming assistant — while also teaching himself ML and LLMs.
He just finished learning about: {topic}

Here are his raw notes / thoughts:
{raw_notes}

Turn these into a structured learning note using this format:
- ## The core idea (plain explanation, no jargon)
- ## Key vocab (table: term | plain meaning)
- ## Why this matters for Bolt (connect to his streaming AI assistant)
- ## What I can do with this now (concrete next steps)
- ## Questions still open (things to explore further)

Keep it concise. Write in plain English. Always connect back to Bolt."""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"  (Claude structuring failed: {e} — saving your raw notes instead)")
        return ""


def capture_note():
    """Interactive prompt to capture a new learning note."""
    print("\n  ⚡  Bolt Learning Capture")
    print("  ─────────────────────────")
    print("  What did you just learn? Let's save it so Bolt knows it too.\n")

    topic = input("  Topic / chapter title: ").strip()
    if not topic:
        print("  (cancelled — no topic entered)")
        return

    source = input("  Source (book chapter, video, experiment, etc.): ").strip() or "LLMs from Scratch"

    print("\n  What did you learn? (paste notes, ramble, whatever — press Enter twice when done):")
    lines = []
    while True:
        line = input()
        if line == "" and lines and lines[-1] == "":
            break
        lines.append(line)
    raw_notes = "\n".join(lines).strip()

    if not raw_notes:
        print("  (cancelled — no notes entered)")
        return

    bolt_connection = input("\n  How does this connect to Bolt? (what file, what feature, what decision): ").strip()
    what_now = input("  What can you do with this now that you couldn't before? ").strip()
    open_questions = input("  Anything still unclear or to come back to? ").strip()

    # Try Claude structuring if notes are long/messy
    structured = ""
    if len(raw_notes) > 100:
        print("\n  Asking Claude to help structure your notes...")
        structured = use_claude_to_structure(raw_notes, topic)

    # Build the note
    date = datetime.now().strftime("%Y-%m-%d")
    filename = f"{slugify(topic)}.md"
    filepath = LEARNING_DIR / filename

    if structured:
        content = f"# {topic}\n*Captured: {date} | Source: {source}*\n\n{structured}"
        if bolt_connection:
            content += f"\n\n## Connected to Bolt\n{bolt_connection}"
    else:
        content = f"""# {topic}
*Captured: {date} | Source: {source}*

## The core idea

{raw_notes}

## Why this matters for Bolt

{bolt_connection or "(fill in later)"}

## What I can do with this now

{what_now or "(fill in later)"}

## Questions still open

{open_questions or "(none right now)"}
"""

    filepath.write_text(content, encoding="utf-8")
    print(f"\n  ✓ Saved to memory/learning/{filename}")
    print(f"  Bolt will know this next session.\n")


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--list" in sys.argv:
        list_notes()
    elif "--read" in sys.argv:
        idx = sys.argv.index("--read")
        slug = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""
        if slug:
            read_note(slug)
        else:
            print("  Usage: python3 scripts/capture_learning.py --read ch03")
    else:
        capture_note()
