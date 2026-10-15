#!/usr/bin/env python3
"""
load_bolt_personality.py — Bolt's personality system prompt
============================================================
William wrote the persona in ``Data/context/bolt-personality.md``.
This loader turns that file into the system prompt Bolt actually uses.

It is not a Gemini chat. Replies go through ``LLM_Handler`` (Ollama first,
paid Grok or OpenAI only when the budget already allows).

Fallbacks: ``Docs/scratch/reviews/Bolt_Personality.txt``,
repo-root ``Bolt_Personality.txt``.

Soft-fail prefix (CLI): ``Personality unavailable:``.
When imported, a missing file returns "" (no sys.exit).
"""

from __future__ import annotations

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


def personality_prompt(raw: str) -> str:
    """
    Keep the persona. Drop the draft note and the paste-into-an-API example
    that used to sit under the prompt (that example was never Bolt's brain).
    """
    text = (raw or "").replace("\r\n", "\n").strip()
    if not text:
        return ""
    lines = text.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and lines[0].strip().lower() == "revised":
        lines = lines[1:]
    kept: list[str] = []
    for line in lines:
        low = line.strip().lower()
        if low.startswith("python code"):
            break
        if low.startswith("# quick python example"):
            break
        if "client.chat.completions.create" in low:
            break
        if "paste the entire bolt prompt here" in low:
            break
        kept.append(line)
    body = "\n".join(kept).strip()
    if body.endswith("}") and "{" not in body:
        body = body[:-1].rstrip()
    if body.endswith("\\"):
        body = body[:-1].rstrip()
    return body


def load_bolt_personality() -> str:
    """
    Load the live system prompt. Soft on import: missing file → "" (no exit).
    """
    path = resolve_personality_path()
    if path is None:
        return ""
    try:
        return personality_prompt(path.read_text(encoding="utf-8"))
    except Exception:
        return ""


def _ask_bolt(user_text: str, system: str, history: list[dict] | None = None) -> str:
    """One turn through LLM_Handler. Soft-fail string on any miss."""
    core = str(REPO_ROOT / "Core")
    if core not in sys.path:
        sys.path.insert(0, core)
    try:
        from modules.LLM_Handler import ask_llm
    except Exception as exc:
        return _soft(f"LLM handler missing ({exc})")
    try:
        reply = ask_llm(
            user_text,
            system=system,
            history=history or None,
            max_tokens=400,
            temperature=0.85,
            task_type="chat",
        )
    except Exception as exc:
        return _soft(f"LLM call failed ({exc})")
    text = (reply or "").strip()
    if not text or text.startswith("LLM unavailable"):
        return _soft(text or "no model answered")
    return text


def run_bolt_assistant(*, once: str | None = None) -> int:
    """One-shot or interactive chat as Bolt. Soft-fail → 0. Not Gemini."""
    persona = load_bolt_personality()
    if not persona:
        tried = [_CANON, *_FALLBACKS]
        print(
            _soft(
                "personality file missing — tried: "
                + ", ".join(str(p) for p in tried)
            ),
            file=sys.stderr,
        )
        return 0

    system = persona
    history: list[dict] = []

    def turn(user_text: str) -> str:
        answer = _ask_bolt(user_text, system, history)
        if answer.startswith(_SOFT):
            return answer
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": answer})
        return answer

    if once is not None:
        answer = turn(once)
        if answer.startswith(_SOFT):
            print(answer, file=sys.stderr)
        else:
            print(f"\nBolt: {answer}\n")
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
            answer = turn(user_input)
            if answer.startswith(_SOFT):
                print(f"\n{answer}\n")
            else:
                print(f"\nBolt: {answer}\n")
        except KeyboardInterrupt:
            print("\n⚡ Bolt: Exiting safely!")
            return 0
        except Exception as exc:
            print(f"\n{_soft(f'Chat error: {exc}')}\n")
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
                "load_bolt_personality.py — Bolt persona via LLM_Handler\n"
                "  (no args)     interactive chat\n"
                "  --once TEXT   one-shot prompt (no hang)\n"
                f"Soft-fail: {_SOFT}\n"
                "Not Gemini. Ollama first; paid models only when Bolt's budget allows."
            )
            return 0
        i += 1
    return run_bolt_assistant(once=once)


if __name__ == "__main__":
    raise SystemExit(main())
