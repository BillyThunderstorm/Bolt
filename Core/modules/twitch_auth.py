"""
modules/twitch_auth.py — Helix API access token management
==========================================================

Owns one job: always return a valid Helix App Access Token.

Twitch's Helix API requires a Bearer token on every call, and tokens expire.
We fetch one via the OAuth 2.0 "client_credentials" grant and cache it on disk
at Data/twitch_token_cache.json so we don't re-auth on every request.

Required .env values (repo-root .env):
    TWITCH_CLIENT_ID=<client id from https://dev.twitch.tv/console/apps>
    TWITCH_CLIENT_SECRET=<client secret from the same page>
    TWITCH_CHANNEL=<your channel login>

This file does NOT call Helix endpoints (see modules/twitch_api.py) and
does NOT connect to Twitch chat (IRC bot lives in bot.py).
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    requests = None  # type: ignore

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore

logger = logging.getLogger("bolt.twitch_auth")

# ── Config ─────────────────────────────────────────────────────────────────────

# Core/modules/twitch_auth.py → parents[0]=modules, [1]=Core, [2]=repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_CORE_DIR = Path(__file__).resolve().parents[1]

# Prefer the repo-root .env (same place launch.py and the rest of Bolt use).
# Fall back to Core/.env only if the root one is missing (legacy layouts).
_ENV_CANDIDATES = [
    _REPO_ROOT / ".env",
    _CORE_DIR / ".env",
]

if load_dotenv is not None:
    for _env_path in _ENV_CANDIDATES:
        if _env_path.exists():
            load_dotenv(_env_path)
            break
    else:
        # Still call load_dotenv() so any already-exported env vars work,
        # and so a future root .env is picked up if created later.
        load_dotenv(_REPO_ROOT / ".env")

TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID", "").strip()
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "").strip()
TWITCH_CHANNEL = os.getenv("TWITCH_CHANNEL", "").strip()

# OAuth token endpoint lives at id.twitch.tv, NOT api.twitch.tv.
OAUTH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"

# Cached token location. Disk (not memory) so it survives process restarts
# and is shared if Bolt is ever split into multiple processes.
CACHE_PATH = _REPO_ROOT / "Data" / "twitch_token_cache.json"

# Refresh this many seconds BEFORE actual expiry — safety margin for clock
# skew and slow requests.
EXPIRY_SAFETY_MARGIN_SECONDS = 300  # 5 minutes


# ── Data ───────────────────────────────────────────────────────────────────────


@dataclass
class CachedToken:
    """A token plus when we fetched it. Persisted to disk as JSON."""

    access_token: str
    expires_at_unix: float

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at_unix

    @property
    def is_near_expiry(self) -> bool:
        return time.time() >= (self.expires_at_unix - EXPIRY_SAFETY_MARGIN_SECONDS)

    def to_dict(self) -> dict:
        return {
            "access_token": self.access_token,
            "expires_at_unix": self.expires_at_unix,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CachedToken":
        return cls(
            access_token=d["access_token"],
            expires_at_unix=float(d["expires_at_unix"]),
        )


# ── Public API ─────────────────────────────────────────────────────────────────


class TwitchAuthError(RuntimeError):
    """Raised when we cannot get a valid Helix access token."""


def get_app_token(*, force_refresh: bool = False) -> str:
    """
    Return a valid Helix App Access Token, fetching a new one if needed.

    Cheap when the cached token is still fresh (just reads the cache file).
    Use force_refresh=True after a 401 to bypass the cache and re-auth.
    """
    if not force_refresh:
        cached = _load_cache()
        if cached and not cached.is_near_expiry:
            return cached.access_token

    fresh = _request_new_app_token()
    _save_cache(fresh)
    return fresh.access_token


def invalidate() -> None:
    """Drop the cached token. Next call to get_app_token() will re-fetch."""
    try:
        if CACHE_PATH.exists():
            CACHE_PATH.unlink()
    except OSError as exc:
        logger.warning("Could not delete token cache: %s", exc)


def describe() -> dict:
    """
    Diagnostic dict for `python3 -m modules.twitch_auth`.

    Safe to log — never includes the raw token.
    """
    cached = _load_cache()
    return {
        "client_id_set": bool(TWITCH_CLIENT_ID),
        "client_secret_set": bool(TWITCH_CLIENT_SECRET),
        "channel": TWITCH_CHANNEL or None,
        "cache_path": str(CACHE_PATH),
        "token_cached": cached is not None,
        "token_expired": cached.is_expired if cached else None,
        "expires_in_seconds": (
            int(cached.expires_at_unix - time.time()) if cached else None
        ),
    }


# ── Private helpers ────────────────────────────────────────────────────────────


def _request_new_app_token() -> CachedToken:
    """POST to id.twitch.tv/oauth2/token with grant_type=client_credentials."""
    if requests is None:
        raise TwitchAuthError(
            "The 'requests' library is not installed. "
            "Run: python3 -m pip install requests"
        )
    if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET:
        raise TwitchAuthError(
            "TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET must both be set in .env. "
            "Generate a secret at https://dev.twitch.tv/console/apps"
        )

    logger.info("Requesting new Twitch App Access Token…")
    try:
        resp = requests.post(
            OAUTH_TOKEN_URL,
            params={
                "client_id": TWITCH_CLIENT_ID,
                "client_secret": TWITCH_CLIENT_SECRET,
                "grant_type": "client_credentials",
            },
            timeout=10,
        )
    except requests.RequestException as exc:
        raise TwitchAuthError(f"Network error talking to Twitch OAuth: {exc}") from exc

    if resp.status_code != 200:
        try:
            err = resp.json()
        except ValueError:
            err = {"message": resp.text[:200]}
        raise TwitchAuthError(
            f"Twitch rejected the auth request "
            f"(HTTP {resp.status_code}): {err.get('message', err)}"
        )

    payload = resp.json()
    access_token = payload.get("access_token")
    expires_in = int(payload.get("expires_in", 0))
    if not access_token or expires_in <= 0:
        raise TwitchAuthError(f"Twitch returned an unexpected payload: {payload!r}")

    expires_at = time.time() + expires_in
    logger.info(
        "Got new Twitch token (expires in %d seconds / ~%d days)",
        expires_in,
        expires_in // 86400,
    )
    return CachedToken(access_token=access_token, expires_at_unix=expires_at)


def _load_cache() -> Optional[CachedToken]:
    """Read the cached token from disk. Return None if missing or unreadable."""
    if not CACHE_PATH.exists():
        return None
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        return CachedToken.from_dict(data)
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("Token cache unreadable, will refetch: %s", exc)
        return None


def _save_cache(token: CachedToken) -> None:
    """Persist the token to disk with best-effort 0600 permissions."""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(token.to_dict(), indent=2), encoding="utf-8"
    )
    try:
        os.chmod(CACHE_PATH, 0o600)
    except OSError:
        # Windows or restricted FS — fine to skip.
        pass


# ── CLI ────────────────────────────────────────────────────────────────────────


def _print_check() -> int:
    """Diagnostic: print auth state and try a refresh. Exit 0 if healthy."""
    state = describe()
    print("Twitch auth diagnostic:")
    for k, v in state.items():
        print(f"  {k}: {v}")

    if not state["client_id_set"] or not state["client_secret_set"]:
        print("\n✗ Missing credentials in .env")
        print("  Expected .env at the repo root (same place launch.py uses).")
        print("  Make sure TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET, and TWITCH_CHANNEL are set.")
        return 1

    print("\n→ Requesting a fresh token to verify credentials work…")
    try:
        new = get_app_token(force_refresh=True)
        print(f"✓ Got token ({len(new)} chars). Auth looks healthy.")
        if state["channel"]:
            print(f"✓ Channel configured as: {state['channel']}")
        else:
            print("○ TWITCH_CHANNEL is empty — set it in .env to ItsSimplyBilly")
        return 0
    except TwitchAuthError as exc:
        print(f"✗ {exc}")
        return 2


if __name__ == "__main__":
    import sys

    if "--check" in sys.argv:
        sys.exit(_print_check())

    # Default: print describe() and exit.
    print(json.dumps(describe(), indent=2))
