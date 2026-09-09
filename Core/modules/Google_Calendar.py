#!/usr/bin/env python3
"""
modules/Google_Calendar.py -- Google Calendar integration for Bolt
==================================================================
Connects Bolt to your Google Calendar so the daily briefing knows
what's actually on your schedule.

Same OAuth *app* as Gmail_Briefing.py / Google_Drive_Handbook.py
(`Core/credentials.json`). Calendar scope is stored in its own token
file under Data/.

Non-interactive callers (`bolt briefing` / `bolt morning` /
format_for_briefing / module imports) never open a browser.
First-time consent: `bolt gcal-auth`.

What this module does:
  - get_todays_events()     -> list of events happening today
  - get_upcoming_events(n)  -> next N events from now
  - format_for_briefing()   -> plain-English summary for the daily briefing
  - authorize()             -> interactive browser consent once
  - status()                -> credentials/token readiness (no browser)

Run directly (default: status, never opens a browser):
    python3 -m modules.Google_Calendar [auth|status|today]
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from .notifier import notify
except ImportError:

    def notify(msg, level="info", reason=None):
        print(f"  [{level.upper()}] {msg}")
        if reason:
            print(f"           Why: {reason}")


# -- Paths ---------------------------------------------------------------------

_CORE = Path(__file__).resolve().parent.parent
_REPO_ROOT = _CORE.parent
CREDENTIALS = _CORE / "credentials.json"
TOKEN_PATH = _REPO_ROOT / "Data" / "google_token.json"
_LEGACY_TOKEN = _CORE / "data" / "google_token.json"
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

# One-time migrate pre-reorg Core/data/ token into Data/
if _LEGACY_TOKEN.exists() and not TOKEN_PATH.exists():
    try:
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_bytes(_LEGACY_TOKEN.read_bytes())
    except OSError:
        pass


# -- Auth ----------------------------------------------------------------------


def _get_service(interactive: bool = False):
    """Return calendar service or None. Never opens a browser unless interactive."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        notify(
            "Google Calendar libraries not installed",
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
            notify(
                "Google Calendar token refreshed",
                level="success",
                reason="Auto-renewed silently. No action needed.",
            )
        except Exception as exc:
            notify(f"Calendar token refresh failed: {exc}", level="warning")
            creds = None

    if not creds or not creds.valid:
        if not interactive:
            return None
        notify(
            "Opening browser for Google Calendar auth...",
            level="info",
            reason="This only happens once. Sign in and click Allow.",
        )
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS), SCOPES)
        creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        notify(
            "Google Calendar token saved",
            level="success",
            reason=f"Saved to {TOKEN_PATH} -- future runs won't need browser auth.",
        )

    return build("calendar", "v3", credentials=creds)


def authorize() -> int:
    """Interactive consent for Calendar read-only. Run from a real Terminal."""
    if not CREDENTIALS.exists():
        print(
            f"Calendar skipped (no Core/credentials.json). "
            f"Expected: {CREDENTIALS}"
        )
        print("Place the OAuth client JSON there, then re-run `bolt gcal-auth`.")
        return 1
    service = _get_service(interactive=True)
    if not service:
        print("Calendar auth failed.")
        return 1
    print(f"Google Calendar authorized. Token: {TOKEN_PATH}")
    return 0


def status() -> dict:
    """Return readiness info without opening a browser."""
    creds_ok = CREDENTIALS.exists()
    token_ok = TOKEN_PATH.exists()
    ready = False
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
    ready = service is not None
    detail["ready"] = ready
    return detail


def _cli_status() -> int:
    info = status()
    print("credentials.json:", info["credentials_exists"], info["credentials_path"])
    print("calendar_token:", info["token_exists"], info["token_path"])
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


# -- Core functions ------------------------------------------------------------


def get_todays_events() -> list:
    service = _get_service(interactive=False)
    if not service:
        return []

    local_tz = datetime.now().astimezone().tzinfo
    today = datetime.now(local_tz).date()
    start_dt = datetime(today.year, today.month, today.day, tzinfo=local_tz).isoformat()
    end_dt = (
        datetime(today.year, today.month, today.day, tzinfo=local_tz)
        + timedelta(days=1)
    ).isoformat()

    try:
        result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=start_dt,
                timeMax=end_dt,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        return [_parse_event(e) for e in result.get("items", [])]
    except Exception as e:
        notify(f"Calendar fetch failed: {e}", level="warning")
        return []


def get_upcoming_events(count: int = 5) -> list:
    service = _get_service(interactive=False)
    if not service:
        return []

    now = datetime.now(timezone.utc).isoformat()

    try:
        result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now,
                maxResults=count,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        return [_parse_event(e) for e in result.get("items", [])]
    except Exception as e:
        notify(f"Upcoming events fetch failed: {e}", level="warning")
        return []


def format_for_briefing() -> str:
    """Briefing line. Soft-fails when unauthorized — never pretends empty day."""
    if not CREDENTIALS.exists():
        return (
            f"Calendar skipped (no Core/credentials.json). "
            f"Place OAuth client at {CREDENTIALS}, then run `bolt gcal-auth` once."
        )

    service = _get_service(interactive=False)
    if not service:
        return "Calendar skipped (not authorized). Run `bolt gcal-auth` once."

    events = get_todays_events()
    today_str = datetime.now().strftime("%A %B %d").replace(" 0", " ")

    if not events:
        return f"Calendar ({today_str}): Nothing scheduled today -- open schedule."

    lines = [f"Today's schedule ({today_str}):"]
    for e in events:
        if e["all_day"]:
            lines.append(f"  - All day: {e['title']}")
        else:
            time_str = e["start"]
            if e["end"]:
                time_str += f" - {e['end']}"
            line = f"  - {time_str}: {e['title']}"
            if e["location"]:
                line += f" @ {e['location']}"
            lines.append(line)

    return "\n".join(lines)


# -- Helpers -------------------------------------------------------------------


def _parse_event(raw: dict) -> dict:
    title = raw.get("summary", "(no title)")
    location = raw.get("location", "")
    start_raw = raw.get("start", {})
    end_raw = raw.get("end", {})

    if "date" in start_raw and "dateTime" not in start_raw:
        return {
            "title": title,
            "start": "All day",
            "end": "",
            "location": location,
            "all_day": True,
        }

    start_str = _fmt_time(start_raw.get("dateTime", ""))
    end_str = _fmt_time(end_raw.get("dateTime", ""))
    return {
        "title": title,
        "start": start_str,
        "end": end_str,
        "location": location,
        "all_day": False,
    }


def _fmt_time(iso_str: str) -> str:
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str)
        hour12 = dt.hour % 12 or 12
        minute = dt.strftime("%M")
        period = "AM" if dt.hour < 12 else "PM"
        return f"{hour12}:{minute} {period}"
    except Exception:
        return iso_str


# -- CLI -----------------------------------------------------------------------

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a]
    # Default status — never open a browser on bare `python -m …`
    cmd = args[0] if args else "status"
    if cmd in ("auth", "authorize", "login"):
        raise SystemExit(authorize())
    if cmd in ("status", "token-status"):
        raise SystemExit(_cli_status())
    if cmd in ("today", "briefing", "events"):
        print(format_for_briefing())
        raise SystemExit(0)
    if cmd in ("-h", "--help", "help"):
        print("Usage: python3 -m modules.Google_Calendar [auth|status|today]")
        print("  auth    One-time browser consent (or: bolt gcal-auth)")
        print("  status  Credentials/token readiness (default; no browser)")
        print("  today   Print format_for_briefing() (no browser)")
        raise SystemExit(0)
    print(f"Unknown arg: {cmd}")
    raise SystemExit(2)
