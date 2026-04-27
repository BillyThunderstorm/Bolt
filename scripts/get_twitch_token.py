#!/usr/bin/env python3
"""
scripts/get_twitch_token.py — Get a Twitch chat token for Bolt
===============================================================
Uses twitchtokengenerator.com — the simplest and most reliable method.

The old localhost redirect method stopped working because Twitch requires
the redirect URI to be registered in your app settings. This new method
sidesteps that entirely.

How it works:
  1. Go to https://twitchtokengenerator.com in your browser
  2. Click "Bot Chat Token"
  3. Log in with the Twitch account you want Bolt to chat as
  4. Authorize the permissions
  5. Copy the ACCESS TOKEN it gives you
  6. Run this script and paste it when prompted
  7. Done — token is saved to .env automatically

Usage:
  python3 scripts/get_twitch_token.py
"""

import sys
import webbrowser
from pathlib import Path

ENV_FILE = Path(__file__).parent.parent / ".env"
TOKEN_URL = "https://twitchtokengenerator.com"


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


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print()
    print("=" * 58)
    print("  🤖  Bolt — Twitch Chat Token Setup")
    print("=" * 58)

    env = load_env()

    print("""
  We'll use twitchtokengenerator.com to get your token.
  It's the most reliable method — no redirect URI setup needed.

  Step 1 — Opening twitchtokengenerator.com in your browser...
""")

    webbrowser.open(TOKEN_URL)

    print("""  Step 2 — On the website:

    a) Click "Bot Chat Token"
    b) Log in with the Twitch account you want Bolt to chat as
       (your main account BillyandRandy is fine)
    c) Authorize the requested permissions
    d) Copy the ACCESS TOKEN shown on the results page
       (it's a long string of letters and numbers)
""")

    token = input("  Step 3 — Paste your ACCESS TOKEN here and press Enter:\n  > ").strip()

    if not token:
        print("\n  ✗  Nothing was pasted. Run the script again.")
        sys.exit(1)

    if len(token) < 10:
        print("\n  ✗  That doesn't look like a valid token. Run the script again.")
        sys.exit(1)

    # Save token to .env
    write_env_key("TWITCH_BOT_TOKEN", token)

    # Also set TWITCH_BOT_NAME if not already set
    existing_bot_name = env.get("TWITCH_BOT_NAME", "").strip()
    if not existing_bot_name:
        channel = env.get("TWITCH_CHANNEL", "billyandrandy").lower()
        write_env_key("TWITCH_BOT_NAME", channel)
        print(f"\n  ✓  TWITCH_BOT_NAME set to: {channel}")

    print(f"""
  ✓  Token saved to .env!

  Test the chat bot:
    python3 -m modules.Bolt_Chat

  Test the voice:
    python3 -m modules.Bolt_Voice

  Or do a full launch:
    python3 launch.py
""")
    print("=" * 58)
    print()


if __name__ == "__main__":
    main()
