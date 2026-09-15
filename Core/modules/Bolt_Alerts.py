#!/usr/bin/env python3
"""
Bolt_Alerts.py — SMS + email + Mac banner notifications (no Discord)
====================================================================
Preferred channels for budget and system alerts.

Soft-fail CLI (PARTIAL): ``bolt alerts`` status / list / test / send
Prefix: ``Alerts unavailable:``. Discord webhooks stay on ``bolt discord``.

SMS uses carrier email-to-SMS via scripts/send_notification.py
(requires SMTP_* in Data/configs/storage_alerts.env or .env).

Mac banner uses osascript display notification (always free, local).

Env:
  BOLT_ALERT_SMS=true|false     (default true)
  BOLT_ALERT_EMAIL=true|false   (default true)
  BOLT_ALERT_MAC=true|false     (default true)
  BOLT_ALERT_SPEAK=true|false   (default true)
  BOLT_ALERT_IMESSAGE=true|false (default true)
  BOLT_ALERT_DISCORD=false      (default false — kept off on purpose)

  bolt alerts                         # status (default)
  bolt alerts status [--json] [--probe]
  bolt alerts list [--json]
  bolt alerts test [--json]           # soft-fail fan-out test
  bolt alerts send "msg" [--json]

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
    _REPO / ".env",
)
_SEND_SCRIPT = _REPO / "scripts" / "send_notification.py"


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
    """Load storage_alerts.env from post-reorg or legacy paths."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for candidate in _ALERT_ENV_CANDIDATES:
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


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Alert-channel readiness. Never raises. PARTIAL — SMTP/phone gate SMS/email."""
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

        mac_ok = bool(ch.get("mac_banner")) and is_darwin and osascript
        email_ok = bool(ch.get("email_enabled") and ch.get("smtp_configured") and ch.get("alert_email_set"))
        sms_ok = bool(ch.get("sms_enabled") and ch.get("smtp_configured") and ch.get("alert_phone_set"))
        # Local Mac banner alone is enough for a usable status surface
        ready = bool(mac_ok or email_ok or sms_ok)

        missing: List[str] = []
        if not is_darwin:
            missing.append("not macOS (Darwin) — Mac banner/Voice unavailable")
        if ch.get("mac_banner") and is_darwin and not osascript:
            missing.append("osascript missing")
        if ch.get("email_enabled") and not ch.get("smtp_configured"):
            missing.append("SMTP not configured (storage_alerts.env)")
        if ch.get("email_enabled") and not ch.get("alert_email_set"):
            missing.append("ALERT_EMAIL unset")
        if ch.get("sms_enabled") and not ch.get("alert_phone_set"):
            missing.append("ALERT_PHONE unset")
        if not send_script_present:
            missing.append("missing scripts/send_notification.py")

        if ready:
            error = None
            hint = (
                "Mac / Voice / email / iMessage path present. "
                "Try: bolt alerts test · Discord stays bolt discord"
            )
            if not email_ok and ch.get("email_enabled"):
                hint += " · email gated until SMTP + ALERT_EMAIL"
            if not sms_ok and ch.get("sms_enabled"):
                hint += " · SMS gated until SMTP + ALERT_PHONE"
        else:
            error = _soft("; ".join(missing[:3]) if missing else "no alert channel ready")
            hint = error

        out: Dict[str, Any] = {
            "checked_at": _utc_now(),
            "ready": ready,
            "partial": True,
            "readiness": "PARTIAL",
            "is_discord_bot": False,
            "discord_default_off": True,
            "soft_fail_prefix": _SOFT,
            "darwin": is_darwin,
            "platform": platform.system(),
            "osascript_present": osascript,
            "say_present": say_cli,
            "send_script_present": send_script_present,
            "alert_env_file": env_file,
            "channels": ch,
            "mac_ready": mac_ok,
            "email_ready": email_ok,
            "sms_ready": sms_ok,
            "missing": missing,
            "error": error,
            "hint": hint,
        }

        if probe:
            out["probe"] = True
            # Probe = local Mac banner only (never SMS/email spam on status --probe)
            if not is_darwin or not ch.get("mac_banner"):
                out["probe_ok"] = False
                out["probe_detail"] = _soft("Mac banner probe skipped (not Darwin or disabled)")
            else:
                try:
                    ok = mac_banner(
                        "Bolt alerts probe",
                        "status --probe (banner only; no SMS/email)",
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
        rows = [
            ("platform_darwin", bool(info.get("darwin"))),
            ("osascript (Mac banner)", bool(info.get("osascript_present"))),
            ("say (Voice 3)", bool(info.get("say_present"))),
            ("mac_banner enabled", bool(ch.get("mac_banner"))),
            ("speak enabled", bool(ch.get("speak_enabled"))),
            ("email enabled", bool(ch.get("email_enabled"))),
            ("sms enabled", bool(ch.get("sms_enabled"))),
            ("imessage enabled", bool(ch.get("imessage_enabled"))),
            ("discord enabled (default off)", bool(ch.get("discord_enabled"))),
            ("SMTP configured", bool(ch.get("smtp_configured"))),
            ("ALERT_EMAIL set", bool(ch.get("alert_email_set"))),
            ("ALERT_PHONE set", bool(ch.get("alert_phone_set"))),
            ("scripts/send_notification.py", bool(info.get("send_script_present"))),
            ("storage_alerts.env / .env present", bool(info.get("alert_env_file"))),
            ("is Discord bot (never)", False),
        ]
        if as_json:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "readiness": "PARTIAL",
                        "is_discord_bot": False,
                        "items": [{"name": n, "ok": ok} for n, ok in rows],
                        "hint": info.get("hint"),
                        "error": info.get("error"),
                    },
                    indent=2,
                )
            )
            return 0
        print("Alert channels (PARTIAL — Mac/Voice/email/iMessage; not Discord)")
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


def try_test(*, as_json: bool = False) -> int:
    """Soft-fail fan-out test (Mac + SMS + email). Never raises."""
    try:
        info = status()
        if not info.get("ready"):
            msg = info.get("error") or _soft("no alert channel ready")
            payload = {"ok": False, "error": msg, "readiness": "PARTIAL", "results": {}}
            if as_json:
                print(json.dumps(payload, indent=2))
            else:
                print(msg, file=sys.stderr)
            return 0

        results = notify(
            "Bolt alerts test — if you got this, Mac/SMS/email paths are working.",
            title="Bolt test",
            subject="Bolt alert test",
            email_body=(
                "Bolt alerts test.\n\n"
                "If you see this email, SMTP is working.\n"
                "SMS uses the same path via your carrier gateway / iMessage.\n"
            ),
        )
        any_ok = any(bool(v) for v in results.values())
        payload: Dict[str, Any] = {
            "ok": any_ok,
            "results": results,
            "readiness": "PARTIAL",
            "is_discord_bot": False,
            "hint": info.get("hint"),
        }
        if not any_ok:
            payload["error"] = _soft(
                "test sent to no channel — check SMTP / ALERT_* / Mac notification permission"
            )
        if as_json:
            print(json.dumps(payload, indent=2))
        else:
            if any_ok:
                print("Bolt alerts test finished")
                print(f"  results: {results}")
            else:
                print(payload["error"], file=sys.stderr)
                print(f"  results: {results}", file=sys.stderr)
            print("  Discord stays off here — use: bolt discord test")
        return 0
    except Exception as exc:
        msg = _soft(f"test failed ({exc})")
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0


def try_send(message: str, *, as_json: bool = False) -> int:
    """Soft-fail send. Empty message → soft-fail."""
    try:
        text = (message or "").strip()
        if not text:
            msg = _soft("empty message")
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
        results = notify(text, title="Bolt")
        any_ok = any(bool(v) for v in results.values())
        payload = {
            "ok": any_ok,
            "results": results,
            "readiness": "PARTIAL",
            "is_discord_bot": False,
        }
        if not any_ok:
            payload["error"] = _soft("send reached no channel")
        if as_json:
            print(json.dumps(payload, indent=2))
        else:
            if any_ok:
                print(f"sent: {results}")
            else:
                print(payload["error"], file=sys.stderr)
                print(f"  results: {results}", file=sys.stderr)
        return 0
    except Exception as exc:
        msg = _soft(f"send failed ({exc})")
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0


def print_status(*, as_json: bool = False, probe: bool = False) -> int:
    try:
        info = status(probe=probe)
        if as_json:
            print(json.dumps(info, indent=2, default=str))
            return 0
        ch = info.get("channels") or {}
        print("Bolt alerts readiness (PARTIAL)")
        print(f"  ready: {info.get('ready')}")
        print(
            f"  readiness: {info.get('readiness')} · discord_bot: {info.get('is_discord_bot')}"
        )
        print(
            f"  mac: {info.get('mac_ready')} · email: {info.get('email_ready')} · "
            f"sms: {info.get('sms_ready')}"
        )
        print(
            f"  flags: mac={ch.get('mac_banner')} speak={ch.get('speak_enabled')} "
            f"email={ch.get('email_enabled')} sms={ch.get('sms_enabled')} "
            f"discord={ch.get('discord_enabled')}"
        )
        print(
            f"  smtp: {ch.get('smtp_configured')} · ALERT_EMAIL: {ch.get('alert_email_set')} · "
            f"ALERT_PHONE: {ch.get('alert_phone_set')}"
        )
        if ch.get("phone_path"):
            print(f"  phone path: {ch.get('phone_path')}")
        if info.get("alert_env_file"):
            print(f"  env file: {info['alert_env_file']}")
        if info.get("probe"):
            print(f"  probe_ok: {info.get('probe_ok')} · {info.get('probe_detail')}")
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
            """bolt alerts — Mac / Voice / email / iMessage readiness (PARTIAL)

  bolt alerts                                      # status (default)
  bolt alerts status [--json] [--probe]
  bolt alerts list [--json]
  bolt alerts test [--json]
  bolt alerts send "message" [--json]

Soft-fail: "Alerts unavailable:".
Not a Discord bot — use bolt discord for webhooks.
budget --test-alert still works (same module).
"""
        )
        return 0

    json_out = "--json" in args
    probe = "--probe" in args
    positionals = [a for a in args if not a.startswith("-")]
    if not positionals:
        return print_status(as_json=json_out, probe=probe)

    cmd = positionals[0].lower()
    if cmd in ("status", "check", "ready"):
        return print_status(as_json=json_out, probe=probe)
    if cmd in ("list", "ls", "channels", "checklist"):
        return list_items(as_json=json_out)
    if cmd in ("test", "probe-send", "selftest"):
        return try_test(as_json=json_out)
    if cmd in ("send", "notify", "message"):
        msg = " ".join(positionals[1:]).strip()
        # Allow: bolt alerts send -- "…" already stripped of flags
        if not msg:
            # leftover after removing flags might be empty
            msg = ""
        return try_send(msg, as_json=json_out)

    # Bare message after unknown? treat first token as send if it looks like text
    # Prefer explicit send. Unknown → soft help.
    print(f"unknown alerts action: {cmd}", file=sys.stderr)
    print(
        "  try: bolt alerts status|list|test|send [--json] [--probe]",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
