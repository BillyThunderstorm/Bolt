#!/usr/bin/env python3
"""
modules/Bolt_Conversation.py — Bolt's voice conversation engine
================================================================
Back-and-forth voice (or text) conversation with Billy.

What it does:
  - Listens via microphone using speech_recognition + Whisper (OpenAI) with Google fallback
  - Maintains persistent conversation history (Project Memory)
  - Routes high-value intents (morning, next, status, queue, research, mission) to real actions
  - Generates personality-driven responses via LLM_Handler (OpenAI or xAI/Grok)
  - Speaks responses aloud through Bolt_Voice (ElevenLabs primary)
  - Can be used hands-free during streams or desk work

Usage:
  PYTHONPATH=Core python3 -m Bolt_Conversation          # start voice chat loop
  PYTHONPATH=Core python3 -m Bolt_Conversation --text   # text-only mode (still speaks replies)
  PYTHONPATH=Core python3 -m Bolt_Conversation --once "What should I post today?"

Environment:
  BOLT_LLM_PROVIDER / XAI_API_KEY / OPENAI_API_KEY  — response generation
  OPENAI_API_KEY                                    — optional, for Whisper transcription only
  ELEVENLABS_API_KEY                                — optional, Bolt_Voice uses it automatically if set
"""

import os
import sys
import json
import re
import time
import tempfile
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# ── Imports ────────────────────────────────────────────────────────────────────

try:
    import speech_recognition as sr

    SPEECH_OK = True
except ImportError:
    SPEECH_OK = False

try:
    from openai import OpenAI

    OPENAI_OK = True
except ImportError:
    OPENAI_OK = False

try:
    from modules.LLM_Handler import ask_llm, get_active_provider, provider_status

    LLM_OK = True
except ImportError:
    LLM_OK = False

    def ask_llm(prompt, **kwargs):
        return "Oh no! My brain is offline right now! That's a problem! Haha!"

    def get_active_provider():
        return "unavailable"

    def provider_status():
        return {}

try:
    from modules.Intent_Router import try_handle_intent

    INTENT_OK = True
except ImportError:
    INTENT_OK = False

    def try_handle_intent(text):
        return None

try:
    from modules.Bolt_Voice import speak, say_event

    VOICE_OK = True
except ImportError:
    VOICE_OK = False

    def speak(text):
        print(f"  [VOICE] {text}")

    def say_event(event, **kw):
        pass


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


# ── Config ──────────────────────────────────────────────────────────────────────

OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")

# Resolve repo root from this file (Core/Bolt_Conversation.py → repo root).
_REPO_ROOT = Path(__file__).resolve().parent.parent
CONVERSATION_DIR = _REPO_ROOT / "Data" / "conversations"
CONVERSATION_DIR.mkdir(parents=True, exist_ok=True)

# Prefer post-reorg Data/ paths; fall back to older locations if present.
_PERSONALITY_CANDIDATES = (
    _REPO_ROOT / "Data" / "context" / "bolt-personality.md",
    _REPO_ROOT / "memory" / "context" / "bolt-personality.md",
    _REPO_ROOT / "Docs" / "scratch" / "reviews" / "Bolt_Personality.txt",
)
_BRAIN_CANDIDATES = (
    _REPO_ROOT / "Core" / "bolt_brain.md",
    _REPO_ROOT / "bolt_brain.md",
    _REPO_ROOT / "Data" / "bolt_brain.md",
)
PERSONALITY_FILE = next((p for p in _PERSONALITY_CANDIDATES if p.exists()), _PERSONALITY_CANDIDATES[0])
BRAIN_FILE = next((p for p in _BRAIN_CANDIDATES if p.exists()), _BRAIN_CANDIDATES[0])
HISTORY_FILE = CONVERSATION_DIR / "voice_history.json"

WHISPER_MODEL = os.getenv("BOLT_WHISPER_MODEL", "whisper-1")
MAX_HISTORY_TURNS = int(os.getenv("BOLT_CONVERSATION_MEMORY", "20"))
LISTEN_TIMEOUT = int(os.getenv("BOLT_LISTEN_TIMEOUT", "10"))
PHRASE_TIMEOUT = int(os.getenv("BOLT_PHRASE_TIMEOUT", "5"))


# ── Conversation Memory ───────────────────────────────────────────────────────


class ConversationMemory:
    """
    Persistent conversation storage.

    Keeps a rolling window of the last N turns so Bolt remembers context
    across restarts. Stored as JSON in data/conversations/.
    """

    def __init__(
        self, filepath: Path = HISTORY_FILE, max_turns: int = MAX_HISTORY_TURNS
    ):
        self.filepath = filepath
        self.max_turns = max_turns
        self.history: List[Dict[str, str]] = []
        self._load()

    def _load(self):
        if self.filepath.exists():
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self.history = json.load(f)
            except Exception as exc:
                notify(
                    "Conversation history load failed", level="warning", reason=str(exc)
                )
                self.history = []
        else:
            self.history = []

    def _save(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            notify("Conversation history save failed", level="warning", reason=str(exc))

    def add(self, role: str, content: str):
        """Add a turn and trim to max length."""
        self.history.append(
            {"role": role, "content": content, "timestamp": datetime.now().isoformat()}
        )
        if len(self.history) > self.max_turns:
            self.history = self.history[-self.max_turns :]
        self._save()

    def as_openai_messages(self) -> List[Dict[str, str]]:
        """Return history formatted for chat completions."""
        return [{"role": h["role"], "content": h["content"]} for h in self.history]

    def last_summary(self, n: int = 3) -> str:
        """Return a plain-text summary of the last N turns for quick context."""
        lines = []
        for h in self.history[-n:]:
            prefix = "Billy" if h["role"] == "user" else "Bolt"
            lines.append(f"{prefix}: {h['content'][:120]}")
        return "\n".join(lines)

    def clear(self):
        self.history = []
        self._save()


# ── Personality & Brain Loaders ────────────────────────────────────────────────


def _load_file(path: Path, fallback: str = "") -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return fallback


def build_system_prompt() -> str:
    """
    Assemble the full system prompt from personality guide + brain + identity.
    """
    personality = _load_file(PERSONALITY_FILE, "Use cheerful, innocent energy.")
    brain = _load_file(BRAIN_FILE, "Billy is a content creator.")

    return f"""You are Bolt — Billy's AI teammate and voice companion.

Your personality guide:
---
{personality}
---

You work for Billy, a self-taught content creator. Here's his profile:
---
{brain}
---

CURRENT MODE: Voice conversation (spoken aloud via TTS).

VOICE CONVERSATION RULES (STRICT):
- Keep responses to 1-3 short plain sentences. Billy is listening, not reading a doc.
- NEVER use markdown: no # headers, no **bold**, no bullet lists, no tables, no code fences.
- NEVER invent fake project plans, dictionaries, or multi-section reports.
- If Billy asks to run a Bolt command (bolt day, queue decide, etc.), say one sentence
  directing him — real commands are handled by the intent system before you reply.
- Maintain cheerful, accidentally-sarcastic energy even with hard truths.
- One clear next step. If you don't know, say so cheerfully.
- Plain spoken English only.

Real system phrases (morning, bolt day, queue, approve next, storage, budget) may already
be handled before you see them. Do not re-invent those.
"""


# ── Speech Input ──────────────────────────────────────────────────────────────

# After OpenAI Whisper hits quota/billing errors, stop trying for this process.
_WHISPER_DISABLED_SESSION = False


def _stt_provider() -> str:
    """
    BOLT_STT_PROVIDER:
      google  — free Google Web Speech (default; no OpenAI / Whisper spend)
      whisper — OpenAI Whisper API (PAID — not recommended)
      auto    — same as google unless BOLT_USE_WHISPER=true

    Whisper is off unless you explicitly opt in. OpenAI credits are separate
    from SuperGrok and xAI API.
    """
    # Hard off unless explicitly enabled — avoids surprise OpenAI bills
    if os.getenv("BOLT_USE_WHISPER", "false").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return "google"
    raw = (os.getenv("BOLT_STT_PROVIDER") or "google").strip().lower()
    if raw in ("google", "whisper", "auto"):
        return raw
    return "google"


def listen_for_speech() -> Optional[str]:
    """
    Listen to the microphone and return transcribed text.

    Default is free Google STT so a dead OpenAI balance does not break voice.
    Set BOLT_STT_PROVIDER=whisper only if you have OpenAI credits for Whisper.
    """
    if not SPEECH_OK:
        notify(
            "Speech recognition not available",
            level="warning",
            reason="Install SpeechRecognition: pip3 install SpeechRecognition",
        )
        return None

    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = PHRASE_TIMEOUT

    # Slightly more sensitive in noisy rooms; Google free STT is picky
    recognizer.energy_threshold = int(os.getenv("BOLT_MIC_ENERGY", "300"))
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = float(os.getenv("BOLT_PHRASE_TIMEOUT", str(PHRASE_TIMEOUT)))

    with sr.Microphone() as source:
        notify("Listening...", level="info")
        try:
            # Longer ambient sample = fewer false "no speech" / empty phrases
            try:
                recognizer.adjust_for_ambient_noise(source, duration=0.8)
            except Exception:
                pass
            listen_timeout = int(os.getenv("BOLT_LISTEN_TIMEOUT", str(LISTEN_TIMEOUT)))
            phrase_limit = int(os.getenv("BOLT_PHRASE_LIMIT", "10"))
            audio = recognizer.listen(
                source, timeout=listen_timeout, phrase_time_limit=phrase_limit
            )
        except sr.WaitTimeoutError:
            notify("No speech detected", level="info")
            return None

    provider = _stt_provider()
    # Only paid Whisper when both provider says whisper AND explicit opt-in
    use_whisper = provider == "whisper" and os.getenv(
        "BOLT_USE_WHISPER", "false"
    ).strip().lower() in ("1", "true", "yes", "on")

    audio_path = None
    if use_whisper:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            audio_path = f.name
        with open(audio_path, "wb") as f:
            f.write(audio.get_wav_data())
        transcript = _transcribe_with_whisper(audio_path)
        if transcript:
            try:
                os.unlink(audio_path)
            except Exception:
                pass
            return transcript.strip()

    # Free path (default): Google Web Speech via speech_recognition
    try:
        transcript = recognizer.recognize_google(audio)
        if audio_path:
            try:
                os.unlink(audio_path)
            except Exception:
                pass
        text = (transcript or "").strip()
        if text:
            return text
    except sr.UnknownValueError:
        notify(
            "Could not understand audio",
            level="warning",
            reason="Try speaking closer / clearer, or use bolt voice --text",
        )
    except sr.RequestError as exc:
        notify("Speech recognition service error", level="warning", reason=str(exc))

    if audio_path:
        try:
            os.unlink(audio_path)
        except Exception:
            pass
    return None


def _transcribe_with_whisper(audio_path: str) -> Optional[str]:
    """Send audio to OpenAI Whisper API (paid). Disabled after quota errors."""
    global _WHISPER_DISABLED_SESSION
    if _WHISPER_DISABLED_SESSION:
        return None
    if not OPENAI_OK or not OPENAI_KEY:
        return None
    try:
        client = OpenAI(api_key=OPENAI_KEY)
        with open(audio_path, "rb") as f:
            result = client.audio.transcriptions.create(
                model=WHISPER_MODEL, file=f, response_format="text"
            )
        if isinstance(result, str):
            return result
        return result.text
    except Exception as exc:
        err = str(exc)
        # Don't spam 429 every listen loop — stop Whisper for this session
        if any(
            x in err.lower()
            for x in (
                "429",
                "insufficient_quota",
                "credit_balance",
                "quota",
                "billing",
            )
        ):
            _WHISPER_DISABLED_SESSION = True
            notify(
                "Whisper disabled for this session (OpenAI out of credits)",
                level="warning",
                reason="Using free Google speech instead. Set BOLT_STT_PROVIDER=google or add OpenAI credits.",
            )
        else:
            notify("Whisper transcription failed", level="warning", reason=err[:160])
        return None


# ── Response Generation ───────────────────────────────────────────────────────


def _strip_for_speech(text: str) -> str:
    """Remove markdown / shout-case walls so TTS stays listenable."""
    if not text:
        return text
    t = text
    # Drop fenced code blocks
    t = re.sub(r"```.*?```", " ", t, flags=re.S)
    # Headers / bullets / bold / tables
    t = re.sub(r"[#*_`|>]+", " ", t)
    t = re.sub(r"(?m)^\s*[-•]\s+", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    # Cap length for spoken delivery
    if len(t) > 420:
        t = t[:417].rsplit(" ", 1)[0] + "…"
    return t


def generate_response(user_text: str, memory: ConversationMemory) -> str:
    """
    Generate a response.

    1. Try Intent_Router for high-value system actions (morning, next, status...).
    2. Otherwise use LLM_Handler (Grok/OpenAI) with personality + history.
    """
    # Intent path first — real actions beat pure chat when the user clearly wants one
    if INTENT_OK:
        handled = try_handle_intent(user_text)
        if handled is not None:
            return handled

    system_prompt = build_system_prompt()

    try:
        reply = ask_llm(
            user_text,
            system=system_prompt,
            # Don't feed a long polluted history into every free-form turn
            history=memory.as_openai_messages()[-6:],
            max_tokens=120,
            temperature=0.85,
            task_type="chat",
            complexity="medium",
        )
        if reply.startswith("LLM unavailable"):
            notify("LLM unavailable — using fallback response", level="warning", reason=reply)
            return "Oh no! My brain is offline right now! That's a problem! Haha!"
        return _strip_for_speech(reply)
    except Exception as exc:
        notify("LLM response failed", level="warning", reason=str(exc))
        return "Oops! My thoughts got tangled! Let's try that again!"


# ── Voice Output ────────────────────────────────────────────────────────────────


def speak_response(text: str):
    """Queue a spoken response via Bolt_Voice."""
    speak(_strip_for_speech(text) if text else text)


# ── Main Conversation Loop ──────────────────────────────────────────────────────


def conversation_loop(text_mode: bool = False):
    """
    Run an interactive conversation loop.

    text_mode=False: listens for voice input, speaks responses.
    text_mode=True:  accepts typed input, still speaks responses.
    """
    memory = ConversationMemory()

    greeting = (
        "Hey William! Bolt is listening. "
        "Say bolt day for your kickoff, queue decide for clips, "
        "or approve next to greenlight a post. "
        "For full video review, use bolt queue decide in the terminal."
    )
    print(f"\n  🤖  {greeting}\n")
    speak_response(greeting)

    try:
        while True:
            if text_mode:
                try:
                    user_input = input("  You: ").strip()
                except (EOFError, KeyboardInterrupt):
                    break
                if not user_input:
                    continue
                if user_input.lower() in ("exit", "quit", "bye", "goodbye"):
                    break
            else:
                user_input = listen_for_speech()
                if not user_input:
                    continue
                print(f"  You: {user_input}")

            memory.add("user", user_input)

            # Detect if morning path already spoke so we don't double-TTS
            already_spoke = False
            try:
                from modules.Content_Manager import is_good_morning_phrase

                if is_good_morning_phrase(user_input):
                    already_spoke = True
            except Exception:
                pass

            reply = generate_response(user_input, memory)
            memory.add("assistant", reply)

            print(f"  Bolt: {reply}\n")
            if not already_spoke:
                speak_response(reply)

    except KeyboardInterrupt:
        pass

    goodbye = "Signing off! It was a good session, Billy!"
    print(f"\n  🤖  {goodbye}\n")
    speak_response(goodbye)
    notify(
        "Conversation saved",
        level="success",
        reason=f"{len(memory.history)} turns in history",
    )


def single_exchange(prompt: str):
    """Process one prompt and exit — useful for scripts and shortcuts."""
    memory = ConversationMemory()
    memory.add("user", prompt)

    already_spoke = False
    try:
        from modules.Content_Manager import is_good_morning_phrase

        if is_good_morning_phrase(prompt):
            already_spoke = True
    except Exception:
        pass

    reply = generate_response(prompt, memory)
    memory.add("assistant", reply)
    print(reply)
    if not already_spoke:
        speak_response(reply)


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]

    if "--clear" in args:
        ConversationMemory().clear()
        notify("Conversation history cleared", level="success")
        sys.exit(0)

    if "--status" in args:
        mem = ConversationMemory()
        status = provider_status()
        print(f"\n  🤖  Bolt Conversation Status")
        print(f"  History turns: {len(mem.history)}")
        print(f"  History file:  {HISTORY_FILE}")
        print(f"  Speech input:  {'✓' if SPEECH_OK else '✗'}")
        print(f"  Voice output:  {'✓' if VOICE_OK else '✗'}")
        print(f"  Intent router: {'✓' if INTENT_OK else '✗'}")
        print(f"  LLM provider:  {get_active_provider()}")
        print(f"  LLM status:    {status}")
        print(f"\n  Recent context:\n{mem.last_summary()}\n")
        sys.exit(0)

    text_mode = "--text" in args

    # Remove flags to check for a one-off prompt
    prompt_args = [a for a in args if not a.startswith("--")]
    if prompt_args:
        single_exchange(" ".join(prompt_args))
        sys.exit(0)

    conversation_loop(text_mode=text_mode)
