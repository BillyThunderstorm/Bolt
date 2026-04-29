#!/usr/bin/env python3
"""
modules/Brain_Controller.py — Bolt's central decision engine (Phase 4)
=======================================================================
This is Bolt's "prefrontal cortex." Instead of event-handling logic
scattered across bot.py, launch.py, and individual modules, ALL decisions
flow through here.

Why this matters:
  Right now if you want to change how Bolt reacts to a highlight —
  you'd have to dig through bot.py, Bolt_Voice.py, and Bolt_Chat.py.
  With Brain_Controller, you change it in ONE place.

How it works:
  1. Something happens (highlight detected, raid incoming, clip ready)
  2. That event gets sent to Brain_Controller.decide()
  3. Brain_Controller evaluates it against the current state + config
  4. It returns a list of actions to take (speak, chat, notify, queue, etc.)
  5. The caller executes those actions

Tier system (how good is this moment?):
  Tier 1 — Excellent (score 80+):  full pipeline, vertical clip, Discord alert
  Tier 2 — Good (score 50–79):     clip + queue, no special treatment
  Tier 3 — Below threshold (<50):  archive only, no queue

Usage:
    from modules.Brain_Controller import BrainController

    brain = BrainController(config, creator_brain)

    actions = brain.decide("highlight", score=85, timestamp=12.4)
    for action in actions:
        brain.execute(action)

    # Or shortcut — decide + execute in one call:
    brain.handle("raid", raider="BigStreamer", count=42)
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional

try:
    from modules.notifier import notify
except ImportError:
    def notify(msg, level="info", reason=None):
        print(f"  [{level.upper()}] {msg}")


# ── Tiers ──────────────────────────────────────────────────────────────────────

TIER_1_THRESHOLD = 80   # excellent — pull out all stops
TIER_2_THRESHOLD = 60   # good — process and queue
# Below TIER_2_THRESHOLD = archive only, skip the queue


# ── BrainController ────────────────────────────────────────────────────────────

class BrainController:
    """
    Bolt's central decision engine.

    All events in Bolt flow through here. Brain_Controller decides
    what to do and why — then hands off execution to the right modules.
    """

    def __init__(self, config: dict, creator_brain: str = ""):
        self.config        = config
        self.creator_brain = creator_brain
        self.state         = self._load_state()
        self._chat_bot     = None
        self._voice        = None

    # ── Wiring ────────────────────────────────────────────────────────────────

    def set_chat_bot(self, chat_bot):
        """Plug in the Twitch chat bot so Brain_Controller can send chat messages."""
        self._chat_bot = chat_bot

    def _get_voice(self):
        """Lazy-load voice module so it doesn't fail if not installed."""
        if self._voice is None:
            try:
                from modules import Bolt_Voice
                self._voice = Bolt_Voice
            except ImportError:
                pass
        return self._voice

    # ── State persistence ─────────────────────────────────────────────────────

    def _state_path(self) -> Path:
        return Path(__file__).parent.parent / "data" / "brain_state.json"

    def _load_state(self) -> dict:
        """
        Load persisted state from last session.
        This is how Brain_Controller remembers things like "how many highlights
        today" or "last raid was 2 hours ago" across runs.
        """
        try:
            with open(self._state_path()) as f:
                return json.load(f)
        except Exception:
            return {
                "highlights_today": 0,
                "clips_queued_today": 0,
                "last_session": None,
                "session_started": datetime.now().isoformat(),
            }

    def _save_state(self):
        """Persist state to disk so it survives restarts."""
        try:
            self._state_path().parent.mkdir(exist_ok=True)
            with open(self._state_path(), "w") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            notify(f"Brain state save failed: {e}", level="warning")

    # ── Core decision logic ───────────────────────────────────────────────────

    def decide(self, event: str, **data) -> list:
        """
        Given an event + data, return a list of action dicts to execute.

        This is the core of Phase 4. Everything that should happen as a
        result of an event is decided here — not scattered across modules.

        Events:
          "highlight"   — a highlight was detected in the recording
          "clip_ready"  — a clip finished processing and is ready to queue
          "raid"        — someone raided Billy's channel
          "sub"         — new subscriber
          "resub"       — returning subscriber
          "bits"        — bit donation
          "stream_start"— stream went live
          "stream_end"  — stream ended
          "peak_hour"   — it's now a peak posting window
          "error"       — something went wrong
        """
        actions = []
        now     = datetime.now().isoformat()

        if event == "highlight":
            score = data.get("score", 0)
            tier  = self._score_to_tier(score)
            self.state["highlights_today"] = self.state.get("highlights_today", 0) + 1
            count = self.state["highlights_today"]

            if tier == 1:
                actions += [
                    {"type": "speak",   "event": "highlight"},
                    {"type": "chat",    "msg": "highlight"},
                    {"type": "notify",  "msg": f"Tier 1 highlight (score {score}) — running full pipeline", "level": "success"},
                    {"type": "pipeline","mode": "full"},
                ]
            elif tier == 2:
                actions += [
                    {"type": "speak",   "event": "highlight"},
                    {"type": "notify",  "msg": f"Tier 2 highlight (score {score}) — clipping and queuing", "level": "info"},
                    {"type": "pipeline","mode": "clip_only"},
                ]
                # Special callout on 3rd highlight of the session
                if count == 3:
                    actions.append({"type": "speak", "event": "highlight_3"})
            else:
                actions.append({
                    "type": "notify",
                    "msg": f"Highlight below threshold (score {score}) — archiving",
                    "level": "info",
                    "reason": "Score is below min_post_score. Archived but not queued."
                })

        elif event == "clip_ready":
            score = data.get("score", 0)
            path  = data.get("path", "")
            tier  = self._score_to_tier(score)
            self.state["clips_queued_today"] = self.state.get("clips_queued_today", 0) + 1

            if tier >= 2:
                actions += [
                    {"type": "queue",   "path": path, "score": score},
                    {"type": "notify",  "msg": f"Clip queued: {Path(path).name} [score {score:.0f}]", "level": "success"},
                ]
            else:
                actions.append({"type": "archive", "path": path, "reason": "Below posting threshold"})

        elif event == "raid":
            raider = data.get("raider", "someone")
            count  = data.get("count", 0)
            actions += [
                {"type": "speak",  "event": "raid" if count >= 10 else "raid_small",
                 "kwargs": {"raider": raider, "count": count}},
                {"type": "chat",   "msg": "raid", "kwargs": {"raider": raider, "count": count}},
                {"type": "notify", "msg": f"Raid from {raider} — {count} viewers", "level": "success"},
            ]

        elif event == "sub":
            name = data.get("name", "someone")
            actions += [
                {"type": "speak",  "event": "sub", "kwargs": {"name": name}},
                {"type": "chat",   "msg": "sub",   "kwargs": {"name": name}},
                {"type": "notify", "msg": f"New sub: {name}", "level": "success"},
            ]

        elif event == "resub":
            name   = data.get("name", "someone")
            months = data.get("months", 1)
            actions += [
                {"type": "speak",  "event": "resub", "kwargs": {"name": name, "months": months}},
                {"type": "notify", "msg": f"Resub: {name} (month {months})", "level": "success"},
            ]

        elif event == "bits":
            name   = data.get("name", "someone")
            amount = data.get("amount", 0)
            actions += [
                {"type": "speak",  "event": "bits", "kwargs": {"name": name, "amount": amount}},
                {"type": "notify", "msg": f"Bits: {amount} from {name}", "level": "success"},
            ]

        elif event == "stream_start":
            actions += [
                {"type": "speak",  "event": "going_live"},
                {"type": "notify", "msg": "Stream started — Bolt is monitoring", "level": "startup"},
                {"type": "memory", "fact": f"Stream started at {now}"},
            ]

        elif event == "stream_end":
            highlights = self.state.get("highlights_today", 0)
            clips      = self.state.get("clips_queued_today", 0)
            actions += [
                {"type": "speak",  "event": "shutdown"},
                {"type": "notify", "msg": f"Stream ended — {highlights} highlights, {clips} clips queued",
                 "level": "success"},
                {"type": "memory", "fact": f"Session ended: {highlights} highlights, {clips} clips queued"},
                {"type": "reset_state"},
            ]

        elif event == "peak_hour":
            label = data.get("label", "")
            clips = data.get("clip_count", 0)
            if clips > 0:
                actions += [
                    {"type": "speak",  "event": "peak_alert"},
                    {"type": "notify", "msg": f"Peak hour ({label}) — {clips} clip(s) ready in Discord",
                     "level": "success"},
                ]

        elif event == "error":
            actions += [
                {"type": "speak",  "event": "error"},
                {"type": "notify", "msg": data.get("msg", "An error occurred"), "level": "error"},
            ]

        self._save_state()
        return actions

    def handle(self, event: str, **data):
        """
        Decide + execute in one call. Convenience shortcut.

        Usage:
            brain.handle("raid", raider="BigStreamer", count=42)
            brain.handle("highlight", score=87)
        """
        actions = self.decide(event, **data)
        for action in actions:
            self.execute(action)

    def execute(self, action: dict):
        """
        Execute a single action dict returned by decide().

        Each action has a "type" key. The rest of the keys are arguments.
        Adding a new action type is as simple as adding a new elif here.
        """
        atype = action.get("type")

        if atype == "speak":
            voice = self._get_voice()
            if voice:
                kwargs = action.get("kwargs", {})
                voice.say_event(action.get("event", ""), **kwargs)

        elif atype == "chat":
            if self._chat_bot:
                try:
                    msg_type = action.get("msg", "")
                    kwargs   = action.get("kwargs", {})
                    if msg_type == "highlight":
                        self._chat_bot.trigger_highlight()
                    elif msg_type == "raid":
                        self._chat_bot.trigger_raid(action.get("kwargs", {}).get("raider", ""), 0)
                    elif msg_type == "sub":
                        self._chat_bot.trigger_sub(kwargs.get("name", ""))
                except Exception as e:
                    notify(f"Chat action failed: {e}", level="warning")

        elif atype == "notify":
            notify(action.get("msg", ""), level=action.get("level", "info"),
                   reason=action.get("reason"))

        elif atype == "memory":
            try:
                from modules.Bolt_Memory import remember
                remember(action.get("fact", ""))
            except Exception:
                pass

        elif atype == "reset_state":
            self.state["highlights_today"]   = 0
            self.state["clips_queued_today"]  = 0
            self.state["last_session"]        = datetime.now().isoformat()
            self._save_state()

        elif atype in ("pipeline", "queue", "archive"):
            # These are handled by the caller (bot.py) — Brain_Controller just
            # signals the intent, it doesn't run the pipeline itself.
            # This keeps Brain_Controller lightweight and testable.
            pass

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _score_to_tier(self, score: float) -> int:
        """
        Convert a clip/highlight score (0-100) to a tier (1, 2, or 3).

        Tier 1 = excellent  (80+)  → full pipeline
        Tier 2 = good       (50+)  → clip + queue
        Tier 3 = below floor (<50) → archive only
        """
        min_score = self.config.get("min_post_score", TIER_2_THRESHOLD)
        if score >= TIER_1_THRESHOLD:
            return 1
        elif score >= min_score:
            return 2
        else:
            return 3

    def session_summary(self) -> str:
        """Return a human-readable summary of the current session."""
        return (
            f"Session started: {self.state.get('session_started', 'unknown')}\n"
            f"Highlights today: {self.state.get('highlights_today', 0)}\n"
            f"Clips queued: {self.state.get('clips_queued_today', 0)}"
        )


# ── CLI — test from terminal ───────────────────────────────────────────────────

if __name__ == "__main__":
    import sys, json
    from pathlib import Path

    # Load real config if available
    try:
        with open(Path(__file__).parent.parent / "config.json") as f:
            config = json.load(f)
    except Exception:
        config = {"min_post_score": 50}

    brain = BrainController(config)

    print("\n  🤖  Brain_Controller — Event Test")
    print(f"  Tier 1 threshold: {TIER_1_THRESHOLD}+")
    print(f"  Tier 2 threshold: {config.get('min_post_score', TIER_2_THRESHOLD)}+")
    print()

    # Simulate some events
    test_events = [
        ("highlight", {"score": 92}),
        ("highlight", {"score": 60}),
        ("highlight", {"score": 30}),
        ("raid",      {"raider": "BigStreamer", "count": 42}),
        ("sub",       {"name": "CoolViewer123"}),
    ]

    for event, data in test_events:
        print(f"  Event: {event} {data}")
        actions = brain.decide(event, **data)
        for a in actions:
            print(f"    → {a['type']}: {a.get('msg') or a.get('event') or a.get('fact') or ''}")
        print()

    print(f"  {brain.session_summary()}")
    print()
