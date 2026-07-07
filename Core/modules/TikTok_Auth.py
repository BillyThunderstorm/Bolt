#!/usr/bin/env python3
"""TikTok OAuth token helpers for Bolt.

Keeps TikTok credentials in the local `.env` file and refreshes short-lived
access tokens with the long-lived refresh token.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"


def load_env(path: Path = ENV_FILE) -> dict:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def write_env_values(values: dict, path: Path = ENV_FILE) -> None:
    lines = []
    seen = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
            key = line.split("=", 1)[0].strip() if "=" in line else ""
            if key in values:
                lines.append(f"{key}={values[key]}\n")
                seen.add(key)
            else:
                lines.append(line)
    for key, value in values.items():
        if key not in seen:
            lines.append(f"{key}={value}\n")
    path.write_text("".join(lines), encoding="utf-8")


def access_token_is_fresh(
    env: Optional[dict] = None, leeway_seconds: int = 300
) -> bool:
    env = env or load_env()
    token = env.get("TIKTOK_ACCESS_TOKEN", "").strip()
    expires_at = float(env.get("TIKTOK_ACCESS_TOKEN_EXPIRES_AT", "0") or 0)
    return bool(token and expires_at > time.time() + leeway_seconds)


def post_token_request(payload: dict) -> dict:
    encoded = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(
        TOKEN_URL,
        data=encoded,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Cache-Control": "no-cache",
        },
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
        raise RuntimeError(f"TikTok token request failed: {error}") from exc


def save_token_bundle(data: dict, path: Path = ENV_FILE) -> dict:
    if "data" in data and isinstance(data["data"], dict):
        data = data["data"]
    if not data.get("access_token"):
        safe = {key: value for key, value in data.items() if "token" not in key.lower()}
        raise RuntimeError(f"TikTok did not return an access token. Response: {safe}")

    now = int(time.time())
    values = {
        "TIKTOK_ACCESS_TOKEN": data.get("access_token", ""),
        "TIKTOK_REFRESH_TOKEN": data.get("refresh_token", ""),
        "TIKTOK_OPEN_ID": data.get("open_id", ""),
        "TIKTOK_SCOPE": data.get("scope", ""),
        "TIKTOK_TOKEN_TYPE": data.get("token_type", "Bearer"),
        "TIKTOK_ACCESS_TOKEN_EXPIRES_AT": str(
            now + int(data.get("expires_in", 0) or 0)
        ),
        "TIKTOK_REFRESH_TOKEN_EXPIRES_AT": str(
            now + int(data.get("refresh_expires_in", 0) or 0)
        ),
    }
    write_env_values(values, path=path)
    return values


def exchange_code_for_tokens(
    client_key: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    code_verifier: str = "",
    path: Path = ENV_FILE,
) -> dict:
    payload = {
        "client_key": client_key,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
    if code_verifier:
        payload["code_verifier"] = code_verifier
    data = post_token_request(payload)
    save_token_bundle(data, path=path)
    return data


def refresh_access_token(path: Path = ENV_FILE) -> Optional[str]:
    env = load_env(path)
    client_key = env.get("TIKTOK_CLIENT_KEY", "")
    client_secret = env.get("TIKTOK_CLIENT_SECRET", "")
    refresh_token = env.get("TIKTOK_REFRESH_TOKEN", "")
    if not client_key or not client_secret or not refresh_token:
        return env.get("TIKTOK_ACCESS_TOKEN", "") or None

    data = post_token_request(
        {
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
    )
    saved = save_token_bundle(data, path=path)
    return saved.get("TIKTOK_ACCESS_TOKEN") or None


def ensure_access_token(path: Path = ENV_FILE) -> Optional[str]:
    env = load_env(path)
    if access_token_is_fresh(env):
        return env.get("TIKTOK_ACCESS_TOKEN")
    return refresh_access_token(path=path)
