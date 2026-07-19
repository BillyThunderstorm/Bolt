import logging
import subprocess
from pathlib import Path
import sys

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

from modules.Watcher import watch_folder
from modules.Highlight_Detector import detect_highlights
from modules.Clip_Generator import generate_clips
from modules.Subtitle_Generator import generate_subtitles
from modules.Title_Generator import generate_title
from modules.twitch_api import get_all_twitch_data  # migrated to new auth-aware module

# ── Bolt Voice ──────────────────────────────────────────────────────────────
# Uses macOS's built-in `say` command with Nathan (Enhanced) — Billy's pick.
# subprocess.run() calls the command silently in the background so it doesn't
# block the bot. If Nathan isn't installed, it falls back to the system default.
Bolt_VOICE = "Nathan (Enhanced)"


def Bolt_speak(message: str) -> None:
    """Speak a message out loud using Bolt's voice."""
    try:
        subprocess.run(
            ["say", "-v", Bolt_VOICE, message],
            check=False,  # don't crash the bot if say fails
            timeout=30,  # safety cap so it never hangs
        )
    except Exception as e:
        logging.warning(f"Bolt voice error: {e}")


# ────────────────────────────────────────────────────────────────────────────

APP_ROOT = Path(__file__).resolve().parent
LOG_DIR = APP_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "Bolt_app.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)


def main():
    logging.info("Bolt Bot starting...")
    Bolt_speak("Bolt is online. Let's go, Billy.")

    # ── NEW: Fetch and announce Twitch stats at startup ──
    # WHY: Billy wants to know stream stats at the start of each session
    # This happens once, then the bot processes clips normally
    try:
        logging.info("Fetching Twitch stats...")
        twitch_data = get_all_twitch_data()

        # Build a spoken announcement from the data
        # WHY: Convert numbers into natural language so Bolt can speak it
        followers = twitch_data.get("followers") or "unknown"
        last_viewers = twitch_data.get("last_stream_viewers") or 0
        current_game = twitch_data.get("current_game") or "unknown"

        # Bolt announces the stats
        # WHY: Billy wanted Bolt to SPEAK this data, not just log it
        stats_announcement = (
            f"You have {followers} followers. "
            f"Last stream had {last_viewers} viewers. "
            f"You're streaming {current_game}."
        )
        Bolt_speak(stats_announcement)

        # Log the data for debugging
        logging.info(f"Twitch Stats: {twitch_data}")

    except Exception as e:
        logging.error(f"Error fetching Twitch stats: {e}")
        Bolt_speak("Couldn't fetch Twitch stats. Continuing anyway.")
    # ────────────────────────────────────────────────────────────────────────

    try:
        for recording in watch_folder():
            logging.info(f"Scanning recording: {recording}")
            Bolt_speak("New recording detected. Processing highlights.")

            timestamps = detect_highlights(recording)
            clips = generate_clips(recording, timestamps)

            Bolt_speak(
                f"Found {len(clips)} clip{'s' if len(clips) != 1 else ''}. Generating titles and subtitles."
            )

            for clip in clips:
                subtitles = generate_subtitles(clip)
                title = generate_title()

                logging.info("Clip ready")
                logging.info(f"Title: {title}")
                logging.info(f"Subtitles (sample): {subtitles[:100]}")

            Bolt_speak("Clips are ready.")

    except Exception as e:
        logging.exception("Unhandled exception in Bolt Bot")
        Bolt_speak("Bolt hit an error. Check the logs.")
        raise


if __name__ == "__main__":
    main()
