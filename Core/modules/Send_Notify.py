#!/usr/bin/env python3
"""
Send_Notify.py — ``bolt send`` / ``bolt notify`` (READY, 20 Oct 2026)
=====================================================================
Send yourself a quick text (iMessage via Messages on this Mac) and/or an
email. Goes through ``modules.Bolt_Alerts`` (same delivery code as
``bolt alerts`` / weekly ``--send``), so it is logged to
``logs/alerts.jsonl``. Falls back to ``scripts/send_notification.py`` only
when Bolt_Alerts can't be imported. Soft-fail prefix ``Notify unavailable:``.

CLI (via ``bolt send`` / ``bolt notify``):
  status [--json] [--probe]          --probe logs in to Gmail SMTP, sends nothing
  list   [--json]
  send   "message" [--subject S] [--sms-only|--email-only] [--banner] [--speak]
         [--dry-run] [--json]
  run    "message" …                 alias of send

Bare ``bolt send`` → status (safe). Legacy ``bolt send "msg"`` still sends.

Default channels are text + email only (quiet: no banner, no spoken line).
Add ``--banner`` / ``--speak`` for those, or use ``bolt alerts send`` for the
full fan-out. Settings: ``Data/configs/storage_alerts.env`` (ALERT_PHONE,
ALERT_EMAIL, SMTP_USERNAME, SMTP_PASSWORD; BOLT_ALERT_SMS / BOLT_ALERT_EMAIL /
BOLT_ALERT_IMESSAGE=false turn a channel off). Distinct from READY
``bolt alerts`` and READY ``bolt discord`` (webhooks; not a bot).
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SOFT = "Notify unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_ENGINE = _REPO / "scripts" / "send_notification.py"
_ENV_CANDIDATES = (
    _REPO / "Data" / "configs" / "storage_alerts.env",
    _REPO / "configs" / "storage_alerts.env",
)
_ENV_EXAMPLE = _REPO / "Data" / "configs" / "storage_alerts.example.env"
_ALERTS_MOD = _REPO / "Core" / "modules" / "Bolt_Alerts.py"
_ALERT_LOG = _REPO / "logs" / "alerts.jsonl"
_DEAD_GATEWAYS = {"att", "att-sms", "cricket", "firstnet"}
_APP_PW_URL = "https://myaccount.google.com/apppasswords"


def _soft(msg: str) -> str:
    return msg if msg.startswith(_SOFT) else f"{_SOFT} {msg}"


def _iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _env_path() -> Path:
    for p in _ENV_CANDIDATES:
        if p.is_file():
            return p
    return _ENV_CANDIDATES[0]


def _flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")


def _try_import_alerts():
    core = str(_REPO / "Core")
    if core not in sys.path:
        sys.path.insert(0, core)
    try:
        from modules import Bolt_Alerts as ba  # type: ignore

        return ba
    except Exception:
        return None


def _load_env(alerts=None) -> None:
    """Same env order as Bolt_Alerts: storage_alerts.env, .env.local, .env."""
    if alerts is not None and hasattr(alerts, "_load_alert_env"):
        try:
            alerts._load_alert_env()
        except Exception:
            pass
    # Always also read the files ourselves (never overrides what's set), so a
    # Python without python-dotenv still sees the settings.
    for path in (_env_path(), _REPO / ".env.local", _REPO / ".env"):
        if not path.is_file():
            continue
        try:
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
        except Exception:
            pass


def _load_engine():
    scripts = str(_REPO / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    if not _ENGINE.is_file():
        raise FileNotFoundError(f"missing {_ENGINE}")
    spec = importlib.util.spec_from_file_location("bolt_send_notification", _ENGINE)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {_ENGINE}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mask_email(addr: str) -> str:
    if "@" not in addr:
        return "set" if addr else ""
    user, _, dom = addr.partition("@")
    return f"{user[:2]}…@{dom}"


def _mask_phone(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    return f"…{digits[-4:]}" if len(digits) >= 4 else ("set" if phone else "")


def _channel_info(alerts=None) -> Dict[str, Dict[str, Any]]:
    """Plain-words readiness for the text and email channels (no sending)."""
    _load_env(alerts)
    smtp_user = os.getenv("SMTP_USERNAME") or os.getenv("SMTP_USER") or ""
    smtp_pw = os.getenv("SMTP_PASSWORD") or os.getenv("SMTP_PASS") or ""
    to_email = os.getenv("ALERT_EMAIL") or os.getenv("EMAIL_TO") or ""
    phone = os.getenv("ALERT_PHONE") or os.getenv("SMS_TO") or ""
    carrier = (os.getenv("CARRIER") or os.getenv("SMS_CARRIER") or "").lower().strip()
    imessage_on = _flag("BOLT_ALERT_IMESSAGE", True)
    env = _env_path()

    email: Dict[str, Any] = {"ok": False, "to": _mask_email(to_email), "fix": ""}
    if not _flag("BOLT_ALERT_EMAIL", True):
        email["fix"] = "email is turned off (BOLT_ALERT_EMAIL=false in storage_alerts.env)"
    elif not to_email:
        email["fix"] = f"add ALERT_EMAIL=you@example.com to {env}"
    elif not (smtp_user and smtp_pw):
        email["fix"] = (
            f"add SMTP_USERNAME and SMTP_PASSWORD (a Gmail App Password, {_APP_PW_URL}) to {env}"
        )
    else:
        email["ok"] = True
        email["detail"] = f"to {_mask_email(to_email)} via {os.getenv('SMTP_SERVER', 'smtp.gmail.com')}"

    sms: Dict[str, Any] = {"ok": False, "to": _mask_phone(phone), "fix": ""}
    if not _flag("BOLT_ALERT_SMS", True):
        sms["fix"] = "texts are turned off (BOLT_ALERT_SMS=false in storage_alerts.env)"
    elif not phone:
        sms["fix"] = f"add ALERT_PHONE=5551234567 to {env}"
    elif imessage_on:
        sms["ok"] = True
        sms["detail"] = f"iMessage to {_mask_phone(phone)} via Messages on this Mac (Messages must be signed in)"
    elif carrier in _DEAD_GATEWAYS:
        sms["fix"] = (
            f"carrier '{carrier}' email-to-text shut down in 2025 and iMessage is off — "
            "set BOLT_ALERT_IMESSAGE=true and sign in to Messages"
        )
    elif smtp_user and smtp_pw and carrier:
        sms["ok"] = True
        sms["detail"] = f"carrier email-to-text ({carrier}) to {_mask_phone(phone)}"
    else:
        sms["fix"] = "set BOLT_ALERT_IMESSAGE=true (Messages signed in) or a working CARRIER + SMTP login"
    return {"sms": sms, "email": email}


def status(*, probe: bool = False) -> Dict[str, Any]:
    alerts = _try_import_alerts()
    ch = _channel_info(alerts)
    any_channel = ch["sms"]["ok"] or ch["email"]["ok"]
    delivery_ok = alerts is not None or _ENGINE.is_file()
    info: Dict[str, Any] = {
        "checked_at": _iso(),
        "readiness": "READY",
        "ready": bool(delivery_ok and any_channel),
        "soft_fail_prefix": _SOFT,
        "cli": "bolt send",
        "via": "Bolt_Alerts" if alerts is not None else ("scripts/send_notification.py" if _ENGINE.is_file() else ""),
        "alerts_import_ok": alerts is not None,
        "engine_present": _ENGINE.is_file(),
        "env_path": str(_env_path()),
        "env_present": _env_path().is_file(),
        "env_example": str(_ENV_EXAMPLE),
        "channels": ch,
        "default_channels": "text + email (add --banner / --speak)",
        "log": str(_ALERT_LOG),
        "probe": bool(probe),
        "probe_result": None,
        "error": "",
        "hint": 'bolt send "message" · --sms-only / --email-only · --dry-run shows what would go out',
    }
    if not delivery_ok:
        info["error"] = _soft("Bolt_Alerts won't import and scripts/send_notification.py is missing")
    elif not info["env_present"]:
        info["error"] = _soft(
            f"no settings file — copy {_ENV_EXAMPLE.name} to {_env_path()} and fill in ALERT_PHONE / ALERT_EMAIL / SMTP_*"
        )
    elif not any_channel:
        info["error"] = _soft(f"no channel set up — text: {ch['sms']['fix']}; email: {ch['email']['fix']}")
    if probe and ch["email"]["ok"]:
        try:
            if alerts is not None and hasattr(alerts, "_probe_smtp"):
                info["probe_result"] = alerts._probe_smtp()
            else:
                info["probe_result"] = {"ok": None, "detail": "SMTP probe needs Bolt_Alerts"}
        except Exception as exc:
            info["probe_result"] = {"ok": False, "detail": f"{type(exc).__name__}: {exc}"[:200]}
        if info["probe_result"] and info["probe_result"].get("ok") is False:
            ch["email"]["ok"] = False
            ch["email"]["fix"] = info["probe_result"].get("detail", "")
    return info


def list_items() -> List[Dict[str, Any]]:
    st = status(probe=False)
    ch = st["channels"]
    return [
        {"id": "delivery", "ok": bool(st["via"]), "detail": st["via"] or "missing"},
        {"id": "settings", "ok": st["env_present"], "detail": st["env_path"]},
        {"id": "text", "ok": ch["sms"]["ok"], "detail": ch["sms"].get("detail") or ch["sms"]["fix"]},
        {"id": "email", "ok": ch["email"]["ok"], "detail": ch["email"].get("detail") or ch["email"]["fix"]},
        {"id": "log", "ok": True, "detail": st["log"]},
    ]


def _pick(sms_only: bool, email_only: bool, banner: bool, speak: bool) -> Dict[str, bool]:
    if sms_only and email_only:
        sms_only = email_only = False  # both flags = both channels
    return {
        "sms": not email_only,
        "email": not sms_only,
        "banner": bool(banner),
        "speak": bool(speak),
    }


def try_send(
    message: str,
    *,
    subject: str = "Bolt Notification",
    sms_only: bool = False,
    email_only: bool = False,
    banner: bool = False,
    speak: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Send to the chosen channels. Never raises; ``ok`` = at least one delivered."""
    text = (message or "").strip()
    subject = (subject or "").strip() or "Bolt Notification"
    chosen = _pick(sms_only, email_only, banner, speak)
    out: Dict[str, Any] = {
        "ok": False,
        "dry_run": bool(dry_run),
        "chosen": chosen,
        "results": {},
        "failed": {},
        "via": "",
        "error": "",
        "details": [],
    }
    if not text:
        out["error"] = _soft('message required (try: bolt send "Stream starts in 10")')
        return out

    alerts = _try_import_alerts()
    ch = _channel_info(alerts)
    # Skip channels that can't work, with the reason, before trying anything.
    for name in ("sms", "email"):
        if chosen[name] and not ch[name]["ok"]:
            out["failed"][name] = ch[name]["fix"]
            chosen = dict(chosen, **{name: False})
    if not any(chosen.values()):
        out["error"] = _soft("nothing to send to — " + "; ".join(f"{k}: {v}" for k, v in out["failed"].items()))
        return out

    sms_text = f"Bolt: {text}"[:160]
    if dry_run:
        out["ok"] = True
        out["via"] = "dry-run"
        out["would_send"] = {
            k: v
            for k, v in {
                "sms": f"text to {ch['sms']['to']}: {sms_text}" if chosen["sms"] else None,
                "email": f"email to {ch['email']['to']} — subject {subject!r}" if chosen["email"] else None,
                "banner": "Mac banner" if chosen["banner"] else None,
                "speak": "spoken line (ElevenLabs, then Nathan)" if chosen["speak"] else None,
            }.items()
            if v
        }
        return out

    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            if alerts is not None and hasattr(alerts, "notify"):
                out["via"] = "Bolt_Alerts"
                res = alerts.notify(
                    text,
                    title="Bolt",
                    subject=subject,
                    sms=chosen["sms"],
                    email=chosen["email"],
                    banner=chosen["banner"],
                    speak=chosen["speak"],
                )
                results = {
                    "sms": bool(res.get("sms")),
                    "email": bool(res.get("email")),
                    "banner": bool(res.get("mac")),
                    "speak": res.get("voice") or "",
                }
            else:
                out["via"] = "scripts/send_notification.py"
                eng = _load_engine()
                results = {
                    "sms": bool(eng.send_sms(sms_text)) if chosen["sms"] else False,
                    "email": bool(eng.send_email(subject, text)) if chosen["email"] else False,
                    "banner": False,
                    "speak": "",
                }
    except Exception as exc:
        out["details"] = [l for l in buf.getvalue().splitlines() if l.strip()]
        out["error"] = _soft(f"send crashed ({type(exc).__name__}: {exc})"[:300])
        return out

    out["details"] = [l for l in buf.getvalue().splitlines() if l.strip()]
    out["results"] = {k: v for k, v in results.items() if chosen.get(k)}
    hints = {
        "sms": "Messages didn't send it — open Messages on this Mac and check you're signed in to iMessage",
        "email": f"Gmail didn't accept it — run `bolt send status --probe`; you may need a new App Password ({_APP_PW_URL})",
        "banner": "banner didn't show — check System Settings > Notifications for Script Editor / terminal",
        "speak": "nothing spoke — check `bolt alerts status` (ElevenLabs key / Nathan voice)",
    }
    for name, val in out["results"].items():
        if not val:
            out["failed"][name] = hints[name]
    out["ok"] = any(bool(v) for v in out["results"].values())
    if not out["ok"]:
        out["error"] = _soft("nothing was delivered — " + "; ".join(f"{k}: {v}" for k, v in out["failed"].items()))
    return out


def _print_status(info: Dict[str, Any], as_json: bool) -> int:
    if as_json:
        print(json.dumps(info, indent=2))
        return 0
    ch = info["channels"]
    print(f"bolt send: {info['readiness']} · {'ready' if info['ready'] else 'not ready'}")
    for label, key in (("text ", "sms"), ("email", "email")):
        c = ch[key]
        mark = "ok " if c["ok"] else "no "
        print(f"  {label} {mark} {c.get('detail') or c['fix']}")
    pr = info.get("probe_result")
    if info.get("probe"):
        if pr is None:
            print("  probe  skipped (email not set up)")
        else:
            print(f"  probe  {'ok ' if pr.get('ok') else 'no '} {pr.get('detail')}")
    print(f"  default: {info['default_channels']} · log: logs/alerts.jsonl")
    if info.get("error"):
        print(f"  {info['error']}")
    else:
        print(f"  try: {info['hint']}")
    return 0


def _print_send(result: Dict[str, Any]) -> None:
    if result.get("dry_run") and result.get("ok"):
        print("Dry run — nothing sent. Would send:")
        for v in (result.get("would_send") or {}).values():
            print(f"  • {v}")
    elif result.get("ok"):
        sent = [k for k, v in result["results"].items() if v]
        names = {"sms": "text", "email": "email", "banner": "banner", "speak": "voice"}
        print("Sent: " + ", ".join(names[k] for k in sent))
    else:
        print(result.get("error") or _soft("nothing was delivered"))
    for name, why in (result.get("failed") or {}).items():
        if result.get("ok"):
            print(f"  not sent ({name}): {why}")


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    known = ("status", "list", "send", "run", "-h", "--help")
    if argv and argv[0] not in known:
        if argv[0] in ("--json", "--probe"):
            argv = ["status"] + argv
        else:
            argv = ["send"] + argv  # legacy: bolt send "msg" / bolt send --sms-only "msg"

    parser = argparse.ArgumentParser(prog="bolt send", description="Text and/or email yourself (READY)")
    sub = parser.add_subparsers(dest="cmd")
    p_status = sub.add_parser("status", help="what's set up (--probe logs in to Gmail, sends nothing)")
    p_status.add_argument("--json", action="store_true")
    p_status.add_argument("--probe", action="store_true")
    p_list = sub.add_parser("list", help="checklist")
    p_list.add_argument("--json", action="store_true")
    for name in ("send", "run"):
        p = sub.add_parser(name, help="send a message" if name == "send" else "alias of send")
        p.add_argument("message", nargs="+", help="message text")
        p.add_argument("--subject", default="Bolt Notification")
        p.add_argument("--sms-only", action="store_true", help="text only")
        p.add_argument("--email-only", action="store_true", help="email only")
        p.add_argument("--banner", action="store_true", help="also show a Mac banner")
        p.add_argument("--speak", action="store_true", help="also say it out loud")
        p.add_argument("--dry-run", action="store_true", help="show what would be sent")
        p.add_argument("--json", action="store_true")

    if not argv:
        argv = ["status"]
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        if isinstance(e.code, int) and e.code != 0:
            print(_soft('bad args; try: bolt send status | bolt send "msg"'), file=sys.stderr)
        return 0

    cmd = args.cmd or "status"
    try:
        if cmd == "status":
            return _print_status(status(probe=args.probe), args.json)
        if cmd == "list":
            rows = list_items()
            if args.json:
                print(json.dumps(rows, indent=2))
            else:
                for row in rows:
                    print(f"[{'OK' if row['ok'] else 'NO'}] {row['id']}: {row['detail']}")
            return 0
        result = try_send(
            " ".join(args.message),
            subject=args.subject,
            sms_only=args.sms_only,
            email_only=args.email_only,
            banner=args.banner,
            speak=args.speak,
            dry_run=args.dry_run,
        )
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            _print_send(result)
        return 0
    except Exception as exc:
        print(_soft(f"{type(exc).__name__}: {exc}"))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
