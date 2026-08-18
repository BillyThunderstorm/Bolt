#!/usr/bin/env python3
"""
bolt_live_voice.py — Hands-free voice I/O for Bolt
==================================================
Billy speaks → Bolt listens → interprets (intents or LLM) → speaks back.

This is a thin, stable entry point over Bolt_Conversation + Bolt_Voice.
It replaces the earlier Gemini multimodal experiment, which never played
audio and did not share the rest of Bolt's voice stack.

Usage (from repo root):
  PYTHONPATH=Core python3 Core/bolt_live_voice.py
  PYTHONPATH=Core python3 Core/bolt_live_voice.py --text
  PYTHONPATH=Core python3 Core/bolt_live_voice.py --once "queue status"
  PYTHONPATH=Core python3 Core/bolt_live_voice.py --status

Or via CLI (preferred):
  bolt voice
  bolt voice --text
  bolt talk "what's next?"
  bolt say "Clips are ready."
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure Core/ is importable when this file is run directly.
_CORE = Path(__file__).resolve().parent
_REPO = _CORE.parent
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))
os.chdir(_REPO)


def _speak_line(text: str) -> int:
    """One-shot TTS via Bolt_Voice (for `bolt say ...`)."""
    try:
        from modules.Bolt_Voice import speak, _speech_queue

        speak(text)
        _speech_queue.join()
        return 0
    except Exception as exc:
        print(f"bolt voice: speak failed: {exc}", file=sys.stderr)
        try:
            import subprocess

            voice = os.getenv("Bolt_VOICE") or os.getenv("BOLT_VOICE") or "Voice 3"
            subprocess.run(["say", "-v", voice, text], check=False)
            return 0
        except Exception:
            return 1


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    # `bolt say <text>` / `python bolt_live_voice.py --say <text>`
    if args and args[0] in ("--say", "say"):
        text = " ".join(args[1:]).strip()
        if not text:
            print("Usage: bolt say \"message to speak\"", file=sys.stderr)
            return 2
        print(text)
        return _speak_line(text)

    # Delegate conversation / status / clear / one-shot to Bolt_Conversation
    # so listen → intent → LLM → speak stays in one place.
    try:
        import Bolt_Conversation as conv
    except ImportError as exc:
        print(
            f"bolt voice: could not import Bolt_Conversation: {exc}\n"
            "  Try: PYTHONPATH=Core python3 -m Bolt_Conversation",
            file=sys.stderr,
        )
        return 1

    if "--clear" in args:
        conv.ConversationMemory().clear()
        print("Conversation history cleared.")
        return 0

    if "--status" in args:
        # Reuse conversation status printer
        sys.argv = ["Bolt_Conversation", "--status"]
        try:
            # Run the status branch by invoking the module's CLI path
            mem = conv.ConversationMemory()
            status = conv.provider_status()
            print("\n  Bolt Live Voice Status")
            print(f"  History turns: {len(mem.history)}")
            print(f"  History file:  {conv.HISTORY_FILE}")
            print(f"  Speech input:  {'yes' if conv.SPEECH_OK else 'no'}")
            print(f"  Voice output:  {'yes' if conv.VOICE_OK else 'no'}")
            print(f"  Intent router: {'yes' if conv.INTENT_OK else 'no'}")
            print(f"  LLM provider:  {conv.get_active_provider()}")
            print(f"  LLM status:    {status}")
            print(f"\n  Recent context:\n{mem.last_summary()}\n")
            return 0
        except Exception as exc:
            print(f"bolt voice: status failed: {exc}", file=sys.stderr)
            return 1

    text_mode = "--text" in args
    # Support both `--once "…"` and bare prompt args (like Bolt_Conversation)
    once_prompt: str | None = None
    if "--once" in args:
        i = args.index("--once")
        once_prompt = " ".join(args[i + 1 :]).strip() or None
        if not once_prompt:
            print('Usage: bolt voice --once "your question"', file=sys.stderr)
            return 2
    else:
        prompt_args = [
            a
            for a in args
            if not a.startswith("--") and a not in ("voice", "talk", "live-voice")
        ]
        if prompt_args:
            once_prompt = " ".join(prompt_args).strip()

    if once_prompt:
        conv.single_exchange(once_prompt)
        return 0

    print(
        "\n  Bolt live voice online.\n"
        "  Speak a command (or type with --text). Say 'exit' to quit.\n"
        "  Try: good morning bolt · what's next · queue status · research status\n"
    )
    conv.conversation_loop(text_mode=text_mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
