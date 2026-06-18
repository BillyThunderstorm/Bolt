#!/usr/bin/env python3
"""
modules/Brain_Controller.py — Bolt compatibility decision controller
======================================================================
This module keeps the older BrainController API alive, but it now shares
the same tier vocabulary and memory path as the live Bolt pipeline.

The current runtime uses Think_Learn_Decide as the canonical action layer.
Brain_Controller exists for legacy callers and standalone testing, but it
no longer carries a separate tier system or conflicting thresholds.

Shared tier semantics:
  - discard  : below quality_tiers.discard_below
  - mid      : at or above discard_below, but below min_post_score
  - queue    : at or above min_post_score
  - alert    : at or above quality_tiers.queue_at

Compatibility note:
  The live bot path should call Think_Learn_Decide directly. This controller
  mirrors those thresholds and can still emit local speak/chat/notify actions
  when used directly.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .notifier import notify
except ImportError:

    def notify(msg, level="info", reason=None):
        print(f"  [{level.upper()}] {msg}")


try:
    from .Think_Learn_Decide import ThinkLearnDecideEngine, sys_stdin_interactive
except ImportError:
    ThinkLearnDecideEngine = None

    def sys_stdin_interactive() -> bool:
        return False


TIER_DISCARD = "discard"
TIER_MID = "mid"
TIER_QUEUE = "queue"


def _load_thresholds() -> tuple:
    cfg_path = Path(__file__).parent.parent / "config.json"
    try:
        with open(cfg_path, "r", encoding="utf-8") as fh:
            config = json.load(fh)
    except Exception:
        config = {}

    tiers = config.get("quality_tiers", {})
    discard_below = float(tiers.get("discard_below", 60.0))
    min_post_score = float(
        config.get("min_post_score", config.get("min_clip_score", 65.0))
    )
    queue_at = float(tiers.get("queue_at", 80.0))

    min_post_score = max(min_post_score, discard_below)
    queue_at = max(queue_at, min_post_score)
    return discard_below, min_post_score, queue_at


DISCARD_BELOW, MIN_POST_SCORE, QUEUE_AT = _load_thresholds()


class BrainController:
    """
    Legacy-compatible event controller for Bolt.

    The main job here is to keep older callers working while sharing the
    same thresholds and memory store as Think_Learn_Decide.
    """

    def __init__(self, config: dict, creator_brain: str = ""):
        self.config = config or {}
        self.creator_brain = creator_brain
        self.state = self._load_state()
        self._chat_bot = None
        self._voice = None
        self._intelligence = None

        if ThinkLearnDecideEngine is not None:
            try:
                self._intelligence = ThinkLearnDecideEngine(self.config)
            except Exception:
                self._intelligence = None

    # ── Wiring ────────────────────────────────────────────────────────────────

    def set_chat_bot(self, chat_bot):
        """Plug in the Twitch chat bot so Brain_Controller can send chat messages."""
        self._chat_bot = chat_bot

    def _get_voice(self):
        """Lazy-load voice module so it doesn't fail if not installed."""
        if self._voice is None:
            try:
                from . import Bolt_Voice

                self._voice = Bolt_Voice
            except ImportError:
                pass
        return self._voice

    def _record_event(
        self,
        source: str,
        intent: str,
        action: str,
        result: str,
        confidence: float,
        reason: str,
        feedback: Optional[str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self._intelligence:
            return
        try:
            self._intelligence.record_event(
                source=source,
                intent=intent,
                action=action,
                result=result,
                confidence=confidence,
                reason=reason,
                feedback=feedback,
                metadata=metadata or {},
            )
        except Exception:
            pass

    # ── State persistence ─────────────────────────────────────────────────────

    def _state_path(self) -> Path:
        return Path(__file__).parent.parent / "data" / "brain_state.json"

    def _load_state(self) -> dict:
        try:
            with open(self._state_path(), "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {
                "highlights_today": 0,
                "clips_queued_today": 0,
                "last_session": None,
                "session_started": datetime.now().isoformat(),
            }

    def _save_state(self):
        try:
            self._state_path().parent.mkdir(parents=True, exist_ok=True)
            with open(self._state_path(), "w", encoding="utf-8") as fh:
                json.dump(self.state, fh, indent=2)
        except Exception as exc:
            notify(f"Brain state save failed: {exc}", level="warning")

    # ── Core decision logic ───────────────────────────────────────────────────

    def decide(self, event: str, **data) -> list:
        """
        Given an event + data, return a list of action dicts to execute.

        Tiers mirror the rest of Bolt:
          - discard: below discard_below
          - mid    : between discard_below and min_post_score
          - queue  : at or above min_post_score
          - alert  : at or above queue_at
        """
        actions = []
        now = datetime.now().isoformat()

        if event == "highlight":
            score = float(data.get("score", 0))
            tier = self._score_to_tier(score)
            alert = score >= QUEUE_AT
            self.state["highlights_today"] = self.state.get("highlights_today", 0) + 1
            count = self.state["highlights_today"]

            self._record_event(
                source="brain_controller",
                intent="highlight",
                action="classify",
                result=tier,
                confidence=min(0.99, max(0.5, score / 100.0)),
                reason=f"Classified highlight with tier={tier}",
                feedback=None,
                metadata={"score": score, "tier": tier},
            )

            if tier == TIER_DISCARD:
                actions.append(
                    {
                        "type": "notify",
                        "msg": f"Highlight below floor (score {score}) — archiving",
                        "level": "info",
                        "reason": "Score is below quality_tiers.discard_below. Archived but not queued.",
                    }
                )
            elif tier == TIER_MID:
                actions.extend(
                    [
                        {
                            "type": "notify",
                            "msg": f"Mid-tier highlight (score {score}) — keeping it local",
                            "level": "info",
                        },
                        {"type": "pipeline", "mode": "clip_only"},
                    ]
                )
                if count == 3:
                    actions.append({"type": "speak", "event": "highlight_3"})
            else:
                actions.extend(
                    [
                        {"type": "speak", "event": "highlight"},
                        {
                            "type": "notify",
                            "msg": f"Queue-tier highlight (score {score}) — clipping and queuing",
                            "level": "success",
                        },
                        {"type": "pipeline", "mode": "clip_only"},
                    ]
                )
                if alert:
                    actions.append({"type": "chat", "msg": "highlight"})

        elif event == "clip_ready":
            score = float(data.get("score", 0))
            path = data.get("path", "")
            tier = self._score_to_tier(score)
            self.state["clips_queued_today"] = (
                self.state.get("clips_queued_today", 0) + 1
            )

            self._record_event(
                source="brain_controller",
                intent="clip_ready",
                action="classify",
                result=tier,
                confidence=min(0.99, max(0.5, score / 100.0)),
                reason=f"Classified clip_ready with tier={tier}",
                feedback=None,
                metadata={"score": score, "path": path, "tier": tier},
            )

            if score >= MIN_POST_SCORE:
                actions += [
                    {"type": "queue", "path": path, "score": score},
                    {
                        "type": "notify",
                        "msg": f"Clip queued: {Path(path).name} [score {score:.0f}]",
                        "level": "success",
                    },
                ]
            else:
                actions.append(
                    {"type": "archive", "path": path, "reason": "Below posting floor"}
                )

        elif event == "raid":
            raider = data.get("raider", "someone")
            count = data.get("count", 0)
            actions += [
                {
                    "type": "speak",
                    "event": "raid" if count >= 10 else "raid_small",
                    "kwargs": {"raider": raider, "count": count},
                },
                {
                    "type": "chat",
                    "msg": "raid",
                    "kwargs": {"raider": raider, "count": count},
                },
                {
                    "type": "notify",
                    "msg": f"Raid from {raider} — {count} viewers",
                    "level": "success",
                },
            ]

        elif event == "sub":
            name = data.get("name", "someone")
            actions += [
                {"type": "speak", "event": "sub", "kwargs": {"name": name}},
                {"type": "chat", "msg": "sub", "kwargs": {"name": name}},
                {"type": "notify", "msg": f"New sub: {name}", "level": "success"},
            ]

        elif event == "resub":
            name = data.get("name", "someone")
            months = data.get("months", 1)
            actions += [
                {
                    "type": "speak",
                    "event": "resub",
                    "kwargs": {"name": name, "months": months},
                },
                {
                    "type": "notify",
                    "msg": f"Resub: {name} (month {months})",
                    "level": "success",
                },
            ]

        elif event == "bits":
            name = data.get("name", "someone")
            amount = data.get("amount", 0)
            actions += [
                {
                    "type": "speak",
                    "event": "bits",
                    "kwargs": {"name": name, "amount": amount},
                },
                {
                    "type": "notify",
                    "msg": f"Bits: {amount} from {name}",
                    "level": "success",
                },
            ]

        elif event == "stream_start":
            actions += [
                {"type": "speak", "event": "going_live"},
                {
                    "type": "notify",
                    "msg": "Stream started — Bolt is monitoring",
                    "level": "startup",
                },
                {"type": "memory", "fact": f"Stream started at {now}"},
            ]

        elif event == "stream_end":
            highlights = self.state.get("highlights_today", 0)
            clips = self.state.get("clips_queued_today", 0)
            actions += [
                {"type": "speak", "event": "shutdown"},
                {
                    "type": "notify",
                    "msg": f"Stream ended — {highlights} highlights, {clips} clips queued",
                    "level": "success",
                },
                {
                    "type": "memory",
                    "fact": f"Session ended: {highlights} highlights, {clips} clips queued",
                },
                {"type": "reset_state"},
            ]

        elif event == "peak_hour":
            label = data.get("label", "")
            clips = data.get("clip_count", 0)
            if clips > 0:
                actions += [
                    {"type": "speak", "event": "peak_alert"},
                    {
                        "type": "notify",
                        "msg": f"Peak hour ({label}) — {clips} clip(s) ready in Discord",
                        "level": "success",
                    },
                ]

        elif event == "error":
            actions += [
                {"type": "speak", "event": "error"},
                {
                    "type": "notify",
                    "msg": data.get("msg", "An error occurred"),
                    "level": "error",
                },
            ]

        self._save_state()
        return actions

    def handle(self, event: str, **data):
        """Decide + execute in one call."""
        actions = self.decide(event, **data)
        for action in actions:
            self.execute(action)

    def execute(self, action: dict):
        """Execute a single action dict returned by decide()."""
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
                    kwargs = action.get("kwargs", {})
                    if msg_type == "highlight":
                        self._chat_bot.trigger_highlight()
                    elif msg_type == "raid":
                        self._chat_bot.trigger_raid(
                            kwargs.get("raider", ""), kwargs.get("count", 0)
                        )
                    elif msg_type == "sub":
                        self._chat_bot.trigger_sub(kwargs.get("name", ""))
                except Exception as exc:
                    notify(f"Chat action failed: {exc}", level="warning")

        elif atype == "notify":
            notify(
                action.get("msg", ""),
                level=action.get("level", "info"),
                reason=action.get("reason"),
            )

        elif atype == "memory":
            try:
                from .Bolt_Memory import remember

                remember(action.get("fact", ""))
            except Exception:
                pass

        elif atype == "reset_state":
            self.state["highlights_today"] = 0
            self.state["clips_queued_today"] = 0
            self.state["last_session"] = datetime.now().isoformat()
            self._save_state()

        elif atype in ("pipeline", "queue", "archive"):
            pass

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _score_to_tier(self, score: float) -> str:
        if score < DISCARD_BELOW:
            return TIER_DISCARD
        if score < MIN_POST_SCORE:
            return TIER_MID
        return TIER_QUEUE

    def session_summary(self) -> str:
        return (
            f"Session started: {self.state.get('session_started', 'unknown')}\n"
            f"Highlights today: {self.state.get('highlights_today', 0)}\n"
            f"Clips queued: {self.state.get('clips_queued_today', 0)}"
        )


if __name__ == "__main__":
    import sys

    try:
        with open(
            Path(__file__).parent.parent / "config.json", "r", encoding="utf-8"
        ) as fh:
            config = json.load(fh)
    except Exception:
        config = {}

    brain = BrainController(config)

    print("\n  🤖  Brain_Controller — Event Test")
    print(f"  Discard below: {DISCARD_BELOW:.0f}")
    print(f"  Queue floor:    {MIN_POST_SCORE:.0f}")
    print(f"  Alert at:       {QUEUE_AT:.0f}")
    print()

    test_events = [
        ("highlight", {"score": 92}),
        ("highlight", {"score": 72}),
        ("highlight", {"score": 58}),
        ("highlight", {"score": 30}),
        ("raid", {"raider": "BigStreamer", "count": 42}),
        ("sub", {"name": "CoolViewer123"}),
    ]

    for event, data in test_events:
        print(f"  Event: {event} {data}")
        actions = brain.decide(event, **data)
        for a in actions:
            print(
                f"    → {a['type']}: {a.get('msg') or a.get('event') or a.get('fact') or ''}"
            )
        print()

    print(f"  {brain.session_summary()}")
    print()
