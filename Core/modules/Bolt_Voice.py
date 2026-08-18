#!/usr/bin/env python3
"""
modules/Bolt_Voice.py — Bolt's spoken voice (TTS)
==================================================
Bolt speaks out loud for key stream moments — highlights, raids,
subs — so Billy never misses something important even when he's
deep in a game.

macOS `say` and free edge-tts are both available. Pick the path with
Bolt_TTS_PROVIDER in .env:

  macos / say / siri  — use macOS `say` first (Siri Voice 3 = "Voice 3")
  edge / auto         — edge-tts first, then `say`

Voice options (set Bolt_VOICE for macOS `say`):
  Voice 3            — Siri Voice 3 (current pick; `say -v ?`)
  Nathan (Enhanced)  — clear US male
  Samantha           — natural female

edge-tts voices (set Bolt_EDGE_VOICE; used when provider is edge/auto):
  en-US-AndrewNeural — warm US male
  en-US-BrianNeural  — casual US male

To list voices:
  say -v ?
  edge-tts --list-voices

Optional paid upgrade:
  ELEVENLABS_API_KEY + ELEVENLABS_VOICE_ID for character TTS

Volume / speed:
  Bolt_VOICE_RATE  — macOS words per minute (default: 190)
  Bolt_EDGE_RATE   — edge-tts rate e.g. +12%
  Bolt_VOICE_MUTE  — set to "true" to silence TTS
"""

import os
import shutil
import subprocess
import threading
import queue
import asyncio
import tempfile
import time
from typing import Optional

try:
    from dotenv import load_dotenv
    from pathlib import Path

    _repo_env = Path(__file__).resolve().parents[2] / ".env"
    if _repo_env.is_file():
        load_dotenv(_repo_env)
    else:
        load_dotenv()
except ImportError:
    pass

try:
    from modules.notifier import notify
except ImportError:

    def notify(msg, level="info", reason=None):
        print(f"  {msg}")


# ── Config ─────────────────────────────────────────────────────────────────────

# macOS `say` voice — "Voice 3" is Siri Voice 3 on current macOS
VOICE = os.getenv("Bolt_VOICE") or os.getenv("BOLT_VOICE") or "Voice 3"
RATE = int(os.getenv("Bolt_VOICE_RATE") or os.getenv("BOLT_VOICE_RATE") or "190")
MUTED = (
    os.getenv("Bolt_VOICE_MUTE") or os.getenv("BOLT_VOICE_MUTE") or "false"
).lower() == "true"
TTS_PROVIDER = (
    os.getenv("Bolt_TTS_PROVIDER") or os.getenv("BOLT_TTS_PROVIDER") or "macos"
).strip().lower()

# edge-tts primary free path — Ana = Cartoon/Cute (high-energy cheerful)
# List: edge-tts --list-voices
EDGE_TTS_VOICE = (
    os.getenv("Bolt_EDGE_VOICE")
    or os.getenv("BOLT_EDGE_VOICE")
    or "en-US-AndrewNeural"
)
EDGE_TTS_RATE = os.getenv("Bolt_EDGE_RATE") or os.getenv("BOLT_EDGE_RATE") or "+15%"
EDGE_TTS_PITCH = os.getenv("Bolt_EDGE_PITCH") or os.getenv("BOLT_EDGE_PITCH") or "+5Hz"

# ElevenLabs optional (only if key AND voice id set)
ELEVENLABS_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "")


# ── What Bolt says for each event type ────────────────────────────────────────
#
# These are written to sound like Bolt talking TO Billy during the stream,
# not to the audience. Heard through headphones, not over stream audio.
# (If you want Bolt heard by viewers, route your mic — ask Billy.)

VOICE_LINES = {
    "startup": "All systems online, William. Bolt is ready when you are.",
    "highlight": "Highlight sequence detected. Archiving the moment.",
    "highlight_3": "That is the third highlight of the session. Confidence in your performance is increasing.",
    "sub": "New subscriber confirmed. {name} has joined the channel.",
    "resub": "{name} has returned for month {months}. Loyalty noted.",
    "raid": "{raider} has initiated a raid. {count} incoming viewers. Standby.",
    "raid_small": "{raider} has arrived with reinforcements. Welcome to the channel.",
    "bits": "Contribution received from {name}. {amount} bits. Acknowledged.",
    "going_live": "Stream is active. O B S is connected. I am monitoring.",
    "peak_alert": "William — optimal posting window is now open. Your clips are standing by for approval.",
    "morning": "Good morning, William. Loading your creator briefing.",
    "error": "Alert. A system error has occurred. Terminal review recommended.",
    "shutdown": "Signing off. It was a good session, William.",
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
    _worker_thread = threading.Thread(
        target=_speech_worker, name="BoltVoice", daemon=True
    )
    _worker_thread.start()


def _speak_now(text: str):
    """
    The actual TTS call.

    Bolt_TTS_PROVIDER:
      macos / say / siri — macOS `say` first (Siri Voice 3)
      edge / auto        — edge-tts first, then `say`
    ElevenLabs only if both key and voice id are set, after the primary path fails.
    """
    if MUTED:
        return

    prefer_macos = TTS_PROVIDER in ("macos", "say", "siri")

    if prefer_macos:
        if _try_macos_say(text):
            return
        if _try_edge_tts(text):
            return
        if ELEVENLABS_KEY and ELEVENLABS_VOICE_ID:
            _try_elevenlabs(text)
        return

    if _try_edge_tts(text):
        return
    if ELEVENLABS_KEY and ELEVENLABS_VOICE_ID and _try_elevenlabs(text):
        return
    _try_macos_say(text)


def _try_edge_tts(text: str) -> bool:
    """
    Speak using Microsoft Edge TTS via the edge-tts Python package.

    Why edge-tts? It uses the same neural voices as Microsoft Edge's
    read-aloud feature — they sound like real people, not a robot.
    It's completely free, no API key, just needs an internet connection.

    Install: pip3 install edge-tts --break-system-packages
    List voices: edge-tts --list-voices (in Terminal)

    Returns True if successful, False if it should fall back to `say`.
    """
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        return False  # not installed, skip silently

    try:

        async def _generate_audio(tmp_path: str):
            # pitch: e.g. +5Hz for a slightly brighter "cartoon" lift
            kwargs = {"rate": EDGE_TTS_RATE}
            if EDGE_TTS_PITCH:
                kwargs["pitch"] = EDGE_TTS_PITCH
            communicate = edge_tts.Communicate(text, EDGE_TTS_VOICE, **kwargs)
            await communicate.save(tmp_path)

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmp_path = f.name

        # edge-tts is async — run it in a fresh event loop from this thread
        asyncio.run(_generate_audio(tmp_path))

        # Play the audio file using macOS afplay (built-in, no install needed)
        subprocess.run(["afplay", tmp_path], check=True, capture_output=True)
        os.unlink(tmp_path)
        return True

    except Exception:
        # If anything goes wrong (no internet, bad voice name, etc.) fall back quietly
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        return False


def macos_say(text: str, *, wait: bool = True) -> bool:
    """Speak with Siri Voice 3 (`Bolt_VOICE`, default 'Voice 3').

    Always pass `-v` so alerts never fall back to Samantha/Alex/Damon.
    """
    if not (text or "").strip() or MUTED:
        return False
    try:
        subprocess.run(
            ["say", "-v", VOICE, "-r", str(RATE), text],
            check=True,
            capture_output=True,
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def _try_macos_say(text: str) -> bool:
    """
    Speak using macOS built-in TTS.

    The `say` command is part of macOS. It's offline, free, and works
    with no setup. The -v flag picks the voice, -r sets words per minute.

    Returns True if successful.
    """
    if macos_say(text):
        return True
    if not shutil.which("say"):
        notify(
            "TTS unavailable — `say` command not found",
            level="warning",
            reason="Bolt's voice requires macOS. On Windows/Linux, set ELEVENLABS_API_KEY "
            "in .env as an alternative.",
        )
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
        url = (
            f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}/stream"
        )
        headers = {"xi-api-key": ELEVENLABS_KEY, "Content-Type": "application/json"}
        body = {
            "text": text,
            "model_id": "eleven_turbo_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
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


def wait_for_speech(timeout: Optional[float] = None) -> None:
    """Block until every queued speak() has finished playing.

    CLI entry points (briefing, morning, one-shot scripts) must call this
    before process exit — the speech worker is a daemon thread, so an early
    exit kills audio mid-queue (or before it starts).
    """
    if MUTED:
        return
    _start_worker()
    if timeout is None:
        _speech_queue.join()
        return
    # queue.Queue.join has no timeout; poll unfinished_tasks instead.
    deadline = time.time() + max(0.0, timeout)
    while _speech_queue.unfinished_tasks > 0:
        if time.time() >= deadline:
            break
        time.sleep(0.05)


def speak(text: str, *, wait: bool = False, timeout: Optional[float] = None):
    """
    Queue a message for Bolt to speak aloud.

    By default non-blocking (returns immediately; voice plays in background)
    so live stream event handlers stay responsive.

    Pass wait=True for CLI / briefing paths that exit right after speaking —
    otherwise the daemon worker is killed and you hear nothing.

    Usage:
        from modules.Bolt_Voice import speak
        speak("Highlight detected.")                 # async (live bot)
        speak("Good morning briefing…", wait=True)   # sync (CLI)
    """
    if not text:
        return
    if MUTED:
        return
    _start_worker()
    _speech_queue.put(str(text))
    if wait:
        wait_for_speech(timeout=timeout)


def speak_enabled(*, force: bool = False) -> bool:
    """True when CLI/result auto-speak should run.

    On when any of:
      - force=True
      - BOLT_SPEAK / BOLT_SPEAK_CLI is 1/true/yes/on
      - ``--speak`` appears in sys.argv
    Off when muted (Bolt_VOICE_MUTE) or BOLT_SPEAK is 0/false/no/off.
    """
    if MUTED:
        return False
    if force:
        return True
    import sys

    flag = (os.getenv("BOLT_SPEAK") or os.getenv("BOLT_SPEAK_CLI") or "").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return False
    if flag in ("1", "true", "yes", "on"):
        return True
    if "--speak" in sys.argv:
        return True
    # Default: auto-speak high-value CLI status results (can disable with BOLT_SPEAK=0)
    default = (os.getenv("BOLT_SPEAK_DEFAULT") or "1").strip().lower()
    return default in ("1", "true", "yes", "on")


def speak_result(text: str, *, force: bool = False, max_chars: int = 420) -> None:
    """Speak a short summary of a CLI/terminal result when auto-speak is on.

    Strips markdown noise and truncates so TTS stays listenable.
    Silent no-op when muted or speak is disabled.
    """
    if not speak_enabled(force=force):
        return
    if not text:
        return
    # Collapse whitespace / light markdown for speech
    cleaned = str(text)
    for ch in ("#", "*", "`", "|"):
        cleaned = cleaned.replace(ch, " ")
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > max_chars:
        cleaned = cleaned[: max_chars - 1].rsplit(" ", 1)[0] + "…"
    speak(cleaned)


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
    speak("Hey William, Bolt voice is working.")
    _speech_queue.join()  # wait for queue to drain


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    try:
        import edge_tts as _et

        edge_available = True
    except ImportError:
        edge_available = False

    print(f"\n  🤖  Bolt Voice — TTS Test")
    print(f"  Provider:  {TTS_PROVIDER}")
    print(f"  macOS say: {VOICE} @ {RATE} wpm")
    print(
        f"  edge-tts:  {'✓ ' + EDGE_TTS_VOICE + ' @ ' + EDGE_TTS_RATE if edge_available else '✗ not installed (pip install edge-tts)'}"
    )
    print(f"  pitch:     {EDGE_TTS_PITCH or 'default'}")
    print(f"  Muted:     {MUTED}")
    print(f"  Available: {is_available()}")
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
        print("    • Change voice:  add Bolt_VOICE='Voice 3' to .env  (Siri Voice 3)")
        print("    • Use macOS:     add Bolt_TTS_PROVIDER=macos to .env")
        print("    • Change speed:  add Bolt_VOICE_RATE=160 to .env")
        print("    • Mute Bolt:     add Bolt_VOICE_MUTE=true to .env")
        print("    • Speak custom:  python -m modules.Bolt_Voice 'your text here'")
        print("    • List events:   python -m modules.Bolt_Voice --list-events")
