#!/usr/bin/env python3
"""
scripts/send_notification.py — Send Bolt notifications via SMS and email
=======================================================================
Reads configs/storage_alerts.env for phone, email, and SMTP credentials.

SMS delivery uses the carrier's email-to-SMS gateway (free, works with any
email provider that can send to @mms.att.net etc.).

Email delivery uses SMTP (Gmail by default with App Password).

Usage:
  python3 scripts/send_notification.py "Test message"
  python3 scripts/send_notification.py --sms-only "Quick alert"
  python3 scripts/send_notification.py --email-only "Subject" "Body text"

Import functions:
  from scripts.send_notification import send_sms, send_email, send_briefing
"""

import argparse
import os
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

# Post-reorg path bootstrap. Adds the script's own dir to sys.path so
# `from _paths import …` works in both direct invocation and `from
# scripts import X` (test) contexts. The helper itself adds Core/ and
# 3rd_Party/llm/ to sys.path so `from modules import Y` resolves, and
# chdirs to the repo root for any CWD-relative paths the script uses.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from _paths import REPO_ROOT, DATA_DIR, CLIPS_DIR, LOGS_DIR, CONFIG_FILE  # noqa: E402

# Backward-compatible aliases for code that uses `ROOT` / `PROJECT_ROOT`.
PROJECT_ROOT = REPO_ROOT
ROOT = REPO_ROOT

ROOT = Path(__file__).parent.parent
# Prefer post-reorg Data/configs/, then legacy configs/
_ENV_CANDIDATES = (
    ROOT / "Data" / "configs" / "storage_alerts.env",
    ROOT / "configs" / "storage_alerts.env",
)
ENV_FILE = next((p for p in _ENV_CANDIDATES if p.exists()), _ENV_CANDIDATES[0])
CONFIG_DIR = ENV_FILE.parent

# Load storage_alerts.env explicitly if it exists, fall back to .env
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
load_dotenv(ROOT / ".env", override=False)

# Email-to-SMS gateways (many carriers retired these in 2025).
# AT&T shut down txt.att.net / mms.att.net on 2025-06-17 — do not use.
# For AT&T, Bolt uses iMessage (Mac Messages) or email instead.
SMS_GATEWAYS = {
    "att": None,  # discontinued — see send_sms / iMessage path
    "att-sms": None,
    "verizon": "@vtext.com",
    "tmobile": "@tmomail.net",
    "sprint": "@messaging.sprintpcs.com",
    "boost": "@myboostmobile.com",
    "virgin": "@vmobl.com",
}

# Carriers whose free email-to-SMS gateways are known dead
SMS_GATEWAY_DEAD = frozenset({"att", "att-sms", "cricket", "firstnet"})


def _configured() -> tuple:
    """Return (smtp_server, smtp_port, smtp_user, smtp_password, from_email)."""
    return (
        os.getenv("SMTP_SERVER", "smtp.gmail.com"),
        int(os.getenv("SMTP_PORT", "587")),
        os.getenv("SMTP_USERNAME", ""),
        os.getenv("SMTP_PASSWORD", ""),
        os.getenv("ALERT_EMAIL", ""),
    )


def _check_config(label: str) -> bool:
    server, port, user, password, from_email = _configured()
    missing = []
    if not user:
        missing.append("SMTP_USERNAME")
    if not password:
        missing.append("SMTP_PASSWORD")
    if not from_email:
        missing.append("ALERT_EMAIL")
    if missing:
        print(f"Cannot send {label}: missing {', '.join(missing)}")
        print(f"Update: {ENV_FILE}")
        return False
    return True


def _send_mail(
    to: str, subject: str, body: str, attachments: list = None
) -> bool:
    """Send one email via SMTP.

    `attachments` is an optional list of `(filename, path)` tuples. Paths
    are read as bytes; missing files are skipped with a warning.
    """
    if not _check_config("email"):
        return False

    server, port, user, password, from_email = _configured()

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to
    msg.attach(MIMEText(body, "plain"))

    for filename, path in attachments or []:
        try:
            data = Path(path).read_bytes()
        except OSError as exc:
            print(f"Skipping attachment {filename}: {exc}")
            continue
        part = MIMEText(data.decode("utf-8", errors="replace"), "calendar")
        del part["Content-Type"]
        part.add_header(
            "Content-Type", "text/calendar; method=PUBLISH; charset=UTF-8"
        )
        part.add_header(
            "Content-Disposition", f'attachment; filename="{filename}.ics"'
        )
        msg.attach(part)

    try:
        with smtplib.SMTP(server, port, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.sendmail(from_email, [to], msg.as_string())
        return True
    except Exception as exc:
        print(f"Failed to send email: {exc}")
        return False


def get_sms_email() -> str:
    """Return the email-to-SMS address for the configured phone + carrier.

    Returns empty string when the carrier gateway is discontinued (e.g. AT&T).
    """
    phone = os.getenv("ALERT_PHONE", "").strip()
    carrier = os.getenv("CARRIER", "att").lower().strip()
    if not phone:
        return ""
    if carrier in SMS_GATEWAY_DEAD:
        return ""
    gateway = SMS_GATEWAYS.get(carrier)
    if not gateway:
        return ""
    return f"{phone}{gateway}"


def send_imessage(message: str, phone: str = None) -> bool:
    """Send via macOS Messages (iMessage/SMS) — free local path.

    Requires Messages signed in on this Mac. Best free option after AT&T
    shut down email-to-text (June 2025).
    """
    phone = (phone or os.getenv("ALERT_PHONE", "")).strip()
    if not phone:
        print("iMessage: ALERT_PHONE not set")
        return False
    # Normalize to +1… for US numbers
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 10:
        buddy = f"+1{digits}"
    elif len(digits) == 11 and digits.startswith("1"):
        buddy = f"+{digits}"
    else:
        buddy = phone if phone.startswith("+") else f"+{digits}"

    text = (message or "")[:500].replace("\\", "\\\\").replace('"', '\\"')
    # Prefer iMessage service; fall back to first SMS-capable service
    script = f'''
    on run
      set targetBuddy to "{buddy}"
      set msg to "{text}"
      tell application "Messages"
        set sentOk to false
        try
          set iServ to 1st service whose service type is iMessage
          set theBuddy to buddy targetBuddy of iServ
          send msg to theBuddy
          set sentOk to true
        end try
        if sentOk is false then
          try
            set sServ to 1st service whose service type is SMS
            set theBuddy to buddy targetBuddy of sServ
            send msg to theBuddy
            set sentOk to true
          end try
        end if
        return sentOk
      end tell
    end run
    '''
    try:
        import subprocess

        r = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        ok = r.returncode == 0 and "true" in (r.stdout or "").lower()
        if ok:
            print(f"iMessage/SMS sent via Messages to {buddy}")
        else:
            err = (r.stderr or r.stdout or "").strip()[:200]
            print(f"iMessage send failed ({buddy}): {err or 'Messages not signed in?'}")
        return ok
    except Exception as exc:
        print(f"iMessage error: {exc}")
        return False


def send_sms(message: str) -> bool:
    """Deliver a phone alert.

    Priority:
      1. iMessage via macOS Messages (works for AT&T after email-to-text shutdown)
      2. Carrier email-to-SMS gateway (Verizon/T-Mobile etc., if still alive)
    """
    phone = os.getenv("ALERT_PHONE", "").strip()
    carrier = os.getenv("CARRIER", "att").lower().strip()
    text = (message or "")[:300]

    if not phone:
        print("SMS not configured: add ALERT_PHONE to storage_alerts.env")
        return False

    # Prefer iMessage on Mac (AT&T email gateways are dead as of 2025-06-17)
    if os.getenv("BOLT_ALERT_IMESSAGE", "true").lower() not in ("0", "false", "no"):
        if send_imessage(text, phone):
            return True

    if carrier in SMS_GATEWAY_DEAD:
        print(
            f"Carrier '{carrier}' no longer supports email-to-text "
            f"(AT&T shut this down June 2025). "
            f"Use iMessage (sign into Messages on this Mac) or email alerts."
        )
        return False

    sms_email = get_sms_email()
    if not sms_email:
        print("No email-to-SMS gateway for this carrier; use iMessage or email.")
        return False

    ok = _send_mail(sms_email, "", text)
    if ok:
        print(f"SMS accepted by SMTP for {sms_email}: {text[:80]}")
    else:
        print(f"SMS SMTP send failed for {sms_email}")
    return ok


def send_email(
    subject: str,
    body: str,
    to_email: str = None,
    attachments: list = None,
) -> bool:
    """Send an email to the configured address (or to_email override).

    `attachments` is an optional list of `(filename, path)` tuples. Each
    file is attached using its basename and read as bytes.
    """
    if not to_email:
        to_email = os.getenv("ALERT_EMAIL", "")
    if not to_email:
        print("Email not configured: add ALERT_EMAIL to storage_alerts.env")
        return False

    ok = _send_mail(to_email, subject, body, attachments=attachments)
    if ok:
        print(f"Email sent to {to_email}: {subject}")
    return ok


def send_briefing(
    briefing_text: str,
    sms_summary: str = "",
    attachments: list = None,
) -> bool:
    """Send daily/weekly briefing: SMS summary + full email.

    `attachments` is forwarded to send_email so the briefing email can ship
    alongside calendar ICS files for one-click subscription.
    """
    if sms_summary:
        sms_text = "Bolt Briefing: " + sms_summary
    else:
        # Build a one-line SMS summary
        lines = [
            line.strip()
            for line in briefing_text.splitlines()
            if any(k in line for k in ("Clips ready", "Disk Usage", "Queue Status", "Success Rate", "Total Views"))
        ]
        sms_text = "Bolt Briefing: " + " | ".join(lines[:3])

    sms_ok = send_sms(sms_text)
    email_ok = send_email("Bolt Briefing", briefing_text, attachments=attachments)
    return sms_ok or email_ok


def main():
    parser = argparse.ArgumentParser(description="Send Bolt notifications")
    parser.add_argument("--sms-only", action="store_true", help="Send SMS only")
    parser.add_argument("--email-only", action="store_true", help="Send email only")
    parser.add_argument("--subject", default="Bolt Notification", help="Email subject")
    parser.add_argument("message", nargs="+", help="Message text")
    args = parser.parse_args()

    message = " ".join(args.message) if args.message else ""
    if not message:
        parser.print_help()
        sys.exit(1)

    if args.sms_only:
        send_sms(message)
    elif args.email_only:
        send_email(args.subject, message)
    else:
        send_sms(message)
        send_email(args.subject, message)


if __name__ == "__main__":
    main()
