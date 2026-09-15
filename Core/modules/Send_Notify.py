#!/usr/bin/env python3
"""
Send_Notify.py — soft-fail CLI for bolt send / notify (PARTIAL)
==============================================================
Soft-fail wrapper for SMS/email notifications. Prefers
``modules.Bolt_Alerts`` (same path as ``bolt alerts`` / weekly ``--send``);
falls back to ``scripts/send_notification.py``. Soft-fail prefix:
``Notify unavailable:``.

CLI (via ``bolt send`` / ``bolt notify``):
  status [--json] [--probe]
  list   [--json]
  send   "message" [--subject S] [--sms-only|--email-only]
  run    "message" …   # alias of send

Bare ``bolt send`` / ``bolt notify`` → status (safe).
Legacy ``bolt send "msg"`` (no subcommand) still sends.

Stay PARTIAL — SMTP / carrier-SMS / iMessage gated (needs
``Data/configs/storage_alerts.env``). **Distinct from PARTIAL**
``bolt alerts`` (full Mac/Voice/email/iMessage surface) and PARTIAL
``bolt discord`` (webhooks). Former thin SCRIPT_MAP ``send``/``notify``
→ ``scripts/send_notification.py`` (no soft-fail status/list/run).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SOFT = "Notify unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_ENGINE = _REPO / "scripts" / "send_notification.py"
_PATHS = _REPO / "scripts" / "_paths.py"
_ENV_CANDIDATES = (
    _REPO / "Data" / "configs" / "storage_alerts.env",
    _REPO / "configs" / "storage_alerts.env",
)
_ENV_EXAMPLE = _REPO / "Data" / "configs" / "storage_alerts.example.env"
_ALERTS_MOD = _REPO / "Core" / "modules" / "Bolt_Alerts.py"


def _soft(msg: str) -> str:
    if msg.startswith(_SOFT):
        return msg
    return f"{_SOFT} {msg}"


def _iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _env_path() -> Path:
    for p in _ENV_CANDIDATES:
        if p.is_file():
            return p
    return _ENV_CANDIDATES[0]


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
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


def _channel_flags() -> Dict[str, Any]:
    _load_dotenv(_env_path())
    smtp_user = bool(os.getenv("SMTP_USER") or os.getenv("SMTP_USERNAME"))
    smtp_pass = bool(os.getenv("SMTP_PASSWORD") or os.getenv("SMTP_PASS"))
    smtp_server = bool(os.getenv("SMTP_SERVER") or os.getenv("SMTP_HOST") or True)
    alert_email = bool(os.getenv("ALERT_EMAIL") or os.getenv("EMAIL_TO"))
    alert_phone = bool(os.getenv("ALERT_PHONE") or os.getenv("SMS_TO") or os.getenv("PHONE"))
    carrier = os.getenv("SMS_CARRIER") or os.getenv("ALERT_CARRIER") or ""
    return {
        "env_path": str(_env_path()),
        "env_present": _env_path().is_file(),
        "smtp_user": smtp_user,
        "smtp_password": smtp_pass,
        "smtp_server_configured": smtp_server,
        "alert_email": alert_email,
        "alert_phone": alert_phone,
        "sms_carrier": carrier,
        "email_ready": smtp_user and smtp_pass and alert_email,
        "sms_ready": smtp_user and smtp_pass and alert_phone,
    }


def _try_import_alerts():
    core = str(_REPO / "Core")
    if core not in sys.path:
        sys.path.insert(0, core)
    try:
        from modules import Bolt_Alerts as ba  # type: ignore

        return ba
    except Exception:
        return None


def _load_engine():
    scripts = str(_REPO / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    if not _ENGINE.is_file():
        raise FileNotFoundError(f"missing engine {_ENGINE}")
    spec = importlib.util.spec_from_file_location("bolt_send_notification", _ENGINE)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {_ENGINE}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def status(*, probe: bool = False) -> Dict[str, Any]:
    ch = _channel_flags()
    alerts = _try_import_alerts()
    info: Dict[str, Any] = {
        "checked_at": _iso(),
        "ready": False,
        "partial": True,
        "readiness": "PARTIAL",
        "soft_fail_prefix": _SOFT,
        "cli": "bolt send",
        "engine": str(_ENGINE),
        "engine_present": _ENGINE.is_file(),
        "paths_helper": str(_PATHS),
        "paths_present": _PATHS.is_file(),
        "alerts_module": str(_ALERTS_MOD),
        "alerts_module_present": _ALERTS_MOD.is_file(),
        "alerts_import_ok": alerts is not None,
        "env_example": str(_ENV_EXAMPLE),
        "env_example_present": _ENV_EXAMPLE.is_file(),
        "channels": ch,
        "probe": bool(probe),
        "probe_ok": None,
        "error": "",
        "hint": (
            "SMS/email via Bolt_Alerts (preferred) or scripts/send_notification.py · "
            "needs Data/configs/storage_alerts.env · distinct from bolt alerts / bolt discord · "
            "stay PARTIAL"
        ),
        "is_stranger_ready": False,
    }
    # ready = engine or alerts module present (config may still gate send)
    info["ready"] = bool(info["engine_present"] or info["alerts_module_present"])
    if not info["ready"]:
        info["error"] = _soft("missing Bolt_Alerts and send_notification.py")
    if probe and info["ready"]:
        try:
            if alerts is not None and hasattr(alerts, "status"):
                a = alerts.status()
                info["probe_ok"] = True
                info["alerts_status_ready"] = bool(a.get("ready") if isinstance(a, dict) else True)
            else:
                _load_engine()
                info["probe_ok"] = True
        except Exception as exc:
            info["probe_ok"] = False
            info["error"] = _soft(str(exc) or type(exc).__name__)
    return info


def list_items() -> List[Dict[str, Any]]:
    st = status(probe=False)
    ch = st.get("channels") or {}
    rows: List[Dict[str, Any]] = [
        {"id": "engine", "ok": st["engine_present"], "detail": st["engine"]},
        {"id": "paths", "ok": st["paths_present"], "detail": st["paths_helper"]},
        {
            "id": "alerts_module",
            "ok": st["alerts_module_present"],
            "detail": f"{st['alerts_module']} import_ok={st['alerts_import_ok']}",
        },
        {
            "id": "env",
            "ok": bool(ch.get("env_present")),
            "detail": f"{ch.get('env_path')} present={ch.get('env_present')}",
        },
        {
            "id": "email_channel",
            "ok": bool(ch.get("email_ready")),
            "detail": f"email_ready={ch.get('email_ready')} alert_email={ch.get('alert_email')}",
        },
        {
            "id": "sms_channel",
            "ok": bool(ch.get("sms_ready")),
            "detail": (
                f"sms_ready={ch.get('sms_ready')} phone={ch.get('alert_phone')} "
                f"carrier={ch.get('sms_carrier') or '-'}"
            ),
        },
        {
            "id": "soft_fail",
            "ok": True,
            "detail": (
                f"prefix {_SOFT!r}; stay PARTIAL; distinct from bolt alerts / bolt discord"
            ),
        },
    ]
    return rows


def try_send(
    message: str,
    *,
    subject: str = "Bolt Notification",
    sms_only: bool = False,
    email_only: bool = False,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "ok": False,
        "error": "",
        "exit_code": 0,
        "report": "",
        "via": "",
        "results": {},
    }
    if not (message or "").strip():
        out["error"] = _soft("message required (try: bolt send \"hello\")")
        return out

    st = status(probe=False)
    if not st.get("ready") and st.get("error"):
        out["error"] = st["error"]
        return out

    # Prefer Bolt_Alerts.notify when available
    alerts = _try_import_alerts()
    if alerts is not None and hasattr(alerts, "notify"):
        try:
            kwargs: Dict[str, Any] = {"title": subject, "subject": subject}
            if sms_only:
                kwargs["email"] = False
            if email_only:
                kwargs["sms"] = False
                kwargs["mac"] = False
                kwargs["voice"] = False
            # notify(message, ...) — tolerate signature variants
            try:
                result = alerts.notify(message, **kwargs)
            except TypeError:
                result = alerts.notify(message)
            out["via"] = "Bolt_Alerts.notify"
            out["results"] = result if isinstance(result, dict) else {"raw": result}
            out["ok"] = True
            out["report"] = f"sent via Bolt_Alerts: {out['results']}\n"
            return out
        except Exception as exc:
            # fall through to engine
            fallback_err = str(exc) or type(exc).__name__
    else:
        fallback_err = ""

    try:
        eng = _load_engine()
        out["via"] = "scripts/send_notification.py"
        ok_sms = ok_email = None
        if email_only:
            ok_email = bool(eng.send_email(subject, message))
        elif sms_only:
            ok_sms = bool(eng.send_sms(message))
        else:
            ok_sms = bool(eng.send_sms(message))
            ok_email = bool(eng.send_email(subject, message))
        out["results"] = {"sms": ok_sms, "email": ok_email}
        out["ok"] = bool(ok_sms or ok_email)
        if not out["ok"]:
            hint = fallback_err or "SMTP/phone not configured or send failed"
            out["error"] = _soft(hint)
            out["report"] = out["error"] + "\n"
        else:
            out["report"] = f"sent via engine: sms={ok_sms} email={ok_email}\n"
        return out
    except Exception as exc:
        out["ok"] = False
        msg = str(exc) or type(exc).__name__
        if fallback_err:
            msg = f"{fallback_err}; engine: {msg}"
        out["error"] = _soft(msg)
        out["report"] = traceback.format_exc()
        out["exit_code"] = 0
        return out


def _print_status(info: Dict[str, Any], as_json: bool) -> int:
    if as_json:
        print(json.dumps(info, indent=2))
    else:
        ready = "yes" if info.get("ready") else "no"
        print(f"send readiness: {info.get('readiness')}  ready={ready}")
        print(f"  engine:  {info.get('engine')}  present={info.get('engine_present')}")
        print(
            f"  alerts:  {info.get('alerts_module')}  "
            f"present={info.get('alerts_module_present')} "
            f"import_ok={info.get('alerts_import_ok')}"
        )
        ch = info.get("channels") or {}
        print(
            f"  env:     {ch.get('env_path')}  present={ch.get('env_present')} "
            f"email_ready={ch.get('email_ready')} sms_ready={ch.get('sms_ready')}"
        )
        if info.get("probe"):
            print(f"  probe_ok: {info.get('probe_ok')}")
        if info.get("error"):
            print(f"  {info['error']}")
        else:
            print(f"  hint: {info.get('hint')}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Bare flags / message → send (legacy thin SCRIPT_MAP passthrough)
    if argv and argv[0] not in (
        "status",
        "list",
        "send",
        "run",
        "-h",
        "--help",
    ):
        if argv[0].startswith("-") and argv[0] not in ("--json", "--probe"):
            # flags like --sms-only before message
            argv = ["send"] + argv
        elif argv[0] in ("--json", "--probe"):
            argv = ["status"] + argv
        else:
            # first token is the message (or start of it)
            argv = ["send"] + argv

    parser = argparse.ArgumentParser(
        prog="bolt send",
        description="SMS/email notify (PARTIAL; soft-fail Notify unavailable:)",
    )
    sub = parser.add_subparsers(dest="cmd")

    p_status = sub.add_parser("status", help="readiness")
    p_status.add_argument("--json", action="store_true")
    p_status.add_argument("--probe", action="store_true")

    p_list = sub.add_parser("list", help="checklist")
    p_list.add_argument("--json", action="store_true")

    p_send = sub.add_parser("send", help="send a message")
    p_send.add_argument("message", nargs="+", help="message text")
    p_send.add_argument("--subject", default="Bolt Notification")
    p_send.add_argument("--sms-only", action="store_true")
    p_send.add_argument("--email-only", action="store_true")
    p_send.add_argument("--json", action="store_true")

    p_run = sub.add_parser("run", help="alias of send")
    p_run.add_argument("message", nargs="+", help="message text")
    p_run.add_argument("--subject", default="Bolt Notification")
    p_run.add_argument("--sms-only", action="store_true")
    p_run.add_argument("--email-only", action="store_true")
    p_run.add_argument("--json", action="store_true")

    if not argv:
        argv = ["status"]

    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        # argparse help/error — soft-fail unknown for PARTIAL surface
        code = int(e.code) if isinstance(e.code, int) else 0
        if code != 0:
            print(_soft("bad args; try: bolt send status | bolt send \"msg\""), file=sys.stderr)
            return 0
        return 0

    cmd = args.cmd or "status"
    try:
        if cmd == "status":
            info = status(probe=bool(getattr(args, "probe", False)))
            return _print_status(info, bool(getattr(args, "json", False)))
        if cmd == "list":
            rows = list_items()
            if getattr(args, "json", False):
                print(json.dumps(rows, indent=2))
            else:
                for row in rows:
                    mark = "OK" if row.get("ok") else "NO"
                    print(f"[{mark}] {row.get('id')}: {row.get('detail')}")
            return 0
        if cmd in ("send", "run"):
            message = " ".join(args.message)
            result = try_send(
                message,
                subject=getattr(args, "subject", "Bolt Notification"),
                sms_only=bool(getattr(args, "sms_only", False)),
                email_only=bool(getattr(args, "email_only", False)),
            )
            if getattr(args, "json", False):
                print(json.dumps(result, indent=2))
            else:
                if result.get("error"):
                    print(result["error"])
                elif result.get("report"):
                    print(result["report"], end="")
            return 0
    except Exception as exc:
        print(_soft(str(exc) or type(exc).__name__))
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
