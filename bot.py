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
       detect highlights → generate clips → deduplicate → generate titles
       → add subtitles → rank by virality → format for TikTok → notify
       Billy at peak posting hours

Fixes applied (2026-05):
  - Watcher now persists processed files to disk (no more duplicate clips on restart)
  - ClipDeduplicator is now wired in after clip generation (was built but never called)
  - chat_bot.trigger_highlight() moved to AFTER ranking/approval (was firing on raw
    audio spikes, flooding chat with fake highlights)
  - Caption .txt files are now written next to each vertical clip so titles are
    actually accessible — not just buried in data/ready_to_post.json
"""

import os
import sys
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(".env.local")

from modules.notifier import notify, notify_startup, notify_error
from modules.Config_Loader import load_config
from modules.Think_Learn_Decide import ThinkLearnDecideEngine
from scripts.site_data_writer import write_site_data

write_site_data(push=True)
# ── Constants ──────────────────────────────────────────────────────────────────
BRAIN_FILE = "Bolt_brain.md"
CONFIG_FILE = "config.json"


# ── 1. Load Billy's creator profile ───────────────────────────────────────────


def load_brain() -> str:
    """
    Reads Bolt_brain.md and returns it as a string.

    This is what makes Bolt personal. The content goes into the memory
    system so Bolt can personalize behavior based on Billy's profile.

    If the file is missing, Bolt still works — it just uses generic defaults.
    """
    brain_path = Path(BRAIN_FILE)
    if not brain_path.exists():
        lower_case_brain = Path("bolt_brain.md")
        if lower_case_brain.exists():
            brain_path = lower_case_brain

    if not brain_path.exists():
        notify(
            f"{BRAIN_FILE} not found — using generic AI prompts",
            level="warning",
            reason=f"Create {BRAIN_FILE} in the project root to personalise AI output. "
            "It should describe your content style, audience, and vibe.",
        )
        return ""

    brain = brain_path.read_text()
    notify(
        f"{brain_path.name} loaded ✓ — Bolt knows who you are",
        level="success",
        reason="Billy's creator profile is now active. All AI calls (titles, suggestions) "
        "will be tailored to his style, games, and audience.",
    )
    return brain


# ── 2. Load config ─────────────────────────────────────────────────────────────

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
      detect → clip → deduplicate → title → subtitle → rank → format → notify

    creator_brain is the Bolt_brain.md content. It's passed to
    Title_Generator for context but titles now use local templates.

    chat_bot is the BoltBot instance (or None). When provided, Bolt
    reacts in Twitch chat only after a clip has been ranked and approved —
    not on raw audio spikes.
    """
    filename = Path(recording_path).name

    intelligence = intelligence or ThinkLearnDecideEngine(config)
    notify(
        f"New recording detected: {filename}",
        level="info",
        reason="Starting the full processing pipeline. "
        "This takes a minute depending on clip length.",
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
    else:
        print("⚠️ Brain engine has no record_event(); skipping recording_detected log.")

    game = config.get("game", "Gaming")
    sensitivity = config.get("highlight_sensitivity", 0.7)
    style = config.get("tiktok_style", "letterbox")
    min_score = config.get("min_post_score", config.get("min_clip_score", 50))

    # ── Step A: Detect highlights ─────────────────────────────────────────────
    notify(
        "Step 1/6 — Detecting highlights…",
        level="info",
        reason="Scanning the video for audio spikes and motion bursts that "
        "signal exciting moments worth clipping.",
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
                f"{sensitivity} (lower = more sensitive).",
            )
            return

        notify(f"Found {len(highlights)} highlight(s) ✓", level="success")

        for h in highlights:
            score = getattr(h, "score", 0)

        # Voice alert is fine here — it's local and low-stakes
        try:
            from modules.Bolt_Voice import say_event

            say_event("highlight")
        except Exception:
            pass

        # NOTE: chat_bot.trigger_highlight() is intentionally NOT called here.
        # The audio detector fires on any loud sound — game effects, music, etc.
        # Chat is only notified in Step F, after a clip has been ranked, approved,
        # formatted, and confirmed as a real highlight worth posting.

    except Exception as e:
        notify_error("Highlight_Detector", e)
        return

    # ── Step B: Generate clips ────────────────────────────────────────────────
    notify(
        "Step 2/6 — Generating clips…",
        level="info",
        reason="Cutting clips around each highlight moment. "
        "Padding is added before and after to capture the full play.",
    )
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
            notify(
                "No clips generated",
                level="warning",
                reason="The pipeline ran but all clip attempts failed. "
                "Check that ffmpeg is installed: brew install ffmpeg",
            )
            return
    except Exception as e:
        notify_error("Clip_Generator", e)
        return

    # ── Step B2: Deduplicate ──────────────────────────────────────────────────
    # ClipDeduplicator checks against seen_clips.json (persisted across sessions).
    # If a clip's timestamp + file size matches something already processed, it's
    # dropped here before titles, subtitles, or ranking waste any cycles on it.
    # This was built but never wired in — that's now fixed.
    try:
        from modules.Clip_Deduplicator import ClipDeduplicator

        dedup = ClipDeduplicator()
        timestamps = [getattr(c.highlight, "timestamp", None) for c in successful_clips]
        before_count = len(successful_clips)
        unique_clips = []
        for clip, ts in zip(successful_clips, timestamps):
            if not dedup.is_duplicate(clip.output_file, ts):
                unique_clips.append(clip)
        successful_clips = unique_clips
        removed = before_count - len(successful_clips)
        if removed:
            notify(
                f"Deduplication: {removed} duplicate clip(s) removed, "
                f"{len(successful_clips)} unique clip(s) continuing",
                level="info",
                reason="Duplicates matched previously processed clips in seen_clips.json.",
            )
        if not successful_clips:
            notify(
                "All clips were duplicates — nothing new to process",
                level="info",
                reason="This recording was likely already processed in a previous session.",
            )
            return
    except Exception as e:
        notify(
            f"Deduplicator skipped: {e}",
            level="warning",
            reason="Continuing without deduplication. Clips may be duplicates.",
        )

    notify(
        f"{len(successful_clips)} unique clip(s) ready ✓",
        level="success",
        reason="Clips saved to clips/ folder.",
    )

    # ── Step C: Generate AI titles (Billy's profile injected here) ────────────
    use_ai_titles = bool(
        config.get("use_ai_titles")
        or config.get("title_generation", {}).get("enabled")
        or config.get("quality_tiers", {}).get("use_ai_titles")
    )
    notify(
        "Step 3/6 — Generating titles…",
        level="info",
        reason=(
            "AI titles are enabled; Bolt will use cached LLM captions with template fallback."
            if use_ai_titles
            else "Using local templates to generate TikTok titles. "
            "Enable use_ai_titles when you want cached LLM captions."
        ),
    )
    clip_titles = {}  # keyed by output_file path string
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
            notify(f"  Title: {titles[0]}", level="success")
    except Exception as e:
        notify_error("Title_Generator", e)
        for clip in successful_clips:
            clip_titles[clip.output_file] = {
                "titles": [f"Clip from {game}"],
                "hashtags": [],
            }

    # ── Step D: Generate subtitles ────────────────────────────────────────────
    notify(
        "Step 4/6 — Generating subtitles…",
        level="info",
        reason="Using Whisper to transcribe speech and burn subtitles into clips. "
        "Subtitles significantly boost watch time and accessibility.",
    )
    try:
        from modules.AI_Analyzer import analyze_tech_source

        for clip in successful_clips:
            segments, transcript = generate_subtitles(clip.output_file)
            if transcript and clip.output_file in clip_titles:
                clip_titles[clip.output_file]["transcript"] = transcript
    except Exception as e:
        notify_error("Subtitle_Generator", e, recoverable=True)

    # ── Step E: Rank clips by virality ────────────────────────────────────────
    max_clips = config.get("max_clips_per_session", 5)
    notify(
        "Step 5/6 — Ranking clips…",
        level="info",
        reason="Each clip gets a 0-100 virality score based on visual energy, "
        "audio peaks, scene changes, and length. "
        f"Only clips scoring {min_score}+ will be queued (max {max_clips} per session).",
    )
    ranked_clips = []
    try:
        from modules.Clip_Ranker import rank_clips

        ranked = rank_clips(successful_clips)
        above_floor = [c for c in ranked if getattr(c, "score", 0) >= min_score]
        ranked_clips = above_floor[:max_clips]
        skipped_score = len(ranked) - len(above_floor)
        skipped_cap = len(above_floor) - len(ranked_clips)
        msg = f"{len(ranked_clips)} clip(s) queued"
        if skipped_score:
            msg += f", {skipped_score} below score floor"
        if skipped_cap:
            msg += f", {skipped_cap} cut by session cap (max {max_clips})"
        notify(
            msg,
            level="success" if ranked_clips else "warning",
            reason=f"Score floor: {min_score}/100 · Session cap: {max_clips}. "
            "Adjust 'min_post_score'/'min_clip_score' and 'max_clips_per_session' in config.json.",
        )
    except Exception as e:
        notify_error("Clip_Ranker", e, recoverable=True)
        ranked_clips = successful_clips[:max_clips]

    # ── Step F: Format for TikTok + notify Billy at peak hours ───────────────
    if not config.get("auto_format_tiktok", True):
        notify(
            "TikTok formatting disabled — clips saved to clips/",
            level="info",
            reason="Set 'auto_format_tiktok': true in config.json to enable 9:16 conversion.",
        )
        return

    notify(
        "Step 6/6 — Formatting for TikTok and saving to post queue…",
        level="info",
        reason=f"Converting clips to vertical 9:16 format. Style: {style}. "
        "Bolt will alert you via Discord when it's peak posting time "
        "(7–9 AM, 12–2 PM, 7–10 PM). You post manually — no API needed.",
    )
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
        retrieved_count = think_output.get("retrieved_memory_count", 0)
        retrieved_memory = think_output.get("retrieved_memory", [])
        memory_influence = think_output.get("memory_influence", {})
        top_memory = retrieved_memory[0] if retrieved_memory else {}
        memory_reason = (
            f"Based on {think_output['memory_signals_used']} recent memory signals"
        )
        if retrieved_count:
            direction = (
                memory_influence.get("net_direction", "neutral")
                if isinstance(memory_influence, dict)
                else "neutral"
            )
            memory_reason += (
                f" and {retrieved_count} retrieved match(es); "
                f"top match: {top_memory.get('title', 'memory')} from {top_memory.get('source', 'unknown source')}; "
                f"influence: {direction}."
            )
        else:
            memory_reason += "."
        notify(
            f"Think step: {think_output['recommended_next_step']}",
            level="info",
            reason=memory_reason,
        )

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
                    "memory_context": retrieved_memory,
                    "memory_influence": memory_influence,
                }
            )

        if skipped_discard:
            notify(
                f"Skipped {skipped_discard} discard-tier clip(s) before decision gate",
                level="info",
                reason="Clips below quality_tiers.discard_below in config.json never "
                "reach the intelligence layer or the post queue.",
            )

        proposals = intelligence.propose_actions(candidates)
        approved_paths = set()

        for proposal in proposals:
            proposal_dict = proposal.as_dict()
            intelligence.audit("proposal", proposal_dict)
            allowed = intelligence.enforce_action_policy(proposal)
            if not allowed:
                intelligence.learn_from_feedback(
                    proposal.action, accepted=False, feedback_text="blocked_by_policy"
                )
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
                intelligence.audit(
                    "deferred", {"proposal": proposal_dict, "reason": "non_interactive"}
                )
                notify(
                    f"Deferred for batch review: "
                    f"{Path(proposal.payload.get('clip_path', '')).name or proposal.action}",
                    level="info",
                    reason="Run: python -m modules.Think_Learn_Decide --review-pending",
                )
                continue

            intelligence.learn_from_feedback(
                proposal.action,
                accepted=approved,
                feedback_text="approved_by_user" if approved else "rejected_by_user",
            )
            intelligence.audit(
                "confirmation", {"proposal": proposal_dict, "approved": approved}
            )
            clip_path = proposal.payload.get("clip_path", "")
            if approved and clip_path:
                approved_paths.add(clip_path)
            else:
                notify(
                    f"Skipped by decision gate: "
                    f"{Path(clip_path).name if clip_path else proposal.action}",
                    level="info",
                    reason="Assistive mode requires explicit approval for each action.",
                )

        if not approved_paths:
            notify(
                "No clips approved for queueing",
                level="warning",
                reason="Decision gate denied all actions (interactive approval required).",
            )

            if hasattr(intelligence, "record_event"):
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
            else:
                print(
                    "⚠️ Brain engine has no record_event(); skipping queue_decision log."
                )

            return

        for clip in ranked_clips:
            clip_path = clip.output_file
            if clip_path not in approved_paths:
                continue

            score = getattr(clip, "score", 50)
            tier = getattr(clip, "tier", "queue")

            try:
                vertical = format_for_tiktok(clip_path, style=style)
                if not vertical:
                    raise ValueError("format_for_tiktok returned empty path")
            except Exception as e:
                print(f"⚠️ TikTok formatting failed for {clip_path}: {e}")
                print("⚠️ Queueing original clip instead.")
                vertical = clip_path

            title_data = clip_titles.get(clip_path, {})
            titles = title_data.get("titles", [f"Clip from {game}"])
            best_title = titles[0]
            hashtags = title_data.get("hashtags", [])

            add_to_queue(
                clip_path=vertical,
                title=best_title,
                hashtags=hashtags,
                score=score,
                tier=tier,
            )

            # ── Write caption .txt file next to the vertical clip ─────────
            # Titles were generating correctly but only showing in terminal
            # and getting buried in data/ready_to_post.json. Now each vertical
            # clip gets a matching .txt file you can open and copy-paste
            # directly into TikTok — no JSON digging required.
            try:
                caption_path = Path(vertical).with_suffix(".txt")
                hashtag_str = " ".join(hashtags)
                alternates = "\n  ".join(titles[1:]) if len(titles) > 1 else "(none)"
                caption_text = (
                    f"TITLE (best option):\n"
                    f"  {best_title}\n\n"
                    f"CAPTION (copy this into TikTok):\n"
                    f"  {best_title} {hashtag_str}\n\n"
                    f"ALTERNATES:\n"
                    f"  {alternates}\n\n"
                    f"SCORE: {score:.0f}/100\n"
                    f"GAME:  {game}\n"
                )
                caption_path.write_text(caption_text, encoding="utf-8")
                notify(
                    f"Caption saved: {caption_path.name}",
                    level="success",
                    reason="Open this .txt file to copy-paste your title and hashtags into TikTok.",
                )
            except Exception as cap_err:
                notify(f"Caption file write failed: {cap_err}", level="warning")

            intelligence.learn_from_outcome(
                "queue_clip",
                success=True,
                details={
                    "clip_path": clip_path,
                    "vertical_path": vertical,
                    "score": score,
                },
            )
            intelligence.audit(
                "execution",
                {
                    "action": "queue_clip",
                    "clip_path": clip_path,
                    "score": score,
                    "status": "success",
                },
            )
            notify(
                f"Ready to post: {Path(clip_path).name}  [score {score:.0f}]",
                level="success",
                reason=f"Title: '{best_title}'\n"
                "     → Bolt will ping you when it's peak time.\n"
                f"     → Vertical clip saved to: vertical_clips/",
            )

            # ── Notify Twitch chat — ONLY after a clip is confirmed real ──
            # This replaces the old behavior of firing on every raw audio
            # spike. Chat now gets one message per clip that actually made
            # it through ranking, approval, and formatting. No more spam.
            if chat_bot:
                chat_bot.trigger_highlight()

    except Exception as e:
        notify_error("TikTok formatting / post queue", e)

    notify(
        f"Pipeline complete for {filename} ✓",
        level="success",
        reason="All done! Clips are queued. Bolt will alert you at peak hours.\n"
        "     → Check queue now: python -m modules.Peak_Hour_Notifier\n"
        "     → After posting:   python -m modules.Peak_Hour_Notifier --mark-posted",
    )


# ── Helper: guess trigger type from clip filename ──────────────────────────────


def _guess_trigger(clip_path: str, highlights: list) -> str:
    """
    Simple heuristic: map clip filename or highlight metadata to a trigger type.
    Falls back to 'highlight' if nothing specific is found.
    """
    name = Path(clip_path).stem.lower()
    trigger_keywords = {
        "kill": ["kill", "elim", "downed", "death"],
        "multi_kill": ["multi", "double", "triple", "quad", "penta"],
        "ace": ["ace", "wipe", "clutch"],
        "donation": ["donation", "donate", "dono"],
        "raid": ["raid"],
        "sub": ["sub", "subscriber"],
        "chat_hype": ["chat", "hype"],
        "reaction": ["react", "reaction"],
        "manual": ["manual", "marked"],
    }
    for trigger, keywords in trigger_keywords.items():
        if any(k in name for k in keywords):
            return trigger
    return "highlight"


# ── 4. Chat bot launcher ───────────────────────────────────────────────────────


def _start_chat_bot(creator_brain: str):
    """
    Start Bolt's Twitch chat bot in a background thread.

    Returns the bot instance so we can trigger events on it.
    Returns None if the bot can't start (missing token, missing library, etc.)
    """
    try:
        from modules.Bolt_Chat import start_chat_bot

        return start_chat_bot(brain=creator_brain)
    except Exception as exc:
        notify(
            f"Chat bot failed to start: {exc}",
            level="warning",
            reason="Bolt will still process clips — chat bot is optional. "
            "Check TWITCH_BOT_TOKEN and twitchio install.",
        )
        return None


# ── 5. Main loop ───────────────────────────────────────────────────────────────


def main():
    creator_brain = load_brain()
    config = load_config()
    intelligence = ThinkLearnDecideEngine(config)
    if hasattr(intelligence, "ingest_all_sources"):
        intelligence.ingest_all_sources()
    else:
        print(
            "⚠️ BrainController has no ingest_all_sources(); skipping source ingestion."
        )

    game = config.get("game", "Gaming")
    sensitivity = config.get("highlight_sensitivity", 0.7)

    notify_startup(
        game=game,
        sensitivity=sensitivity,
        auto_post=False,
        style=config.get("tiktok_style", "letterbox"),
        min_score=config.get("min_post_score", config.get("min_clip_score", 50)),
    )

    chat_bot = _start_chat_bot(creator_brain)

    mode = sys.argv[1] if len(sys.argv) > 1 else "live"

    if mode == "process":
        recordings_folder = os.getenv("RECORDINGS_FOLDER", "recordings")
        recordings = sorted(Path(recordings_folder).glob("*.mp4")) + sorted(
            Path(recordings_folder).glob("*.mkv")
        )
        if not recordings:
            notify(
                "No recordings found",
                level="warning",
                reason=f"Drop .mp4 or .mkv files into the '{recordings_folder}/' "
                "folder and run again.",
            )
            return
        latest = recordings[-1]
        notify(f"Processing mode — running pipeline on: {latest.name}", level="info")
        process_recording(str(latest), config, creator_brain, intelligence=intelligence)
        return

    notify(
        "Live mode — watching recordings/ folder for new clips",
        level="startup",
        reason="Bolt is now running. Any new .mp4 or .mkv that appears in "
        "recordings/ will be processed automatically.",
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
