# Bolt - Billy's AI Teammate

Bolt is Billy's local-first AI teammate for creator work, learning, and content operations.

It started as a Twitch and clip assistant, but the current vision is broader: Bolt helps Billy learn, test, teach, create, and improve across gaming, tech, AI development, product testing, Amazon Influencer storefront reviews, beauty/skincare, and building Bolt itself.

## Current Shape

- Clip pipeline: watches recordings, detects highlights, cuts clips, ranks them, formats vertical exports, queues posts, and alerts Billy when clips are worth posting.
- Decision layer: `Think_Learn_Decide` is the canonical intake/reasoning path, with `Brain_Controller` kept as a compatibility wrapper.
- Memory layer: `modules/Memory_Index.py` builds a local searchable index from Markdown memory, queue/history data, decision logs, and posted-performance outcomes.
- Content memory: `memory/content/` now tracks the full creator vision, product reviews, Amazon storefront context, beauty/skincare, AI learning, hooks, and posted-content lessons.
- No-cost defaults: AI-assisted features stay optional and should fall back to local/template behavior when credentials are missing.

## Project Layout

```text
Bolt/
├── launch.py                 # Startup checks, OBS launch, handoff to bot.py
├── bot.py                    # Main runtime pipeline and Twitch bot entrypoint
├── config.json               # Runtime configuration
├── requirements.txt          # Python dependencies
├── .env.example              # Safe environment template
├── bolt_brain.md             # Creator/Bolt brain file
├── modules/                  # Runtime modules and helpers
├── scripts/                  # Setup, utilities, maintenance, verification
├── tests/                    # Unit tests for current behavior
├── docs/                     # Guides, status pages, planning docs
├── memory/                   # Long-term memory and creator context
│   └── content/              # Creator lanes, reviews, hooks, results, AI learning
├── data/                     # Ignored runtime state and generated indexes
├── logs/                     # Runtime logs and decision audit trail
├── clips/                    # Generated highlight clips
├── vertical_clips/           # TikTok/Reels/Shorts-ready clips
├── recordings/               # Local-only source recordings
├── llm/                      # AI learning material and local neural-model experiments
├── brand/                    # Brand vision and identity docs
├── teaching/                 # Teaching/learning helper material
│   └── rag/                  # RAG study notes and helper experiments
├── docs/reports/             # Debug reports and cleanup notes
├── docs/architecture/        # System-level architecture/readme material
└── docs/upgrade/             # Upgrade strategy, status, and implementation notes
```

## Creator Lanes

Bolt should preserve the whole picture:

- gaming highlights and stream moments
- tech learning and reviews
- general product testing
- Amazon Influencer storefront reviews
- beauty and skincare testing
- AI development learning
- building Bolt in public as a virtual teammate

Gaming is one strong lane, not the whole mission.

## What Works Now

- Recording watcher and batch processing
- Hard highlight confidence gate
- Per-clip failure recovery
- Deduplication before titles, subtitles, and ranking
- Clip ranking tiers: `discard`, `mid`, and `queue`
- Title generation, subtitles, and vertical formatting
- Local/manual multi-platform posting packets
- Peak-hour Discord alerts for queue-worthy clips
- Twitch chat bot and local chat commands
- Memory recall through `modules.Memory_Index`
- Posted-performance logging for future learning
- Live checkup dashboard generation

## Quick Start

```bash
cd "/Users/carter/developer/Bolt"
python3 -m pip install -r requirements.txt
python3 launch.py
```

Process the latest recording:

```bash
python3 launch.py process
```

Useful checks:

```bash
python3 scripts/verify.py
python3 -m unittest
python3 -m modules.Bolt_Chat
python3 -m modules.Bolt_Voice "say this out loud"
```

## Memory And Learning

Refresh the local memory index after memory/content changes:

```bash
python3 scripts/refresh_memory_index.py
```

Search memory directly:

```bash
python3 -m modules.Memory_Index --refresh "Amazon Influencer storefront product testing"
python3 -m modules.Bolt_Memory --search "beauty skincare routine product test results"
```

Log posted content results so Bolt can learn from real performance:

```bash
python3 scripts/log_clip_performance.py --clip clips/example.mp4 --platform TikTok --note "Strong opening hook"
```

Run the cleaned neural-network learning example:

```bash
python3 llm/neural_model.py
```

## Configuration

Important config values:

- `highlight_sensitivity` for detection sensitivity
- `quality_tiers.discard_below` and `quality_tiers.queue_at`
- `min_post_score` as the pipeline cutoff for queueing and formatting
- `auto_format_tiktok` for vertical output
- `peak_notifications` for Discord timing alerts
- `use_voice_checklist` for startup voice prompts
- `use_obs_integration`, `obs_host`, and `obs_port` for OBS launch/connect
- `use_ai_titles` / `title_generation.enabled` for optional AI title generation

Suggested quality baseline:

- below `60`: discard
- `60-64`: keep on disk, no queue
- `65-79`: format and queue silently
- `80+`: queue and alert Billy at peak hours

## Documentation

| Doc | What it covers |
|---|---|
| `BOLT_COMMANDS.md` | Practical command sheet |
| `docs/INDEX.md` | Canonical navigation map |
| `docs/PROJECT_STATUS.md` | Current build status |
| `docs/guides/SETUP_GUIDE.md` | Setup and troubleshooting |
| `docs/guides/STREAM_DECK_SETUP.md` | Stream Deck layout |
| `docs/think_learn_decide.md` | Decision and memory schema |
| `docs/daily-briefing-template.md` | Daily briefing prompt/template |
| `docs/reports/DEBUG_REPORT.md` | Latest debug and verification report |
| `docs/architecture/SYSTEM_README.md` | System-level overview notes |
| `docs/upgrade/UPGRADE_INDEX.md` | Upgrade documentation map |
| `brand/BRAND_VISION_DESCRIPTION.md` | Brand and logo direction |
| `memory/content/full-creator-vision.md` | Creator north star |
| `memory/content/product-reviews.md` | Product/Amazon review memory |
| `memory/content/beauty-skincare.md` | Beauty/skincare memory |
| `memory/content/ai-development.md` | AI learning and Bolt teammate memory |

## Troubleshooting

| Problem | First thing to check |
|---|---|
| No highlights found | Lower `highlight_sensitivity` a little |
| OBS will not connect | Confirm obs-websocket is enabled and the password is right |
| Clips are too noisy | Raise `quality_tiers.discard_below` |
| Clips are missing | Lower `min_post_score` or `quality_tiers.discard_below` |
| Chat bot is silent | Confirm Twitch env vars exist in `.env` |
| Voice does not speak | Check `Bolt_VOICE_MUTE`, `use_voice_checklist`, and macOS `say` |
| Memory search feels stale | Run `python3 scripts/refresh_memory_index.py` |

## Upgrade Direction

Before adding new paid services, keep upgrades local-first:

1. Strengthen memory retrieval and decision wiring.
2. Keep optional AI features behind config flags and local fallbacks.
3. Add learning layers one at a time so Bolt stays understandable.
4. Let the full creator vision guide features, not only the clip pipeline.

*Last updated: May 2026*
