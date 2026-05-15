# Bolt Project Status

## Current State

Bolt is running as a working clip pipeline with a live personality layer.
The core loop is stable: watch recordings, detect highlights, cut clips,
rank them, format vertical exports, and notify Billy when a clip is worth
posting.

What is active now:
- recording watcher and batch processing
- hard highlight confidence gate
- per-clip failure recovery
- clip ranking tiers
- title generation and subtitles
- OBS, Twitch, Streamlabs, and Discord integration
- macOS voice alerts
- Twitch chat personality layer
- runtime checkup dashboard generation

## What Phase Means Here

- Phase 1: dashboard and personality shell
- Phase 2: live API connections
- Phase 3: voice and chat personality
- Phase 4: memory and decision engine scaffolding

Phase 3 is active in the current runtime. Phase 4 exists in code, but the
final decision engine is not yet the canonical path through `bot.py`.

## Quality Gating

The current clip flow uses:
- `quality_tiers.discard_below = 60`
- `quality_tiers.queue_at = 80`
- `min_post_score = 60`

That means:
- below 60: discard
- 60 to 79: keep on disk, no alert
- 80 and up: queue and alert Billy at peak hours

## Current Commands

```bash
pip3 install -r requirements.txt
python3 launch.py
python3 launch.py process
python3 -m modules.Bolt_Chat
python3 -m modules.Bolt_Voice "say this out loud"
python3 scripts/log_clip_performance.py --list
```

## What Still Needs Finish Work

1. Reconcile `Brain_Controller` and `Clip_Ranker` so the tier vocabulary is one thing.
2. Decide whether `Think_Learn_Decide` or `Brain_Controller` is canonical.
3. Populate the long-term memory/vector store so Bolt can retrieve past context.
4. Add motion gating only if audio spikes keep missing good moments.

## Troubleshooting Notes

- If clips are too sparse, lower `highlight_sensitivity`.
- If the queue is too noisy, raise `quality_tiers.discard_below`.
- If no chat responses appear, confirm `TWITCH_BOT_TOKEN`, `TWITCH_BOT_NAME`,
  and `ANTHROPIC_API_KEY` are set in `.env`.
- If voice does not speak, check `Bolt_VOICE_MUTE` and the macOS `say` command.

## Last Updated

May 2026
