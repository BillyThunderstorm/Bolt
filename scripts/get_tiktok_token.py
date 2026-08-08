#!/usr/bin/env python3
"""Get and save TikTok OAuth tokens for Bolt.

This script prints a TikTok authorization URL, waits for the redirect URL or
authorization code, exchanges it for tokens, and saves the result to `.env`.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import secrets
import string
import sys
import urllib.parse
from pathlib import Path

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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.TikTok_Auth import (
    ENV_FILE,
    exchange_code_for_tokens,
    load_env,
    write_env_values,
)

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
# video.list is required for stats sync (Performance_Sync / sync_tiktok_stats.py).
# video.publish + video.upload are for Content Posting API (optional if you post manually).
DEFAULT_SCOPES = "user.info.basic,video.list,video.publish,video.upload"


def make_code_verifier(length: int = 64) -> str:
    alphabet = string.ascii_letters + string.digits + "-._~"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def extract_code(value: str) -> tuple[str, str]:
    text = value.strip()
    if text.startswith("http://") or text.startswith("https://"):
        parsed = urllib.parse.urlparse(text)
        query = urllib.parse.parse_qs(parsed.query)
        if query.get("error"):
            raise RuntimeError(f"TikTok returned an error: {query['error'][0]}")
        return query.get("code", [""])[0], query.get("state", [""])[0]
    return text, ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Authorize Bolt with TikTok and save tokens to .env."
    )
    parser.add_argument("--client-key", default="")
    parser.add_argument("--client-secret", default="")
    parser.add_argument("--redirect-uri", default="")
    parser.add_argument("--scopes", default=DEFAULT_SCOPES)
    args = parser.parse_args()

    env = load_env()
    client_key = args.client_key or env.get("TIKTOK_CLIENT_KEY", "").strip()
    client_secret = args.client_secret or env.get("TIKTOK_CLIENT_SECRET", "").strip()
    redirect_uri = args.redirect_uri or env.get("TIKTOK_REDIRECT_URI", "").strip()

    print("\nBolt TikTok Token Setup")
    print("=" * 58)
    print(
        "You need the Client Key, Client Secret, and Redirect URI from your TikTok Developer app."
    )
    print(
        "The Redirect URI must exactly match one registered in TikTok's developer portal.\n"
    )

    if not client_key:
        client_key = input("TikTok Client Key: ").strip()
    if not client_secret:
        client_secret = getpass.getpass("TikTok Client Secret: ").strip()
    if not redirect_uri:
        redirect_uri = input("TikTok Redirect URI: ").strip()

    if not client_key or not client_secret or not redirect_uri:
        print("Missing TikTok app credentials. Run this again when you have them.")
        return 1

    verifier = make_code_verifier()
    state = secrets.token_urlsafe(24)
    params = {
        "client_key": client_key,
        "response_type": "code",
        "scope": args.scopes,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge(verifier),
        "code_challenge_method": "S256",
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    write_env_values(
        {
            "TIKTOK_CLIENT_KEY": client_key,
            "TIKTOK_CLIENT_SECRET": client_secret,
            "TIKTOK_REDIRECT_URI": redirect_uri,
        }
    )

    print("\nOpen this URL in your browser and approve Bolt:")
    print(auth_url)
    print(
        "\nAfter approval, paste the full redirect URL here. If TikTok only shows a code, paste the code."
    )

    pasted = input("\nRedirect URL or code:\n> ").strip()
    code, returned_state = extract_code(pasted)
    if not code:
        print("No authorization code found.")
        return 1
    if returned_state and returned_state != state:
        print("State mismatch. For safety, run the script again.")
        return 1

    data = exchange_code_for_tokens(
        client_key=client_key,
        client_secret=client_secret,
        code=code,
        redirect_uri=redirect_uri,
        code_verifier=verifier,
        path=ENV_FILE,
    )
    if "data" in data and isinstance(data["data"], dict):
        data = data["data"]

    scopes = data.get("scope", "")
    print("\nSaved TikTok tokens to .env.")
    print(f"Authorized scopes: {scopes or '(none returned)'}")
    if "video.list" not in (scopes or ""):
        print(
            "Note: video.list was not granted — stats sync will fail until you "
            "re-run with that scope and it is approved on your TikTok developer app."
        )
    else:
        print(
            "video.list granted — you can pull views/likes with:\n"
            "  python3 scripts/sync_tiktok_stats.py --dry-run"
        )
    if "video.publish" not in (scopes or ""):
        print(
            "Note: direct auto-posting needs the video.publish scope approved by TikTok."
        )
    print("\nVerify with: python3 scripts/verify.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
