# Bolt - Billy's AI Teammate

Bolt is Billy's local-first AI teammate for creator work, learning, and content operations.

**AI Provider:** OpenAI (chat/responses) + ElevenLabs (voice TTS)

It started as a Twitch and clip assistant, but the current vision is broader: Bolt helps Billy learn, test, teach, create, and improve across gaming, tech, AI development, product testing, Amazon Influencer storefront reviews, beauty/skincare, and building Bolt itself.

## Current Shape

- **Clip Pipeline**: Watches recordings, detects highlights, cuts clips, ranks them, formats vertical exports, queues posts, and alerts Billy when clips are worth posting
- **Decision Layer**: `Think_Learn_Decide` is the canonical intake/reasoning path, with `Brain_Controller` kept as a compatibility wrapper
- **Memory Layer**: `modules/Memory_Index.py` builds a local searchable index from Markdown memory, queue/history data, decision logs, and posted-performance outcomes
- **Content Memory**: `memory/content/` tracks the full creator vision, product reviews, Amazon storefront context, beauty/skincare, AI learning, hooks, and posted-content lessons
- **Storage Management**: Automated compression, rotation, and duplicate detection with email/SMS alerts
- **No-Cost Defaults**: AI-assisted features stay optional and fall back to local/template behavior when credentials are missing

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
├── configs/                  # Configuration files (alerts, rotation policies)
├── docs/reports/             # Debug reports and cleanup notes
├── docs/architecture/        # System-level architecture/readme material
└── docs/upgrade/             # Upgrade strategy, status, and implementation notes
```

## Creator Lanes

Bolt should preserve the whole picture:

- Gaming highlights and stream moments
- Tech learning and reviews
- General product testing
- Amazon Influencer storefront reviews
- Beauty and skincare testing
- AI development learning
- Building Bolt in public as a virtual teammate

Gaming is one strong lane, not the whole mission.

## What Works Now

### Clip Pipeline
- Recording watcher and batch processing
- Hard highlight confidence gate
- Per-clip failure recovery
- Deduplication before titles, subtitles, and ranking
- Clip ranking tiers: `discard`, `mid`, and `queue`
- Title generation, subtitles, and vertical formatting
- Local/manual multi-platform posting packets
- Peak-hour Discord alerts for queue-worthy clips

### Communication
- Twitch chat bot and local chat commands
- Voice alerts via macOS TTS and ElevenLabs
- Email and SMS storage alerts

### Memory & Learning
- Memory recall through `modules.Memory_Index`
- Posted-performance logging for future learning
- RAG study materials in `teaching/rag/`

### Storage Management
- Automated video compression (HandBrake H.264/H.265)
- Media rotation and archival (size-based)
- Hash-based duplicate detection
- Storage monitoring with threshold alerts
- Performance baseline tracking

### Monitoring
- Live checkup dashboard generation
- Storage monitoring (every 3 hours)
- Media rotation (every 6 hours)
- Video compression (every 30 minutes)

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

## User Interfaces

Bolt provides multiple ways to interact:

| Interface | Command | Description |
|-----------|---------|-------------|
| **CLI Launcher** | `python3 launch.py` | Main entry point for Bolt |
| **Bot Runtime** | `python3 bot.py` | Direct bot execution |
| **Conversation Module** | `python3 -m modules.Bolt_Conversation` | Voice chat loop with memory (NEW) |
| **Chat Module** | `python3 -m modules.Bolt_Chat` | Local chat testing |
| **Chat with Voice** | `python3 -m modules.Bolt_Chat --voice` | Twitch chat with voice replies (NEW) |
| **Voice Module** | `python3 -m modules.Bolt_Voice "text"` | TTS voice output |
| **Memory Search** | `python3 -m modules.Memory_Index` | Searchable memory index |
| **Memory Browser** | `python3 -m modules.Bolt_Memory` | Full memory operations |
| **Checkup Dashboard** | `docs/Bolt_Checkup.html` | Live status dashboard |
| **Duplicate Scanner** | `python3 scripts/clip_deduplicator.py` | Hash-based dedup |
| **Performance Baseline** | `python3 scripts/performance_baseline.py` | Benchmark metrics |
| **Storage Monitor** | `scripts/monitoring/storage_monitor.sh` | Disk usage + alerts |

### Chat Commands (when running)
```text
!queue                    - Show current clip queue status
!recall <topic>           - Search memory for topic
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

### Storage Alerts Configuration
Edit `configs/storage_alerts.env` to configure:
- Email alerts
- SMS alerts (via email-to-SMS)
- Webhook notifications (Discord, generic)

### Daily Briefing
A morning briefing runs at 7 AM automatically, or generate on-demand:

```bash
python3 scripts/daily_briefing.py
```

Includes queue status, storage usage, recent clips, and action items.

Suggested quality baseline:

- Below `60`: discard
- `60-64`: keep on disk, no queue
- `65-79`: format and queue silently
- `80+`: queue and alert Billy at peak hours

## Documentation

| Doc | What it covers |
|-----|----------------|
| `BOLT_COMMANDS.md` | Practical command sheet with all interfaces |
| `docs/INDEX.md` | Canonical navigation map |
| `docs/PROJECT_STATUS.md` | Current build status and next steps |
| `docs/guides/SETUP_GUIDE.md` | Setup and troubleshooting |
| `docs/guides/STREAM_DECK_SETUP.md` | Stream Deck layout |
| `docs/think_learn_decide.md` | Decision and memory schema |
| `docs/daily-briefing-template.md` | Daily briefing prompt/template |
| `docs/reports/DEBUG_REPORT.md` | Latest debug and verification report |
| `docs/architecture/SYSTEM_README.md` | System-level overview notes |
| `docs/upgrade/UPGRADE_INDEX.md` | Upgrade documentation map |
| `brand/BRAND_VISION_DESCRIPTION.md` | Brand and logo direction |
| `memory/content/full-creator-vision.md` | Creator north star |
| `memory/content/content-creation.md` | Content creation domain (NEW) |
| `memory/content/assistant-productivity.md` | Assistant productivity domain (NEW) |
| `memory/content/game-testing.md` | Game and tech testing domain (NEW) |
| `memory/content/live-streaming.md` | Live streaming domain (NEW) |
| `memory/content/social-media-management.md` | Social media management domain (NEW) |
| `memory/content/product-reviews.md` | Product/Amazon review memory |
| `memory/content/beauty-skincare.md` | Beauty/skincare memory |
| `memory/content/ai-development.md` | AI learning and Bolt teammate memory |
| `NEXT_UPGRADE_STEPS.md` | Immediate next steps and timeline |
| `OPTIMIZATION_ROADMAP.md` | Long-term optimization plan |

## Troubleshooting

| Problem | First thing to check |
|---------|---------------------|
| No highlights found | Lower `highlight_sensitivity` a little |
| OBS will not connect | Confirm obs-websocket is enabled and the password is right |
| Clips are too noisy | Raise `quality_tiers.discard_below` |
| Clips are missing | Lower `min_post_score` or `quality_tiers.discard_below` |
| Chat bot is silent | Confirm Twitch env vars exist in `.env` |
| Voice does not speak | Check `Bolt_VOICE_MUTE`, `use_voice_checklist`, and macOS `say` |
| Memory search feels stale | Run `python3 scripts/refresh_memory_index.py` |
| Storage alerts not sending | Verify `configs/storage_alerts.env` is configured |

## Storage Management

### Automated Maintenance (Cron Jobs)
```bash
# View active cron jobs
crontab -l
```

| Schedule | Task | Description |
|----------|------|-------------|
| `*/30 * * * *` | Video Compression | Compress new clips with HandBrake |
| `0 */3 * * *` | Storage Monitor | Check disk usage, send alerts |
| `0 */6 * * *` | Media Rotation | Archive old recordings/clips |
| `0 3 * * *` | Storage Optimization | Nightly cleanup (3-day retention) |
| `0 7 * * *` | **Daily Briefing** | Morning briefing → SMS/email |
| `0 */2 * * *` | **Auto-Process** | Process recordings automatically |
| `0 9 * * 0` | **Weekly Analysis** | Sunday insights → email (NEW) |

### Manual Storage Commands
```bash
# Detect duplicates
python3 scripts/clip_deduplicator.py

# Run performance baseline
python3 scripts/performance_baseline.py

# Manual storage optimization
python3 scripts/maintenance/storage_optimization.sh
```

### Current Alert Recipients
- **Email**: billycarteriv@gmail.com
- **SMS**: 707-567-8495 (AT&T)

### Alert Thresholds
- **Warning**: 80% disk usage
- **Critical**: 95% disk usage

## Upgrade Direction

Before adding new paid services, keep upgrades local-first:

1. Strengthen memory retrieval and decision wiring
2. Keep optional AI features behind config flags and local fallbacks
3. Add learning layers one at a time so Bolt stays understandable
4. Let the full creator vision guide features, not only the clip pipeline

## Recent Updates (June 2026)

### June 6, 2026 - Upgrades Completed
- Fixed HandBrakeCLI path for cron execution
- Audited and organized `requirements.txt`
- Created hash-based duplicate detection (`scripts/clip_deduplicator.py`)
- Enhanced storage monitor with email/SMS alerts
- Created performance baseline script
- Updated all documentation with comprehensive interface list

### Earlier June 2026
- Dependency pinning for stability
- RAG study materials added to `teaching/rag/`
- Storage alerting infrastructure prepared


## Websites

Bolt runs three live websites on Cloudflare:

| Site | URL | Description |
|------|-----|-------------|
| **Bolt Command Center** | [bolt.billythunderstorm.us](https://bolt.billythunderstorm.us) | Terminal, clip queue, daily briefing, peak hours |
| **Billy Thunderstorm** | [billythunderstorm.us](https://billythunderstorm.us) | Creator portfolio, milestones, storefront |
| **Live Status** | [billythunderstorm.live](https://billythunderstorm.live) | Stream status, peak hours, socials |
| **API Worker** | [api.billythunderstorm.us](https://api.billythunderstorm.us) | JSON endpoints for live data |

Keep site data fresh: `python3 scripts/site_data_writer.py --push`
Redeploy: `wrangler pages deploy /tmp/sites/bolt --project-name=bolt-fortress`

*Last updated: June 8, 2026 - Comprehensive documentation update with all user interfaces, storage management features, and completed upgrades*
