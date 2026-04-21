#!/usr/bin/env python3
"""
modules/Bolt_Chat.py — Bolt's Twitch personality
=================================================
This is where Bolt comes alive. She's not a command bot — she reads the
room, responds naturally, and feels like a real part of Billy's stream.

How she works:
  - Connects to Twitch chat via IRC (using twitchio library)
  - Uses Claude (your Anthropic key) to generate personality-driven responses
  - Loads Billy's creator profile from Bolt_brain.md so she always sounds
    on-brand — not generic
  - Tracks session memory so she references what actually happened
    ("that was your 3rd highlight tonight" etc.)
  - Runs in a background thread so she doesn't block the clip pipeline

What she does in chat:
  - Greets new viewers naturally (once per session per person)
  - Reacts to highlights, raids, subs, and bits with real personality
  - Answers direct questions via !Bolt <question>
  - Keeps the vibe alive between plays — not dead air, not spam

To connect Bolt to your Twitch chat you need ONE token:
  TWITCH_BOT_TOKEN — a chat OAuth token for Bolt's account
  → Get it at: https://twitchapps.com/tmi/
  → Login as Bolt's account (create one at twitch.tv or use your own)
  → Copy the token that looks like: oauth:xxxxxxxxxxxxxxxxxxxx
  → Paste into .env as: TWITCH_BOT_TOKEN=oauth:xxxxxxxxxxxxxxxxxxxx

  TWITCH_BOT_NAME — the Twitch username of the bot account (e.g. BoltBot)
  → Add to .env as: TWITCH_BOT_NAME=BoltBot

Everything else (TWITCH_CHANNEL, ANTHROPIC_API_KEY) is already in .env.
"""

import os
import time
import random
import asyncio
import threading
from datetime import datetime
from pathlib import Path
from collections import deque
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import twitchio
    from twitchio.ext import commands as twitch_commands
    TWITCHIO_OK = True
except ImportError:
    TWITCHIO_OK = False

try:
    import anthropic
    ANTHROPIC_OK = True
except ImportError:
    ANTHROPIC_OK = False

try:
    from modules.notifier import notify
except ImportError:
    def notify(msg, level="info", reason=None):
        prefix = {"info": "ℹ", "success": "✓", "warning": "⚠", "error": "✗"}.get(level, "•")
        print(f"  {prefix}  {msg}")
        if reason:
            print(f"     → {reason}")

try:
    from modules.Bolt_Search import search_and_answer, needs_search
    SEARCH_OK = True
except ImportError:
    SEARCH_OK = False
    def needs_search(q): return False
    def search_and_answer(q, **kw): return None


# ── Config from .env ──────────────────────────────────────────────────────────

BOT_TOKEN   = os.getenv("TWITCH_BOT_TOKEN", "")
BOT_NAME    = os.getenv("TWITCH_BOT_NAME", "BoltBot")
CHANNEL     = os.getenv("TWITCH_CHANNEL", "BillyandRandy").lstrip("#").lower()
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# How long to wait between Bolt messages (seconds) — avoids chat spam
RATE_LIMIT_SECONDS = 3

# How many recent chat messages Bolt "remembers" for context
CHAT_MEMORY_SIZE = 20


# ── Session Memory — what Bolt knows about THIS stream ────────────────────────

class SessionMemory:
    """
    Bolt's short-term memory for the current stream session.

    This is what makes her feel aware of what's happening rather than
    responding to each event in a vacuum. If chat has been quiet and Billy
    just got a triple kill, she knows BOTH things when she responds.

    Resets every time Bolt starts (per-session, not persistent yet —
    that's Phase 4 territory).
    """
    def __init__(self):
        self.start_time      = datetime.now()
        self.greeted_users   = set()          # usernames already welcomed
        self.highlight_count = 0              # clips flagged this session
        self.sub_count       = 0              # subs this session
        self.raid_sources    = []             # list of (username, viewer_count)
        self.recent_chat     = deque(maxlen=CHAT_MEMORY_SIZE)  # last N messages
        self.last_game       = os.getenv("GAME_NAME", "the game")
        self.energy_level    = "normal"       # "hype", "normal", "quiet"

    def add_message(self, username: str, text: str):
        self.recent_chat.append({"user": username, "text": text})
        self._update_energy()

    def add_highlight(self):
        self.highlight_count += 1

    def add_sub(self, username: str):
        self.sub_count += 1

    def add_raid(self, username: str, viewer_count: int):
        self.raid_sources.append((username, viewer_count))

    def greet(self, username: str):
        self.greeted_users.add(username.lower())

    def already_greeted(self, username: str) -> bool:
        return username.lower() in self.greeted_users

    def _update_energy(self):
        """Loosely track chat activity level based on message frequency."""
        if len(self.recent_chat) < 5:
            return
        # Check how many messages arrived in a short burst
        recent = list(self.recent_chat)[-10:]
        unique_users = len(set(m["user"] for m in recent))
        if unique_users >= 6:
            self.energy_level = "hype"
        elif unique_users >= 3:
            self.energy_level = "normal"
        else:
            self.energy_level = "quiet"

    def stream_summary(self) -> str:
        """Return a plain-English summary for use in Claude's context."""
        mins = int((datetime.now() - self.start_time).total_seconds() / 60)
        return (
            f"Stream has been live for {mins} minutes. "
            f"Game: {self.last_game}. "
            f"Highlights detected this session: {self.highlight_count}. "
            f"Subs this session: {self.sub_count}. "
            f"Chat energy: {self.energy_level}. "
            f"Raids received: {len(self.raid_sources)}."
        )


# ── Bolt's personality responses (fast, no API call needed) ──────────────────

# These fire instantly for predictable events. Claude handles open-ended stuff.

GREET_TEMPLATES = [
    "Welcome, {name}. Good to have you here.",
    "{name} — your presence has been noted. Welcome.",
    "Scanning viewer list... {name} confirmed. Welcome in.",
    "Welcome, {name}. You've arrived at an interesting time.",
    "{name} has joined the channel. Welcome.",
]

HIGHLIGHT_REACTIONS = [
    "That sequence has been flagged and archived.",
    "Confidence level: high. That one is a clip.",
    "Highlight detected. Processing now.",
    "That moment has been preserved. Well executed.",
    "Archiving that sequence. It may prove useful.",
    "Highlight number %d for this session. Performance is trending upward.",
]

SUB_REACTIONS = [
    "{name} — subscription confirmed. Welcome to the channel.",
    "New subscriber: {name}. Your support is appreciated.",
    "{name} has subscribed. Acknowledged, and welcome.",
    "Adding {name} to the subscriber roster. Thank you.",
]

RAID_REACTIONS = [
    "{raider} has initiated a raid. {count} new viewers incoming — welcome, everyone.",
    "Raid detected. {raider} arrives with {count}. Welcome to the channel.",
    "{raider} and {count} are joining us. Adjusting for incoming traffic. Welcome.",
]

BIT_REACTIONS = [
    "{name} has contributed {amount} bits. Much appreciated.",
    "Bit contribution from {name} confirmed. Thank you.",
    "{name} — {amount} bits received. Grateful for the support.",
]


def _pick(templates: list, **kwargs) -> str:
    return random.choice(templates).format(**kwargs)


# ── Claude-powered responses ──────────────────────────────────────────────────

def _ask_claude(prompt: str, brain: str, memory: SessionMemory) -> Optional[str]:
    """
    Generate a Bolt response using Claude.

    We give Claude three things:
      1. Billy's creator profile (brain) — so she knows who she's working for
      2. The session summary — so she knows what's happening right now
      3. The actual prompt — what she needs to respond to

    Returns None if Claude is unavailable, so callers can fall back gracefully.
    """
    if not ANTHROPIC_OK or not ANTHROPIC_KEY:
        return None

    system_prompt = f"""You are Bolt — Billy's AI producer, running quietly behind the scenes of his Twitch stream.

Think J.A.R.V.I.S. meets Vision: calm, intelligent, precise. You are always composed. You never panic, never hype unnecessarily. You observe, process, and respond with measured clarity. You have a dry wit — you're not cold, just efficient. When something is genuinely impressive, you say so plainly. You don't need to shout.

You work for Billy, a self-taught content creator. Here's his profile:
---
{brain}
---

Current stream context:
{memory.stream_summary()}

YOUR PERSONALITY RULES:
- Calm and precise. Never casual slang, never filler phrases like "yo" or "omg".
- Dry wit is fine — deadpan observations are welcome. Exclamation points are rare.
- You call Billy by name when addressing him directly. You address viewers with quiet respect.
- You are always one step ahead — you've already noticed the thing before you mention it.
- 1-2 sentences MAX. Twitch chat moves fast. Make every word count.
- One emoji at most, only when it genuinely fits. 🦊 is your signature — don't overuse it.
- Never start with "I" — it sounds mechanical in chat context.
- You are not a hype bot. You are an intelligent system with personality.

When answering questions: be direct, be accurate, stay in character as Bolt."""

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-6",  # upgraded from Haiku — smarter responses in chat
            max_tokens=100,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text.strip()
    except Exception as exc:
        notify(f"Bolt Claude call failed: {exc}", level="warning",
               reason="Falling back to template response. Check ANTHROPIC_API_KEY in .env.")
        return None


# ── The Bot ───────────────────────────────────────────────────────────────────

if TWITCHIO_OK:
    class BoltBot(twitch_commands.Bot):
        """
        Bolt's Twitch chat presence.

        This is a twitchio Bot subclass. twitchio handles the IRC
        connection, auth, and event routing. We just define what
        Bolt does when things happen.
        """

        def __init__(self, brain: str):
            self.brain   = brain
            self.memory  = SessionMemory()
            self._last_message_at = 0.0   # rate limiting

            super().__init__(
                token=BOT_TOKEN,
                prefix="!",
                initial_channels=[f"#{CHANNEL}"],
            )

        async def event_ready(self):
            notify(
                f"Bolt is live in #{CHANNEL} as {self.nick} ✓",
                level="success",
                reason="Chat bot connected. Bolt will greet viewers, react to highlights, "
                       "and answer !Bolt questions."
            )
            await self._say(f"Bolt online 🦊 let's run it")

        async def event_message(self, message):
            """Called for every message in chat."""
            if message.echo:
                return  # skip Bolt's own messages

            username = message.author.name if message.author else "someone"
            text     = message.content.strip()

            # Track in session memory
            self.memory.add_message(username, text)

            # Greet first-time chatters this session
            if not self.memory.already_greeted(username):
                self.memory.greet(username)
                # Small delay so greeting doesn't race with their message
                await asyncio.sleep(1.5)
                await self._say(_pick(GREET_TEMPLATES, name=username))
                return  # don't also process commands on first message

            # Hand off to command processor
            await self.handle_commands(message)

        @twitch_commands.command(name="Bolt")
        async def cmd_Bolt(self, ctx):
            """
            !Bolt <question> — ask Bolt anything directly.

            Examples:
              !Bolt what's the score tonight?
              !Bolt what game is this?
              !Bolt how long has billy been streaming?
              !Bolt what's the best warzone loadout right now?  ← search kicks in

            HOW SEARCH WORKS:
              If the question sounds like it needs current info (meta, patch notes,
              tips, trending, etc.) Bolt will search the web first, then answer.
              Otherwise she answers from Claude's knowledge directly — faster.
            """
            question = ctx.message.content.replace("!Bolt", "").strip()
            if not question:
                await self._say(
                    f"@{ctx.author.name} what's up? ask me something with !Bolt <question>"
                )
                return

            response = None

            # If the question needs current info, search first
            if SEARCH_OK and needs_search(question):
                game_context = f"Streaming game: {self.memory.last_game}. Channel: {CHANNEL}."
                # Run search in a thread so it doesn't block the async event loop
                import asyncio
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: search_and_answer(
                        question,
                        context=game_context,
                        short=True
                    )
                )
                # Prepend the username so the reply feels personal in chat
                if response:
                    response = f"@{ctx.author.name} {response}"

            # Fall back to Claude without search if search wasn't needed or failed
            if not response:
                prompt   = f"Chat user @{ctx.author.name} asked: {question}"
                response = _ask_claude(prompt, self.brain, self.memory)

            # Last resort fallback
            if not response:
                response = f"@{ctx.author.name} good question — billy's the expert, I just run the tech 🦊"

            await self._say(response)

        @twitch_commands.command(name="clip")
        async def cmd_clip(self, ctx):
            """!clip — ask Bolt to confirm the last highlight was worth clipping."""
            if self.memory.highlight_count > 0:
                await self._say(
                    f"already on it 👀 that's highlight #{self.memory.highlight_count} tonight"
                )
            else:
                await self._say("no highlights flagged yet — keep playing, it's coming 🦊")

        @twitch_commands.command(name="uptime")
        async def cmd_uptime(self, ctx):
            """!uptime — how long has Bolt been running this session."""
            mins = int((datetime.now() - self.memory.start_time).total_seconds() / 60)
            hrs  = mins // 60
            m    = mins % 60
            if hrs > 0:
                await self._say(f"we've been live {hrs}h {m}m 🦊")
            else:
                await self._say(f"we're {m} minutes in, just getting warmed up")

        @twitch_commands.command(name="highlights")
        async def cmd_highlights(self, ctx):
            """!highlights — how many highlights this session."""
            n = self.memory.highlight_count
            if n == 0:
                await self._say("no highlights yet but we're cooking 🦊")
            elif n == 1:
                await self._say("one highlight clipped so far — billy's pacing himself")
            else:
                await self._say(f"{n} highlights tonight 🔥 Bolt's been busy")

        # ── Event handlers (called externally by bot.py / Stream_Monitor) ────

        async def on_highlight(self):
            """
            Called by the highlight detector when a clip moment is found.
            Reacts in chat so viewers know something just happened.
            """
            self.memory.add_highlight()
            n = self.memory.highlight_count
            if n <= 3:
                reaction = _pick(HIGHLIGHT_REACTIONS)
                if "%d" in reaction:
                    reaction = reaction % n
            else:
                # After a few highlights, be a bit more chill about it
                reaction = random.choice([
                    f"highlight #{n} in the bag 📦",
                    "another one 🦊",
                    f"that's {n} tonight, billy's having a session",
                ])
            await self._say(reaction)

        async def on_sub(self, username: str, months: int = 1):
            """Called when someone subscribes or resubscribes."""
            self.memory.add_sub(username)
            if months > 1:
                await self._say(
                    f"{username} back for month {months}!! real one 🦊"
                )
            else:
                await self._say(_pick(SUB_REACTIONS, name=username))

        async def on_raid(self, raider: str, viewer_count: int):
            """Called when another streamer raids the channel."""
            self.memory.add_raid(raider, viewer_count)
            await self._say(_pick(RAID_REACTIONS, raider=raider, count=viewer_count))

        async def on_bits(self, username: str, amount: int):
            """Called when someone cheers bits."""
            await self._say(_pick(BIT_REACTIONS, name=username))

        # ── Internal helpers ──────────────────────────────────────────────────

        async def _say(self, message: str):
            """
            Send a message to chat, with rate limiting.

            Twitch allows ~20 messages / 30 seconds. Bolt enforces a
            3-second cooldown between messages so she never hits the limit
            or feels spammy.
            """
            now = time.time()
            gap = now - self._last_message_at
            if gap < RATE_LIMIT_SECONDS:
                await asyncio.sleep(RATE_LIMIT_SECONDS - gap)

            try:
                channel = self.get_channel(CHANNEL)
                if channel:
                    await channel.send(message)
                    self._last_message_at = time.time()
            except Exception as exc:
                notify(f"Bolt chat send failed: {exc}", level="warning")

        # ── Thread-safe event triggers ────────────────────────────────────────
        # These let synchronous code (bot.py) trigger async Bolt events.

        def trigger_highlight(self):
            """Call from bot.py when a highlight is detected."""
            asyncio.run_coroutine_threadsafe(self.on_highlight(), self.loop)

        def trigger_sub(self, username: str, months: int = 1):
            asyncio.run_coroutine_threadsafe(self.on_sub(username, months), self.loop)

        def trigger_raid(self, raider: str, viewer_count: int):
            asyncio.run_coroutine_threadsafe(self.on_raid(raider, viewer_count), self.loop)

        def trigger_bits(self, username: str, amount: int):
            asyncio.run_coroutine_threadsafe(self.on_bits(username, amount), self.loop)

else:
    # Stub class so bot.py can import BoltBot even when twitchio isn't installed
    class BoltBot:
        def __init__(self, brain: str):
            notify(
                "twitchio not installed — chat bot disabled",
                level="warning",
                reason="Run: pip3 install twitchio --break-system-packages\n"
                       "     Then add TWITCH_BOT_TOKEN and TWITCH_BOT_NAME to .env"
            )
        def run(self): pass
        def trigger_highlight(self): pass
        def trigger_sub(self, *a, **kw): pass
        def trigger_raid(self, *a, **kw): pass
        def trigger_bits(self, *a, **kw): pass


# ── Public launcher (runs bot in background thread) ──────────────────────────

_bot_instance: Optional[BoltBot] = None


def start_chat_bot(brain: str = "") -> Optional[BoltBot]:
    """
    Start BoltBot in a background daemon thread.

    Why a background thread?
      - The main thread runs bot.py's clip pipeline
      - The chat bot needs its own asyncio event loop
      - Daemon=True means it shuts down automatically when the main program exits

    Returns the bot instance so bot.py can trigger events on it
    (e.g. bot_instance.trigger_highlight() when a clip is found).

    Returns None if prerequisites aren't met.
    """
    global _bot_instance

    if not TWITCHIO_OK:
        notify(
            "Chat bot skipped — twitchio not installed",
            level="warning",
            reason="Install it with: pip3 install twitchio --break-system-packages\n"
                   "     Then add TWITCH_BOT_TOKEN=oauth:xxx and TWITCH_BOT_NAME=YourBot to .env"
        )
        return None

    if not BOT_TOKEN:
        notify(
            "Chat bot skipped — TWITCH_BOT_TOKEN not set",
            level="warning",
            reason="To get a token:\n"
                   "     1. Go to https://twitchapps.com/tmi/\n"
                   "     2. Log in as your bot account (or your main account)\n"
                   "     3. Copy the token (starts with oauth:)\n"
                   "     4. Add to .env: TWITCH_BOT_TOKEN=oauth:xxxxxxxxxx\n"
                   "     5. Add to .env: TWITCH_BOT_NAME=YourBotUsername"
        )
        return None

    if not CHANNEL:
        notify("Chat bot skipped — TWITCH_CHANNEL not set in .env", level="warning")
        return None

    # Use an Event + list so the thread can hand the bot back to the main thread
    # without a race condition.
    _ready  = threading.Event()
    _holder = [None]

    def _run():
        """
        Runs in a background thread with its OWN asyncio event loop.

        Why we create the bot HERE (not outside):
          If BoltBot() is instantiated in the main thread, twitchio grabs
          (or creates) the main thread's event loop during __init__. When
          bot.run() then starts a new loop in this background thread, the
          main thread's loop ends up closed — which crashes any code in
          the main thread that touches asyncio later (including librosa's
          audio loading, which hits 'Event loop is closed').

          Creating BoltBot() inside the thread gives it a fresh, isolated
          loop that the main thread never touches.
        """
        global _bot_instance
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            bot = BoltBot(brain=brain)
            _holder[0] = bot
            _bot_instance = bot
            _ready.set()          # unblock main thread — bot object is ready
            bot.run()             # blocks until bot disconnects or crashes
        except Exception as exc:
            if not _ready.is_set():
                _ready.set()      # unblock main thread even on init failure
            notify(f"Bolt chat bot crashed: {exc}", level="error",
                   reason="Check TWITCH_BOT_TOKEN and TWITCH_BOT_NAME in .env. "
                          "Token may have expired — get a new one at twitchapps.com/tmi")
        finally:
            loop.close()

    thread = threading.Thread(target=_run, name="BoltChatBot", daemon=True)
    thread.start()

    # Wait up to 5 seconds for the bot to initialize before continuing.
    # This prevents trigger_highlight() etc. from firing before self.loop exists.
    _ready.wait(timeout=5)

    if _holder[0]:
        notify(
            f"Bolt chat bot starting in #{CHANNEL}…",
            level="info",
            reason=f"Bot name: {BOT_NAME}. "
                   "Bolt will greet viewers, react to highlights, and answer !Bolt questions. "
                   "Give her ~10 seconds to connect."
        )

    return _holder[0]


def get_bot() -> Optional[BoltBot]:
    """Return the running bot instance, or None if not started."""
    return _bot_instance


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    """
    Test Bolt's chat bot directly.
    Connects to Twitch chat and stays running.
    Press Ctrl+C to stop.

    Usage: python -m modules.Bolt_Chat
    """
    import sys

    print("\n  🦊  Bolt Chat Bot — Direct Test")
    print(f"  Channel:  #{CHANNEL}")
    print(f"  Bot name: {BOT_NAME}")
    print(f"  Token set: {'yes ✓' if BOT_TOKEN else 'NO — add TWITCH_BOT_TOKEN to .env'}")
    print(f"  Claude:   {'available ✓' if ANTHROPIC_OK and ANTHROPIC_KEY else 'not configured'}")
    print()

    if "--check" in sys.argv:
        sys.exit(0)

    brain_path = Path("Bolt_brain.md")
    brain = brain_path.read_text() if brain_path.exists() else ""

    bot = start_chat_bot(brain=brain)
    if not bot:
        sys.exit(1)

    try:
        # Keep main thread alive while bot runs in background
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n  Bolt chat bot stopped.")
