# Bolt Project Status

## Current State

Bolt is a working local-first creator assistant with a stable clip pipeline and a growing memory/learning layer.

The current mission is broader than Twitch clips. Bolt should support gaming, tech learning, AI development, product testing, Amazon Influencer storefront reviews, beauty/skincare testing, and the long-term goal of becoming Billy's virtual teammate.

## Active Runtime

What is active now:

- recording watcher and batch processing
- hard highlight confidence gate
- deduplication before expensive stages
- per-clip failure recovery
- clip ranking tiers
- title generation and subtitles
- vertical clip formatting
- OBS, Twitch, Streamlabs, and Discord integration
- macOS voice alerts
- Twitch chat personality layer
- local queue and memory chat commands
- runtime checkup dashboard generation
- local memory retrieval through `modules/Memory_Index.py`
- filed loose docs in canonical `docs/`, `memory/`, `teaching/rag/`, and `docs/upgrade/` locations

## Phase Meaning

- Phase 1: dashboard and personality shell
- Phase 2: live API connections
- Phase 3: voice and chat personality
- Phase 4: memory, retrieval, and decision-engine behavior

`Think_Learn_Decide` is the canonical decision path. `Brain_Controller` remains as a compatibility wrapper instead of a competing tier system.

## Quality Gating

The current clip flow uses:

- `quality_tiers.discard_below = 60`
- `quality_tiers.queue_at = 80`
- `min_post_score = 65`

That means:

- below 60: discard
- 60 to 64: keep on disk, no queue
- 65 to 79: format and queue, but no Discord alert
- 80 and up: queue and alert Billy at peak hours

## Memory And Creator Vision

Bolt's memory now includes:

- `memory/content/full-creator-vision.md`
- `memory/content/product-reviews.md`
- `memory/content/beauty-skincare.md`
- `memory/content/ai-development.md`
- `memory/content/brand-vision.md`
- `memory/content/daily-briefing.md`
- `docs/daily-briefing-template.md`
- `docs/reports/DEBUG_REPORT.md`
- `docs/architecture/SYSTEM_README.md`
- `docs/upgrade/UPGRADE_INDEX.md`
- `memory/context/bolt-personality.md`
- `brand/BRAND_VISION_DESCRIPTION.md`

Refresh the index after memory edits:

```bash
python3 scripts/refresh_memory_index.py
```

## Current Commands

```bash
python3 -m pip install -r requirements.txt
python3 launch.py
python3 launch.py process
python3 scripts/verify.py
python3 -m unittest
python3 -m modules.Bolt_Chat
python3 -m modules.Bolt_Voice "say this out loud"
python3 scripts/log_clip_performance.py --list
python3 llm/neural_model.py
```

## What Still Needs Finish Work

1. Keep `Think_Learn_Decide` canonical and avoid reintroducing duplicate decision systems.
2. Continue making retrieved memory change actual decisions, not only summaries.
3. Add upgrade layers sequentially: one feature, one verification loop, one memory refresh.
4. Decide how daily briefings should run locally before connecting calendar/email automation.
5. Keep product/skincare/Amazon/AI learning lanes represented in future features.
6. The old `BillyThunderstorm-site/` tree has been removed from the active repo layout.

## Troubleshooting Notes

- If clips are too sparse, lower `highlight_sensitivity`.
- If the queue is too noisy, raise `quality_tiers.discard_below`.
- If clips are missing, lower `min_post_score` first, then `discard_below`.
- If no chat responses appear, confirm Twitch env vars are set in `.env`.
- If voice does not speak, check `Bolt_VOICE_MUTE`, `use_voice_checklist`, and macOS `say`.
- If memory search feels stale, run `python3 scripts/refresh_memory_index.py`.

## Last Updated

May 2026
