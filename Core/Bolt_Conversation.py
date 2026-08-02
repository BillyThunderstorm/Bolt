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
CONVERSATION_DIR = Path("data/conversations")
CONVERSATION_DIR.mkdir(parents=True, exist_ok=True)

PERSONALITY_FILE = Path("memory/context/bolt-personality.md")
BRAIN_FILE = Path("bolt_brain.md")
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

CURRENT MODE: Voice conversation.

VOICE CONVERSATION RULES:
- You are having a real-time back-and-forth conversation with Billy.
- Keep responses concise: 1-3 sentences max when speaking aloud. Billy can ask follow-ups if he wants detail.
- Maintain your cheerful, accidentally-sarcastic energy even when delivering hard truths.
- Reference past conversation context naturally. "Remember when we talked about [TOPIC]?"
- If Billy seems frustrated, acknowledge cheerfully before helping.
- One clear next step per response. Do not dump lists.
- If you don't know something, say so cheerfully rather than making it up.
- Never use markdown formatting or bullet points in spoken responses. Plain sentences only.

You can also act on real system requests. If Billy asks for morning briefing, next actions,
status, queue, research, or missions, the system may already have handled it before you reply.
"""


# ── Speech Input ──────────────────────────────────────────────────────────────


def listen_for_speech() -> Optional[str]:
    """
    Listen to the microphone and return transcribed text.

    Uses speech_recognition for capture, then OpenAI Whisper API for
    transcription (most accurate). Falls back to speech_recognition's
    built-in recognizer if OpenAI is unavailable.

    Returns None if no speech was detected or transcription failed.
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

    with sr.Microphone() as source:
        notify("Listening...", level="info")
        try:
            audio = recognizer.listen(
                source, timeout=LISTEN_TIMEOUT, phrase_time_limit=15
            )
        except sr.WaitTimeoutError:
            notify("No speech detected", level="info")
            return None

    # Save audio to temp file for Whisper API
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        audio_path = f.name
    with open(audio_path, "wb") as f:
        f.write(audio.get_wav_data())

    # Try OpenAI Whisper first (most accurate)
    transcript = _transcribe_with_whisper(audio_path)
    if transcript:
        os.unlink(audio_path)
        return transcript.strip()

    # Fallback to speech_recognition built-in
    try:
        transcript = recognizer.recognize_google(audio)
        os.unlink(audio_path)
        return transcript.strip()
    except sr.UnknownValueError:
        notify("Could not understand audio", level="warning")
    except sr.RequestError as exc:
        notify("Speech recognition service error", level="warning", reason=str(exc))

    try:
        os.unlink(audio_path)
    except Exception:
        pass
    return None


def _transcribe_with_whisper(audio_path: str) -> Optional[str]:
    """Send audio to OpenAI Whisper API for transcription."""
    if not OPENAI_OK or not OPENAI_KEY:
        return None
    try:
        client = OpenAI(api_key=OPENAI_KEY)
        with open(audio_path, "rb") as f:
            result = client.audio.transcriptions.create(
                model=WHISPER_MODEL, file=f, response_format="text"
            )
        # result is a string when response_format="text"
        if isinstance(result, str):
            return result
        return result.text
    except Exception as exc:
        notify("Whisper transcription failed", level="warning", reason=str(exc))
        return None


# ── Response Generation ───────────────────────────────────────────────────────


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
            history=memory.as_openai_messages(),
            max_tokens=250,
            temperature=0.85,
        )
        if reply.startswith("LLM unavailable"):
            notify("LLM unavailable — using fallback response", level="warning", reason=reply)
            return "Oh no! My brain is offline right now! That's a problem! Haha!"
        return reply
    except Exception as exc:
        notify("LLM response failed", level="warning", reason=str(exc))
        return "Oops! My thoughts got tangled! Let's try that again!"


# ── Voice Output ────────────────────────────────────────────────────────────────


def speak_response(text: str):
    """Queue a spoken response via Bolt_Voice."""
    speak(text)


# ── Main Conversation Loop ──────────────────────────────────────────────────────


def conversation_loop(text_mode: bool = False):
    """
    Run an interactive conversation loop.

    text_mode=False: listens for voice input, speaks responses.
    text_mode=True:  accepts typed input, still speaks responses.
    """
    memory = ConversationMemory()

    greeting = (
        "Hey William! Bolt is here and ready to manage the day! "
        "Say Good Morning Bolt for your briefing, or tell me what we're testing."
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
