#!/usr/bin/env python3
"""
scripts/get_twitch_bot_token.py — Get a Twitch bot chat token using Client ID/Secret

Uses the Twitch OAuth token endpoint to get a bot token.
"""

import sys
import requests
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

ENV_FILE = Path(__file__).parent.parent / ".env"


def load_env():
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


def get_app_access_token(client_id: str, client_secret: str) -> str:
    """Get an app access token using client credentials."""
    url = "https://id.twitch.tv/oauth2/token"
    params = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
    }

    response = requests.post(url, params=params)

    if response.status_code == 200:
        data = response.json()
        return data.get("access_token", "")
    else:
        print(f"  Error: {response.status_code}")
        print(f"  Response: {response.text}")
        return ""


def main():
    print()
    print("=" * 58)
    print("  🤖  Bolt — Twitch Bot Token Setup")
    print("=" * 58)
    print()

    env = load_env()

    client_id = env.get("TWITCH_CLIENT_ID", "").strip()
    client_secret = env.get("TWITCH_CLIENT_SECRET", "").strip()

    if not client_id or not client_secret:
        print("  Missing TWITCH_CLIENT_ID or TWITCH_CLIENT_SECRET in .env")
        print("  Add your credentials from dev.twitch.tv first!")
        sys.exit(1)

    print("  Getting app access token from Twitch...")
    app_token = get_app_access_token(client_id, client_secret)

    if not app_token:
        print("  ✗  Failed to get app access token")
        print("  Check your Client ID and Secret in .env")
        sys.exit(1)

    print(f"  ✓  App access token obtained")
    print()
    print("  IMPORTANT: This is an APP token, not a BOT chat token.")
    print(
        "  For Bolt to chat, you need a USER token with chat:read and chat:edit scopes."
    )
    print()
    print("  The easiest way is to use twitchtokengenerator.com:")
    print("    1. Go to: https://twitchtokengenerator.com")
    print("    2. Click 'Bot Chat Token' or 'Custom Scopes'")
    print("    3. Login with your Twitch account")
    print("    4. Select scopes: chat:read, chat:edit, whispers:read, whispers:edit")
    print("    5. Copy the access token")
    print("    6. Paste it below")
    print()
    print("  Or use the Twitch CLI: twitch token --scopes chat:read,chat:edit")
    print()

    token = input(
        "  Paste your BOT chat token (starts with oauth: or just the token):\n  > "
    ).strip()

    if not token:
        print("\n  ✗  Nothing was pasted. Run the script again.")
        sys.exit(1)

    # Remove 'oauth:' prefix if present (we store it without the prefix)
    if token.lower().startswith("oauth:"):
        token = token[6:]

    # Save token to .env
    write_env_key("TWITCH_BOT_TOKEN", token)

    # Set bot name to channel name if not set
    existing_bot_name = env.get("TWITCH_BOT_NAME", "").strip()
    if not existing_bot_name:
        channel = env.get("TWITCH_CHANNEL", "ThunderstormBilly").lower()
        write_env_key("TWITCH_BOT_NAME", channel)
        print(f"\n  ✓  TWITCH_BOT_NAME set to: {channel}")

    print(f"""
  ✓  Bot token saved to .env!

  Test the chat bot:
    python3 -m modules.Bolt_Chat

  Or do a full launch:
    python3 launch.py
""")
    print("=" * 58)
    print()


if __name__ == "__main__":
    main()
