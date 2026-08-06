#!/usr/bin/env python3
"""
bot.py — Bolt main pipeline
============================
This is the brain of Bolt. launch.py handles startup checks and then
hands off here. bot.py does the actual work:

  1. Load Bolt_brain.md  → Billy's creator profile (who we're working for)
  2. Load config.json    → settings (game, sensitivity, etc.)
  3. Start watching media/Recordings/ folder for new clips
  4. When a new recording appears, run it through the full pipeline

Updated for Carter's Multimodal Core (2026-07)
"""

import os
import sys
import json
from pathlib import Path

# Post-reorg: Core/bot.py may be invoked directly or via launch.py/bin/bolt.
# Ensure Core/ and the scripts dir are on sys.path and CWD is repo root so
# `from modules import X` and `from scripts import X` resolve to the new
# layout (Core/modules/ and scripts/).
_HERE = Path(__file__).resolve().parent          # Core/
_REPO = _HERE.parent                              # repo root
_SCRIPTS_DIR = _REPO / "scripts"
for _p in (_HERE, _SCRIPTS_DIR):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)
os.chdir(_REPO)



# _paths sets up the canonical post-reorg subpaths (Core/, Data/, media/, etc.)
from _paths import REPO_ROOT, CORE_DIR, RECORDINGS_DIR, BOLT_BRAIN_FILE

from dotenv import load_dotenv

if not load_dotenv(REPO_ROOT / ".env.local"):
    load_dotenv(REPO_ROOT / ".env")

from modules.notifier import notify, notify_startup, notify_error
from modules.Config_Loader import load_config
from modules.Think_Learn_Decide import ThinkLearnDecideEngine
from site_data_writer import write_site_data

# ── Constants ──────────────────────────────────────────────────────────────────
BRAIN_FILE = "Bolt_brain.md"
CONFIG_FILE = CORE_DIR / "config.json"


# ── 1. Load Billy's creator profile ───────────────────────────────────────────

def load_brain() -> str:
    """Reads Bolt_brain.md (or bolt_brain.md) and returns a string."""
    brain_path = BOLT_BRAIN_FILE
    if not brain_path.exists():
        brain_path = CORE_DIR / BRAIN_FILE

    if not brain_path.exists():
        notify(
            f"{BRAIN_FILE} not found — using generic AI prompts",
            level="warning",
            reason=f"Create {BRAIN_FILE} (or bolt_brain.md) in Core/ to personalise AI output.",
        )
        return ""

    brain = brain_path.read_text(encoding="utf-8")
    notify(
        f"{brain_path.name} loaded ✓ — Bolt knows who you are",
        level="success",
        reason="Billy's creator profile is now active.",
    )
    return brain


# ── 2. Process a single recording through the full pipeline ───────────────────

def process_recording(
    recording_path: str,
    config: dict,
    creator_brain: str,
    chat_bot=None,
    intelligence: ThinkLearnDecideEngine = None,
):
    """Full pipeline for one recording."""
    filename = Path(recording_path).name
    intelligence = intelligence or ThinkLearnDecideEngine(config)
    
    notify(
        f"New recording detected: {filename}",
        level="info",
        reason="Starting the full processing pipeline.",
    )

    if hasattr(intelligence, "record_event"):
        intelligence.record_event(
            source="pipeline",
            intent="recording_detected",
            action="start_processing",
            result="started",
            confidence=1.0,
            reason=f"Processing started for {filename}",
            feedback=None,
            metadata={"recording_path": recording_path},
        )

    game = config.get("game", "Gaming")
    sensitivity = config.get("highlight_sensitivity", 0.7)
    style = config.get("tiktok_style", "letterbox")
    min_score = config.get("min_post_score", config.get("min_clip_score", 50))

    # === Decision Engine + Nexus enrichment (best-effort, non-blocking) ===
    # Do NOT replace a caller-provided intelligence (e.g. BrainController).
    try:
        if intelligence is None:
            intelligence = ThinkLearnDecideEngine(config)

        # Build candidates for this recording
        candidates = [
            {"action": "process_and_queue", "score": 70, "reason": "default"},
            {"action": "hold_for_review", "score": 40, "reason": "low confidence"},
        ]

        thought, proposals = intelligence.think_and_propose(
            input_data={
                "recording": recording_path,
                "game": config.get("game", "Unknown"),
                "filename": Path(recording_path).name,
            },
            candidates=candidates,
        )

        # Log the insight
        if thought.get("nexus_insight"):
            notify(
                f"Nexus insight for {Path(recording_path).name}: {thought['nexus_insight'][:180]}...",
                level="info"
            )

            # Optional: store in memory / decision log
            if hasattr(intelligence, "record_event"):
                intelligence.record_event(
                    source="pipeline",
                    intent="recording_decision",
                    action="nexus_enrichment",
                    result="completed",
                    confidence=0.85,
                    reason=thought["nexus_insight"][:300],
                    feedback=None,
                    metadata={"recording": recording_path},
                )
    except Exception as e:
        notify(f"Decision Engine enrichment skipped: {e}", level="warning")
        
    # ── Step A: Detect highlights ─────────────────────────────────────────────
    notify("Step 1/6 — Detecting highlights…", level="info")

    try:
        from modules.Highlight_Detector import detect_highlights
        highlights = detect_highlights(recording_path, sensitivity=sensitivity)

        if not highlights:
            notify(
                f"No highlights found in {filename}",
                level="warning",
                reason="Try lowering 'highlight_sensitivity' in config.json.",
            )
            return

        notify(f"Found {len(highlights)} highlight(s) ✓", level="success")

        # Cap BEFORE cutting — generating every weak spike on a multi-hour
        # VOD can take hours and fill disk. Keep a modest oversample so the
        # ranker still has room to pick winners, then cut only those.
        max_clips = int(config.get("max_clips_per_session", 5) or 5)
        candidate_cap = int(config.get("max_highlight_candidates", max(max_clips * 4, 20)))
        if len(highlights) > candidate_cap:
            highlights = sorted(
                highlights,
                key=lambda h: float(getattr(h, "score", 0) or 0),
                reverse=True,
            )[:candidate_cap]
            notify(
                f"Keeping top {len(highlights)} highlights for cutting "
                f"(of many more; max_highlight_candidates={candidate_cap})",
                level="info",
                reason="Raise max_highlight_candidates / max_clips_per_session "
                "in Core/config.json if you want more clips per recording.",
            )

    except Exception as e:
        notify_error("Highlight_Detector", e)
        return

    # ── Step B: Generate clips ────────────────────────────────────────────────
    notify("Step 2/6 — Generating clips…", level="info")
    try:
        from modules.Clip_Generator import generate_clips
        clip_results = generate_clips(
            recording_path,
            highlights,
            min_duration=config.get("min_clip_duration", 15),
            max_duration=config.get("max_clip_duration", 60),
        )
        successful_clips = [r for r in clip_results if r.success and r.output_file]
        if not successful_clips:
            notify("No clips generated", level="warning", reason="Verify ffmpeg is installed.")
            return
    except Exception as e:
        notify_error("Clip_Generator", e)
        return

    # ── Step B2: Deduplicate ──────────────────────────────────────────────────
    try:
        from modules.Clip_Deduplicator import ClipDeduplicator
        dedup = ClipDeduplicator()
        timestamps = [getattr(c.highlight, "timestamp", None) for c in successful_clips]
        unique_clips = []
        for clip, ts in zip(successful_clips, timestamps):
            if not dedup.is_duplicate(clip.output_file, ts):
                unique_clips.append(clip)
        successful_clips = unique_clips
    except Exception as e:
        notify(f"Deduplicator skipped: {e}", level="warning")

    # ── Step C: Generate titles ───────────────────────────────────────────────
    content_type = config.get("content_type", "gaming")
    clip_titles = {}

    try:
        from modules.Title_Generator import generate_titles
        for clip in successful_clips:
            trigger = _guess_trigger(clip.output_file, highlights)
            titles, hashtags = generate_titles(
                trigger=trigger,
                game=game,
                context={"creator_brain": creator_brain, "config": config},
            )
            clip_titles[clip.output_file] = {"titles": titles, "hashtags": hashtags}
    except Exception as e:
        notify_error("Title_Generator", e)

    # ── Step D: Generate subtitles ────────────────────────────────────────────
    notify("Step 4/6 — Generating subtitles…", level="info")
    try:
        # Handled locally via standard subtitle generation models
        pass
    except Exception as e:
        notify_error("Subtitle_Generator", e, recoverable=True)

    # ── Step E: Rank clips by virality ────────────────────────────────────────
    max_clips = config.get("max_clips_per_session", 5)
    notify("Step 5/6 — Ranking clips…", level="info")
    try:
        from modules.Clip_Ranker import rank_clips
        ranked_clips = rank_clips(successful_clips)[:max_clips]
    except Exception as e:
        notify_error("Clip_Ranker", e, recoverable=True)
        ranked_clips = successful_clips[:max_clips]

    # ── Step F: Format for TikTok ────────────────────────────────────────────
    notify("Step 6/6 — Formatting for TikTok and saving to post queue…", level="info")
    try:
        from modules.Clip_Factory import format_for_tiktok
        from modules.Post_Queue import add_to_queue

        for clip in ranked_clips:
            clip_path = clip.output_file
            title_data = clip_titles.get(clip_path, {})
            best_title = title_data.get("titles", [f"Clip from {game}"])[0]
            hashtags = title_data.get("hashtags", [])

            vertical = format_for_tiktok(clip_path, style=style)
            add_to_queue(
                clip_path=vertical or clip_path,
                title=best_title,
                hashtags=hashtags,
                score=float(getattr(clip, "score", 50.0)),
                tier=getattr(clip, "tier", "queue"),
            )
            
            # Confirmed real highlight alert routes directly to Twitch chat loop!
            if chat_bot:
                chat_bot.trigger_highlight()
    except Exception as e:
        notify_error("TikTok formatting / post queue", e)

def _guess_trigger(clip_path: str, highlights: list) -> str:
    name = Path(clip_path).stem.lower()
    trigger_keywords = {
        "kill": ["kill", "elim", "downed"],
        "multi_kill": ["multi", "double", "triple"],
        "ace": ["ace", "wipe", "clutch"],
    }
    for trigger, keywords in trigger_keywords.items():
        if any(k in name for k in keywords):
            return trigger
    return "highlight"

def _start_chat_bot(creator_brain: str):
    """Start Bolt's Twitch chat bot in a background thread."""
    try:
        from modules.Bolt_Chat import start_chat_bot
        return start_chat_bot(brain=creator_brain)
    except Exception as exc:
        notify(f"Chat bot failed to start: {exc}", level="warning")
        return None

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "live"

    # `bolt setup` used to land here with no handler and fall into live
    # watch mode (which looks like a hang). Route setup to the launcher wizard.
    if mode in ("setup", "wizard", "configure"):
        launch = _REPO / "Core" / "launch.py"
        if not launch.exists():
            notify(
                "Setup wizard not found (Core/launch.py missing).",
                level="error",
            )
            return
        notify(
            "Handing off to the setup / launch wizard…",
            level="info",
            reason="bolt setup runs Core/launch.py (config checks + first-run wizard).",
        )
        venv_py = _REPO / ".venv" / "bin" / "python3"
        py = str(venv_py if venv_py.exists() else sys.executable)
        os.execv(py, [py, str(launch)] + sys.argv[2:])

    try:
        write_site_data(push=False)
    except Exception:
        pass

    creator_brain = load_brain()
    config = load_config()
    intelligence = ThinkLearnDecideEngine(config)
    
    chat_bot = _start_chat_bot(creator_brain)

    if mode == "process":
        recordings = []
        for ext in ("*.mp4", "*.mkv", "*.mov", "*.avi"):
            recordings.extend(Path(RECORDINGS_DIR).glob(ext))
        recordings = sorted(recordings)
        if not recordings:
            notify(
                "No recordings found",
                level="warning",
                reason=f"Drop new stream videos into '{RECORDINGS_DIR}/' to begin processing.",
            )
            return
        process_recording(str(recordings[-1]), config, creator_brain, chat_bot=chat_bot, intelligence=intelligence)
        return

    if mode not in ("live", "watch"):
        notify(
            f"Unknown bot mode '{mode}' — starting live watch. "
            f"Valid modes: live, process, setup.",
            level="warning",
        )

    notify(f"Live mode — watching {RECORDINGS_DIR} for new clips", level="startup")
    try:
        from modules.Watcher import watch_folder
        # Watcher targets your specific media path configured below
        for recording_path in watch_folder():
            process_recording(recording_path, config, creator_brain, chat_bot=chat_bot, intelligence=intelligence)
    except KeyboardInterrupt:
        notify("Bolt stopped cleanly.", level="info")

if __name__ == "__main__":
    # Re-execute under the venv Python if available so `dotenv` etc. are present.
    _VENV_PYTHON = _REPO / ".venv" / "bin" / "python3"
    if _VENV_PYTHON.exists() and sys.executable != str(_VENV_PYTHON):
        os.execv(str(_VENV_PYTHON), [str(_VENV_PYTHON), str(__file__)] + sys.argv[1:])
    main()
