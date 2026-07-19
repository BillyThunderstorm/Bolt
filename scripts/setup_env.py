#!/usr/bin/env python3
"""
setup_env.py — Interactive .env setup helper for Bolt

Run this to fill in missing credentials step-by-step.
"""

import os
import sys
from pathlib import Path

ENV_FILE = Path(".env")


def load_current_env():
    """Load existing .env values."""
    env = {}
    if ENV_FILE.exists():
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env[key.strip()] = value.strip()
    return env


def save_env(env):
    """Save env dict back to file, preserving comments."""
    lines = []
    if ENV_FILE.exists():
        with open(ENV_FILE) as f:
            lines = f.readlines()

    with open(ENV_FILE, "w") as f:
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key, _, _ = stripped.partition("=")
                if key.strip() in env:
                    f.write(f"{key.strip()}={env[key.strip()]}\n")
                else:
                    f.write(line)
            else:
                f.write(line)

        # Add any new keys not in original file
        existing_keys = set()
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key, _, _ = stripped.partition("=")
                existing_keys.add(key.strip())

        for key, value in env.items():
            if key not in existing_keys:
                f.write(f"{key}={value}\n")


def prompt(key, description, current_value="", secret=False):
    """Prompt user for a value."""
    if (
        current_value
        and current_value != "TODO_get_from_platform_openai"
        and not current_value.startswith("TODO")
    ):
        display = "****" + current_value[-4:] if secret else current_value
        print(f"  Current: {display}")

    value = input(f"  {description}: ").strip()
    if value:
        return value
    return current_value


def main():
    print("=" * 60)
    print("  Bolt — Environment Setup Helper")
    print("=" * 60)
    print()

    env = load_current_env()

    # ── OBS ───────────────────────────────────────────────────────────────────
    print("OBS WebSocket (for real-time clip saves)")
    print("  Get password: OBS → Tools → WebSocket Server Settings")
    print()
    env["OBS_HOST"] = prompt("OBS_HOST", "OBS Host", env.get("OBS_HOST", "localhost"))
    env["OBS_PORT"] = prompt("OBS_PORT", "OBS Port", env.get("OBS_PORT", "4455"))
    env["OBS_PASSWORD"] = prompt(
        "OBS_PASSWORD", "OBS Password", env.get("OBS_PASSWORD", ""), secret=True
    )
    print()

    # ── Twitch ────────────────────────────────────────────────────────────────
    print("Twitch (for chat bot)")
    print("  Bot token: https://twitchapps.com/tmi/")
    print("  Login as your bot account (e.g., BoltBot)")
    print()
    env["TWITCH_CHANNEL"] = prompt(
        "TWITCH_CHANNEL",
        "Your Twitch channel",
        env.get("TWITCH_CHANNEL", "ThunderstormBilly"),
    )
    env["TWITCH_BOT_NAME"] = prompt(
        "TWITCH_BOT_NAME", "Bot account name", env.get("TWITCH_BOT_NAME", "BoltBot")
    )

    bot_token = env.get("TWITCH_BOT_TOKEN", "")
    if not bot_token or bot_token.startswith("TODO"):
        print("  → TWITCH_BOT_TOKEN is missing or incomplete")
        print("  → Go to https://twitchapps.com/tmi/ and get your oauth token")
        token = input("  Paste Twitch bot token (oauth:...): ").strip()
        if token:
            env["TWITCH_BOT_TOKEN"] = token
    else:
        print(
            "  TWITCH_BOT_TOKEN: ****" + bot_token[-4:]
            if len(bot_token) > 4
            else "  TWITCH_BOT_TOKEN: set"
        )
    print()

    # ── OpenAI ────────────────────────────────────────────────────────────────
    print("OpenAI (for AI titles and chat responses)")
    print("  Get key: https://platform.openai.com/account/api-keys")
    print()

    openai_key = env.get("OPENAI_API_KEY", "")
    if (
        not openai_key
        or openai_key.startswith("TODO")
        or openai_key == "sk_your_key_here"
    ):
        print("  → OPENAI_API_KEY is missing or incomplete")
        print("  → You can skip this for now (Bolt will use template titles)")
        token = input(
            "  Paste OpenAI API key (sk-...) or press Enter to skip: "
        ).strip()
        if token:
            env["OPENAI_API_KEY"] = token
        else:
            print("  (OpenAI skipped — using template fallback)")
    else:
        print("  OPENAI_API_KEY: ****" + openai_key[-8:])
    print()

    # ── Discord ───────────────────────────────────────────────────────────────
    print("Discord (for peak-hour alerts)")
    print("  Create webhook: Discord → Channel Settings → Integrations → Webhooks")
    print()

    discord_url = env.get("DISCORD_WEBHOOK_URL", "")
    if not discord_url or discord_url.startswith("TODO"):
        print("  → DISCORD_WEBHOOK_URL is missing or incomplete")
        webhook = input("  Paste Discord webhook URL or press Enter to skip: ").strip()
        if webhook:
            env["DISCORD_WEBHOOK_URL"] = webhook
        else:
            print("  (Discord alerts skipped)")
    else:
        print(
            "  DISCORD_WEBHOOK_URL: ****" + discord_url[-20:]
            if len(discord_url) > 20
            else "  DISCORD_WEBHOOK_URL: set"
        )
    print()

    # ── ElevenLabs ────────────────────────────────────────────────────────────
    print("ElevenLabs (for neural voice TTS)")
    eleven_key = env.get("ELEVENLABS_API_KEY", "")
    if eleven_key and not eleven_key.startswith("sk_"):
        print(f"  → ELEVENLABS_API_KEY may be invalid (current: {eleven_key[:8]}...)")
    else:
        print(
            f"  ELEVENLABS_API_KEY: ****{eleven_key[-8:] if len(eleven_key) > 8 else 'not set'}"
        )
    print()

    # Save
    save_env(env)
    print("=" * 60)
    print("  .env updated!")
    print("=" * 60)

    # Summary
    print()
    print("Setup Summary:")
    print(f"  OBS Password:       {'✓' if env.get('OBS_PASSWORD') else '○'}")
    print(
        f"  Twitch Bot Token:   {'✓' if env.get('TWITCH_BOT_TOKEN') and not env.get('TWITCH_BOT_TOKEN', '').startswith('TODO') else '○'}"
    )
    print(
        f"  OpenAI API Key:     {'✓' if env.get('OPENAI_API_KEY') and not env.get('OPENAI_API_KEY', '').startswith('TODO') else '○ (using templates)'}"
    )
    print(
        f"  Discord Webhook:    {'✓' if env.get('DISCORD_WEBHOOK_URL') and not env.get('DISCORD_WEBHOOK_URL', '').startswith('TODO') else '○'}"
    )
    print(
        f"  ElevenLabs Key:     {'✓' if env.get('ELEVENLABS_API_KEY') and env.get('ELEVENLABS_API_KEY', '').startswith('sk_') else '○'}"
    )
    print()

    missing = []
    if not env.get("TWITCH_BOT_TOKEN") or env.get("TWITCH_BOT_TOKEN", "").startswith(
        "TODO"
    ):
        missing.append("Twitch bot token (needed for chat)")
    if not env.get("OPENAI_API_KEY") or env.get("OPENAI_API_KEY", "").startswith(
        "TODO"
    ):
        missing.append("OpenAI API key (needed for AI features)")

    if missing:
        print("Still needed for full functionality:")
        for item in missing:
            print(f"  - {item}")
        print()
        print("Bolt will still run without these — features will use fallbacks.")
    else:
        print("All required credentials configured!")

    print()
    print("Run: python3 launch.py")


if __name__ == "__main__":
    main()
