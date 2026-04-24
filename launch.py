#!/usr/bin/env python3
"""
launch.py — Bolt startup launcher
==================================
Run this instead of bot.py. It will:
  1. Run setup wizard on first launch (creates config.json + .env)
  2. Check .env for critical keys and print a todo-checklist
  3. Launch OBS if integration is enabled
  4. Wait for OBS to be ready (with timeout)
  5. Hand off to bot.py

Usage:  python3 launch.py
        python3 launch.py live      # start in live streaming mode
        python3 launch.py process   # process latest recording
"""

import subprocess
import sys
import os
import time
import json
import platform
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from modules.notifier import notify, notify_startup

CONFIG_FILE = "config.json"
ENV_FILE    = ".env"

REQUIRED_KEYS = [
    ("OBS_PASSWORD",             "OBS WebSocket password"),
    ("ANTHROPIC_API_KEY",        "Anthropic key for AI titles + Bolt's personality"),
]
OPTIONAL_KEYS = [
    ("TWITCH_BOT_TOKEN",         "Bolt chat bot (Twitch OAuth token)"),
    ("STREAMLABS_SOCKET_TOKEN",  "Streamlabs token (donations/raids/subs)"),
    ("TWITCH_CLIENT_ID",         "Twitch app credentials (native clip creation)"),
    ("DISCORD_WEBHOOK_URL",      "Discord webhook for peak-hour alerts"),
]


def main():
    notify(
        "Bolt — Streaming AI Assistant",
        level="startup",
        reason="Starting up. Bolt will check your config, launch OBS if needed, "
               "and then begin monitoring your stream."
    )

    # ── Step 1: First-run config wizard ──────────────────────────────────────
    if not Path(CONFIG_FILE).exists():
        notify(
            "No config.json found — running first-time setup wizard",
            level="info",
            reason="This only runs once. Bolt will ask a few questions and create "
                   "config.json and .env automatically. You can edit either file at any time."
        )
        _run_setup_wizard()
    else:
        notify("Config found ✓", level="success")

    config = _load_config()

    # ── Step 2: Check .env file ───────────────────────────────────────────────
    _check_env_file()

    # ── Step 3: Twitch stats ──────────────────────────────────────────────────
    _show_twitch_stats()

    # ── Step 4: Voice pre-stream checklist ───────────────────────────────────
    _run_voice_checklist(config)

    # ── Step 5: Launch OBS if needed ─────────────────────────────────────────
    obs_connected = False
    if config.get("use_obs_integration", True):
        obs_connected = _launch_and_wait_for_obs(config)
    else:
        notify(
            "OBS integration disabled — folder-watch mode only",
            level="info",
            reason="Set 'use_obs_integration': true in config.json to enable OBS auto-launch "
                   "and real-time audio monitoring. In folder-watch mode, Bolt still processes "
                   "any recordings you drop into the recordings/ folder."
        )

    # ── Step 6: Print missing-items checklist ────────────────────────────────
    _print_checklist(config)

    # ── Step 7: Refresh checkup dashboard data ───────────────────────────────
    try:
        from modules.Checkup_Writer import update_checkup
        update_checkup()
    except Exception as exc:
        notify(f"Checkup data skipped: {exc}", level="info")

    # ── Step 8: Clean up old clips ────────────────────────────────────────────
    _cleanup_old_clips()

    # ── Step 9: Start Bolt's voice + chat bot ────────────────────────────────
    _start_personality_layer()

    # ── Step 10: Hand off to bot.py ───────────────────────────────────────────
    mode = sys.argv[1] if len(sys.argv) > 1 else "live"
    notify(
        f"Handing off to bot.py (mode={mode})…",
        level="info",
        reason="launch.py's job is done. bot.py takes over and runs the full pipeline."
    )

    try:
        args = [sys.executable, "bot.py"] + sys.argv[1:]
        os.execv(sys.executable, args)
    except Exception as exc:
        notify(f"Failed to start bot.py: {exc}", level="error")
        sys.exit(1)


# ── Clip cleanup ──────────────────────────────────────────────────────────────

def _cleanup_old_clips(max_age_days: int = 14):
    """
    Delete clips and vertical clips older than max_age_days.

    Why auto-delete? Clips pile up fast. After 14 days they're either
    already posted or not worth posting — keeping them just wastes space.
    Runs silently on every launch so you never have to think about it.
    """
    import time
    cutoff = time.time() - (max_age_days * 86400)  # 86400 seconds in a day
    folders = [Path("clips"), Path("vertical_clips")]
    extensions = {".mp4", ".mkv", ".mov"}
    deleted = []

    for folder in folders:
        if not folder.exists():
            continue
        for f in folder.iterdir():
            if f.suffix.lower() in extensions and f.stat().st_mtime < cutoff:
                try:
                    f.unlink()
                    deleted.append(f.name)
                except Exception:
                    pass  # skip if file is locked or in use

    if deleted:
        notify(
            f"🗑️  Cleaned up {len(deleted)} clip{'s' if len(deleted) != 1 else ''} older than {max_age_days} days.",
            level="info",
            reason="Old clips auto-deleted on launch. Anything older than 14 days is assumed posted or skipped."
        )
    else:
        notify(
            f"✅ No clips older than {max_age_days} days — nothing to clean up.",
            level="info",
            reason="Clip folder check passed. All clips are recent."
        )


# ── Phase 3: Personality layer ─────────────────────────────────────────────────

def _start_personality_layer():
    """
    Start Bolt's voice (TTS) and chat bot before handing off to bot.py.

    Why here and not in bot.py?
      launch.py runs once at startup and sets up everything. The chat bot
      needs to connect to Twitch BEFORE streaming starts so Bolt is already
      live in chat when Billy goes live. Starting it here gives ~30 seconds
      of connection time before bot.py takes over.

    The chat bot runs in a background thread (daemon=True) so it persists
    after os.execv hands off to bot.py — both processes share the same OS
    process, so the thread keeps running.

    Wait — os.execv REPLACES the process. So the thread won't survive.
    That's why bot.py also calls start_chat_bot() if it's not already running.
    launch.py just does an early warm-up attempt.
    """
    # Voice check
    try:
        from modules.Bolt_Voice import say_event, is_available
        if is_available():
            say_event("startup")
            notify("Bolt voice (TTS) active ✓", level="success",
                   reason="Bolt will speak out loud for highlights, raids, and subs. "
                          "Mute with Bolt_VOICE_MUTE=true in .env if needed.")
        else:
            notify("Bolt voice (TTS) not available on this system", level="info",
                   reason="TTS requires macOS. Bolt will still work — just no spoken alerts.")
    except Exception as exc:
        notify(f"Voice module skipped: {exc}", level="info")

    # Chat bot warm-up (full start happens in bot.py after execv)
    twitch_token = os.getenv("TWITCH_BOT_TOKEN", "")
    if twitch_token:
        notify(
            "Bolt chat bot will connect when bot.py starts…",
            level="info",
            reason="TWITCH_BOT_TOKEN found. Bolt will join Twitch chat automatically."
        )
    else:
        notify(
            "Chat bot not configured — skipping",
            level="info",
            reason="To enable: add TWITCH_BOT_TOKEN and TWITCH_BOT_NAME to .env.\n"
                   "     Get a token at: https://twitchapps.com/tmi/"
        )


# ── OBS launcher ──────────────────────────────────────────────────────────────

def _launch_and_wait_for_obs(config: dict) -> bool:
    """
    Launch OBS if not running, then wait up to 30 seconds for WebSocket.
    Returns True if connected, False if timeout.
    """
    if not _is_obs_running():
        notify(
            "OBS not running — launching it now",
            level="info",
            reason="Bolt found OBS integration enabled and will open OBS automatically "
                   "so you don't have to do it manually before every stream."
        )
        _open_obs(config)
        notify("Waiting for OBS to initialise (up to 30 seconds)…", level="info")
        time.sleep(5)
    else:
        notify("OBS is already running ✓", level="success")

    # Poll for WebSocket connection
    for attempt in range(1, 7):
        notify(
            f"Connecting to OBS WebSocket (attempt {attempt}/6)…",
            level="info",
            reason="The OBS WebSocket connection is how Bolt asks OBS to save replay clips. "
                   "It's a persistent two-way channel — like a remote control for OBS."
        )
        try:
            import websocket as _ws
            host = config.get("obs_host", os.getenv("OBS_HOST", "localhost"))
            port = config.get("obs_port", int(os.getenv("OBS_PORT", "4455")))
            sock = _ws.create_connection(f"ws://{host}:{port}", timeout=3)
            sock.close()
            notify(
                f"OBS WebSocket reachable at {host}:{port} ✓",
                level="success",
                reason="OBS is open and accepting connections. Bolt will complete the "
                       "full auth handshake when bot.py starts."
            )
            return True
        except Exception:
            time.sleep(5)

    notify(
        "OBS WebSocket timed out — continuing in folder-watch mode",
        level="warning",
        reason="Could not reach OBS after 30 seconds. Common causes: "
               "WebSocket Server not enabled in OBS (Tools → WebSocket Server Settings), "
               "wrong port (default: 4455), or OBS still loading. "
               "Bolt will still process recordings dropped into the recordings/ folder."
    )
    return False


def _is_obs_running() -> bool:
    system = platform.system()
    try:
        if system == "Windows":
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq obs64.exe"],
                capture_output=True, text=True
            )
            return "obs64.exe" in result.stdout
        else:   # macOS / Linux
            result = subprocess.run(["pgrep", "-x", "OBS"], capture_output=True, text=True)
            return bool(result.stdout.strip())
    except Exception:
        return False


def _open_obs(config: dict):
    system   = platform.system()
    obs_path = config.get("obs_path", "")

    if obs_path and Path(obs_path).exists():
        subprocess.Popen([obs_path])
        return

    defaults = {
        "Windows": [
            r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
            r"C:\Program Files (x86)\obs-studio\bin\32bit\obs32.exe",
        ],
        "Darwin": ["/Applications/OBS.app/Contents/MacOS/OBS"],
        "Linux":  ["obs"],
    }
    for path in defaults.get(system, []):
        try:
            subprocess.Popen([path])
            return
        except FileNotFoundError:
            continue

    notify(
        "Could not find OBS — add 'obs_path' to config.json",
        level="warning",
        reason="Add 'obs_path': '/full/path/to/OBS' to config.json. "
               "Example for macOS: /Applications/OBS.app/Contents/MacOS/OBS"
    )


# ── Config / setup ────────────────────────────────────────────────────────────

def _run_setup_wizard():
    """
    7-step interactive first-run wizard.
    Writes config.json and merges into .env (preserves existing keys).
    """
    print("\n" + "=" * 60)
    print("  Bolt — First-time Setup  (~60 seconds)")
    print("  Press Enter to accept defaults shown in [brackets]")
    print("=" * 60 + "\n")

    # ── Step 1: Game ──────────────────────────────────────────────────────────
    print("STEP 1 — What game are you streaming?")
    print("  Bolt has built-in profiles for Marvel Rivals, Valorant, Apex,")
    print("  Fortnite, Warzone, Overwatch 2, CS2, and more.\n")
    game = input("  Game name [Marvel Rivals]: ").strip() or "Marvel Rivals"

    # ── Step 2: Sensitivity ───────────────────────────────────────────────────
    print("\nSTEP 2 — Highlight sensitivity")
    print("  Controls how easily a moment is flagged as a highlight.")
    print("  You can fine-tune this per-game later in game_configs.json.\n")
    sensitivity = ""
    while sensitivity not in ["1", "2", "3"]:
        sensitivity = input(
            "    1 = very sensitive  (more clips, catches everything)\n"
            "    2 = balanced        (recommended)\n"
            "    3 = strict          (only the biggest moments)\n"
            "  Choose 1/2/3 [2]: "
        ).strip() or "2"
    sens_value = {"1": 0.5, "2": 0.7, "3": 0.85}[sensitivity]

    # ── Step 3: Twitch ────────────────────────────────────────────────────────
    print("\nSTEP 3 — Twitch channel")
    print("  Bolt monitors your Twitch chat for hype moments (no login needed).")
    print("  Optional: add TWITCH_CLIENT_ID + TWITCH_OAUTH_TOKEN later for")
    print("  native Twitch clip creation.\n")
    twitch_channel    = input("  Twitch channel name [BillyandRandyGaming]: ").strip() \
                        or "BillyandRandyGaming"
    hype_threshold    = input("  Chat hype threshold — msgs/sec to trigger a clip [3]: ").strip() \
                        or "3"

    # ── Step 4: OBS ───────────────────────────────────────────────────────────
    print("\nSTEP 4 — OBS integration")
    print("  Lets Bolt save replay buffer clips in real time via OBS WebSocket.")
    print("  Enable OBS WebSocket: Tools → WebSocket Server Settings → Enable\n")
    use_obs      = (input("  Use OBS integration? (y/n) [y]: ").strip().lower() or "y") == "y"
    obs_path     = ""
    obs_password = ""
    if use_obs:
        obs_path     = input("  Full path to OBS (Enter to auto-detect): ").strip()
        obs_password = input("  OBS WebSocket password (OBS → Tools → WebSocket Settings): ").strip()

    # ── Step 5: Streamlabs ────────────────────────────────────────────────────
    print("\nSTEP 5 — Streamlabs events (optional)")
    print("  Clips auto-save on donations ($1+), raids (5+ viewers),")
    print("  subscriptions, bits (100+), and hosts.")
    print("  Token: streamlabs.com/dashboard → Settings → API Settings → Socket API\n")
    sl_token     = input("  Streamlabs Socket API token (Enter to skip): ").strip()

    # ── Step 6: Discord ───────────────────────────────────────────────────────
    print("\nSTEP 6 — Discord notifications (optional)")
    print("  Get a phone ping when a clip posts or an error repeats 3× in a session.")
    print("  Create webhook: Discord server → Edit Channel → Integrations → Webhooks\n")
    discord      = input("  Discord webhook URL (Enter to skip): ").strip()

    # ── Step 7: Auto-post ─────────────────────────────────────────────────────
    print("\nSTEP 7 — TikTok auto-posting")
    print("  Clips are queued and released at peak engagement hours (7-9am,")
    print("  12-2pm, 7-10pm ET). You'll need to add TIKTOK_ACCESS_TOKEN to .env")
    print("  after getting a TikTok developer token. Say 'n' for now if not ready.\n")
    auto_post    = (input("  Enable TikTok auto-posting? (y/n) [n]: ").strip().lower() or "n") == "y"

    # ── Write config.json ─────────────────────────────────────────────────────
    config = {
        "game":                  game,
        "highlight_sensitivity": sens_value,
        "use_obs_integration":   use_obs,
        "obs_path":              obs_path,
        "obs_host":              "localhost",
        "obs_port":              4455,
        "auto_rank":             True,
        "auto_format_tiktok":    True,
        "auto_post_tiktok":      auto_post,
        "tiktok_style":          "letterbox",
        "min_clip_duration":     15,
        "max_clip_duration":     60,
        "min_post_score":        50,
    }
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

    # ── Merge into .env (preserves existing keys) ─────────────────────────────
    existing_env: dict = {}
    if Path(ENV_FILE).exists():
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    existing_env[k.strip()] = v.strip()

    updates = {
        "GAME_NAME":             game,
        "TWITCH_CHANNEL":        twitch_channel,
        "TWITCH_HYPE_THRESHOLD": hype_threshold,
        "AUTO_POST_TIKTOK":      "true" if auto_post else "false",
    }
    if obs_password:
        updates["OBS_PASSWORD"] = obs_password
    if sl_token:
        updates["STREAMLABS_SOCKET_TOKEN"] = sl_token
    if discord:
        updates["DISCORD_WEBHOOK_URL"] = discord

    existing_env.update(updates)

    # Ensure placeholder keys exist
    for key in ("OBS_PASSWORD", "STREAMLABS_SOCKET_TOKEN", "ANTHROPIC_API_KEY",
                "TIKTOK_ACCESS_TOKEN", "TWITCH_CLIENT_ID", "TWITCH_OAUTH_TOKEN",
                "DISCORD_WEBHOOK_URL", "POSTING_TIMEZONE", "MIN_POST_GAP_HOURS"):
        existing_env.setdefault(key, "")

    if not existing_env.get("POSTING_TIMEZONE"):
        existing_env["POSTING_TIMEZONE"] = "America/New_York"
    if not existing_env.get("MIN_POST_GAP_HOURS"):
        existing_env["MIN_POST_GAP_HOURS"] = "2"

    with open(ENV_FILE, "w") as f:
        f.write("# Bolt — environment config\n")
        f.write("# Edit this file to update API keys and settings.\n")
        f.write("# Never share or commit this file to git.\n\n")
        for k, v in existing_env.items():
            f.write(f"{k}={v}\n")

    notify(
        "Setup complete ✓  (config.json and .env created)",
        level="success",
        reason="You can edit config.json or .env at any time. "
               "Bolt will reload settings on next launch."
    )


def _load_config() -> dict:
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except Exception as exc:
        notify(
            f"Could not read config.json: {exc}",
            level="error",
            reason="Delete config.json and run launch.py again to regenerate it."
        )
        return {}


def _check_env_file():
    """Load .env and warn about missing keys."""
    if not Path(ENV_FILE).exists():
        notify(
            ".env not found — creating blank one",
            level="warning",
            reason="The .env file stores API keys and passwords. "
                   "Run the setup wizard (delete config.json) to fill it in."
        )
        with open(ENV_FILE, "w") as f:
            f.write("# Bolt environment config\n")
            for k, _ in REQUIRED_KEYS + OPTIONAL_KEYS:
                f.write(f"{k}=\n")
        return

    # Load into environment
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def _print_checklist(config: dict):
    """Print a ✓ / ○ checklist of configured items."""
    missing = []

    for key, label in REQUIRED_KEYS:
        val = os.getenv(key, "")
        if val:
            notify(f"  ✓ {label}", level="success")
        else:
            notify(f"  ○ {label} not set", level="warning")
            missing.append(f"Add {key}=... to .env")

    for key, label in OPTIONAL_KEYS:
        val = os.getenv(key, "")
        status = "✓" if val else "○"
        level  = "info" if val else "info"
        notify(f"  {status} {label} {'(configured)' if val else '(optional)'}", level=level)

    if missing:
        notify(
            f"{len(missing)} item(s) still to set up:",
            level="info",
            reason="These are optional but unlock more features. "
                   "Edit .env to add them whenever you're ready."
        )
        for item in missing:
            notify(f"    • {item}", level="info")
    else:
        notify("All keys configured ✓", level="success")


# ── Twitch stats display ───────────────────────────────────────────────────────

def _show_twitch_stats():
    """
    Fetch and print live Twitch channel stats at startup.

    Why here? So you always know your current follower count, whether you're
    already live on another device, and what your last stream title was —
    before you even open OBS.

    Skips gracefully if TWITCH_CLIENT_ID or TWITCH_CLIENT_SECRET aren't set.
    """
    client_id     = os.getenv("TWITCH_CLIENT_ID", "").strip()
    client_secret = os.getenv("TWITCH_CLIENT_SECRET", "").strip()

    if not client_id or not client_secret:
        notify(
            "Twitch stats skipped — add TWITCH_CLIENT_ID + TWITCH_CLIENT_SECRET to .env",
            level="info",
            reason="Once added, Bolt will show your follower count, live status, and "
                   "top clips every time you launch."
        )
        return

    notify("Fetching Twitch stats…", level="info",
           reason="Pulling your channel data from the Twitch API so you can see "
                  "follower count, stream status, and top clips before going live.")
    try:
        from modules.Twitch_Stats import TwitchStats
        stats = TwitchStats()
        stats.print_summary()
    except Exception as e:
        notify(
            f"Twitch stats unavailable: {e}",
            level="warning",
            reason="This won't stop Bolt from running. Check your TWITCH_CLIENT_ID "
                   "and TWITCH_CLIENT_SECRET in .env if you want stats at startup."
        )


# ── Voice pre-stream checklist ─────────────────────────────────────────────────

def _run_voice_checklist(config: dict):
    """
    Show the pre-stream task checklist and let Billy check items off by voice.

    Why voice? So you can walk around setting things up and just say
    "OBS done" or "title set" without stopping to click anything.

    Skips if 'skip_checklist': true in config.json, or if --no-checklist
    is passed as a command-line argument.
    """
    if config.get("skip_checklist", False):
        notify("Pre-stream checklist skipped (skip_checklist=true in config.json)", level="info")
        return

    if "--no-checklist" in sys.argv:
        notify("Pre-stream checklist skipped (--no-checklist flag)", level="info")
        return

    notify(
        "Starting pre-stream checklist…",
        level="info",
        reason="Say any task out loud to check it off. For example: "
               "'OBS is good', 'title set', 'Streamlabs on'. "
               "Press Ctrl+C at any time to skip the rest and continue."
    )

    try:
        from modules.Voice_Checklist import VoiceChecklist

        # Use keyboard mode if voice is disabled in config
        use_voice = config.get("use_voice_checklist", True)
        timeout   = config.get("checklist_timeout_minutes", 15)

        checklist = VoiceChecklist(use_voice=use_voice)
        tasks     = checklist.run(timeout_minutes=timeout)

        done  = sum(1 for t in tasks if t["done"])
        total = len(tasks)
        notify(
            f"Checklist complete — {done}/{total} tasks done",
            level="success" if done == total else "info",
            reason="Checklist progress saved to logs/checklist_progress.json."
        )

    except KeyboardInterrupt:
        notify("Checklist skipped by user — continuing launch", level="info")
    except Exception as e:
        notify(
            f"Voice checklist unavailable: {e}",
            level="warning",
            reason="Install speech_recognition to enable voice: "
                   "pip3 install SpeechRecognition pyaudio --break-system-packages. "
                   "Bolt will continue without the checklist."
        )


if __name__ == "__main__":
    main()
