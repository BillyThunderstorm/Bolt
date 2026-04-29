#!/usr/bin/env python3
"""
bot.py — Bolt main pipeline
============================
This is the brain of Bolt. launch.py handles startup checks and then
hands off here. bot.py does the actual work:

  1. Load Bolt_brain.md  → Billy's creator profile (who we're working for)
  2. Load config.json    → settings (game, sensitivity, etc.)
  3. Start watching recordings/ folder for new clips
  4. When a new recording appears, run it through the full pipeline:
       detect highlights → generate clips → generate titles (AI-powered,
       using Billy's profile) → add subtitles → rank by virality →
       format for TikTok → notify Billy at peak posting hours

Why Bolt_brain.md matters here:
  Without it, the AI title generator uses a generic "you are a TikTok creator"
  prompt. With it, Claude knows Billy's actual vibe, his games, his audience,
  and what kind of titles feel authentic to him vs corporate.

Note on TikTok posting:
  Bolt does NOT auto-post to TikTok. Instead, it queues ready clips and sends
  a Discord + terminal alert when it's peak posting time (7-9AM, 12-2PM,
  7-10PM). You post manually — which keeps you in control and actually gets
  better reach from TikTok's algorithm.
"""

import os
import sys
import json
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from modules.notifier import notify, notify_startup, notify_error
from modules.Think_Learn_Decide import ThinkLearnDecideEngine

from modules.Brain_Controller import BrainController

# ── Constants ──────────────────────────────────────────────────────────────────
BRAIN_FILE  = "Bolt_brain.md"
CONFIG_FILE = "config.json"


# ── 1. Load Billy's creator profile ───────────────────────────────────────────

def load_brain() -> str:
    """
    Reads Bolt_brain.md and returns it as a string.

    This is what makes Bolt personal. The content goes into the system prompt
    of every Claude API call so the AI 'knows' who Billy is before it starts
    generating titles, suggestions, or anything else.

    If the file is missing, Bolt still works — it just uses generic prompts.
    """
    brain_path = Path(BRAIN_FILE)
    if not brain_path.exists():
        notify(
            f"{BRAIN_FILE} not found — using generic AI prompts",
            level="warning",
            reason=f"Create {BRAIN_FILE} in the project root to personalise AI output. "
                   "It should describe your content style, audience, and vibe."
        )
        return ""

    brain = brain_path.read_text()
    notify(
        "Bolt_brain.md loaded ✓ — Bolt knows who you are",
        level="success",
        reason="Billy's creator profile is now active. All AI calls (titles, suggestions) "
               "will be tailored to his style, games, and audience."
    )
    return brain


# ── 2. Load config ─────────────────────────────────────────────────────────────

def load_config() -> dict:
    """
    Load config.json. If missing, return safe defaults.
    Run launch.py to generate config.json via the setup wizard.
    """
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        notify(
            "config.json not found — run launch.py to create it",
            level="warning",
            reason="Using safe defaults. Some features (OBS, TikTok posting) "
                   "won't work without a proper config."
        )
        return {
            "game": "Gaming",
            "highlight_sensitivity": 0.7,
            "auto_rank": True,
            "auto_format_tiktok": True,
            "auto_post_tiktok": False,
            "tiktok_style": "letterbox",
            "min_clip_duration": 15,
            "max_clip_duration": 60,
            "min_post_score": 50,
        }


# ── 3. Process a single recording through the full pipeline ───────────────────

def process_recording(
    recording_path: str,
    config: dict,
    creator_brain: str,
    chat_bot=None,
    intelligence: ThinkLearnDecideEngine = None,
):
    """
    Full pipeline for one recording:
      detect → clip → title → subtitle → rank → format → notify

    creator_brain is the Bolt_brain.md content. It gets passed to
    Title_Generator so Claude knows Billy's style when writing titles.

    chat_bot is the BoltBot instance (or None). When provided, Bolt
    reacts in Twitch chat as highlights are detected.
    """
    from pathlib import Path
    filename = Path(recording_path).name

    intelligence = intelligence or ThinkLearnDecideEngine(config)
    notify(
        f"New recording detected: {filename}",
        level="info",
        reason="Starting the full processing pipeline. "
               "This takes a minute depending on clip length."
    )
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

    game        = config.get("game", "Gaming")
    sensitivity = config.get("highlight_sensitivity", 0.7)
    style       = config.get("tiktok_style", "letterbox")
    min_score   = config.get("min_post_score", 50)

    brain = BrainController()

    # ── Step A: Detect highlights ─────────────────────────────────────────────
    notify(
        "Step 1/6 — Detecting highlights…",
        level="info",
        reason="Scanning the video for audio spikes and motion bursts that "
               "signal exciting moments worth clipping."
    )

    try:
        from modules.Highlight_Detector import detect_highlights
        highlights = detect_highlights(recording_path, sensitivity=sensitivity)

        if not highlights:
            notify(
                f"No highlights found in {filename}",
                level="warning",
                reason="Try lowering 'highlight_sensitivity' in config.json if you "
                       "think moments were missed. Current value: "
                       f"{sensitivity} (lower = more sensitive)."
            )
            return

        notify(f"Found {len(highlights)} highlight(s) ✓", level="success")

        for h in highlights:
            score = getattr(h, "score", 0)
            brain.handle("highlight", score=score)

        # Bolt reacts in chat + speaks when highlights are found
        try:
            from modules.Bolt_Voice import say_event
            say_event("highlight")
        except Exception:
            pass

        if chat_bot:
            for _ in highlights:
                chat_bot.trigger_highlight()

    except Exception as e:
        notify_error("Highlight_Detector", e)
        return

    # ── Step B: Generate clips ────────────────────────────────────────────────
    notify("Step 2/6 — Generating clips…", level="info",
           reason="Cutting 30-second clips around each highlight moment. "
                  "Padding is added before and after to capture the full play.")
    try:
        from modules.Clip_Generator import generate_clips
        # generate_clips returns List[GeneratedClip] objects, not raw path strings.
        # We keep the objects for the ranker (it needs .highlight, .score etc.)
        # and extract .output_file as a string whenever we need the path.
        clip_results = generate_clips(recording_path, highlights,
                                      min_duration=config.get("min_clip_duration", 15),
                                      max_duration=config.get("max_clip_duration", 60))
        successful_clips = [r for r in clip_results if r.success and r.output_file]
        if not successful_clips:
            notify("No clips generated", level="warning",
                   reason="The pipeline ran but all clip attempts failed. "
                          "Check that ffmpeg is installed: brew install ffmpeg")
            return
        notify(f"{len(successful_clips)} clip(s) generated ✓", level="success",
               reason="Clips saved to clips/ folder.")
    except Exception as e:
        notify_error("Clip_Generator", e)
        return

    # ── Step C: Generate AI titles (Billy's profile injected here) ────────────
    notify("Step 3/6 — Generating titles…", level="info",
           reason="Asking Claude to write TikTok titles. "
                  "It has Billy's creator profile loaded so titles match his vibe.")
    clip_titles = {}  # keyed by output_file path string
    try:
        from modules.Title_Generator import generate_titles
        for clip in successful_clips:
            trigger = _guess_trigger(clip.output_file, highlights)
            titles, hashtags = generate_titles(
                trigger=trigger,
                game=game,
                context={"creator_brain": creator_brain}
            )
            clip_titles[clip.output_file] = {"titles": titles, "hashtags": hashtags}
            notify(f"  Title: {titles[0]}", level="success")
    except Exception as e:
        notify_error("Title_Generator", e)
        for clip in successful_clips:
            clip_titles[clip.output_file] = {
                "titles": [f"Clip from {game}"], "hashtags": []
            }

    # ── Step D: Generate subtitles ────────────────────────────────────────────
    notify("Step 4/6 — Generating subtitles…", level="info",
           reason="Using Whisper to transcribe speech and burn subtitles into clips. "
                  "Subtitles significantly boost watch time and accessibility.")
    try:
        from modules.Subtitle_Generator import generate_subtitles_with_timestamps as generate_subtitles
        for clip in successful_clips:
            segments, transcript = generate_subtitles(clip.output_file)
            # Store transcript on the clip's title entry for reference
            # (Subtitle_Generator transcribes audio — it doesn't burn a new video file)
            if transcript and clip.output_file in clip_titles:
                clip_titles[clip.output_file]["transcript"] = transcript
    except Exception as e:
        notify_error("Subtitle_Generator", e, recoverable=True)
        # continue without subtitles — clips already in successful_clips as-is

    # ── Step E: Rank clips by virality ────────────────────────────────────────
    #
    # Why we rank AND cap:
    #   Ranking sorts by quality (0-100 score). The cap ensures we don't flood
    #   your queue — one great clip beats five okay ones for TikTok's algorithm.
    #   Both limits are configurable in config.json:
    #     "min_post_score"       — quality floor (default 50)
    #     "max_clips_per_session"— how many to queue per recording (default 5)
    #
    max_clips   = config.get("max_clips_per_session", 5)
    notify("Step 5/6 — Ranking clips…", level="info",
           reason="Each clip gets a 0-100 virality score based on visual energy, "
                  "audio peaks, scene changes, and length. "
                  f"Only clips scoring {min_score}+ will be queued (max {max_clips} per session).")
    ranked_clips = []
    try:
        from modules.Clip_Ranker import rank_clips
        ranked      = rank_clips(successful_clips)   # returns sorted List[GeneratedClip], best first
        above_floor = [c for c in ranked if getattr(c, "score", 0) >= min_score]
        ranked_clips = above_floor[:max_clips]        # take only the top N
        skipped_score = len(ranked) - len(above_floor)
        skipped_cap   = len(above_floor) - len(ranked_clips)
        msg = f"{len(ranked_clips)} clip(s) queued"
        if skipped_score:
            msg += f", {skipped_score} below score floor"
        if skipped_cap:
            msg += f", {skipped_cap} cut by session cap (max {max_clips})"
        notify(
            msg,
            level="success" if ranked_clips else "warning",
            reason=f"Score floor: {min_score}/100 · Session cap: {max_clips}. "
                   "Adjust 'min_post_score' and 'max_clips_per_session' in config.json."
        )
    except Exception as e:
        notify_error("Clip_Ranker", e, recoverable=True)
        ranked_clips = successful_clips[:max_clips]  # still respect cap if ranker fails

    # ── Step F: Format for TikTok + notify Billy at peak hours ───────────────
    #
    # No auto-posting. Instead:
    #   1. Convert clips to vertical 9:16 TikTok format
    #   2. Save them to the ready-to-post queue (data/ready_to_post.json)
    #   3. Bolt sends a Discord + terminal alert when it's peak time
    #   4. Billy posts manually — full control, better algorithm reach
    #
    if not config.get("auto_format_tiktok", True):
        notify("TikTok formatting disabled — clips saved to clips/", level="info",
               reason="Set 'auto_format_tiktok': true in config.json to enable 9:16 conversion.")
        return

    notify("Step 6/6 — Formatting for TikTok and saving to post queue…", level="info",
           reason=f"Converting clips to vertical 9:16 format. Style: {style}. "
                  "Bolt will alert you via Discord when it's peak posting time "
                  "(7–9 AM, 12–2 PM, 7–10 PM). You post manually — no API needed.")
    try:
        from modules.Clip_Factory import format_for_tiktok
        from modules.Post_Queue import add_to_queue

        think_output = intelligence.think(
            {
                "recording": filename,
                "game": game,
                "ranked_clip_count": len(ranked_clips),
                "min_score": min_score,
            }
        )
        intelligence.audit("think", think_output)
        notify(
            f"Think step: {think_output['recommended_next_step']}",
            level="info",
            reason=f"Based on {think_output['memory_signals_used']} memory signals.",
        )

        # ── Tier filter: drop "discard" clips before the decision gate ────
        # discard-tier clips never enter intelligence's consideration. mid
        # and queue tier both proceed but with different downstream behavior
        # (mid stays silent, queue triggers peak-hour pings).
        candidates = []
        skipped_discard = 0
        for clip in ranked_clips:
            tier = getattr(clip, "tier", "queue")
            if tier == "discard":
                skipped_discard += 1
                continue
            clip_path = clip.output_file
            title_data = clip_titles.get(clip_path, {})
            candidates.append(
                {
                    "action": "queue_clip",
                    "clip_path": clip_path,
                    "score": float(getattr(clip, "score", 0.0)),
                    "tier": tier,
                    "title": title_data.get("titles", [""])[0] if title_data else "",
                    "hashtags": title_data.get("hashtags", []) if title_data else [],
                    "style": style,
                }
            )

        if skipped_discard:
            notify(
                f"Skipped {skipped_discard} discard-tier clip(s) before decision gate",
                level="info",
                reason="Clips below quality_tiers.discard_below in config.json never "
                       "reach the intelligence layer or the post queue. Lower the "
                       "threshold to be more lenient."
            )

        proposals = intelligence.propose_actions(candidates)
        approved_paths = set()
        for proposal in proposals:
            proposal_dict = proposal.as_dict()
            intelligence.audit("proposal", proposal_dict)
            allowed = intelligence.enforce_action_policy(proposal)
            if not allowed:
                intelligence.learn_from_feedback(proposal.action, accepted=False, feedback_text="blocked_by_policy")
                intelligence.audit("blocked", proposal_dict)
                notify(
                    f"Blocked by policy: {proposal.action}",
                    level="warning",
                    reason="Action is not in allowlist or is in denylist.",
                )
                continue

            approved = intelligence.confirm_action(proposal)
            if not approved and not os.isatty(0):
                intelligence.enqueue_pending_proposal(proposal)
                intelligence.audit("deferred", {"proposal": proposal_dict, "reason": "non_interactive"})
                notify(
                    f"Deferred for batch review: {Path(proposal.payload.get('clip_path', '')).name or proposal.action}",
                    level="info",
                    reason="Run: python -m modules.Think_Learn_Decide --review-pending",
                )
                continue
            intelligence.learn_from_feedback(
                proposal.action,
                accepted=approved,
                feedback_text="approved_by_user" if approved else "rejected_by_user_or_non_interactive",
            )
            intelligence.audit("confirmation", {"proposal": proposal_dict, "approved": approved})
            clip_path = proposal.payload.get("clip_path", "")
            if approved and clip_path:
                approved_paths.add(clip_path)
            else:
                notify(
                    f"Skipped by decision gate: {Path(clip_path).name if clip_path else proposal.action}",
                    level="info",
                    reason="Assistive mode requires explicit approval for each action.",
                )

        if not approved_paths:
            notify(
                "No clips approved for queueing",
                level="warning",
                reason="Decision gate denied all actions (interactive approval required).",
            )
            intelligence.record_event(
                source="decision_engine",
                intent="queue_decision",
                action="queue_clip",
                result="none_approved",
                confidence=0.9,
                reason="No clip actions passed assistive confirmation",
                feedback=None,
                metadata={"proposals": [p.as_dict() for p in proposals]},
            )
            return

        for clip in ranked_clips:
            clip_path  = clip.output_file
            if clip_path not in approved_paths:
                continue
            score      = getattr(clip, "score", 50)
            tier       = getattr(clip, "tier", "queue")
            vertical   = format_for_tiktok(clip_path, style=style)
            title_data = clip_titles.get(clip_path, {})
            best_title = title_data.get("titles", [""])[0]
            hashtags   = title_data.get("hashtags", [])

            add_to_queue(
                clip_path=vertical,
                title=best_title,
                hashtags=hashtags,
                score=score,
                tier=tier,
            )
            intelligence.learn_from_outcome(
                "queue_clip",
                success=True,
                details={"clip_path": clip_path, "vertical_path": vertical, "score": score},
            )
            intelligence.audit(
                "execution",
                {"action": "queue_clip", "clip_path": clip_path, "score": score, "status": "success"},
            )
            notify(
                f"Ready to post: {Path(clip_path).name}  [score {score:.0f}]",
                level="success",
                reason=f"Title: '{best_title}'\n"
                       "     → Bolt will ping you when it's peak time.\n"
                       f"     → Vertical clip saved to: vertical_clips/"
            )
    except Exception as e:
        notify_error("TikTok formatting / post queue", e)

    notify(
        f"Pipeline complete for {filename} ✓",
        level="success",
        reason="All done! Clips are queued. Bolt will alert you at peak hours.\n"
               "     → Check queue now: python -m modules.Peak_Hour_Notifier\n"
               "     → After posting:   python -m modules.Peak_Hour_Notifier --mark-posted"
    )


# ── Helper: guess trigger type from clip filename ──────────────────────────────

def _guess_trigger(clip_path: str, highlights: list) -> str:
    """
    Simple heuristic: map clip filename or highlight metadata to a trigger type.
    Falls back to 'highlight' if nothing specific is found.
    """
    name = Path(clip_path).stem.lower()
    trigger_keywords = {
        "kill":      ["kill", "elim", "downed", "death"],
        "multi_kill":["multi", "double", "triple", "quad", "penta"],
        "ace":       ["ace", "wipe", "clutch"],
        "donation":  ["donation", "donate", "dono"],
        "raid":      ["raid"],
        "sub":       ["sub", "subscriber"],
        "chat_hype": ["chat", "hype"],
        "reaction":  ["react", "reaction"],
        "manual":    ["manual", "marked"],
    }
    for trigger, keywords in trigger_keywords.items():
        if any(k in name for k in keywords):
            return trigger
    return "highlight"


# ── 4. Phase 3: Chat bot + voice launcher ─────────────────────────────────────

def _start_chat_bot(creator_brain: str):
    """
    Start Bolt's Twitch chat bot in a background thread.

    Returns the bot instance so we can trigger events on it (highlights, etc.)
    Returns None if the bot can't start (missing token, missing library, etc.)

    Why we do this in bot.py (not just launch.py):
      launch.py calls os.execv() to hand off to bot.py, which REPLACES the
      process — any threads launch.py started are gone. So bot.py starts
      the chat bot fresh. launch.py just checks config and warns if anything
      is missing before the handoff.
    """
    try:
        from modules.Bolt_Chat import start_chat_bot
        return start_chat_bot(brain=creator_brain)
    except Exception as exc:
        notify(f"Chat bot failed to start: {exc}", level="warning",
               reason="Bolt will still process clips — chat bot is optional. "
                      "Check TWITCH_BOT_TOKEN and twitchio install.")
        return None


# ── 5. Main loop ───────────────────────────────────────────────────────────────

def main():
    # Load Billy's profile FIRST — everything else uses it
    creator_brain = load_brain()
    config        = load_config()
    intelligence  = ThinkLearnDecideEngine(config)
    intelligence.ingest_all_sources()

    game        = config.get("game", "Gaming")
    sensitivity = config.get("highlight_sensitivity", 0.7)

    notify_startup(
        game=game,
        sensitivity=sensitivity,
        auto_post=False,   # auto-posting removed — Bolt notifies, Billy posts
        style=config.get("tiktok_style", "letterbox"),
        min_score=config.get("min_post_score", 50),
    )

    # ── Phase 3: Start Bolt's chat bot ────────────────────────────────────────
    # Connects to Twitch chat so Bolt can react live during the stream.
    # Runs in a background thread — doesn't block the clip pipeline.
    chat_bot = _start_chat_bot(creator_brain)

    # Check if we're in single-file mode (process one recording and exit)
    mode = sys.argv[1] if len(sys.argv) > 1 else "live"

    if mode == "process":
        # Process the most recent recording in the recordings folder
        recordings_folder = os.getenv("RECORDINGS_FOLDER", "recordings")
        recordings = sorted(Path(recordings_folder).glob("*.mp4")) + \
                     sorted(Path(recordings_folder).glob("*.mkv"))
        if not recordings:
            notify("No recordings found", level="warning",
                   reason=f"Drop .mp4 or .mkv files into the '{recordings_folder}/' "
                          "folder and run again.")
            return
        latest = recordings[-1]
        notify(f"Processing mode — running pipeline on: {latest.name}", level="info")
        process_recording(str(latest), config, creator_brain, intelligence=intelligence)
        return

    # Live mode — watch folder for new recordings
    notify(
        "Live mode — watching recordings/ folder for new clips",
        level="startup",
        reason="Bolt is now running. Any new .mp4 or .mkv that appears in "
               "recordings/ will be processed automatically. "
               "In live streaming mode, OBS replay buffer saves go straight here."
    )

    try:
        from modules.Watcher import watch_folder
        for recording_path in watch_folder():
            process_recording(
                recording_path,
                config,
                creator_brain,
                chat_bot=chat_bot,
                intelligence=intelligence,
            )
    except KeyboardInterrupt:
        notify("Bolt stopped by user (Ctrl+C)", level="info")
        try:
            from modules.Bolt_Voice import say_event
            say_event("shutdown")
        except Exception:
            pass
    except Exception as e:
        notify_error("main loop", e, recoverable=False)
        sys.exit(1)


if __name__ == "__main__":
    main()
