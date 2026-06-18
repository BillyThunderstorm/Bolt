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

ROOT = Path(__file__).parent.parent
CONFIG_DIR = ROOT / "configs"
ENV_FILE = CONFIG_DIR / "storage_alerts.env"

# Load storage_alerts.env explicitly if it exists, fall back to .env
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
else:
    load_dotenv(ROOT / ".env")

# Email-to-SMS gateways
SMS_GATEWAYS = {
    "att": "@txt.att.net",
    "verizon": "@vtext.com",
    "tmobile": "@tmomail.net",
    "sprint": "@messaging.sprintpcs.com",
    "boost": "@myboostmobile.com",
    "virgin": "@vmobl.com",
}


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


def _send_mail(to: str, subject: str, body: str) -> bool:
    """Send one email via SMTP."""
    if not _check_config("email"):
        return False

    server, port, user, password, from_email = _configured()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to
    msg.attach(MIMEText(body, "plain"))

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
    """Return the email-to-SMS address for the configured phone + carrier."""
    phone = os.getenv("ALERT_PHONE", "").strip()
    carrier = os.getenv("CARRIER", "att").lower().strip()
    if not phone:
        return ""
    gateway = SMS_GATEWAYS.get(carrier, SMS_GATEWAYS["att"])
    return f"{phone}{gateway}"


def send_sms(message: str) -> bool:
    """Send a short SMS via the carrier's email-to-SMS gateway."""
    sms_email = get_sms_email()
    if not sms_email:
        print("SMS not configured: add ALERT_PHONE and CARRIER to storage_alerts.env")
        return False

    # Hard truncate to 160 chars for SMS reliability
    text = message[:160]
    ok = _send_mail(sms_email, "Bolt Alert", text)
    if ok:
        print(f"SMS sent to {sms_email}: {text}")
    return ok


def send_email(subject: str, body: str, to_email: str = None) -> bool:
    """Send an email to the configured address (or to_email override)."""
    if not to_email:
        to_email = os.getenv("ALERT_EMAIL", "")
    if not to_email:
        print("Email not configured: add ALERT_EMAIL to storage_alerts.env")
        return False

    ok = _send_mail(to_email, subject, body)
    if ok:
        print(f"Email sent to {to_email}: {subject}")
    return ok


def send_briefing(briefing_text: str, sms_summary: str = "") -> bool:
    """Send daily/weekly briefing: SMS summary + full email."""
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
    email_ok = send_email("Bolt Briefing", briefing_text)
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
