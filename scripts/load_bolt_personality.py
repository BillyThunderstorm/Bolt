#!/usr/bin/env python3
"""
load_bolt_personality.py — Gemini chat with Bolt persona (engine)
=================================================================
Former SHELL: ``parents[3]`` → ``/Users/carter`` + missing
``Bolt_Personality.txt``. Now bootstraps via ``scripts/_paths.py``.

Canonical persona: ``Data/context/bolt-personality.md``.
Fallbacks: ``Docs/scratch/reviews/Bolt_Personality.txt``,
repo-root ``Bolt_Personality.txt``.

Soft-fail prefix (CLI): ``Personality unavailable:``.
When imported, missing file returns "" (no sys.exit).
CLI chat soft-fails (exit 0) on missing file / google.genai / GEMINI_API_KEY.

Soft-fail CLI wrapper (PARTIAL): ``bolt personality status|list|run``.
Distinct from READY ``bolt gemini`` / ``bolt nexus`` / ``bolt chat``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from _paths import REPO_ROOT  # noqa: E402

_SOFT = "Personality unavailable:"

_CANON = REPO_ROOT / "Data" / "context" / "bolt-personality.md"
_FALLBACKS = (
    REPO_ROOT / "Docs" / "scratch" / "reviews" / "Bolt_Personality.txt",
    REPO_ROOT / "Bolt_Personality.txt",
)


def _soft(msg: str) -> str:
    if msg.startswith(_SOFT):
        return msg
    return f"{_SOFT} {msg}"


def resolve_personality_path() -> Path | None:
    """Return first existing personality file (canonical, then fallbacks)."""
    if _CANON.is_file():
        return _CANON
    for p in _FALLBACKS:
        if p.is_file():
            return p
    return None


def load_bolt_personality() -> str:
    """
    Load personality text. Soft on import: missing file → "" (no exit).
    """
    path = resolve_personality_path()
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env", override=False)
        load_dotenv(override=False)
    except Exception:
        pass


def run_bolt_assistant(*, once: str | None = None) -> int:
    """Interactive (or one-shot) Gemini chat with Bolt persona. Soft-fail → 0."""
    bolt_instructions = load_bolt_personality()
    if not bolt_instructions:
        tried = [_CANON, *_FALLBACKS]
        print(
            _soft(
                "personality file missing — tried: "
                + ", ".join(str(p) for p in tried)
            ),
            file=sys.stderr,
        )
        return 0

    _load_dotenv()
    my_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not my_key:
        print(_soft("GEMINI_API_KEY missing (chat gated)"), file=sys.stderr)
        return 0

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        print(
            _soft(f"google.genai not installed ({exc})"),
            file=sys.stderr,
        )
        return 0

    try:
        client = genai.Client(api_key=my_key)
        config = types.GenerateContentConfig(
            system_instruction=bolt_instructions,
            temperature=0.85,
        )
        chat = client.chats.create(model="gemini-2.0-flash", config=config)
    except Exception as exc:
        print(_soft(f"Gemini client failed ({exc})"), file=sys.stderr)
        return 0

    if once is not None:
        try:
            response = chat.send_message(once)
            print(f"\nBolt: {getattr(response, 'text', response)}\n")
        except Exception as exc:
            print(_soft(f"Chat error: {exc}"), file=sys.stderr)
        return 0

    print("\n⚡ Bolt is online and ready to build!")
    print("Type 'exit' or 'quit' to end the session.\n")

    while True:
        try:
            user_input = input("You: ")
            if user_input.lower() in ("exit", "quit"):
                print("\n⚡ Bolt: Goodbye!")
                break
            if not user_input.strip():
                continue
            response = chat.send_message(user_input)
            print(f"\nBolt: {getattr(response, 'text', response)}\n")
        except KeyboardInterrupt:
            print("\n⚡ Bolt: Exiting safely!")
            return 0
        except Exception as e:
            print(f"\n{_soft(f'Chat error: {e}')}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    once = None
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--once", "--prompt", "-q") and i + 1 < len(args):
            once = args[i + 1]
            i += 2
            continue
        if a in ("-h", "--help", "help"):
            print(
                "load_bolt_personality.py — Gemini persona chat\n"
                "  (no args)     interactive chat\n"
                "  --once TEXT   one-shot prompt (no hang)\n"
                f"Soft-fail: {_SOFT}"
            )
            return 0
        i += 1
    return run_bolt_assistant(once=once)


if __name__ == "__main__":
    raise SystemExit(main())
