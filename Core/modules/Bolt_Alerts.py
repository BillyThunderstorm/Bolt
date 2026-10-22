#!/usr/bin/env python3
"""
Bolt_Alerts.py — Mac banner + spoken line + iMessage/SMS + email (no Discord)
=============================================================================
Preferred channels for budget, system, briefing and weekly alerts.

READY CLI: ``bolt alerts`` status / list / test / send
Soft-fail prefix: ``Alerts unavailable:``. Discord webhooks stay on ``bolt discord``.

Channels:
  mac    — native macOS banner (osascript ``display notification``; local, free)
  voice  — one spoken line: William's ElevenLabs voice first
           (Bolt_TTS_PROVIDER=elevenlabs + ELEVENLABS_API_KEY + ELEVENLABS_VOICE_ID,
           normally in .env.local), then the fixed male macOS voice
           "Nathan (Enhanced)". Siri voices ("Voice 1–5", "Siri …") are never
           used — if Bolt_VOICE is set to one, Nathan (Enhanced) is used instead.
  sms    — iMessage via the Mac's Messages app to ALERT_PHONE (AT&T email-to-text
           died 2025-06-17), else carrier email-to-SMS gateway
  email  — SMTP (Gmail App Password) to ALERT_EMAIL

Config is read from Data/configs/storage_alerts.env (SMTP_* / ALERT_* / CARRIER),
then .env.local, then .env (first value wins, like the rest of Bolt).
Every fan-out is logged (title + per-channel result, no bodies) to logs/alerts.jsonl.

Env switches:
  BOLT_ALERT_SMS=true|false     (default true)
  BOLT_ALERT_EMAIL=true|false   (default true)
  BOLT_ALERT_MAC=true|false     (default true)
  BOLT_ALERT_SPEAK=true|false   (default true)
  BOLT_ALERT_IMESSAGE=true|false (default true)
  BOLT_ALERT_DISCORD=false      (default false — kept off on purpose)

  bolt alerts                         # status (default)
  bolt alerts status [--json] [--probe] [--banner]
  bolt alerts list [--json]
  bolt alerts test [--only mac,voice,sms,email] [--no-sms] [--no-email] [--no-speak] [--json]
  bolt alerts send "msg" [same channel flags] [--json]

Aliases: alert, alert-status, notify-alerts, bolt-alerts.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO = Path(__file__).resolve().parents[2]
_SOFT = "Alerts unavailable:"
_ALERT_ENV_CANDIDATES = (
    _REPO / "Data" / "configs" / "storage_alerts.env",
    _REPO / "configs" / "storage_alerts.env",
)
# Bolt-wide env: .env.local (William's local keys, e.g. ElevenLabs) beats .env
_BOLT_ENV_CANDIDATES = (
    _REPO / ".env.local",
    _REPO / ".env",
)
_SEND_SCRIPT = _REPO / "scripts" / "send_notification.py"
_ALERT_LOG = _REPO / "logs" / "alerts.jsonl"

# The only macOS voice Bolt falls back to. Never a Siri voice.
FALLBACK_VOICE = "Nathan (Enhanced)"
_SIRI_VOICE_RE = None  # compiled lazily
CHANNELS = ("mac", "voice", "sms", "email")
_LAST_VOICE: str = ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _soft(msg: str) -> str:
    if msg.startswith(_SOFT):
        return msg
    return f"{_SOFT} {msg}"


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() not in ("0", "false", "no", "off")


def _load_alert_env() -> None:
    """Load storage_alerts.env, then .env.local, then .env (first value wins)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for candidate in _ALERT_ENV_CANDIDATES + _BOLT_ENV_CANDIDATES:
        if candidate.exists():
            load_dotenv(candidate, override=False)


def _is_siri_voice(name: str) -> bool:
    global _SIRI_VOICE_RE
    import re

    if _SIRI_VOICE_RE is None:
        _SIRI_VOICE_RE = re.compile(r"^\s*(voice\s*\d+|siri\b.*)\s*$", re.I)
    return bool(_SIRI_VOICE_RE.match(name or ""))


def fallback_voice() -> str:
    """macOS voice for the spoken line when ElevenLabs can't speak.

    Uses Bolt_VOICE when set, but never a Siri voice ("Voice 3" etc.) —
    those are swapped for Nathan (Enhanced).
    """
    voice = (os.getenv("Bolt_VOICE") or os.getenv("BOLT_VOICE") or "").strip()
    if not voice or _is_siri_voice(voice):
        return FALLBACK_VOICE
    return voice


def _voice_rate() -> str:
    raw = os.getenv("Bolt_VOICE_RATE") or os.getenv("BOLT_VOICE_RATE") or "190"
    return raw if str(raw).strip().isdigit() else "190"


def _voice_muted() -> bool:
    raw = os.getenv("Bolt_VOICE_MUTE") or os.getenv("BOLT_VOICE_MUTE") or "false"
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def elevenlabs_configured() -> bool:
    provider = (
        os.getenv("Bolt_TTS_PROVIDER") or os.getenv("BOLT_TTS_PROVIDER") or ""
    ).strip().lower()
    return provider in ("elevenlabs", "eleven") and bool(
        os.getenv("ELEVENLABS_API_KEY") and os.getenv("ELEVENLABS_VOICE_ID")
    )


def _say_fallback(text: str) -> bool:
    try:
        r = subprocess.run(
            ["say", "-v", fallback_voice(), "-r", _voice_rate(), text],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return r.returncode == 0
    except Exception:
        return False


def _speak_elevenlabs(text: str) -> bool:
    """William's ElevenLabs voice via Bolt_Voice (keys read at call time)."""
    try:
        from modules import Bolt_Voice as bv  # type: ignore
    except Exception:
        return False
    try:
        # Bolt_Voice reads keys at import time and only loads .env — sync them
        # from the env we just loaded (.env.local holds William's key).
        bv.ELEVENLABS_KEY = os.getenv("ELEVENLABS_API_KEY", "") or bv.ELEVENLABS_KEY
        bv.ELEVENLABS_VOICE_ID = (
            os.getenv("ELEVENLABS_VOICE_ID", "") or bv.ELEVENLABS_VOICE_ID
        )
        if not (bv.ELEVENLABS_KEY and bv.ELEVENLABS_VOICE_ID):
            return False
        return bool(bv._try_elevenlabs(text))
    except Exception:
        return False


def _speak_alert(text: str) -> str:
    """Speak one alert line. Returns which voice spoke ("" = nothing spoke).

    Order: William's ElevenLabs voice → Nathan (Enhanced). Never Siri.
    """
    global _LAST_VOICE
    _LAST_VOICE = ""
    if not _env_bool("BOLT_ALERT_SPEAK", True):
        return ""
    _load_alert_env()
    if _voice_muted():
        return ""
    spoken = " ".join((text or "").split())[:280]
    if not spoken:
        return ""
    if elevenlabs_configured() and _speak_elevenlabs(spoken):
        _LAST_VOICE = "elevenlabs"
    elif _say_fallback(spoken):
        _LAST_VOICE = fallback_voice()
    return _LAST_VOICE


def mac_banner(
    title: str,
    message: str,
    subtitle: str = "Bolt",
    *,
    speak: bool = True,
) -> bool:
    """Show a native macOS banner and (optionally) speak it — ElevenLabs, else Nathan."""
    if not _env_bool("BOLT_ALERT_MAC", True):
        return False
    # Escape for AppleScript string
    def esc(s: str) -> str:
        return (
            (s or "")
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", " ")
            .replace("\r", " ")
        )[:200]

    script = (
        f'display notification "{esc(message)}" '
        f'with title "{esc(title)}" '
        f'subtitle "{esc(subtitle)}"'
    )
    shown = False
    try:
        r = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        shown = r.returncode == 0
    except Exception:
        shown = False
    if speak:
        spoken = f"{title}. {message}" if title else message
        _speak_alert(spoken)
    return shown


def _import_send_notification():
    scripts = _REPO / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    # Ensure send_notification finds Data/configs
    import send_notification as sn  # type: ignore

    return sn


def send_sms(message: str) -> bool:
    if not _env_bool("BOLT_ALERT_SMS", True):
        return False
    _load_alert_env()
    try:
        sn = _import_send_notification()
        return bool(sn.send_sms(message))
    except Exception as exc:
        print(f"Bolt_Alerts SMS failed: {exc}")
        return False


def send_email(subject: str, body: str) -> bool:
    if not _env_bool("BOLT_ALERT_EMAIL", True):
        return False
    _load_alert_env()
    try:
        sn = _import_send_notification()
        return bool(sn.send_email(subject, body))
    except Exception as exc:
        print(f"Bolt_Alerts email failed: {exc}")
        return False


def _log_alert(title: str, results: dict) -> None:
    try:
        _ALERT_LOG.parent.mkdir(parents=True, exist_ok=True)
        row = {"at": _utc_now(), "title": (title or "")[:120], "results": results}
        with _ALERT_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except Exception:
        pass


def notify(
    message: str,
    *,
    title: str = "Bolt",
    subject: Optional[str] = None,
    sms: bool = True,
    email: bool = True,
    banner: bool = True,
    speak: bool = True,
    email_body: Optional[str] = None,
) -> dict:
    """
    Fan-out alert to Mac banner + spoken line + iMessage/SMS + email
    (never Discord by default).

    Returns channel success map: mac / sms / email (bool) and voice
    (which voice spoke, "" when nothing spoke).
    """
    _load_alert_env()
    results: Dict[str, Any] = {"mac": False, "voice": "", "sms": False, "email": False}
    short = (message or "").strip()
    if not short:
        return results

    if banner:
        results["mac"] = mac_banner(title, short, speak=False)
    if speak:
        results["voice"] = _speak_alert(f"{title}. {short}" if title else short)

    if sms:
        results["sms"] = send_sms(f"{title}: {short}"[:160])

    if email:
        results["email"] = send_email(
            subject or f"{title} alert",
            email_body or short,
        )

    _log_alert(title, results)
    return results


def smtp_configured() -> bool:
    _load_alert_env()
    return bool(os.getenv("SMTP_USERNAME") and os.getenv("SMTP_PASSWORD"))


def channels_status() -> dict:
    """Legacy compact channel map (still used by ``bolt budget``)."""
    _load_alert_env()
    carrier = (os.getenv("CARRIER") or "").lower().strip()
    att_gateway_dead = carrier in ("att", "att-sms", "cricket", "firstnet")
    return {
        "mac_banner": _env_bool("BOLT_ALERT_MAC", True),
        "sms_enabled": _env_bool("BOLT_ALERT_SMS", True),
        "email_enabled": _env_bool("BOLT_ALERT_EMAIL", True),
        "imessage_enabled": _env_bool("BOLT_ALERT_IMESSAGE", True),
        "discord_enabled": _env_bool("BOLT_ALERT_DISCORD", False),
        "speak_enabled": _env_bool("BOLT_ALERT_SPEAK", True),
        "alert_phone_set": bool(os.getenv("ALERT_PHONE")),
        "alert_email_set": bool(os.getenv("ALERT_EMAIL")),
        "smtp_configured": smtp_configured(),
        "carrier": os.getenv("CARRIER", ""),
        "att_email_to_text": "discontinued_2025-06-17" if att_gateway_dead else "n/a",
        "phone_path": (
            "iMessage via Mac Messages (AT&T email-to-text is dead)"
            if att_gateway_dead
            else "carrier email gateway and/or iMessage"
        ),
    }


def _voice_installed(name: str) -> bool:
    try:
        r = subprocess.run(
            ["say", "-v", "?"], capture_output=True, text=True, timeout=10, check=False
        )
        return any(line.startswith(name + " ") for line in (r.stdout or "").splitlines())
    except Exception:
        return False


def voice_status() -> Dict[str, Any]:
    _load_alert_env()
    fb = fallback_voice()
    configured = (os.getenv("Bolt_VOICE") or os.getenv("BOLT_VOICE") or "").strip()
    return {
        "speak_enabled": _env_bool("BOLT_ALERT_SPEAK", True),
        "muted": _voice_muted(),
        "first_choice": "elevenlabs" if elevenlabs_configured() else fb,
        "elevenlabs_configured": elevenlabs_configured(),
        "elevenlabs_voice_id_set": bool(os.getenv("ELEVENLABS_VOICE_ID")),
        "fallback_voice": fb,
        "fallback_installed": _voice_installed(fb) if platform.system() == "Darwin" else False,
        "siri_voice_blocked": bool(configured and _is_siri_voice(configured)),
        "never_siri": True,
    }


def _probe_smtp() -> Dict[str, Any]:
    """Log in to SMTP and quit — proves the password works, sends nothing."""
    import smtplib

    _load_alert_env()
    user = os.getenv("SMTP_USERNAME", "")
    pw = os.getenv("SMTP_PASSWORD", "")
    if not (user and pw):
        return {"ok": False, "detail": "SMTP_USERNAME / SMTP_PASSWORD not set"}
    server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587") or 587)
    try:
        with smtplib.SMTP(server, port, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(user, pw)
        return {"ok": True, "detail": f"login ok ({server}:{port}; nothing sent)"}
    except smtplib.SMTPAuthenticationError:
        return {
            "ok": False,
            "detail": "SMTP login rejected — make a new Gmail App Password "
            "(https://myaccount.google.com/apppasswords) and put it in "
            "Data/configs/storage_alerts.env as SMTP_PASSWORD",
        }
    except Exception as exc:
        return {"ok": False, "detail": f"SMTP connect failed ({exc.__class__.__name__}: {exc})"[:200]}


def _probe_elevenlabs() -> Dict[str, Any]:
    """Check the ElevenLabs key can see William's voice — no audio, no credits."""
    _load_alert_env()
    if not elevenlabs_configured():
        return {"ok": False, "detail": "ElevenLabs not set (Nathan (Enhanced) will speak)"}
    try:
        import requests

        vid = os.getenv("ELEVENLABS_VOICE_ID", "")
        r = requests.get(
            f"https://api.elevenlabs.io/v1/voices/{vid}",
            headers={"xi-api-key": os.getenv("ELEVENLABS_API_KEY", "")},
            timeout=10,
        )
        if r.status_code == 200:
            name = (r.json() or {}).get("name") or vid
            return {"ok": True, "detail": f"voice found: {name}"}
        if r.status_code in (401, 403):
            # Restricted keys may speak but not read voices — not a hard fail
            return {
                "ok": None,
                "detail": f"key can't read voice info (HTTP {r.status_code}); "
                "speaking may still work — try bolt alerts test",
            }
        return {"ok": False, "detail": f"ElevenLabs HTTP {r.status_code}"}
    except Exception as exc:
        return {"ok": False, "detail": f"ElevenLabs check failed ({exc.__class__.__name__})"}


def status(*, probe: bool = False, banner_probe: bool = False) -> Dict[str, Any]:
    """Alert-channel readiness. Never raises.

    READY when the Mac banner works locally; email / iMessage are reported
    per channel with the exact fix when something is missing.
    """
    try:
        ch = channels_status()
        is_darwin = platform.system() == "Darwin"
        env_file = next((str(p) for p in _ALERT_ENV_CANDIDATES if p.is_file()), None)
        send_script_present = _SEND_SCRIPT.is_file()
        osascript = bool(
            subprocess.run(
                ["which", "osascript"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            ).stdout.strip()
        ) if is_darwin else False
        say_cli = bool(
            subprocess.run(
                ["which", "say"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            ).stdout.strip()
        ) if is_darwin else False
        voice = voice_status() if is_darwin else {"speak_enabled": False}

        mac_ok = bool(ch.get("mac_banner")) and is_darwin and osascript
        email_ok = bool(ch.get("email_enabled") and ch.get("smtp_configured") and ch.get("alert_email_set"))
        imessage_path = bool(
            is_darwin and ch.get("imessage_enabled") and ch.get("alert_phone_set")
        )
        gateway_path = bool(
            ch.get("smtp_configured")
            and ch.get("alert_phone_set")
            and ch.get("att_email_to_text") == "n/a"
        )
        sms_ok = bool(ch.get("sms_enabled") and (imessage_path or gateway_path))
        voice_ok = bool(
            is_darwin
            and voice.get("speak_enabled")
            and not voice.get("muted")
            and (voice.get("elevenlabs_configured") or (say_cli and voice.get("fallback_installed")))
        )
        ready = bool(mac_ok or email_ok or sms_ok)

        missing: List[str] = []
        if not is_darwin:
            missing.append("not macOS (Darwin) — Mac banner/voice/iMessage unavailable")
        if ch.get("mac_banner") and is_darwin and not osascript:
            missing.append("osascript missing")
        if ch.get("email_enabled") and not ch.get("smtp_configured"):
            missing.append(
                "SMTP not configured — add SMTP_USERNAME + SMTP_PASSWORD (Gmail App Password) "
                "to Data/configs/storage_alerts.env"
            )
        if ch.get("email_enabled") and not ch.get("alert_email_set"):
            missing.append("ALERT_EMAIL unset in Data/configs/storage_alerts.env")
        if ch.get("sms_enabled") and not ch.get("alert_phone_set"):
            missing.append("ALERT_PHONE unset in Data/configs/storage_alerts.env")
        if is_darwin and voice.get("speak_enabled") and not voice.get("muted"):
            if not voice.get("elevenlabs_configured") and not voice.get("fallback_installed"):
                missing.append(
                    f"voice: '{voice.get('fallback_voice')}' not installed — System Settings → "
                    "Accessibility → Read & Speak → System Voice → Manage Voices → Nathan (Enhanced)"
                )
        if not send_script_present:
            missing.append("missing scripts/send_notification.py")

        if ready:
            error = None
            hint = "Try: bolt alerts test --no-sms (one banner + one spoken line + one email)"
            gated = [m for m in missing if not m.startswith("voice:")]
            if gated:
                hint += " · still missing: " + "; ".join(gated[:2])
            elif any(m.startswith("voice:") for m in missing):
                hint += " · " + next(m for m in missing if m.startswith("voice:"))
        else:
            error = _soft("; ".join(missing[:3]) if missing else "no alert channel ready")
            hint = error

        out: Dict[str, Any] = {
            "checked_at": _utc_now(),
            "ready": ready,
            "partial": not ready,
            "readiness": "READY" if ready else "PARTIAL",
            "is_discord_bot": False,
            "discord_default_off": True,
            "soft_fail_prefix": _SOFT,
            "darwin": is_darwin,
            "platform": platform.system(),
            "osascript_present": osascript,
            "say_present": say_cli,
            "send_script_present": send_script_present,
            "alert_env_file": env_file,
            "alert_log": str(_ALERT_LOG),
            "channels": ch,
            "voice": voice,
            "mac_ready": mac_ok,
            "voice_ready": voice_ok,
            "email_ready": email_ok,
            "sms_ready": sms_ok,
            "sms_path": (
                "iMessage (Messages app)" if imessage_path
                else ("carrier email-to-SMS" if gateway_path else "none")
            ),
            "missing": missing,
            "error": error,
            "hint": hint,
        }

        if probe:
            # Silent probes: SMTP login + ElevenLabs voice lookup. Nothing is sent.
            out["probe"] = True
            out["smtp_probe"] = _probe_smtp()
            out["elevenlabs_probe"] = _probe_elevenlabs()
            if out["smtp_probe"].get("ok") is False and ch.get("email_enabled"):
                out["email_ready"] = False
        if banner_probe:
            if not is_darwin or not ch.get("mac_banner"):
                out["probe_ok"] = False
                out["probe_detail"] = _soft("Mac banner probe skipped (not Darwin or disabled)")
            else:
                try:
                    ok = mac_banner(
                        "Bolt alerts probe",
                        "status --banner (banner only; no voice, SMS or email)",
                        speak=False,
                    )
                    out["probe_ok"] = bool(ok)
                    out["probe_detail"] = (
                        "Mac banner shown" if ok else _soft("Mac banner failed")
                    )
                    if not ok and not out.get("error"):
                        out["error"] = out["probe_detail"]
                        out["hint"] = out["error"]
                except Exception as exc:
                    out["probe_ok"] = False
                    out["probe_detail"] = _soft(f"probe failed ({exc})")
                    out["error"] = out["probe_detail"]
                    out["hint"] = out["error"]
        return out
    except Exception as exc:
        return {
            "checked_at": _utc_now(),
            "ready": False,
            "partial": True,
            "readiness": "PARTIAL",
            "is_discord_bot": False,
            "soft_fail_prefix": _SOFT,
            "error": _soft(f"status failed ({exc})"),
            "hint": _soft(f"status failed ({exc})"),
        }


def list_items(*, as_json: bool = False) -> int:
    """Checklist of alert channels / config files."""
    try:
        info = status()
        ch = info.get("channels") or {}
        v = info.get("voice") or {}
        rows = [
            ("platform_darwin", bool(info.get("darwin"))),
            ("osascript (Mac banner)", bool(info.get("osascript_present"))),
            ("mac_banner enabled", bool(ch.get("mac_banner"))),
            ("speak enabled", bool(ch.get("speak_enabled")) and not v.get("muted")),
            ("ElevenLabs (William's voice) configured", bool(v.get("elevenlabs_configured"))),
            (f"fallback voice installed ({v.get('fallback_voice', FALLBACK_VOICE)})", bool(v.get("fallback_installed"))),
            ("never Siri / Voice 3", True),
            ("email enabled", bool(ch.get("email_enabled"))),
            ("SMTP configured", bool(ch.get("smtp_configured"))),
            ("ALERT_EMAIL set", bool(ch.get("alert_email_set"))),
            ("sms enabled", bool(ch.get("sms_enabled"))),
            ("imessage enabled", bool(ch.get("imessage_enabled"))),
            ("ALERT_PHONE set", bool(ch.get("alert_phone_set"))),
            ("discord enabled (default off)", bool(ch.get("discord_enabled"))),
            ("scripts/send_notification.py", bool(info.get("send_script_present"))),
            ("Data/configs/storage_alerts.env present", bool(info.get("alert_env_file"))),
        ]
        if as_json:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "readiness": info.get("readiness"),
                        "is_discord_bot": False,
                        "items": [{"name": n, "ok": ok} for n, ok in rows],
                        "hint": info.get("hint"),
                        "error": info.get("error"),
                    },
                    indent=2,
                )
            )
            return 0
        print(f"Alert channels ({info.get('readiness')} — Mac banner / voice / iMessage / email; not Discord)")
        for name, ok in rows:
            mark = "OK" if ok else "--"
            print(f"  [{mark}] {name}")
        if info.get("hint"):
            print(f"  → {info['hint']}")
        return 0
    except Exception as exc:
        msg = _soft(f"list failed ({exc})")
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0


def _parse_channels(args: List[str]) -> Dict[str, bool]:
    """--only mac,voice,sms,email  and/or  --no-mac --no-speak --no-sms --no-email."""
    chosen = {c: True for c in CHANNELS}
    for i, a in enumerate(args):
        val = None
        if a.startswith("--only="):
            val = a.split("=", 1)[1]
        elif a == "--only" and i + 1 < len(args):
            val = args[i + 1]
        if val is not None:
            names = {x.strip().lower() for x in val.split(",") if x.strip()}
            names = {"voice" if n in ("speak", "say") else n for n in names}
            names = {"sms" if n in ("imessage", "text") else n for n in names}
            names = {"mac" if n in ("banner",) else n for n in names}
            chosen = {c: (c in names) for c in CHANNELS}
    flag_map = {
        "--no-mac": "mac", "--no-banner": "mac",
        "--no-speak": "voice", "--no-voice": "voice", "--quiet": "voice",
        "--no-sms": "sms", "--no-imessage": "sms", "--no-text": "sms",
        "--no-email": "email",
    }
    for a in args:
        if a in flag_map:
            chosen[flag_map[a]] = False
    return chosen


def _strip_channel_args(args: List[str]) -> List[str]:
    out: List[str] = []
    skip = False
    for i, a in enumerate(args):
        if skip:
            skip = False
            continue
        if a == "--only":
            skip = True
            continue
        if a.startswith("-"):
            continue
        out.append(a)
    return out


def _fanout(
    message: str,
    *,
    title: str,
    chosen: Dict[str, bool],
    subject: Optional[str] = None,
    email_body: Optional[str] = None,
) -> Dict[str, Any]:
    return notify(
        message,
        title=title,
        subject=subject,
        email_body=email_body,
        banner=chosen.get("mac", True),
        speak=chosen.get("voice", True),
        sms=chosen.get("sms", True),
        email=chosen.get("email", True),
    )


def _print_results(results: Dict[str, Any], chosen: Dict[str, bool], *, stream=None) -> None:
    stream = stream or sys.stdout
    for c in CHANNELS:
        if not chosen.get(c, True):
            print(f"  {c:<5} skipped", file=stream)
            continue
        val = results.get(c)
        if c == "voice":
            label = (
                "spoke in William's ElevenLabs voice" if val == "elevenlabs"
                else (f"spoke in {val}" if val else "did not speak")
            )
            print(f"  {c:<5} {label}", file=stream)
        else:
            print(f"  {c:<5} {'sent' if val else 'FAILED'}", file=stream)


def try_test(*, as_json: bool = False, chosen: Optional[Dict[str, bool]] = None) -> int:
    """One test alert across the chosen channels. Never raises."""
    chosen = chosen or {c: True for c in CHANNELS}
    try:
        info = status()
        if not info.get("ready"):
            msg = info.get("error") or _soft("no alert channel ready")
            payload = {"ok": False, "error": msg, "readiness": info.get("readiness"), "results": {}}
            if as_json:
                print(json.dumps(payload, indent=2))
            else:
                print(msg, file=sys.stderr)
            return 0

        results = _fanout(
            "Bolt alerts test. If you can see or hear this, alerts are working.",
            title="Bolt test",
            chosen=chosen,
            subject="Bolt alert test",
            email_body=(
                "Bolt alerts test.\n\n"
                "If you see this email, Bolt's email alerts are working.\n"
                "Budget, system, briefing and weekly alerts use this same path.\n"
            ),
        )
        failed = [
            c for c in CHANNELS
            if chosen.get(c, True) and not results.get(c)
        ]
        any_ok = any(bool(results.get(c)) for c in CHANNELS if chosen.get(c, True))
        payload: Dict[str, Any] = {
            "ok": any_ok and not failed,
            "results": results,
            "channels_tested": [c for c in CHANNELS if chosen.get(c, True)],
            "failed": failed,
            "readiness": info.get("readiness"),
            "is_discord_bot": False,
        }
        if failed:
            payload["error"] = _soft(
                "test did not reach: " + ", ".join(failed)
                + " — run bolt alerts status --probe for the fix"
            )
        if as_json:
            print(json.dumps(payload, indent=2))
        else:
            print("Bolt alerts test")
            _print_results(results, chosen)
            if failed:
                print(payload["error"], file=sys.stderr)
            print("  (Discord stays off here — use: bolt discord test)")
        return 0
    except Exception as exc:
        msg = _soft(f"test failed ({exc})")
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0


def try_send(message: str, *, as_json: bool = False, chosen: Optional[Dict[str, bool]] = None) -> int:
    """Soft-fail send. Empty message → soft-fail."""
    chosen = chosen or {c: True for c in CHANNELS}
    try:
        text = (message or "").strip()
        if not text:
            msg = _soft('empty message — try: bolt alerts send "Stream starts in 10"')
            if as_json:
                print(json.dumps({"ok": False, "error": msg}, indent=2))
            else:
                print(msg, file=sys.stderr)
            return 0
        info = status()
        if not info.get("ready"):
            msg = info.get("error") or _soft("no alert channel ready")
            if as_json:
                print(json.dumps({"ok": False, "error": msg, "results": {}}, indent=2))
            else:
                print(msg, file=sys.stderr)
            return 0
        results = _fanout(text, title="Bolt", chosen=chosen)
        any_ok = any(bool(results.get(c)) for c in CHANNELS if chosen.get(c, True))
        payload = {
            "ok": any_ok,
            "results": results,
            "readiness": info.get("readiness"),
            "is_discord_bot": False,
        }
        if not any_ok:
            payload["error"] = _soft("send reached no channel")
        if as_json:
            print(json.dumps(payload, indent=2))
        else:
            print("Bolt alert sent" if any_ok else payload["error"])
            _print_results(results, chosen)
        return 0
    except Exception as exc:
        msg = _soft(f"send failed ({exc})")
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0


def _yn(v: Any) -> str:
    return "yes" if v else "no"


def print_status(*, as_json: bool = False, probe: bool = False, banner_probe: bool = False) -> int:
    try:
        info = status(probe=probe, banner_probe=banner_probe)
        if as_json:
            print(json.dumps(info, indent=2, default=str))
            return 0
        ch = info.get("channels") or {}
        v = info.get("voice") or {}
        print(f"Bolt alerts — {info.get('readiness')}")
        print(f"  Mac banner : {_yn(info.get('mac_ready'))}")
        if v.get("muted") or not v.get("speak_enabled"):
            vline = "off (Bolt_VOICE_MUTE / BOLT_ALERT_SPEAK)"
        elif v.get("elevenlabs_configured"):
            vline = f"William's ElevenLabs voice, then {v.get('fallback_voice')}"
        else:
            vline = f"{v.get('fallback_voice')} (ElevenLabs not set)"
        if v.get("siri_voice_blocked"):
            vline += " · Bolt_VOICE is a Siri voice — ignored"
        print(f"  Voice      : {vline}  (never Siri)")
        print(f"  iMessage   : {_yn(info.get('sms_ready'))} · via {info.get('sms_path')}")
        print(f"  Email      : {_yn(info.get('email_ready'))}")
        print(f"  Discord    : off (use bolt discord)")
        if info.get("alert_env_file"):
            print(f"  config     : {info['alert_env_file']}")
        print(f"  log        : {info.get('alert_log')}")
        if info.get("probe"):
            sp = info.get("smtp_probe") or {}
            ep = info.get("elevenlabs_probe") or {}
            print(f"  probe smtp : {'ok' if sp.get('ok') else 'FAILED'} — {sp.get('detail')}")
            emark = "ok" if ep.get("ok") else ("?" if ep.get("ok") is None else "FAILED")
            print(f"  probe 11labs: {emark} — {ep.get('detail')}")
        if "probe_ok" in info:
            print(f"  banner probe: {info.get('probe_ok')} · {info.get('probe_detail')}")
        if info.get("error"):
            print(f"  → {info['error']}")
        elif info.get("hint"):
            print(f"  → {info['hint']}")
        return 0
    except Exception as exc:
        msg = _soft(f"status print failed ({exc})")
        if as_json:
            print(json.dumps({"ready": False, "error": msg, "readiness": "PARTIAL"}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help", "help"):
        print(
            """bolt alerts — Mac banner / voice / iMessage / email alerts (READY)

  bolt alerts                                      # status (default)
  bolt alerts status [--json] [--probe] [--banner]
      --probe   silent checks: SMTP login + ElevenLabs voice (sends nothing)
      --banner  show one test banner only
  bolt alerts list [--json]
  bolt alerts test [channel flags] [--json]        # one test alert
  bolt alerts send "message" [channel flags] [--json]

Channel flags: --only mac,voice,sms,email · --no-mac · --no-speak · --no-sms · --no-email
  e.g. bolt alerts test --no-sms   (banner + one spoken line + one email)

Voice: William's ElevenLabs voice first, then Nathan (Enhanced). Never Siri.
Config: Data/configs/storage_alerts.env (SMTP_*, ALERT_EMAIL, ALERT_PHONE, CARRIER).
Log: logs/alerts.jsonl. Soft-fail: "Alerts unavailable:".
Not a Discord bot — use bolt discord for webhooks.
budget --test-alert still works (same module).
"""
        )
        return 0

    json_out = "--json" in args
    probe = "--probe" in args
    banner_probe = "--banner" in args and not any(
        a in ("test", "send", "notify", "message", "probe-send", "selftest") for a in args
    )
    chosen = _parse_channels(args)
    positionals = _strip_channel_args(args)
    if not positionals:
        return print_status(as_json=json_out, probe=probe, banner_probe=banner_probe)

    cmd = positionals[0].lower()
    if cmd in ("status", "check", "ready"):
        return print_status(as_json=json_out, probe=probe, banner_probe=banner_probe)
    if cmd in ("list", "ls", "channels", "checklist"):
        return list_items(as_json=json_out)
    if cmd in ("test", "probe-send", "selftest"):
        return try_test(as_json=json_out, chosen=chosen)
    if cmd in ("send", "notify", "message"):
        msg = " ".join(positionals[1:]).strip()
        return try_send(msg, as_json=json_out, chosen=chosen)

    print(f"unknown alerts action: {cmd}", file=sys.stderr)
    print(
        "  try: bolt alerts status|list|test|send [--json] [--probe] [--no-sms] [--only …]",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
