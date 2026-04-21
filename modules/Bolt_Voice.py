#!/usr/bin/env python3
"""
modules/Bolt_Voice.py — Bolt's spoken voice (TTS)
==================================================
Bolt speaks out loud for key stream moments — highlights, raids,
subs — so Billy never misses something important even when he's
deep in a game.

Uses macOS built-in text-to-speech (the `say` command) by default.
No API key needed. No extra install. It just works on a Mac.

Voice options (set Bolt_VOICE in .env):
  Alex      — natural male voice
  Samantha  — default, natural female voice
  Victoria  — clear, slightly formal
  Karen     — Australian accent (fun option)

To list all voices on your Mac, run in Terminal:
  say -v ?

Upgrade path (optional):
  Set ELEVENLABS_API_KEY in .env to unlock a more natural voice.
  ElevenLabs free tier gives ~10,000 chars/month which is plenty
  for streaming alerts.

Volume / speed:
  Bolt_VOICE_RATE  — words per minute (default: 175, try 160-200)
  Bolt_VOICE_MUTE  — set to "true" to silence TTS without removing it
"""

import os
import subprocess
import threading
import queue
import time
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
        print(f"  {msg}")


# ── Config ─────────────────────────────────────────────────────────────────────

VOICE      = os.getenv("Bolt_VOICE", "Nathan (Enhanced)")
RATE       = int(os.getenv("Bolt_VOICE_RATE", "175"))   # words per minute
MUTED      = os.getenv("Bolt_VOICE_MUTE", "false").lower() == "true"

ELEVENLABS_KEY     = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "")  # from ElevenLabs dashboard


# ── What Bolt says for each event type ────────────────────────────────────────
#
# These are written to sound like Bolt talking TO Billy during the stream,
# not to the audience. Heard through headphones, not over stream audio.
# (If you want Bolt heard by viewers, route your mic — ask Billy.)

VOICE_LINES = {
    "startup":     "All systems online, Billy. Bolt is ready when you are.",
    "highlight":   "Highlight sequence detected. Archiving the moment.",
    "highlight_3": "That is the third highlight of the session. Confidence in your performance is increasing.",
    "sub":         "New subscriber confirmed. {name} has joined the channel.",
    "resub":       "{name} has returned for month {months}. Loyalty noted.",
    "raid":        "{raider} has initiated a raid. {count} incoming viewers. Standby.",
    "raid_small":  "{raider} has arrived with reinforcements. Welcome to the channel.",
    "bits":        "Contribution received from {name}. {amount} bits. Acknowledged.",
    "going_live":  "Stream is active. O B S is connected. I am monitoring.",
    "peak_alert":  "Billy — optimal posting window is now open. Your clips are standing by in Discord.",
    "error":       "Alert. A system error has occurred. Terminal review recommended.",
    "shutdown":    "Signing off. It was a good session, Billy.",
}


# ── TTS Queue (so voices don't overlap) ───────────────────────────────────────

_speech_queue: queue.Queue = queue.Queue()
_worker_thread: Optional[threading.Thread] = None


def _speech_worker():
    """
    Background thread that speaks queued messages one at a time.

    Why a queue? Because if a raid and a highlight happen at the same
    second, we want Bolt to say both — not overlap them into noise.
    Messages play in order, back-to-back.
    """
    while True:
        text = _speech_queue.get()
        if text is None:
            break  # sentinel to stop the worker
        _speak_now(text)
        _speech_queue.task_done()


def _start_worker():
    global _worker_thread
    if _worker_thread and _worker_thread.is_alive():
        return
    _worker_thread = threading.Thread(target=_speech_worker, name="BoltVoice", daemon=True)
    _worker_thread.start()


def _speak_now(text: str):
    """
    The actual TTS call. Tries ElevenLabs first if configured,
    falls back to macOS say command.
    """
    if MUTED:
        return

    # ElevenLabs (higher quality, requires API key + internet)
    if ELEVENLABS_KEY and ELEVENLABS_VOICE_ID:
        if _try_elevenlabs(text):
            return

    # macOS say command (free, offline, works immediately)
    _try_macos_say(text)


def _try_macos_say(text: str) -> bool:
    """
    Speak using macOS built-in TTS.

    The `say` command is part of macOS. It's offline, free, and works
    with no setup. The -v flag picks the voice, -r sets words per minute.

    Returns True if successful.
    """
    try:
        subprocess.run(
            ["say", "-v", VOICE, "-r", str(RATE), text],
            check=True,
            capture_output=True
        )
        return True
    except FileNotFoundError:
        # `say` not available (non-macOS system)
        notify(
            "TTS unavailable — `say` command not found",
            level="warning",
            reason="Bolt's voice requires macOS. On Windows/Linux, set ELEVENLABS_API_KEY "
                   "in .env as an alternative."
        )
        return False
    except subprocess.CalledProcessError:
        return False


def _try_elevenlabs(text: str) -> bool:
    """
    Speak using ElevenLabs API (optional upgrade).

    Much more natural voice than macOS TTS. Uses their streaming API
    to play audio directly. Requires:
      ELEVENLABS_API_KEY  — from elevenlabs.io
      ELEVENLABS_VOICE_ID — the voice ID from your ElevenLabs dashboard

    Returns True if successful, False if it should fall back to `say`.
    """
    try:
        import requests
    except ImportError:
        return False

    try:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}/stream"
        headers = {
            "xi-api-key": ELEVENLABS_KEY,
            "Content-Type": "application/json"
        }
        body = {
            "text": text,
            "model_id": "eleven_turbo_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
        }
        resp = requests.post(url, json=body, headers=headers, stream=True, timeout=10)
        if resp.status_code != 200:
            return False

        # Write to temp file and play via afplay (macOS)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            for chunk in resp.iter_content(chunk_size=1024):
                f.write(chunk)
            tmp_path = f.name

        subprocess.run(["afplay", tmp_path], check=True, capture_output=True)
        os.unlink(tmp_path)
        return True

    except Exception:
        return False


# ── Public API ─────────────────────────────────────────────────────────────────

def speak(text: str):
    """
    Queue a message for Bolt to speak aloud.
    Non-blocking — returns immediately. Voice plays in background.

    Usage anywhere in Bolt's codebase:
        from modules.Bolt_Voice import speak
        speak("Highlight detected. That one's a clip.")
    """
    _start_worker()
    _speech_queue.put(text)


def say_event(event: str, **kwargs):
    """
    Speak a predefined event line by name, with optional substitutions.

    Examples:
        say_event("startup")
        say_event("sub", name="CoolViewer123")
        say_event("raid", raider="BigStreamer", count=42)
        say_event("highlight")

    Falls back silently if the event key isn't in VOICE_LINES.
    """
    template = VOICE_LINES.get(event)
    if not template:
        return
    try:
        text = template.format(**kwargs)
    except KeyError:
        text = template  # use as-is if substitution fails
    speak(text)


def is_available() -> bool:
    """Check if TTS is available on this system."""
    if MUTED:
        return False
    if ELEVENLABS_KEY:
        return True
    # Check if macOS `say` command exists
    result = subprocess.run(["which", "say"], capture_output=True)
    return result.returncode == 0


def test_voice():
    """Speak a test line and wait for it to finish. Used at startup to confirm TTS works."""
    speak("Hey Billy, Bolt voice is working.")
    _speech_queue.join()  # wait for queue to drain


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    print(f"\n  🦊  Bolt Voice — TTS Test")
    print(f"  Voice:     {VOICE}")
    print(f"  Rate:      {RATE} wpm")
    print(f"  Muted:     {MUTED}")
    print(f"  Available: {is_available()}")
    print(f"  ElevenLabs: {'configured ✓' if ELEVENLABS_KEY else 'not set (using macOS say)'}")
    print()

    if "--list-events" in sys.argv:
        print("  Available event lines:")
        for k, v in VOICE_LINES.items():
            print(f"    {k:15} → {v}")
        print()
        sys.exit(0)

    test_text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None

    if test_text and not test_text.startswith("--"):
        print(f"  Speaking: '{test_text}'")
        speak(test_text)
        _speech_queue.join()
    else:
        print("  Running voice test…")
        test_voice()
        print("  Done. If you heard Bolt, TTS is working ✓")
        print()
        print("  Tips:")
        print("    • Change voice:  add Bolt_VOICE=Alex to .env")
        print("    • Change speed:  add Bolt_VOICE_RATE=160 to .env")
        print("    • Mute Bolt:     add Bolt_VOICE_MUTE=true to .env")
        print("    • Speak custom:  python -m modules.Bolt_Voice 'your text here'")
        print("    • List events:   python -m modules.Bolt_Voice --list-events")
    
