"""
Notifier
========
Colored console output + optional Discord webhook + daily log file.
Every pipeline decision includes a 'reason' string explaining why.
"""

import os
import json
import urllib.request
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "")

_COLORS = {
    "info":    "\033[36m",   # cyan
    "success": "\033[32m",   # green
    "warning": "\033[33m",   # yellow
    "error":   "\033[31m",   # red
    "learn":   "\033[35m",   # magenta
    "startup": "\033[34m",   # blue
}
_RESET = "\033[0m"
_BOLD  = "\033[1m"

_session_log = []


def notify(msg: str, level: str = "info", reason: str = None,
           force_discord: bool = False, **kwargs):
    color     = _COLORS.get(level, "")
    tag       = f"[{level.upper()}]"
    timestamp = datetime.now().strftime("%H:%M:%S")
    line      = f"{color}{_BOLD}{timestamp} {tag}{_RESET} {msg}"
    print(line)
    if reason:
        print(f"  {_COLORS['learn']}↳ {reason}{_RESET}")

    entry = {"time": timestamp, "level": level, "msg": msg, "reason": reason}
    _session_log.append(entry)
    _write_log(entry)

    if DISCORD_WEBHOOK and (force_discord or level == "error"):
        _send_discord(msg, level, reason)


def notify_startup(game: str = "Gaming",
                   obs_connected: bool = False,
                   sensitivity: float = 0.7,
                   auto_post: bool = False,
                   style: str = "letterbox",
                   pad_before: float = 12.0,
                   pad_after: float = 20.0,
                   spike_mult: float = 2.8,
                   min_score: float = 40.0,
                   queue_pending: int = 0,
                   **kwargs):
    obs_status = "connected ✓" if obs_connected else "offline (folder-watch mode)"
    if sensitivity < 0.5:
        sens_desc = "very sensitive — more clips, some may be weak"
    elif sensitivity <= 0.7:
        sens_desc = "balanced — only clear highlights"
    else:
        sens_desc = "strict — only the most obvious moments"

    msg = (
        f"Bolt starting — game: {game} | OBS: {obs_status} | "
        f"auto-post: {'on' if auto_post else 'off'} | "
        f"queue: {queue_pending} pending"
    )
    reason = (
        f"Game profile: {game}. "
        f"Clip padding: {pad_before}s before / {pad_after}s after highlight. "
        f"Spike threshold: {spike_mult}x baseline ({sens_desc}). "
        f"Min clip score to post: {min_score}/100. "
        f"TikTok style: {style}."
    )
    notify(msg, level="startup", reason=reason, force_discord=True)


def notify_highlight(ts: float = 0, level: float = 0,
                     source: str = "audio_spike", reason: str = None, **kwargs):
    mins = int(ts // 60)
    secs = int(ts % 60)
    msg  = f"Highlight detected at {mins}:{secs:02d} — source: {source} (level={level:.4f})"
    notify(msg, level="success", reason=reason)


def notify_score(clip_name: str, score: float, grade: str,
                 audio: float = 0, motion: float = 0,
                 duration: float = 0, reason: str = None, **kwargs):
    msg = (f"Score: {grade} ({score}/100) — {clip_name} | "
           f"audio={audio:.0f} motion={motion:.0f} dur={duration:.0f}s")
    notify(msg, level="success" if score >= 65 else "info", reason=reason)


def notify_title(title: str, method: str = "template", reason: str = None, **kwargs):
    msg = f"Title ({method}): \"{title}\""
    notify(msg, level="info", reason=reason)


def notify_post(clip: str, title: str, scheduled: str = None,
                reason: str = None, **kwargs):
    when = f" @ {scheduled}" if scheduled else ""
    msg  = f"Queued for TikTok{when}: \"{title}\" ({clip})"
    notify(msg, level="success", reason=reason)


def notify_skip(clip: str, reason_str: str = "", **kwargs):
    msg = f"Skipping: {clip} — {reason_str}"
    notify(msg, level="warning", reason=reason_str)


def notify_error(ctx: str, err, recoverable: bool = True, **kwargs):
    msg = f"Error in {ctx}: {err}"
    notify(msg, level="error",
           reason="Recoverable — will retry." if recoverable else "Non-recoverable.")
    if DISCORD_WEBHOOK:
        _send_discord(msg, "error", str(err))


def daily_summary():
    errors   = [e for e in _session_log if e["level"] == "error"]
    successes = [e for e in _session_log if e["level"] == "success"]
    msg = (f"Session ended — {len(successes)} successes, "
           f"{len(errors)} errors, {len(_session_log)} total events")
    notify(msg, level="info", force_discord=bool(errors))


def _send_discord(msg: str, level: str, reason: str = None):
    emoji = {"error": "❌", "success": "✅", "warning": "⚠️", "startup": "🦊"}.get(level, "ℹ️")
    body  = {"content": f"{emoji} **Bolt** | {msg}" + (f"\n> {reason}" if reason else "")}
    try:
        req = urllib.request.Request(
            DISCORD_WEBHOOK,
            data    = json.dumps(body).encode(),
            headers = {"Content-Type": "application/json"},
            method  = "POST",
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def _write_log(entry: dict):
    try:
        log_file = f"logs/Bolt_{datetime.now().strftime('%Y-%m-%d')}.log"
        os.makedirs("logs", exist_ok=True)
        with open(log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass
