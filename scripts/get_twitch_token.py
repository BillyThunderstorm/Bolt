#!/usr/bin/env python3
"""
scripts/get_twitch_token.py — Get a Twitch chat token for Bolt
===============================================================
Simple version — no local server, no ports, no firewall issues.

How it works:
  1. Opens Twitch's authorization page in your browser
  2. You click Authorize
  3. Your browser goes to a URL that contains your token
     (the page might show an error — that's fine, the token is in the URL)
  4. You copy the full URL from your browser's address bar and paste it here
  5. Done — token is saved to .env automatically

Usage:
  python3 scripts/get_twitch_token.py
"""

import os
import re
import sys
import webbrowser
import urllib.parse
from pathlib import Path

ENV_FILE      = Path(__file__).parent.parent / ".env"
CLIENT_ID_KEY = "TWITCH_CLIENT_ID"
SCOPES        = "chat:read chat:edit"

# We use https://localhost:3000 as the redirect URI — Twitch requires a registered URI.
# The page will likely show "connection refused" or a certificate error — that's fine.
# The token is in the URL bar, not on the page.
REDIRECT_URI  = "https://localhost:3000"


# ── Load / write .env ─────────────────────────────────────────────────────────

def load_env() -> dict:
    env = {}
    if ENV_FILE.exists():
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
    return env


def write_env_key(key: str, value: str):
    lines = []
    found = False
    if ENV_FILE.exists():
        with open(ENV_FILE) as f:
            for line in f:
                if line.strip().startswith(f"{key}="):
                    lines.append(f"{key}={value}\n")
                    found = True
                else:
                    lines.append(line)
    if not found:
        lines.append(f"{key}={value}\n")
    with open(ENV_FILE, "w") as f:
        f.writelines(lines)


# ── Token parsing ─────────────────────────────────────────────────────────────

def extract_token(pasted_url: str) -> str:
    """
    Pull the access_token out of whatever the user pasted.
    Works whether they pasted the full URL or just the fragment.

    Twitch puts the token in the URL hash like:
      http://localhost:3000/#access_token=abc123&scope=...&token_type=bearer
    """
    # Try to parse from URL hash fragment first
    if "#" in pasted_url:
        fragment = pasted_url.split("#", 1)[1]
        params   = urllib.parse.parse_qs(fragment)
        if "access_token" in params:
            return params["access_token"][0]

    # Try query string (some flows use ?access_token=...)
    if "?" in pasted_url or "access_token=" in pasted_url:
        query  = pasted_url.split("?", 1)[-1].split("#", 1)[0]
        params = urllib.parse.parse_qs(query)
        if "access_token" in params:
            return params["access_token"][0]

    # Last resort: just look for the token pattern directly
    match = re.search(r"access_token=([a-z0-9]+)", pasted_url)
    if match:
        return match.group(1)

    return ""


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print()
    print("=" * 58)
    print("  🦊  Bolt — Twitch Chat Token Setup (simple version)")
    print("=" * 58)

    env       = load_env()
    client_id = env.get(CLIENT_ID_KEY, "").strip()

    if not client_id:
        print(f"""
  ✗  {CLIENT_ID_KEY} not found in .env

  Open .env and make sure TWITCH_CLIENT_ID is set.
  Get it from: https://dev.twitch.tv/console/apps
""")
        sys.exit(1)

    # Build the implicit-grant auth URL.
    # response_type=token means Twitch puts the token directly in the redirect URL
    # — no code exchange step needed, and no server needed to catch it.
    auth_url = (
        "https://id.twitch.tv/oauth2/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        "&response_type=token"
        f"&scope={urllib.parse.quote(SCOPES)}"
        "&force_verify=true"
    )

    print(f"""
  Step 1 — Opening Twitch authorization page…
  Log in as the account you want Bolt to chat as
  (your main Twitch account is fine).

  If the browser doesn't open automatically, go here:
  {auth_url}
""")

    webbrowser.open(auth_url)

    print("""  Step 2 — After you click "Authorize" on Twitch's page:

    Your browser will go to a URL starting with:
      https://localhost:3000/#access_token=...

    The page might show an error like "This site can't be reached"
    — that's totally normal and expected. The page doesn't need to load.

    Just look at your browser's ADDRESS BAR and copy the full URL.
""")

    pasted = input("  Step 3 — Paste the full URL here and press Enter:\n  > ").strip()

    if not pasted:
        print("\n  ✗  Nothing was pasted. Run the script again.")
        sys.exit(1)

    token = extract_token(pasted)

    if not token:
        print(f"""
  ✗  Couldn't find an access_token in what you pasted.

  Make sure you copied the FULL URL from the browser address bar.
  It should look like:
    http://localhost:3000/#access_token=abc123xyz...&scope=...

  Run the script again and try once more.
""")
        sys.exit(1)

    # Save to .env
    write_env_key("TWITCH_BOT_TOKEN", token)
    write_env_key("TWITCH_BOT_NAME", env.get("TWITCH_CHANNEL", "").lower() or "billyandrandy")

    print(f"""
  ✓  Token saved to .env!

  Test the chat bot:
    python3 -m modules.Bolt_Chat

  Or do a full launch:
    python3 launch.py
""")
    print("=" * 58)
    print()


if __name__ == "__main__":
    main()
