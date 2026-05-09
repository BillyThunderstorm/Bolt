#!/usr/bin/env python3
"""
modules/Google_Calendar.py -- Google Calendar integration for Bolt
==================================================================
Connects Bolt to your Google Calendar so the daily briefing knows
what's actually on your schedule.

How the auth flow works (important to understand):
  1. First run: opens a browser window asking you to sign in to Google
     and approve access. This happens ONCE.
  2. After you approve, Google gives Bolt a token that gets saved to
     data/google_token.json on your machine.
  3. Every run after that: Bolt uses the saved token. No browser needed.
  4. If the token expires, it auto-refreshes silently using the refresh
     token embedded in the file.

What this module does:
  - get_todays_events()     -> list of events happening today
  - get_upcoming_events(n)  -> next N events from now
  - format_for_briefing()   -> plain-English summary for the daily briefing

Run directly to test:
    python3 -m modules.Google_Calendar
"""

import os
from pathlib import Path
from datetime import datetime, timezone, timedelta

try:
    from .notifier import notify
except ImportError:
    def notify(msg, level="info", reason=None):
        print(f"  [{level.upper()}] {msg}")
        if reason:
            print(f"           Why: {reason}")


# -- Paths ---------------------------------------------------------------------

_ROOT       = Path(__file__).parent.parent
CREDENTIALS = _ROOT / "credentials.json"
TOKEN_PATH  = _ROOT / "data" / "google_token.json"
SCOPES      = ["https://www.googleapis.com/auth/calendar.readonly"]


# -- Auth ----------------------------------------------------------------------

def _get_service():
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        notify(
            "Google Calendar libraries not installed",
            level="warning",
            reason="Run: pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib"
        )
        return None

    if not CREDENTIALS.exists():
        notify(
            "credentials.json not found",
            level="error",
            reason=f"Expected at: {CREDENTIALS}"
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
                notify("Google Calendar token refreshed", level="success",
                       reason="Auto-renewed silently. No action needed.")
            except Exception as e:
                notify(f"Token refresh failed: {e} -- re-authenticating", level="warning")
                creds = None

        if not creds or not creds.valid:
            notify(
                "Opening browser for Google Calendar auth...",
                level="info",
                reason="This only happens once. Sign in and click Allow."
            )
            flow  = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS), SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
        notify("Google Calendar token saved", level="success",
               reason=f"Saved to {TOKEN_PATH} -- future runs won't need browser auth.")

    return build("calendar", "v3", credentials=creds)


# -- Core functions ------------------------------------------------------------

def get_todays_events() -> list:
    service = _get_service()
    if not service:
        return []

    local_tz = datetime.now().astimezone().tzinfo
    today    = datetime.now(local_tz).date()
    start_dt = datetime(today.year, today.month, today.day, tzinfo=local_tz).isoformat()
    end_dt   = (datetime(today.year, today.month, today.day, tzinfo=local_tz)
                + timedelta(days=1)).isoformat()

    try:
        result = service.events().list(
            calendarId="primary",
            timeMin=start_dt,
            timeMax=end_dt,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        return [_parse_event(e) for e in result.get("items", [])]
    except Exception as e:
        notify(f"Calendar fetch failed: {e}", level="warning")
        return []


def get_upcoming_events(count: int = 5) -> list:
    service = _get_service()
    if not service:
        return []

    now = datetime.now(timezone.utc).isoformat()

    try:
        result = service.events().list(
            calendarId="primary",
            timeMin=now,
            maxResults=count,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        return [_parse_event(e) for e in result.get("items", [])]
    except Exception as e:
        notify(f"Upcoming events fetch failed: {e}", level="warning")
        return []


def format_for_briefing() -> str:
    events    = get_todays_events()
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
    title    = raw.get("summary", "(no title)")
    location = raw.get("location", "")
    start_raw = raw.get("start", {})
    end_raw   = raw.get("end", {})

    if "date" in start_raw and "dateTime" not in start_raw:
        return {"title": title, "start": "All day", "end": "",
                "location": location, "all_day": True}

    start_str = _fmt_time(start_raw.get("dateTime", ""))
    end_str   = _fmt_time(end_raw.get("dateTime", ""))
    return {"title": title, "start": start_str, "end": end_str,
            "location": location, "all_day": False}


def _fmt_time(iso_str: str) -> str:
    if not iso_str:
        return ""
    try:
        dt     = datetime.fromisoformat(iso_str)
        hour12 = dt.hour % 12 or 12
        minute = dt.strftime("%M")
        period = "AM" if dt.hour < 12 else "PM"
        return f"{hour12}:{minute} {period}"
    except Exception:
        return iso_str


# -- CLI test ------------------------------------------------------------------

if __name__ == "__main__":
    print("\nGoogle_Calendar.py -- test run\n")
    print(format_for_briefing())
    print()
    upcoming = get_upcoming_events(3)
    if upcoming:
        print("Next 3 upcoming events:")
        for e in upcoming:
            print(f"  {e['start']} -- {e['title']}")
    print()