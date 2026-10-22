"""
Notifier
========
Colored console output + optional Discord webhook + daily log file.
Every pipeline decision includes a 'reason' string explaining why.

Discord surface (READY): webhook alerts only — not a Discord bot.
Every Discord post in Bolt (errors, startup, peak-hour clip alerts) goes
through ``post_webhooks``: proper User-Agent (Discord's firewall answers
403 to Python's default one), real HTTP status check, one retry on a 429
rate limit, long messages split at 2000 characters, @everyone/@here never
pings, and every send logged to ``logs/discord.jsonl``.
Settings: ``.env.local`` then ``.env`` at the Bolt folder (first value wins).
``status --probe`` checks each webhook with a GET (posts nothing).
``bolt discord`` soft-fails with ``Discord unavailable:`` when no webhook
is set or a POST fails. Budget / system alerts stay on Mac / voice / email /
iMessage (``Bolt_Alerts``; ``BOLT_ALERT_DISCORD`` defaults off).
"""

import argparse
import os
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    from dotenv import load_dotenv
except ImportError:

    def load_dotenv(*args: Any, **kwargs: Any) -> bool:
        return False


_REPO_ROOT = Path(__file__).resolve().parents[2]
_LOG_DIR = _REPO_ROOT / "logs"
DISCORD_LOG = _LOG_DIR / "discord.jsonl"
DISCORD_LIMIT = 2000
# Discord's Cloudflare front end rejects Python's default urllib User-Agent
# with HTTP 403 (error 1010), so every post sends a real one.
USER_AGENT = "Bolt-Notifier/1.0 (+local Bolt on macOS)"


def _load_env_files() -> None:
    """Load .env.local then .env from the Bolt folder (first value wins)."""
    for name in (".env.local", ".env"):
        path = _REPO_ROOT / name
        if path.exists():
            try:
                load_dotenv(path, override=False)
            except Exception:
                pass


_load_env_files()

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
    # notify(level="error") already posts to the Discord webhooks once — the old
    # extra _send_discord here sent every error twice.
    notify(
        msg,
        level="error",
        reason="Recoverable — continuing." if recoverable else "Non-recoverable.",
    )
    # Keep a lasting record for `bolt error-recovery run` (Data/pipeline_errors.jsonl).
    try:
        try:
            from modules.Error_Recovery import record_error, current_context
        except ImportError:
            from Error_Recovery import record_error, current_context  # type: ignore
        record_error(ctx, kwargs.get("recording") or current_context(), err, quiet=True)
    except Exception:
        pass


def daily_summary():
    errors = [e for e in _session_log if e["level"] == "error"]
    successes = [e for e in _session_log if e["level"] == "success"]
    msg = (
        f"Session ended — {len(successes)} successes, "
        f"{len(errors)} errors, {len(_session_log)} total events"
    )
    notify(msg, level="info", force_discord=bool(errors))


def _split_message(text: str, limit: int = DISCORD_LIMIT) -> List[str]:
    """Split text into Discord-sized pieces, preferring line breaks."""
    text = text or ""
    if len(text) <= limit:
        return [text]
    parts: List[str] = []
    rest = text
    while len(rest) > limit:
        cut = rest.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        parts.append(rest[:cut].rstrip("\n"))
        rest = rest[cut:].lstrip("\n")
    if rest:
        parts.append(rest)
    return parts


def _log_send(entry: Dict[str, Any]) -> None:
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(DISCORD_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def _post_one(webhook: str, content: str) -> Optional[str]:
    """POST one piece to one webhook. Returns None on success, else an error."""
    body = json.dumps(
        {"content": content, "allowed_mentions": {"parse": []}}
    ).encode()
    for attempt in range(2):
        req = urllib.request.Request(
            webhook,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                code = getattr(resp, "status", 200)
                if 200 <= code < 300:
                    return None
                return f"HTTP {code}"
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt == 0:
                wait = 1.0
                try:
                    wait = float(json.loads(exc.read() or b"{}").get("retry_after", 1.0))
                except Exception:
                    pass
                time.sleep(min(max(wait, 0.5), 5.0))
                continue
            hint = {
                401: "webhook token is wrong — copy the webhook URL again",
                403: "Discord refused the request",
                404: "webhook was deleted in Discord — make a new one and update .env.local",
                429: "rate limited by Discord — try again in a minute",
            }.get(exc.code, "")
            return f"HTTP {exc.code}" + (f" ({hint})" if hint else "")
        except Exception as exc:
            return f"{type(exc).__name__}: {exc}"
    return "rate limited"


def post_webhooks(content: str, *, source: str = "bolt") -> Dict[str, Any]:
    """Send ``content`` to every configured webhook. Never raises."""
    webhooks = _discord_webhooks()
    if not webhooks:
        return {
            "ok": False,
            "sent": 0,
            "attempted": 0,
            "error": "Discord unavailable: no webhook URL "
            "(set DISCORD_WEBHOOK_URL in .env.local; optional CAPTAIN_HOOK_WEBHOOK_URL / DISCORD_WEBHOOK_URLS)",
        }
    pieces = _split_message((content or "").strip())
    sent = 0
    errors: List[str] = []
    for webhook in webhooks:
        failed = None
        for piece in pieces:
            failed = _post_one(webhook, piece)
            if failed:
                break
        if failed:
            errors.append(f"{_redact_webhook(webhook)}: {failed}")
        else:
            sent += 1
    _log_send(
        {
            "time": datetime.now().isoformat(timespec="seconds"),
            "source": source,
            "chars": len(content or ""),
            "pieces": len(pieces),
            "sent": sent,
            "attempted": len(webhooks),
            "errors": errors,
            "preview": (content or "")[:120],
        }
    )
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


def _send_discord(msg: str, level: str, reason: Optional[str] = None) -> Dict[str, Any]:
    """POST a Bolt-formatted alert to configured webhooks. Never raises."""
    emoji = {"error": "❌", "success": "✅", "warning": "⚠️", "startup": "🦊"}.get(
        level, "ℹ️"
    )
    content = f"{emoji} **Bolt** | {msg}" + (f"\n> {reason}" if reason else "")
    return post_webhooks(content, source=f"notifier:{level}")


def check_webhook(webhook: str) -> Dict[str, Any]:
    """GET a webhook (posts nothing): is it still valid, and where does it go?"""
    req = urllib.request.Request(webhook, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read() or b"{}")
        return {
            "ok": True,
            "webhook": _redact_webhook(webhook),
            "name": data.get("name"),
            "channel_id": data.get("channel_id"),
        }
    except urllib.error.HTTPError as exc:
        why = {401: "token is wrong", 404: "webhook was deleted in Discord"}.get(
            exc.code, "Discord refused it"
        )
        return {"ok": False, "webhook": _redact_webhook(webhook), "error": f"HTTP {exc.code} ({why})"}
    except Exception as exc:
        return {"ok": False, "webhook": _redact_webhook(webhook), "error": f"{type(exc).__name__}: {exc}"}


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
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = _LOG_DIR / f"Bolt_{datetime.now().strftime('%Y-%m-%d')}.log"
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
    _load_env_files()


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Discord webhook readiness. Not a Discord bot.

    ``ready`` = at least one webhook URL configured (optional alerts can fire).
    Soft-fail hint uses ``Discord unavailable:``. ``probe`` checks each
    webhook with a GET (nothing is posted); ``probe_ok`` only when all pass.
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
        "log": str(DISCORD_LOG),
        "last_send": _last_send(),
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
            checks = [check_webhook(u) for u in webhooks]
            info["probe"] = checks
            info["probe_ok"] = all(c.get("ok") for c in checks)
            bad = [f"{c['webhook']}: {c.get('error')}" for c in checks if not c.get("ok")]
            if bad:
                info["probe_error"] = "Discord unavailable: " + "; ".join(bad)
    return info


def _last_send() -> Optional[Dict[str, Any]]:
    try:
        lines = DISCORD_LOG.read_text(encoding="utf-8").strip().splitlines()
        return json.loads(lines[-1]) if lines else None
    except Exception:
        return None


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
            for c in info.get("probe") or []:
                if c.get("ok"):
                    print(f"  check {c['webhook']}: ok — \"{c.get('name')}\" (channel {c.get('channel_id')}), nothing posted")
                else:
                    print(f"  check {c['webhook']}: {c.get('error')}")
            if not info.get("probe") and not info.get("probe_ok"):
                print(f"  probe: {info.get('probe_error') or 'failed'}")
        last = info.get("last_send")
        if last:
            state = "ok" if last.get("sent") else "FAILED"
            print(f"  last send: {last.get('time')} {state} ({last.get('sent')}/{last.get('attempted')} webhooks) — {last.get('source')}")
            if last.get("errors"):
                print(f"    error: {'; '.join(last['errors'])}")
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
        help="status: check each webhook with a GET (posts nothing)",
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
