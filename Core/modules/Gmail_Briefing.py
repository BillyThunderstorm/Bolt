#!/usr/bin/env python3
"""
modules/Gmail_Briefing.py -- Gmail input for Bolt's daily briefing.

Uses the same Google OAuth app as Google_Calendar.py / Google_Drive_Handbook.py
(`Core/credentials.json`), but stores a separate Gmail token because Gmail
needs a different read-only scope.

Non-interactive callers (`bolt briefing` / `bolt morning` /
format_for_briefing / module imports) never open a browser.
First-time consent: `bolt gmail-auth`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from .notifier import notify
except ImportError:

    def notify(msg, level="info", reason=None):
        print(f"  [{level.upper()}] {msg}")
        if reason:
            print(f"           Why: {reason}")


_CORE = Path(__file__).resolve().parent.parent
_REPO_ROOT = _CORE.parent
CREDENTIALS = _CORE / "credentials.json"
TOKEN_PATH = _REPO_ROOT / "Data" / "gmail_token.json"
_LEGACY_TOKEN = _CORE / "data" / "gmail_token.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

if _LEGACY_TOKEN.exists() and not TOKEN_PATH.exists():
    try:
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_bytes(_LEGACY_TOKEN.read_bytes())
    except OSError:
        pass

IMPORTANT_QUERY = (
    "is:unread newer_than:7d "
    "(from:github OR from:google OR from:twitch OR from:tiktok OR "
    "from:amazon OR subject:security OR subject:account OR subject:invoice OR "
    "subject:collab OR subject:sponsorship OR subject:creator OR subject:urgent)"
)


def _get_service(interactive: bool = False):
    """Return Gmail service or None. Never opens a browser unless interactive."""
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
        return None

    creds = None
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)

    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except Exception:
            creds = None

    if creds and creds.valid:
        pass
    elif creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
            notify("Gmail token refreshed", level="success")
        except Exception as exc:
            notify(f"Gmail token refresh failed: {exc}", level="warning")
            creds = None

    if not creds or not creds.valid:
        if not interactive:
            return None
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


def authorize() -> int:
    """Interactive consent for Gmail read-only. Run from a real Terminal."""
    if not CREDENTIALS.exists():
        print(
            f"Gmail skipped (no Core/credentials.json). "
            f"Expected: {CREDENTIALS}"
        )
        print("Place the OAuth client JSON there, then re-run `bolt gmail-auth`.")
        return 1
    service = _get_service(interactive=True)
    if not service:
        print("Gmail auth failed.")
        return 1
    print(f"Gmail authorized. Token: {TOKEN_PATH}")
    return 0


def status() -> dict:
    """Return readiness info without opening a browser."""
    creds_ok = CREDENTIALS.exists()
    token_ok = TOKEN_PATH.exists()
    detail: dict = {
        "credentials_path": str(CREDENTIALS),
        "credentials_exists": creds_ok,
        "token_path": str(TOKEN_PATH),
        "token_exists": token_ok,
        "ready": False,
    }
    if not creds_ok or not token_ok:
        return detail
    service = _get_service(interactive=False)
    detail["ready"] = service is not None
    return detail


def _cli_status() -> int:
    info = status()
    print("credentials.json:", info["credentials_exists"], info["credentials_path"])
    print("gmail_token:", info["token_exists"], info["token_path"])
    if TOKEN_PATH.exists():
        try:
            data = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
            print("token_keys:", sorted(data.keys()))
            scopes = data.get("scopes") or data.get("scope") or []
            if isinstance(scopes, str):
                scopes = scopes.split()
            print("scopes:", list(scopes))
            print("has_refresh_token:", bool(data.get("refresh_token")))
            print("has_access_token:", bool(data.get("token") or data.get("access_token")))
            print("size_bytes:", TOKEN_PATH.stat().st_size)
        except Exception as exc:
            print("token_read_error:", exc)
    print("ready:", info["ready"])
    return 0


def get_important_unread(limit: int = 5) -> list[dict]:
    service = _get_service(interactive=False)
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
    """Briefing line. Soft-fails when unauthorized — never pretends empty inbox."""
    if not CREDENTIALS.exists():
        return (
            f"Gmail skipped (no Core/credentials.json). "
            f"Place OAuth client at {CREDENTIALS}, then run `bolt gmail-auth` once."
        )

    service = _get_service(interactive=False)
    if not service:
        return "Gmail skipped (not authorized). Run `bolt gmail-auth` once."

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
    args = [a for a in sys.argv[1:] if a]
    # Default status — never open a browser on bare `python -m …`
    cmd = args[0] if args else "status"
    if cmd in ("auth", "authorize", "login"):
        raise SystemExit(authorize())
    if cmd in ("status", "token-status"):
        raise SystemExit(_cli_status())
    if cmd in ("briefing", "unread", "today"):
        print(format_for_briefing())
        raise SystemExit(0)
    if cmd in ("-h", "--help", "help"):
        print("Usage: python3 -m modules.Gmail_Briefing [auth|status|briefing]")
        print("  auth      One-time browser consent (or: bolt gmail-auth)")
        print("  status    Credentials/token readiness (default; no browser)")
        print("  briefing  Print format_for_briefing() (no browser)")
        raise SystemExit(0)
    print(f"Unknown arg: {cmd}")
    raise SystemExit(2)
