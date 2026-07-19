# Bolt - Billy's AI Teammate

Bolt is Billy's local-first AI teammate for creator work, learning, and content operations.

**AI Provider:** OpenAI (chat/responses) + ElevenLabs (voice TTS)

It started as a Twitch and clip assistant, but the current vision is broader: Bolt helps Billy learn, test, teach, create, and improve across gaming, tech, AI development, product testing, Amazon Influencer storefront reviews, beauty/skincare, and building Bolt itself.

## Current Shape

- **Clip Pipeline**: Watches recordings, detects highlights, cuts clips, ranks them, formats vertical exports, queues posts, and alerts Billy when clips are worth posting
- **Decision Layer**: `Think_Learn_Decide` is the canonical intake/reasoning path, with `Brain_Controller` kept as a compatibility wrapper. The `think_and_propose()` method bridges memory retrieval into proposal ranking in one call.
- **Memory Layer**: `modules/Memory_Index.py` builds a local searchable index from Markdown memory, queue/history data, decision logs, and posted-performance outcomes
- **Memory-Aware Briefings**: Both `scripts/daily_briefing.py` and `scripts/weekly_analysis.py` retrieve memory through topic queries and surface concrete, memory-grounded action items
- **Content Memory**: `memory/content/` tracks the full creator vision, product reviews, Amazon storefront context, beauty/skincare, AI learning, hooks, and posted-content lessons
- **Calendar Feeds**: `scripts/generate_calendar.py` writes RFC 5545 (iCalendar) feeds for daily briefings, weekly insights, peak hours, and scheduled posts. Briefing email auto-attaches them as `text/calendar` MIME parts
- **Thumbnail Generation**: `scripts/generate_thumbnails.py` extracts JPG thumbnails for clips via ffmpeg with smart frame selection (skips black frames)
- **Storage Management**: Automated compression, rotation, and duplicate detection with email/SMS alerts
- **No-Cost Defaults**: AI-assisted features stay optional and fall back to local/template behavior when credentials are missing
- **Content Manager**: William's daily creator OS — catalog, drafts, store, social, sponsors. `bin/bolt manage ...` covers the full M1–M13 surface (see `Core/modules/BOLT_COMMANDS.md`)
- **Learned Clip Ranking**: `modules/Clip_Ranker.py` adds a 4th scoring component (`learned_boost`) that uses recency-weighted views + like_rate per (game, trigger) instead of the old raw-view linear formula. Inspect with `bolt manage model-inspect` and `bolt manage model-status`
- **Layout Scanner**: `scripts/check_layout.py` + `bin/bolt layout` keeps the repo at the 10 canonical directories

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
- **JPG thumbnail generation** for every clip via ffmpeg

### Communication
- Twitch chat bot and local chat commands
- Voice alerts via macOS TTS and ElevenLabs
- Voice conversation engine (mic -> Whisper -> OpenAI -> TTS, with persistent memory)
- Email and SMS storage alerts
- Calendar feeds (RFC 5545) auto-attached to briefing emails

### Memory & Learning
- Memory recall through `modules.Memory_Index`
- **Memory-aware daily briefing** — surfaces retrieved memory as concrete action items
- **Memory-aware weekly insights** — Memory Highlights section + memory-grounded recommendations
- **think_and_propose() bridge** — single-call memory → ranking pipeline
- Posted-performance logging for future learning
- RAG study materials in `teaching/rag/`
- **Creator-lane reachability tests** — regression suite verifying all 7 creator lanes stay queryable

### Storage Management
- Automated video compression (HandBrake H.264/H.265)
- Media rotation and archival (size-based)
- Hash-based duplicate detection
- Storage monitoring with threshold alerts
- Performance baseline tracking
- **JPG thumbnail refresh** (daily 5am cron)

### Monitoring
- Live checkup dashboard generation
- Storage monitoring (every 3 hours)
- Media rotation (every 6 hours)
- Video compression (every 30 minutes)
- **Thumbnail refresh** (daily 5am)
- **Memory-aware daily briefing** (daily 7am, sends via SMS/email with calendar attachments)
- **Memory-aware weekly analysis** (Sundays 9am, sends via SMS/email)
- **Auto-process recordings** (every 2 hours)

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
| **Daily Briefing** | `python3 scripts/daily_briefing.py [--print\|--send]` | Memory-aware morning briefing |
| **Weekly Analysis** | `python3 scripts/weekly_analysis.py [--print\|--send]` | Memory-aware Sunday insights |
| **Calendar Feeds** | `python3 scripts/generate_calendar.py` | RFC 5545 ICS feeds for calendar subscribe |
| **Thumbnails** | `python3 scripts/generate_thumbnails.py` | JPG thumbnails via ffmpeg |
| **Twitch Auto-Clip** | `python3 scripts/auto_clip_twitch.py` | Download VODs → clip pipeline (NEW) |
| **Highlight Reel** | `python3 scripts/make_twitch_highlights.py` | Compile best clips into VOD (NEW) |

### Chat Commands (when running)
```text
!queue                    - One-line summary of posting queue counts
!qstatus                  - Rich per-clip dashboard (id, score, status,
                            attempt count, hold reasons)
!recall <topic>           - Search memory for topic
!postnow [clip_id]        - Approve and publish the next ready clip
!dontpost [clip_id] <reason>  - Hold a clip and save why
!stopclip                 - Reject the next auto-post
!skip [clip_id]           - Skip the next post
!rank [score]             - Show or override a clip's ranking score
!config                   - Show current config summary
```

### Auto-Posting Safeguards
The queue has a 30-minute review window before each peak posting
time. Discord pings Billy, who can respond with `!postnow` / `!dontpost`
or let the deadline pass. Failed publishes get retried up to
`max_publish_attempts` times with `min_retry_gap_minutes` between
attempts, then auto-held. After 3 consecutive ignored reviews the
next Discord ping is prefixed with a `🚨 URGENT` banner. See
`Docs/BOLT_COMMANDS.md` for the full state machine.

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
| `0 5 * * *` | **Thumbnail Refresh** | JPGs for clips/ + vertical_clips/ |
| `0 7 * * *` | **Daily Briefing** | Memory-aware briefing → SMS/email + ICS attach |
| `0 */2 * * *` | **Auto-Process** | Process recordings automatically |
| `0 9 * * 0` | **Weekly Analysis** | Sunday insights → email |

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

### July 1, 2026 - Twitch VOD Auto-Clip + Highlight Reel Compiler

- **Twitch VOD auto-clipping** (`scripts/auto_clip_twitch.py`): Downloads past
  stream VODs from Twitch via yt-dlp and runs them through Bolt's full clip
  pipeline. Tracks processed VODs to avoid reprocessing. All 15 existing
  VODs already processed (clips existed from local OBS recordings).
- **Highlight reel compiler** (`scripts/make_twitch_highlights.py`): Stitches
  best clips into a 1920x1080 H.264 VOD with title card for Twitch upload.
- **Twitch client secret rotated** July 1, 2026.
- **Content posted**: 2 new clips (Ehkay.mp4, Bam.mp4) to TikTok, YouTube Shorts, X.
- **Queue**: 84 clips total, 13 posted.

### June 21, 2026 - Six New Features + Drift Fix

- **Memory-aware daily briefing** (`scripts/daily_briefing.py`): retrieves
  memory via three topic queries, surfaces a Memory Notes section, and
  uses memory-grounded action items instead of generic placeholders.
- **Memory-aware weekly analysis** (`scripts/weekly_analysis.py`): adds a
  Memory Highlights section and memory-grounded recommendations to
  the Sunday report.
- **Auto-thumbnail generation** (`scripts/generate_thumbnails.py`):
  ffmpeg-based JPG thumbnails with smart frame selection (avoids black
  frames). 134 thumbnails generated on first run in ~26 seconds.
- **Calendar/email automation** (`scripts/generate_calendar.py`): writes
  four RFC 5545 ICS feeds to `data/calendar/` for calendar subscribe.
  Briefing email auto-attaches them as `text/calendar` MIME parts.
- **Decision engine bridge** (`ThinkLearnDecideEngine.think_and_propose`):
  single-call bridge that flows retrieved memory into proposal ranking
  without manual wiring.
- **Lazy loading + startup perf fix** (`modules/_lazy_imports.py`): bot.py
  side-effect-at-import bug fixed (`import bot`: 2.2s -> 45ms, 48x faster).
- **Drift fix** (`scripts/log_clip_performance.py`): aligned with test
  expectations (PERFORMANCE_OUTCOMES_FILE, _is_success,
  _record_learning_outcome).
- **Regression suite** (`tests/test_creator_lanes_reachable.py`):
  verifies all 7 creator lanes remain reachable through memory retrieval.
- **Test suite**: 122 tests passing (up from 34).
- **Cron jobs**: added 5am thumbnail refresh; 7am briefing now auto-refreshes calendar feeds.

### June 6, 2026 - Upgrades Completed
- Fixed HandBrakeCLI path for cron execution
- Audited and organized `requirements.txt`
- Created hash-based duplicate detection (`scripts/clip_deduplicator.py`)
- Enhanced storage monitor with email/SMS alerts
- Created performance baseline script
- Updated all documentation with comprehensive interface list


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

*Last updated: July 1, 2026 - Added Twitch VOD auto-clipping pipeline and highlight reel compiler. Total test suite: 122 passing.*
