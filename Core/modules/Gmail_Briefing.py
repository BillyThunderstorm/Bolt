#!/usr/bin/env python3
"""
modules/Gmail_Briefing.py -- Gmail input for Bolt's daily briefing.

Uses the same Google OAuth app style as Google_Calendar.py, but stores a
separate Gmail token because Gmail needs a different read-only scope.
"""

from __future__ import annotations

from pathlib import Path

try:
    from .notifier import notify
except ImportError:

    def notify(msg, level="info", reason=None):
        print(f"  [{level.upper()}] {msg}")
        if reason:
            print(f"           Why: {reason}")


ROOT = Path(__file__).parent.parent
CREDENTIALS = ROOT / "credentials.json"
TOKEN_PATH = ROOT / "data" / "gmail_token.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

IMPORTANT_QUERY = (
    "is:unread newer_than:7d "
    "(from:github OR from:google OR from:twitch OR from:tiktok OR "
    "from:amazon OR subject:security OR subject:account OR subject:invoice OR "
    "subject:collab OR subject:sponsorship OR subject:creator OR subject:urgent)"
)


def _get_service():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        notify(
            "Gmail libraries not installed",
            level="warning",
            reason="Run: pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib",
        )
        return None

    if not CREDENTIALS.exists():
        notify(
            "credentials.json not found",
            level="warning",
            reason=f"Expected at: {CREDENTIALS}",
        )
        return None

    creds = None
    TOKEN_PATH.parent.mkdir(exist_ok=True)

    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except Exception:
            TOKEN_PATH.unlink(missing_ok=True)
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as exc:
                notify(f"Gmail token refresh failed: {exc}", level="warning")
                creds = None

        if not creds or not creds.valid:
            notify(
                "Opening browser for Gmail auth...",
                level="info",
                reason="This only happens once. Sign in and approve read-only Gmail access.",
            )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS), SCOPES)
            creds = flow.run_local_server(port=0)

        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        notify("Gmail token saved", level="success", reason=f"Saved to {TOKEN_PATH}")

    return build("gmail", "v1", credentials=creds)


def get_important_unread(limit: int = 5) -> list[dict]:
    service = _get_service()
    if not service:
        return []

    try:
        result = (
            service.users()
            .messages()
            .list(
                userId="me",
                q=IMPORTANT_QUERY,
                maxResults=limit,
            )
            .execute()
        )
        messages = result.get("messages", [])
    except Exception as exc:
        notify(f"Gmail search failed: {exc}", level="warning")
        return []

    items = []
    for message in messages:
        try:
            raw = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=message["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                )
                .execute()
            )
        except Exception:
            continue
        headers = {
            h.get("name", ""): h.get("value", "")
            for h in raw.get("payload", {}).get("headers", [])
        }
        items.append(
            {
                "from": headers.get("From", "(unknown sender)"),
                "subject": headers.get("Subject", "(no subject)"),
                "date": headers.get("Date", ""),
                "snippet": raw.get("snippet", ""),
            }
        )

    return items


def format_for_briefing(limit: int = 5) -> str:
    if not CREDENTIALS.exists():
        return f"Gmail unavailable: credentials.json not found at {CREDENTIALS}."

    items = get_important_unread(limit=limit)
    if not items:
        return "No important unread Gmail items found by the current filter."

    lines = ["Important unread Gmail items:"]
    for item in items:
        snippet = item["snippet"].replace("\n", " ").strip()
        if len(snippet) > 140:
            snippet = snippet[:137].rstrip() + "..."
        lines.append(f"- {item['subject']} — {item['from']}")
        if snippet:
            lines.append(f"  Why it matters: {snippet}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(format_for_briefing())
