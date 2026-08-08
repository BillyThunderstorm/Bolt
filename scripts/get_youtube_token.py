#!/usr/bin/env python3
"""Get and save YouTube (Google) OAuth tokens for Bolt.

Creates an authorization URL for the YouTube Data API readonly scope,
waits for you to paste the redirect URL/code, and saves tokens to ``.env``.

Prerequisites:
  1. Google Cloud project with **YouTube Data API v3** enabled
  2. OAuth client (Desktop app recommended)
  3. Your Google account added as a test user if the app is in Testing

Usage:
  python3 scripts/get_youtube_token.py
  python3 scripts/get_youtube_token.py --client-id ... --client-secret ...
"""

from __future__ import annotations

import argparse
import getpass
import secrets
import sys
import urllib.parse
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from _paths import REPO_ROOT  # noqa: E402

_CORE = REPO_ROOT / "Core"
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

from modules.YouTube_Auth import (  # noqa: E402
    DEFAULT_REDIRECT_URI,
    DEFAULT_SCOPE,
    ENV_FILE,
    build_authorize_url,
    exchange_code_for_tokens,
    load_env,
    write_env_values,
)


def extract_code(value: str) -> tuple[str, str]:
    text = value.strip()
    if text.startswith("http://") or text.startswith("https://"):
        parsed = urllib.parse.urlparse(text)
        query = urllib.parse.parse_qs(parsed.query)
        if query.get("error"):
            raise RuntimeError(
                f"Google returned an error: {query['error'][0]} "
                f"({(query.get('error_description') or [''])[0]})"
            )
        return query.get("code", [""])[0], query.get("state", [""])[0]
    return text, ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Authorize Bolt with YouTube and save tokens to .env."
    )
    parser.add_argument("--client-id", default="")
    parser.add_argument("--client-secret", default="")
    parser.add_argument("--redirect-uri", default="")
    parser.add_argument("--scope", default=DEFAULT_SCOPE)
    args = parser.parse_args()

    env = load_env()
    client_id = args.client_id or env.get("YOUTUBE_CLIENT_ID", "").strip()
    client_secret = args.client_secret or env.get("YOUTUBE_CLIENT_SECRET", "").strip()
    redirect_uri = (
        args.redirect_uri
        or env.get("YOUTUBE_REDIRECT_URI", "").strip()
        or DEFAULT_REDIRECT_URI
    )

    print("\nBolt YouTube Token Setup")
    print("=" * 58)
    print(
        "You need a Google Cloud OAuth Client ID + Secret with "
        "YouTube Data API v3 enabled."
    )
    print(
        "Desktop app type is easiest. Redirect URI must match exactly "
        f"(default: {DEFAULT_REDIRECT_URI}).\n"
    )

    if not client_id:
        client_id = input("YouTube / Google Client ID: ").strip()
    if not client_secret:
        client_secret = getpass.getpass("YouTube / Google Client Secret: ").strip()
    if args.redirect_uri or not env.get("YOUTUBE_REDIRECT_URI"):
        # Only re-prompt if not already saved and not passed
        if not (args.redirect_uri or env.get("YOUTUBE_REDIRECT_URI", "").strip()):
            custom = input(
                f"Redirect URI [{DEFAULT_REDIRECT_URI}]: "
            ).strip()
            if custom:
                redirect_uri = custom

    if not client_id or not client_secret:
        print("Missing Google OAuth credentials. Create them in Cloud Console first.")
        return 1

    state = secrets.token_urlsafe(16)
    auth_url = build_authorize_url(
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=args.scope,
        state=state,
    )

    write_env_values(
        {
            "YOUTUBE_CLIENT_ID": client_id,
            "YOUTUBE_CLIENT_SECRET": client_secret,
            "YOUTUBE_REDIRECT_URI": redirect_uri,
        }
    )

    print("\nOpen this URL in your browser and approve Bolt:")
    print(auth_url)
    print(
        "\nAfter approval, the browser will go to a (possibly blank) page on "
        "127.0.0.1. Copy the FULL address bar URL and paste it here."
    )

    pasted = input("\nRedirect URL or code:\n> ").strip()
    try:
        code, returned_state = extract_code(pasted)
    except RuntimeError as exc:
        print(exc)
        return 1
    if not code:
        print("No authorization code found.")
        return 1
    if returned_state and returned_state != state:
        print("State mismatch. For safety, run the script again.")
        return 1

    try:
        data = exchange_code_for_tokens(
            client_id=client_id,
            client_secret=client_secret,
            code=code,
            redirect_uri=redirect_uri,
            path=ENV_FILE,
        )
    except RuntimeError as exc:
        print(f"\nToken exchange failed: {exc}")
        return 1

    print("\nSaved YouTube tokens to .env.")
    print(f"Scopes: {data.get('scope') or args.scope}")
    if not data.get("refresh_token") and not load_env().get("YOUTUBE_REFRESH_TOKEN"):
        print(
            "Warning: no refresh_token returned. Re-run with prompt=consent "
            "(this script already requests it), or revoke app access at "
            "https://myaccount.google.com/permissions and try again."
        )
    print("\nNext:")
    print("  python3 scripts/sync_youtube_stats.py --dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
