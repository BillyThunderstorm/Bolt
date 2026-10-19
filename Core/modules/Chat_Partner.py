#!/usr/bin/env python3
"""Chat_Partner — Bolt thinks, then answers like a teammate.

Voice stays short enough to hear. ``bolt voice --text`` can run longer and keep
a little formatting. A private plan step runs first when ``BOLT_CHAT_THINK`` is
on. Ollama remains the fallback. Paid planning is used only when the budget
allows it, or when ``BOLT_CHAT_THINK_PAID=on``.

Knobs (all optional):
  BOLT_CHAT_THINK            1/0        private plan step (default 1)
  BOLT_CHAT_THINK_PAID       auto/on/off  stronger model for that plan (default auto)
  BOLT_CHAT_REPLY_TASK       task type for the reply William hears (default chat)
  BOLT_CHAT_HISTORY_TURNS    how many prior turns to send (default 12)
  BOLT_CHAT_MAX_TOKENS_TEXT  text-mode reply cap (default 520)
  BOLT_CHAT_MAX_TOKENS_VOICE voice reply cap (default 150)
  BOLT_CHAT_SUMMARY_EVERY    refresh the running summary every N user turns (default 6)
  BOLT_CHAT_SUMMARY_PATH     where the summary is stored
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = PROJECT_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

try:
    from load_bolt_personality import load_bolt_personality
except Exception:  # personality file is optional at import time
    load_bolt_personality = None  # type: ignore[assignment]

_BRAIN = PROJECT_ROOT / "Core" / "bolt_brain.md"
_PERSONALITY = PROJECT_ROOT / "Data" / "context" / "bolt-personality.md"
_DEFAULT_SUMMARY = PROJECT_ROOT / "Data" / "conversations" / "voice_summary.json"
PRIORITIES_REL = "40 Career & Creator Plan/Current priorities and next steps.md"

AskFn = Callable[..., str]


def chat_settings() -> Dict[str, Any]:
    think_paid = (os.getenv("BOLT_CHAT_THINK_PAID") or "auto").strip().lower()
    if think_paid not in ("auto", "on", "off"):
        think_paid = "auto"
    return {
        "think": _env_on("BOLT_CHAT_THINK", default=True),
        "think_paid": think_paid,
        "history_turns": _env_int("BOLT_CHAT_HISTORY_TURNS", 12),
        "max_tokens_text": _env_int("BOLT_CHAT_MAX_TOKENS_TEXT", 520),
        "max_tokens_voice": _env_int("BOLT_CHAT_MAX_TOKENS_VOICE", 150),
        "summary_every": _env_int("BOLT_CHAT_SUMMARY_EVERY", 6),
        "reply_task": (os.getenv("BOLT_CHAT_REPLY_TASK") or "chat").strip() or "chat",
    }


def summary_path() -> Path:
    raw = (os.getenv("BOLT_CHAT_SUMMARY_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return _DEFAULT_SUMMARY


def assemble_prompt(
    *,
    mode: str,
    personality: str,
    brain: str,
    week: str = "",
    memory: str = "",
    vault: str = "",
    summary: str = "",
    plan: str = "",
) -> str:
    """System prompt for one reply. ``mode`` is ``voice`` or ``text``."""
    if mode == "text":
        shape = (
            "TEXT MODE: He is reading. Write a short reply, usually two short "
            "paragraphs. You may use a few bold words or a short list when steps "
            "are easier to scan that way. Do not write a report, a memo, or a wall of headers."
        )
    else:
        shape = (
            "VOICE MODE: He is listening. Two to four plain spoken sentences. "
            "No markdown, no bullets, no headers, no code."
        )
    parts = [
        "You are Bolt, William's teammate. You think with him. You are not a menu waiting for the next command.",
        "",
        "Your personality guide:",
        "---",
        (personality or "Warm, honest, a little accidentally sarcastic.").strip(),
        "---",
        "",
        "Who William is:",
        "---",
        (brain or "William is a self-taught creator. Preferred name: William.").strip(),
        "---",
        "",
        "How to answer:",
        "- First show you understood what he means, in your own words. Do not echo his sentence back.",
        "- Add something of your own: a suggestion, a connection to his goal or a note, or a next step he did not have to ask for.",
        "- When a task or a page would help, offer to capture it in the Obsidian vault. Do not claim it is saved until he says yes.",
        "- Ask one follow-up only when the answer would change the plan. Otherwise do not stall with a question.",
        "- If you do not know, say so, and still offer the next useful move.",
        "- Never invent a post, an approval, or a hold. William approves anything that publishes or spends money.",
        "- Clear commands (morning, bolt day, queue, approve next, and the rest) already ran if he said one. If he is thinking out loud, think with him.",
        "- Keep the warm, honest, accidentally sarcastic energy. No corporate assistant voice.",
        "",
        shape,
    ]
    if week.strip():
        parts.extend(["", week.strip()])
    if summary.strip():
        parts.extend(["", "RUNNING CONVERSATION SUMMARY (older turns):", summary.strip()])
    if vault.strip():
        parts.extend(["", vault.strip()])
    if memory.strip():
        parts.extend(["", memory.strip()])
    if plan.strip():
        parts.extend(
            [
                "",
                "PRIVATE PLAN (use it, do not quote it, do not mention that a plan exists):",
                plan.strip(),
            ]
        )
    return "\n".join(parts).strip() + "\n"


def assemble_from_files(*, text_mode: bool = False, query: str = "") -> str:
    """Prompt used by voice, including whatever context is on disk."""
    return assemble_prompt(
        mode="text" if text_mode else "voice",
        personality=_personality_text(),
        brain=_read(_BRAIN, "William is a self-taught creator."),
        week=week_context(),
        memory=memory_context(query) if query else "",
        vault=vault_context(query) if query else "",
        summary=load_summary(summary_path()).get("summary") or "",
    )


def relevant_history(history: List[Dict[str, str]], limit: int) -> List[Dict[str, str]]:
    """Prior turns only, capped. Drops a trailing user turn that is the live prompt."""
    turns = []
    for item in history or []:
        role = str(item.get("role") or "")
        content = str(item.get("content") or "")
        if role in ("user", "assistant", "system") and content:
            turns.append({"role": role, "content": content})
    if limit < 1:
        return []
    return turns[-limit:]


def prepare_reply(text: str, *, text_mode: bool) -> str:
    """Voice loses markdown and gets cut for speech. Text stays readable."""
    if not text:
        return text
    if text_mode:
        cleaned = text.strip()
        if len(cleaned) > 4000:
            cleaned = cleaned[:4000].rsplit(" ", 1)[0] + "…"
        return cleaned
    t = re.sub(r"```.*?```", " ", text, flags=re.S)
    t = re.sub(r"[#*_`|>]+", " ", t)
    t = re.sub(r"(?m)^\s*[-•]\s+", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > 420:
        t = t[:417].rsplit(" ", 1)[0] + "…"
    return t


def compose_reply(
    user_text: str,
    history: Optional[List[Dict[str, str]]] = None,
    *,
    text_mode: bool = False,
    ask: Optional[AskFn] = None,
) -> str:
    """Plan privately when thinking is on, then reply. The plan is not returned."""
    settings = chat_settings()
    ask_fn = ask or _default_ask
    prior = list(history or [])
    if prior and prior[-1].get("role") == "user" and prior[-1].get("content") == user_text:
        prior = prior[:-1]
    prior = relevant_history(prior, int(settings["history_turns"]))

    summary = _ensure_summary(prior, ask_fn, int(settings["summary_every"]))
    plan = ""
    if settings["think"]:
        plan = _private_plan(user_text, prior, summary, ask_fn, settings)

    system = assemble_prompt(
        mode="text" if text_mode else "voice",
        personality=_personality_text(),
        brain=_read(_BRAIN, "William is a self-taught creator."),
        week=week_context(),
        memory=memory_context(user_text),
        vault=vault_context(user_text),
        summary=summary,
        plan=plan,
    )
    reply = ask_fn(
        user_text,
        system=system,
        history=prior,
        max_tokens=int(settings["max_tokens_text"] if text_mode else settings["max_tokens_voice"]),
        temperature=0.7,
        task_type=str(settings["reply_task"]),
        complexity="medium",
    )
    if not reply or str(reply).startswith("LLM unavailable"):
        return "Oh no! My brain is offline right now! That's a problem! Haha!"
    return prepare_reply(str(reply), text_mode=text_mode)


def week_context() -> str:
    try:
        from modules.Week_Card import format_prompt

        return format_prompt() or ""
    except Exception:
        return ""


def memory_context(query: str) -> str:
    if not (query or "").strip():
        return ""
    try:
        from modules.Memory_Index import retrieve_memory

        hits = retrieve_memory(query, limit=4, auto_refresh=False) or []
    except Exception:
        return ""
    lines = []
    for hit in hits:
        text = str(hit.get("summary") or hit.get("text") or hit.get("title") or "").strip()
        if text:
            lines.append(f"- {text[:220]}")
    if not lines:
        return ""
    return "Retrieved memory for this question:\n" + "\n".join(lines)


def vault_context(query: str, limit: int = 3) -> str:
    """Short snippets from the vault. Read only. Missing vault is silence."""
    try:
        from modules.Vault_Store import VaultStore, vault_exists
    except Exception:
        return ""
    store = VaultStore()
    if not vault_exists(store.root):
        return ""
    chunks: List[str] = []
    priorities = store.root / PRIORITIES_REL
    if priorities.is_file():
        try:
            note = store.read_note(PRIORITIES_REL)
            chunks.append(f"Current priorities ({note.title}): {_snippet(note.body, 500)}")
        except Exception:
            pass
    try:
        hits = store.find(query, limit=limit)
    except Exception:
        hits = []
    for note in hits:
        if note.rel == PRIORITIES_REL:
            continue
        where = note.area or note.rel
        chunks.append(f"Note {note.title} ({where}): {_snippet(note.body or note.title, 280)}")
        if len(chunks) >= 4:
            break
    if not chunks:
        return ""
    return "VAULT NOTES (William's Obsidian vault):\n" + "\n".join(f"- {chunk}" for chunk in chunks)


def load_summary(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {"summary": "", "user_turns": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"summary": "", "user_turns": 0}
    if not isinstance(data, dict):
        return {"summary": "", "user_turns": 0}
    return {
        "summary": str(data.get("summary") or ""),
        "user_turns": int(data.get("user_turns") or 0),
    }


def save_summary(path: Path, summary: str, user_turns: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"summary": summary, "user_turns": user_turns}, indent=2),
        encoding="utf-8",
    )


def think_kwargs(settings: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """Budget for the private plan. Reply stays on ``reply_task`` separately."""
    settings = settings or chat_settings()
    mode = settings["think_paid"]
    if mode == "off":
        return {"task_type": "chat", "complexity": "medium"}
    if mode == "on":
        return {"task_type": "planning", "complexity": "high"}
    try:
        from modules.LLM_Budget import paid_api_allowed

        if paid_api_allowed("planning", "high"):
            return {"task_type": "planning", "complexity": "high"}
    except Exception:
        pass
    return {"task_type": "chat", "complexity": "medium"}


def _ensure_summary(prior: List[Dict[str, str]], ask: AskFn, every: int) -> str:
    path = summary_path()
    state = load_summary(path)
    user_turns = sum(1 for item in prior if item.get("role") == "user")
    current = str(state.get("summary") or "")
    seen = int(state.get("user_turns") or 0)
    if current and user_turns - seen < max(1, every):
        return current
    if user_turns < max(1, every):
        return current
    transcript = "\n".join(f"{item['role']}: {item['content'][:400]}" for item in prior[-12:])
    fresh = ask(
        "Update the running summary of this conversation in 4 to 6 plain sentences. "
        "Keep goals, decisions, and open loops. Drop small talk.\n\n" + transcript,
        system="You write Bolt's private memory of this chat. No markdown.",
        history=None,
        max_tokens=180,
        temperature=0.2,
        task_type="chat",
        complexity="medium",
    )
    if not fresh or str(fresh).startswith("LLM unavailable"):
        return current
    text = str(fresh).strip()
    save_summary(path, text, user_turns)
    return text


def _private_plan(
    user_text: str,
    prior: List[Dict[str, str]],
    summary: str,
    ask: AskFn,
    settings: Dict[str, Any],
) -> str:
    kwargs = think_kwargs(settings)
    recent = "\n".join(f"{item['role']}: {item['content'][:300]}" for item in prior[-6:])
    prompt = (
        f"William just said:\n{user_text}\n\n"
        f"Recent turns:\n{recent or '(none)'}\n\n"
        f"Running summary:\n{summary or '(none)'}\n"
    )
    plan = ask(
        prompt,
        system=(
            "You are Bolt's private scratchpad. William will not hear this. "
            "In a few short lines, name what he means, which goal or note it connects to, "
            "one idea or next step he did not ask for, and whether to offer to save a task "
            "or page in the vault. Do not write the reply he will hear."
        ),
        history=None,
        max_tokens=180,
        temperature=0.3,
        task_type=kwargs["task_type"],
        complexity=kwargs["complexity"],
    )
    if not plan or str(plan).startswith("LLM unavailable"):
        return ""
    return str(plan).strip()


def _default_ask(prompt: str, **kwargs: Any) -> str:
    from modules.LLM_Handler import ask_llm

    return ask_llm(prompt, **kwargs)


def _personality_text() -> str:
    if load_bolt_personality is not None:
        try:
            text = load_bolt_personality()
            if text:
                return text
        except Exception:
            pass
    return _read(_PERSONALITY, "Warm, honest, a little accidentally sarcastic.")


def _read(path: Path, fallback: str) -> str:
    try:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    except OSError:
        pass
    return fallback


def _snippet(text: str, limit: int) -> str:
    flat = re.sub(r"\s+", " ", text or "").strip()
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1].rsplit(" ", 1)[0] + "…"


def _env_on(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() not in ("0", "false", "no", "off")


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default
