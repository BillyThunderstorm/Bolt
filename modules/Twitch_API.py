"""
modules/twitch_api.py — Twitch Helix API client
================================================

Public functions (kept identical to the old Twitch_API.py so existing callers
in scripts/bot_with_twitch.py still work):

    get_follower_count() -> int | None
    get_last_stream_info() -> dict
    get_current_game() -> str
    get_all_twitch_data() -> dict

Plus a Session-3 helper:
    get_user_id(login) -> str | None

Every request goes through modules.twitch_auth.get_app_token(), so this file
doesn't know anything about how tokens are fetched or refreshed.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

try:
    import requests
except ImportError:
    requests = None  # type: ignore

from modules import twitch_auth

logger = logging.getLogger("bolt.twitch_api")

HELIX_BASE_URL = "https://api.twitch.tv/helix"

# Fallback if Twitch returns 429 without a Ratelimit-Reset header.
DEFAULT_RATE_LIMIT_BACKOFF = 5.0


# ── Errors ─────────────────────────────────────────────────────────────────────


class TwitchAPIError(RuntimeError):
    """Base error for Helix API failures."""


class TwitchAuthExpiredError(TwitchAPIError):
    """Raised after a single refresh-and-retry still fails with 401."""


class TwitchRateLimitError(TwitchAPIError):
    """Raised when Twitch returns HTTP 429."""

    def __init__(self, reset_at_unix: float | None = None):
        self.reset_at_unix = reset_at_unix
        wait = (
            max(0.0, reset_at_unix - time.time())
            if reset_at_unix
            else DEFAULT_RATE_LIMIT_BACKOFF
        )
        super().__init__(f"Rate limited by Twitch; retry in {wait:.1f}s")


# ── Session ────────────────────────────────────────────────────────────────────

# One Session for the whole module — reuses TCP connections across calls.
_session: Optional["requests.Session"] = None


def _get_session() -> "requests.Session":
    global _session
    if _session is None:
        _session = requests.Session()
    return _session


# ── Low-level HTTP ─────────────────────────────────────────────────────────────


def _headers() -> dict:
    """Build request headers. Pulls a token from twitch_auth on every call."""
    return {
        "Authorization": f"Bearer {twitch_auth.get_app_token()}",
        "Client-ID": twitch_auth.TWITCH_CLIENT_ID,
        "Content-Type": "application/json",
    }


def _request(
    method: str,
    path: str,
    *,
    params: dict | None = None,
    json_body: dict | None = None,
    _retry_on_401: bool = True,
) -> dict:
    """
    Make a Helix request with transparent 401-retry.

    On 401: invalidate the cached token, fetch a new one, retry exactly once.
    On 429: surface the Ratelimit-Reset timestamp via TwitchRateLimitError.
    """
    if requests is None:
        raise TwitchAPIError("The 'requests' library is not installed.")

    url = f"{HELIX_BASE_URL}{path}"
    session = _get_session()

    def _do() -> "requests.Response":
        return session.request(
            method,
            url,
            headers=_headers(),
            params=params,
            json=json_body,
            timeout=10,
        )

    try:
        resp = _do()
    except requests.RequestException as exc:
        raise TwitchAPIError(f"Network error talking to Twitch Helix: {exc}") from exc

    if resp.status_code == 401 and _retry_on_401:
        logger.warning("Got 401 from Twitch, refreshing token and retrying once…")
        twitch_auth.invalidate()
        resp = _do()
        if resp.status_code == 401:
            raise TwitchAuthExpiredError(
                "Twitch still returns 401 after a fresh token. "
                "Verify TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET in .env."
            )

    if resp.status_code == 429:
        reset_header = resp.headers.get("Ratelimit-Reset")
        reset_at = float(reset_header) if reset_header else None
        raise TwitchRateLimitError(reset_at)

    if not resp.ok:
        try:
            err = resp.json()
        except ValueError:
            err = {"message": resp.text[:200]}
        raise TwitchAPIError(
            f"Twitch Helix error "
            f"(HTTP {resp.status_code} on {method} {path}): "
            f"{err.get('message', err)}"
        )

    if not resp.content:
        return {}
    try:
        return resp.json()
    except ValueError as exc:
        raise TwitchAPIError(
            f"Twitch returned non-JSON response on {method} {path}: {exc}"
        ) from exc


# ── User lookup (used by Session 3 for VOD-clip work) ─────────────────────────


def get_user_id(login: str) -> Optional[str]:
    """Resolve a Twitch login name to a numeric user ID. None if not found."""
    if not login:
        return None
    try:
        data = _request("GET", "/users", params={"login": login})
    except TwitchAPIError as exc:
        logger.warning("Could not look up user %s: %s", login, exc)
        return None
    rows = data.get("data") or []
    return rows[0]["id"] if rows else None


# ── Public data fetchers (kept identical to old Twitch_API.py) ─────────────────


def get_follower_count() -> Optional[int]:
    """Total follower count for the configured channel. None on error."""
    try:
        user_id = get_user_id(twitch_auth.TWITCH_CHANNEL)
        if not user_id:
            return None
        data = _request(
            "GET", "/channels/followers", params={"broadcaster_id": user_id}
        )
        # Twitch Helix puts `total` at the top level of the response, not
        # inside the `data` array (which holds individual follower objects).
        return data.get("total", 0)
    except TwitchAPIError as exc:
        logger.warning("get_follower_count failed: %s", exc)
        return None


def get_last_stream_info() -> dict:
    """
    Info about the most recent broadcast VOD.

    Returns dict with `viewers` (VOD total views, NOT live concurrent),
    `title`, and `created_at`. Stub with zeros if no VOD exists.
    """
    stub = {"viewers": 0, "game": "Unknown", "title": "No recent streams"}
    try:
        user_id = get_user_id(twitch_auth.TWITCH_CHANNEL)
        if not user_id:
            return stub
        data = _request(
            "GET",
            "/videos",
            params={"user_id": user_id, "type": "archive", "first": 1},
        )
        rows = data.get("data") or []
        if not rows:
            return stub
        vod = rows[0]
        return {
            "viewers": vod.get("view_count", 0),
            "title": vod.get("title", "Unknown"),
            "created_at": vod.get("created_at", "Unknown"),
        }
    except TwitchAPIError as exc:
        logger.warning("get_last_stream_info failed: %s", exc)
        return {"viewers": 0, "game": "Unknown", "title": "Error fetching stream data"}


def get_current_game() -> str:
    """Game name of the last/current broadcast. 'Unknown' on errors."""
    try:
        user_id = get_user_id(twitch_auth.TWITCH_CHANNEL)
        if not user_id:
            return "Unknown"
        data = _request("GET", "/channels", params={"broadcaster_id": user_id})
        rows = data.get("data") or []
        return rows[0].get("game_name", "Unknown") if rows else "Unknown"
    except TwitchAPIError as exc:
        logger.warning("get_current_game failed: %s", exc)
        return "Unknown"


def get_all_twitch_data() -> dict[str, Any]:
    """
    All Twitch data Bolt uses at startup, in one call.

    Wraps the three single-purpose functions above. Single failure point =
    easier to debug.
    """
    last = get_last_stream_info()
    return {
        "followers": get_follower_count(),
        "last_stream_viewers": last["viewers"],
        "last_stream_title": last["title"],
        "current_game": get_current_game(),
    }


# ── CLI ────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    print("Testing Twitch Helix connection…\n")

    describe = twitch_auth.describe()
    print("Auth state:")
    for k, v in describe.items():
        print(f"  {k}: {v}")

    if not describe["client_id_set"] or not describe["client_secret_set"]:
        print("\n✗ Missing credentials. Run python3 -m modules.twitch_auth --check")
        raise SystemExit(1)

    print("\n→ Fetching live data…")
    data = get_all_twitch_data()
    print(f"✓ Followers: {data['followers']}")
    print(f"✓ Last Stream Viewers (VOD views): {data['last_stream_viewers']}")
    print(f"✓ Last Stream Title: {data['last_stream_title']}")
    print(f"✓ Current Game: {data['current_game']}")