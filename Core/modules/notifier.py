"""
Notifier
========
Colored console output + optional Discord webhook + daily log file.
Every pipeline decision includes a 'reason' string explaining why.

Discord surface (PARTIAL): webhook alerts only — not a Discord bot.
``status`` / ``try_send`` / ``bolt discord`` soft-fail with
``Discord unavailable:`` when no webhook is set or POST fails.
Budget / system alerts stay on Mac / Voice 3 / email / iMessage
(``Bolt_Alerts``; ``BOLT_ALERT_DISCORD`` defaults off).
"""

import argparse
import os
import json
import sys
import urllib.request
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

try:
    from dotenv import load_dotenv
except ImportError:

    def load_dotenv(*args: Any, **kwargs: Any) -> bool:
        return False


load_dotenv()

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "")

_COLORS = {
    "info": "\033[36m",  # cyan
    "success": "\033[32m",  # green
    "warning": "\033[33m",  # yellow
    "error": "\033[31m",  # red
    "learn": "\033[35m",  # magenta
    "startup": "\033[34m",  # blue
}
_RESET = "\033[0m"
_BOLD = "\033[1m"

_session_log = []


def notify(
    msg: str,
    level: str = "info",
    reason: Optional[str] = None,
    force_discord: bool = False,
    **kwargs: Any,
) -> None:
    color = _COLORS.get(level, "")
    tag = f"[{level.upper()}]"
    timestamp = datetime.now().strftime("%H:%M:%S")
    line = f"{color}{_BOLD}{timestamp} {tag}{_RESET} {msg}"
    print(line)
    if reason:
        print(f"  {_COLORS['learn']}↳ {reason}{_RESET}")

    entry = {"time": timestamp, "level": level, "msg": msg, "reason": reason}
    _session_log.append(entry)
    _write_log(entry)

    if _discord_webhooks() and (force_discord or level == "error"):
        _send_discord(msg, level, reason)


def notify_startup(
    game: str = "Gaming",
    obs_connected: bool = False,
    sensitivity: float = 0.7,
    auto_post: bool = False,
    style: str = "letterbox",
    pad_before: float = 12.0,
    pad_after: float = 20.0,
    spike_mult: float = 2.8,
    min_score: float = 40.0,
    queue_pending: int = 0,
    **kwargs,
):
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


def notify_highlight(
    ts: float = 0,
    level: float = 0,
    source: str = "audio_spike",
    reason: Optional[str] = None,
    **kwargs,
):
    mins = int(ts // 60)
    secs = int(ts % 60)
    msg = f"Highlight detected at {mins}:{secs:02d} — source: {source} (level={level:.4f})"
    notify(msg, level="success", reason=reason)


def notify_score(
    clip_name: str,
    score: float,
    grade: str,
    audio: float = 0,
    motion: float = 0,
    duration: float = 0,
    reason: Optional[str] = None,
    **kwargs,
):
    msg = (
        f"Score: {grade} ({score}/100) — {clip_name} | "
        f"audio={audio:.0f} motion={motion:.0f} dur={duration:.0f}s"
    )
    notify(msg, level="success" if score >= 65 else "info", reason=reason)


def notify_title(
    title: str, method: str = "template", reason: Optional[str] = None, **kwargs
):
    msg = f'Title ({method}): "{title}"'
    notify(msg, level="info", reason=reason)


def notify_post(
    clip: str,
    title: str,
    scheduled: Optional[str] = None,
    reason: Optional[str] = None,
    **kwargs,
):
    when = f" @ {scheduled}" if scheduled else ""
    msg = f'Queued for TikTok{when}: "{title}" ({clip})'
    notify(msg, level="success", reason=reason)


def notify_skip(clip: str, reason_str: str = "", **kwargs):
    msg = f"Skipping: {clip} — {reason_str}"
    notify(msg, level="warning", reason=reason_str)


def notify_error(ctx: str, err, recoverable: bool = True, **kwargs):
    msg = f"Error in {ctx}: {err}"
    notify(
        msg,
        level="error",
        reason="Recoverable — will retry." if recoverable else "Non-recoverable.",
    )
    if _discord_webhooks():
        _send_discord(msg, "error", str(err))


def daily_summary():
    errors = [e for e in _session_log if e["level"] == "error"]
    successes = [e for e in _session_log if e["level"] == "success"]
    msg = (
        f"Session ended — {len(successes)} successes, "
        f"{len(errors)} errors, {len(_session_log)} total events"
    )
    notify(msg, level="info", force_discord=bool(errors))


def _send_discord(msg: str, level: str, reason: Optional[str] = None) -> Dict[str, Any]:
    """POST to configured webhooks. Never raises. Returns ok/sent/errors."""
    webhooks = _discord_webhooks()
    if not webhooks:
        return {
            "ok": False,
            "sent": 0,
            "attempted": 0,
            "error": "Discord unavailable: no webhook URL "
            "(set DISCORD_WEBHOOK_URL in .env; optional CAPTAIN_HOOK_WEBHOOK_URL / DISCORD_WEBHOOK_URLS)",
        }
    emoji = {"error": "❌", "success": "✅", "warning": "⚠️", "startup": "🦊"}.get(
        level, "ℹ️"
    )
    body = {
        "content": f"{emoji} **Bolt** | {msg}" + (f"\n> {reason}" if reason else "")
    }
    sent = 0
    errors: List[str] = []
    for webhook in webhooks:
        try:
            req = urllib.request.Request(
                webhook,
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
            sent += 1
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
    if sent:
        return {"ok": True, "sent": sent, "attempted": len(webhooks), "errors": errors}
    return {
        "ok": False,
        "sent": 0,
        "attempted": len(webhooks),
        "error": "Discord unavailable: webhook POST failed "
        f"({'; '.join(errors) if errors else 'unknown'})",
        "errors": errors,
    }


def _discord_webhooks() -> List[str]:
    urls = [
        os.getenv("DISCORD_WEBHOOK_URL", ""),
        os.getenv("CAPTAIN_HOOK_WEBHOOK_URL", ""),
    ]
    extra = os.getenv("DISCORD_WEBHOOK_URLS", "")
    if extra:
        urls.extend(extra.replace("\n", ",").split(","))

    cleaned = []
    for url in urls:
        text = url.strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _write_log(entry: dict):
    try:
        log_file = f"logs/Bolt_{datetime.now().strftime('%Y-%m-%d')}.log"
        os.makedirs("logs", exist_ok=True)
        with open(log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def _redact_webhook(url: str) -> str:
    """Show last 6 chars only — never log full webhook secrets."""
    text = (url or "").strip()
    if not text:
        return ""
    try:
        parts = text.rstrip("/").split("/")
        token = parts[-1] if parts else ""
        tail = token[-6:] if len(token) >= 6 else token
        return f"…/{tail}"
    except Exception:
        return "(set)"


def _reload_dotenv() -> None:
    try:
        from dotenv import load_dotenv as _load
        from pathlib import Path as _P

        env_path = _P(__file__).resolve().parents[2] / ".env"
        if env_path.exists():
            _load(env_path, override=False)
    except Exception:
        pass


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Discord webhook readiness. Not a Discord bot.

    ``ready`` = at least one webhook URL configured (optional alerts can fire).
    Soft-fail hint uses ``Discord unavailable:``. ``probe`` POSTs a tiny
    test message when a webhook is set; without a webhook, probe stays soft-fail.
    """
    _reload_dotenv()
    webhooks = _discord_webhooks()
    alert_raw = str(os.getenv("BOLT_ALERT_DISCORD", "false")).strip().lower()
    alert_discord = alert_raw not in ("0", "false", "no", "off", "")
    info: Dict[str, Any] = {
        "ready": bool(webhooks),
        "surface": "discord_webhook",
        "is_discord_bot": False,
        "webhook_count": len(webhooks),
        "webhooks_redacted": [_redact_webhook(u) for u in webhooks],
        "env": {
            "DISCORD_WEBHOOK_URL": bool(os.getenv("DISCORD_WEBHOOK_URL", "").strip()),
            "CAPTAIN_HOOK_WEBHOOK_URL": bool(
                os.getenv("CAPTAIN_HOOK_WEBHOOK_URL", "").strip()
            ),
            "DISCORD_WEBHOOK_URLS": bool(os.getenv("DISCORD_WEBHOOK_URLS", "").strip()),
            "BOLT_ALERT_DISCORD": alert_discord,
        },
        "used_by": [
            "Peak_Hour_Notifier (queue / peak alerts)",
            "notifier (startup / errors when webhook set)",
        ],
        "hint": (
            "Webhook alerts optional. Not a Discord bot — Core README. "
            "Budget alerts use Mac/Voice/email/iMessage (Bolt_Alerts)."
            if webhooks
            else "Discord unavailable: no webhook URL "
            "(set DISCORD_WEBHOOK_URL in .env). Peak queue still works locally."
        ),
    }
    if probe:
        if not webhooks:
            info["probe_ok"] = False
            info["probe_error"] = info["hint"]
        else:
            result = try_send(
                "[Bolt] discord status --probe (safe test ping)",
                level="info",
                reason="bolt discord status --probe",
            )
            info["probe_ok"] = bool(result.get("ok"))
            if not result.get("ok"):
                info["probe_error"] = result.get("error")
            else:
                info["probe_sent"] = result.get("sent")
    return info


def try_send(
    message: str,
    *,
    level: str = "info",
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Send one Discord webhook message. Soft-fail; never raises."""
    _reload_dotenv()
    msg = (message or "").strip()
    if not msg:
        return {
            "ok": False,
            "sent": 0,
            "error": "Discord unavailable: empty message",
        }
    return _send_discord(msg, level=level, reason=reason)


def print_status(*, as_json: bool = False, probe: bool = False) -> int:
    info = status(probe=probe)
    if as_json:
        print(json.dumps(info, indent=2))
    else:
        ready = "ready" if info.get("ready") else "not ready"
        print(f"Discord webhooks: {ready} (bot=no, count={info.get('webhook_count')})")
        env = info.get("env") or {}
        for key, present in env.items():
            if key == "BOLT_ALERT_DISCORD":
                print(f"  {key}: {'on' if present else 'off'}")
            else:
                print(f"  {key}: {'set' if present else 'unset'}")
        for red in info.get("webhooks_redacted") or []:
            print(f"  webhook: {red}")
        if probe:
            if info.get("probe_ok"):
                print(f"  probe: ok (sent={info.get('probe_sent')})")
            else:
                print(f"  probe: {info.get('probe_error') or 'failed'}")
        print(f"  hint: {info.get('hint')}")
    return 0  # soft-fail informational


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bolt discord",
        description=(
            "Optional Discord webhook alerts (not a Discord bot). "
            "Soft-fail: Discord unavailable:"
        ),
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="status",
        help="status | test | send  (default: status)",
    )
    parser.add_argument("message", nargs="?", default=None, help="Message for send/test")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="status: POST a tiny test ping when webhook is set",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    action = (args.action or "status").lower().replace("_", "-")

    if action in ("status", "check", "ready"):
        return print_status(as_json=args.json, probe=args.probe)

    if action in ("test", "ping", "probe"):
        result = try_send(
            args.message
            or "[Bolt] discord test ping — webhook OK (not a Discord bot)",
            level="info",
            reason="bolt discord test",
        )
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result.get("ok"):
                print(f"Discord: sent={result.get('sent')} (test ok)")
            else:
                print(result.get("error") or "Discord unavailable:", file=sys.stderr)
        return 0

    if action in ("send", "notify", "post"):
        if not args.message:
            print(
                "Discord unavailable: message required "
                '(usage: bolt discord send "hello")',
                file=sys.stderr,
            )
            return 0
        result = try_send(args.message, level="info", reason="bolt discord send")
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result.get("ok"):
                print(f"Discord: sent={result.get('sent')}")
            else:
                print(result.get("error") or "Discord unavailable:", file=sys.stderr)
        return 0

    print(f"unknown discord action: {action}", file=sys.stderr)
    print(
        '  try: bolt discord | bolt discord test | bolt discord send "…"',
        file=sys.stderr,
    )
    return 2


NotifyFn = Callable[[str, str, Optional[str]], None]


if __name__ == "__main__":
    raise SystemExit(main())
