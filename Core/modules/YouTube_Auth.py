#!/usr/bin/env python3
"""YouTube / Google OAuth helpers for Bolt.

Stores OAuth client credentials and tokens in the repo-root ``.env`` and
refreshes short-lived access tokens with the long-lived refresh token.

Setup (one-time):
  1. https://console.cloud.google.com/ → create/select a project
  2. Enable **YouTube Data API v3**
  3. APIs & Services → Credentials → Create OAuth client ID
     - Application type: **Desktop app** (or Web with localhost redirect)
  4. Download JSON or copy Client ID + Client Secret
  5. OAuth consent screen: External (or Internal if Workspace), add your
     Google account as a test user while the app is in Testing
  6. python3 scripts/get_youtube_token.py
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

# Reuse env helpers so .env path stays consistent with TikTok.
from modules.TikTok_Auth import ENV_FILE, ROOT, load_env, write_env_values  # noqa: F401

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
DEFAULT_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8765/callback"


def access_token_is_fresh(
    env: Optional[dict] = None, leeway_seconds: int = 120
) -> bool:
    env = env or load_env()
    token = env.get("YOUTUBE_ACCESS_TOKEN", "").strip()
    expires_at = float(env.get("YOUTUBE_ACCESS_TOKEN_EXPIRES_AT", "0") or 0)
    return bool(token and expires_at > time.time() + leeway_seconds)


def post_token_request(payload: dict) -> dict:
    encoded = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(
        TOKEN_URL,
        data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            error = json.loads(body)
        except Exception:
            error = {"error": body}
        raise RuntimeError(f"YouTube token request failed: {error}") from exc


def save_token_bundle(data: dict, path: Path = ENV_FILE) -> dict:
    if not data.get("access_token"):
        safe = {k: v for k, v in data.items() if "token" not in k.lower()}
        raise RuntimeError(f"YouTube did not return an access token. Response: {safe}")

    now = int(time.time())
    values = {
        "YOUTUBE_ACCESS_TOKEN": data.get("access_token", ""),
        "YOUTUBE_TOKEN_TYPE": data.get("token_type", "Bearer"),
        "YOUTUBE_SCOPE": data.get("scope", DEFAULT_SCOPE),
        "YOUTUBE_ACCESS_TOKEN_EXPIRES_AT": str(
            now + int(data.get("expires_in", 3600) or 3600)
        ),
    }
    # Google only returns refresh_token on first consent (or prompt=consent).
    if data.get("refresh_token"):
        values["YOUTUBE_REFRESH_TOKEN"] = data["refresh_token"]
    write_env_values(values, path=path)
    return values


def build_authorize_url(
    client_id: str,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
    scope: str = DEFAULT_SCOPE,
    state: str = "bolt-youtube",
) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "access_type": "offline",
        "prompt": "consent",  # ensure refresh_token is issued
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


def exchange_code_for_tokens(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
    path: Path = ENV_FILE,
) -> dict:
    data = post_token_request(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
    )
    save_token_bundle(data, path=path)
    write_env_values(
        {
            "YOUTUBE_CLIENT_ID": client_id,
            "YOUTUBE_CLIENT_SECRET": client_secret,
            "YOUTUBE_REDIRECT_URI": redirect_uri,
        },
        path=path,
    )
    return data


def refresh_access_token(path: Path = ENV_FILE) -> Optional[str]:
    env = load_env(path)
    client_id = env.get("YOUTUBE_CLIENT_ID", "").strip()
    client_secret = env.get("YOUTUBE_CLIENT_SECRET", "").strip()
    refresh_token = env.get("YOUTUBE_REFRESH_TOKEN", "").strip()
    if not client_id or not client_secret or not refresh_token:
        return env.get("YOUTUBE_ACCESS_TOKEN", "") or None

    data = post_token_request(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
    )
    # Preserve existing refresh_token if Google omits it on refresh.
    if not data.get("refresh_token"):
        data["refresh_token"] = refresh_token
    saved = save_token_bundle(data, path=path)
    return saved.get("YOUTUBE_ACCESS_TOKEN") or None


def ensure_access_token(path: Path = ENV_FILE) -> Optional[str]:
    env = load_env(path)
    if access_token_is_fresh(env):
        return env.get("YOUTUBE_ACCESS_TOKEN")
    return refresh_access_token(path=path)
