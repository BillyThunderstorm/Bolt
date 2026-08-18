#!/usr/bin/env python3
"""
Bolt_Alerts.py — SMS + email + Mac banner notifications (no Discord)
====================================================================
Preferred channels for budget and system alerts.

SMS uses carrier email-to-SMS via scripts/send_notification.py
(requires SMTP_* in Data/configs/storage_alerts.env or .env).

Mac banner uses osascript display notification (always free, local).

Env:
  BOLT_ALERT_SMS=true|false     (default true)
  BOLT_ALERT_EMAIL=true|false   (default true)
  BOLT_ALERT_MAC=true|false     (default true)
  BOLT_ALERT_DISCORD=false      (default false — kept off on purpose)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

_REPO = Path(__file__).resolve().parents[2]


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() not in ("0", "false", "no", "off")


def _load_alert_env() -> None:
    """Load storage_alerts.env from post-reorg or legacy paths."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for candidate in (
        _REPO / "Data" / "configs" / "storage_alerts.env",
        _REPO / "configs" / "storage_alerts.env",
        _REPO / ".env",
    ):
        if candidate.exists():
            load_dotenv(candidate, override=False)


def _speak_alert(text: str) -> bool:
    """Speak an alert with Siri Voice 3 — same voice as bolt say / briefings."""
    if not _env_bool("BOLT_ALERT_SPEAK", True):
        return False
    spoken = " ".join((text or "").split())
    if not spoken:
        return False
    try:
        from modules.Bolt_Voice import macos_say

        return macos_say(spoken[:280])
    except Exception:
        pass
    voice = os.getenv("Bolt_VOICE") or os.getenv("BOLT_VOICE") or "Voice 3"
    try:
        r = subprocess.run(
            ["say", "-v", voice, spoken[:280]],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return r.returncode == 0
    except Exception:
        return False


def mac_banner(
    title: str,
    message: str,
    subtitle: str = "Bolt",
    *,
    speak: bool = True,
) -> bool:
    """Show a native macOS Notification Center banner, spoken in Voice 3."""
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


def notify(
    message: str,
    *,
    title: str = "Bolt",
    subject: Optional[str] = None,
    sms: bool = True,
    email: bool = True,
    banner: bool = True,
    email_body: Optional[str] = None,
) -> dict:
    """
    Fan-out alert to Mac banner + SMS + email (never Discord by default).

    Returns channel success map.
    """
    _load_alert_env()
    results = {"mac": False, "sms": False, "email": False}
    short = (message or "").strip()
    if not short:
        return results

    if banner:
        results["mac"] = mac_banner(title, short)

    if sms:
        results["sms"] = send_sms(f"{title}: {short}"[:160])

    if email:
        results["email"] = send_email(
            subject or f"{title} alert",
            email_body or short,
        )

    return results


def smtp_configured() -> bool:
    _load_alert_env()
    return bool(os.getenv("SMTP_USERNAME") and os.getenv("SMTP_PASSWORD"))


def channels_status() -> dict:
    _load_alert_env()
    carrier = (os.getenv("CARRIER") or "").lower().strip()
    att_gateway_dead = carrier in ("att", "att-sms", "cricket", "firstnet")
    return {
        "mac_banner": _env_bool("BOLT_ALERT_MAC", True),
        "sms_enabled": _env_bool("BOLT_ALERT_SMS", True),
        "email_enabled": _env_bool("BOLT_ALERT_EMAIL", True),
        "imessage_enabled": _env_bool("BOLT_ALERT_IMESSAGE", True),
        "discord_enabled": _env_bool("BOLT_ALERT_DISCORD", False),
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


if __name__ == "__main__":
    import json

    print(json.dumps(channels_status(), indent=2))
    if "--test" in sys.argv:
        print(notify("Test alert from Bolt_Alerts", title="Bolt test"))
