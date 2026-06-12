# Bolt Project Status

## Current State

Bolt is a working local-first creator assistant with a stable clip pipeline and a growing memory/learning layer.

The current mission is broader than Twitch clips. Bolt should support gaming, tech learning, AI development, product testing, Amazon Influencer storefront reviews, beauty/skincare testing, and the long-term goal of becoming Billy's virtual teammate.

## Active Runtime

What is active now:

- Recording watcher and batch processing
- Hard highlight confidence gate
- Deduplication before expensive stages
- Per-clip failure recovery
- Clip ranking tiers
- Title generation and subtitles
- Vertical clip formatting
- OBS, Twitch, Streamlabs, and Discord integration
- macOS voice alerts
- Twitch chat personality layer with persistent conversation memory
- **Voice conversation engine** — hands-free back-and-forth via mic, Whisper, OpenAI, and ElevenLabs
- Local queue and memory chat commands
- Runtime checkup dashboard generation
- Local memory retrieval through `modules/Memory_Index.py`
- Filed loose docs in canonical `docs/`, `memory/`, `teaching/rag/`, and `docs/upgrade/` locations

## Storage Management (NEW - June 6, 2026)

Automated storage optimization is now active:

- **Video Compression**: HandBrake H.264/H.265 encoding (75% average savings)
- **Media Rotation**: Size-based archival to keep recordings under 50GB, clips under 1GB
- **Duplicate Detection**: SHA256 hash-based deduplication
- **Storage Monitoring**: Disk usage checks every 3 hours with email/SMS alerts
- **Alert Recipients**: billycarteriv@gmail.com, 707-567-8495 (AT&T)
- **Alert Thresholds**: Warning at 80%, Critical at 95%

## Phase Meaning

- Phase 1: Dashboard and personality shell
- Phase 2: Live API connections
- Phase 3: Voice and chat personality
- Phase 4: Memory, retrieval, and decision-engine behavior

`Think_Learn_Decide` is the canonical decision path. `Brain_Controller` remains as a compatibility wrapper instead of a competing tier system.

## Quality Gating

The current clip flow uses:

- `quality_tiers.discard_below = 60`
- `quality_tiers.queue_at = 80`
- `min_post_score = 65`

That means:

- Below 60: discard
- 60 to 64: keep on disk, no queue
- 65 to 79: format and queue, no Discord alert
- 80 and up: queue and alert Billy at peak hours

## Memory And Creator Vision

Bolt's memory now includes:

- `memory/content/full-creator-vision.md`
- `memory/content/product-reviews.md`
- `memory/content/beauty-skincare.md`
- `memory/content/ai-development.md`
- `memory/content/brand-vision.md`
- `memory/content/daily-briefing.md`
- `memory/content/content-creation.md` (NEW)
- `memory/content/assistant-productivity.md` (NEW)
- `memory/content/game-testing.md` (NEW)
- `memory/content/live-streaming.md` (NEW)
- `memory/content/social-media-management.md` (NEW)
- `docs/daily-briefing-template.md`
- `docs/reports/DEBUG_REPORT.md`
- `docs/architecture/SYSTEM_README.md`
- `docs/upgrade/UPGRADE_INDEX.md`
- `docs/requirements/creator-domains-requirements.md` (NEW)
- `.github/instructions/creator-domains.instructions.md` (NEW)
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
python3 -m modules.Bolt_Chat --voice
python3 -m modules.Bolt_Conversation
python3 -m modules.Bolt_Voice "say this out loud"
python3 scripts/log_clip_performance.py --list
python3 llm/neural_model.py
```

## Storage Management Commands

```bash
# Detect and track duplicates
python3 scripts/clip_deduplicator.py

# Run performance baseline
python3 scripts/performance_baseline.py

# Manual storage optimization
python3 scripts/maintenance/storage_optimization.sh

# View active cron jobs
crontab -l
```

## What Still Needs Finish Work

1. Keep `Think_Learn_Decide` canonical and avoid reintroducing duplicate decision systems
2. Continue making retrieved memory change actual decisions, not only summaries
3. Add upgrade layers sequentially: one feature, one verification loop, one memory refresh
4. Decide how daily briefings should run locally before connecting calendar/email automation
5. Keep product/skincare/Amazon/AI learning lanes represented in future features
6. The old `BillyThunderstorm-site/` tree has been removed from the active repo layout

## Troubleshooting Notes

- If clips are too sparse, lower `highlight_sensitivity`
- If the queue is too noisy, raise `quality_tiers.discard_below`
- If clips are missing, lower `min_post_score` first, then `discard_below`
- If no chat responses appear, confirm Twitch env vars are set in `.env`
- If voice does not speak, check `Bolt_VOICE_MUTE`, `use_voice_checklist`, and macOS `say`
- If memory search feels stale, run `python3 scripts/refresh_memory_index.py`
- If storage alerts aren't sending, verify `configs/storage_alerts.env` is configured

## Last Updated
June 8, 2026

## Recent Updates (June 2026)

### June 8, 2026 - Creator Domains & Voice Conversation ✅
- **Voice Conversation Engine**: `modules/Bolt_Conversation.py` — hands-free back-and-forth voice chat
  - Listens via microphone using `speech_recognition` + OpenAI Whisper
  - Persistent conversation memory stored in `data/conversations/voice_history.json`
  - Personality-driven responses using `memory/context/bolt-personality.md`
  - Speaks replies through `Bolt_Voice` (ElevenLabs primary, edge-tts fallback, macOS say fallback)
  - CLI modes: voice loop (`--text` for typed), `--once` for single prompts, `--status`, `--clear`
- **Twitch Chat Voice Mode**: `--voice` flag added to `Bolt_Chat` — speaks replies aloud via ElevenLabs
- **Chat commands expanded**: `!postnow`, `!dontpost`, `!stopclip`, `!skip`, `!rank`, `!config`, `!uptime`, `!highlights`
- **Creator Domains System Requirements**: `docs/requirements/creator-domains-requirements.md`
  - Functional requirements for 7 domains: content creation, assistant productivity, game/tech testing, product review, live streaming, AI learning, social media management
- **Master Instruction Template**: `.github/instructions/creator-domains.instructions.md`
  - Full Bolt personality integration (cheerful energy, accidental sarcasm, decision hierarchy, burnout detection)
  - Domain-specific behavioral prompts with voice conversation rules
  - Cross-domain priority stack and memory layer management
- **New Domain Memory Files**:
  - `memory/content/content-creation.md`
  - `memory/content/assistant-productivity.md`
  - `memory/content/game-testing.md`
  - `memory/content/live-streaming.md`
  - `memory/content/social-media-management.md`
- **Personality integration**: `Bolt_Chat.py` now loads `memory/context/bolt-personality.md` correctly (fixed path bug)
- **Memory index refreshed**: 1380 entries indexed
- **34 unit tests pass** with no regressions

### June 6, 2026 - Upgrades Completed ✅
- **Fixed HandBrakeCLI Path**: Added PATH export for cron execution in video compression script
- **Requirements Audited**: Organized `requirements.txt` by category, removed unused packages
- **Duplicate Detection**: Created `scripts/clip_deduplicator.py` with SHA256 hashing
- **Storage Alerts**: Enhanced storage monitor with email (billycarteriv@gmail.com) and SMS (707-567-8495 AT&T)
- **Performance Baseline**: Created `scripts/performance_baseline.py` for benchmarking
- **Documentation Updated**: README.md, BOLT_COMMANDS.md, and PROJECT_STATUS.md with all user interfaces

### Earlier June 2026
- **Dependency Pinning**: Updated specific packages to resolve conflicts (completed via targeted pip installs)
  - `asyncer==0.0.8`, `gepa==0.0.27`, `importlib-metadata==8.9.0`, `pillow==11.3.0`, `protobuf==6.33.6`, `pydantic-core==2.46.4`, `typeguard==4.4.3`, `typer==0.25.1`, `websockets==15.0.1`
- **RAG Study Materials**: Added Retrieval-Augmented Generation learning resources to `teaching/rag/` directory
- **Preparation for Storage Alerts**: Prepared to enhance storage monitoring with alerting capabilities

## Completed Upgrades Summary

| Upgrade | Status | Details |
|---------|--------|---------|
| Voice Conversation Engine | ✅ Complete | `modules/Bolt_Conversation.py` — mic, Whisper, OpenAI, ElevenLabs, persistent memory |
| Twitch Chat Voice Mode | ✅ Complete | `--voice` flag speaks chat replies aloud |
| Creator Domains Requirements | ✅ Complete | System requirements for 7 creator/business domains |
| Master Instruction Template | ✅ Complete | `.github/instructions/creator-domains.instructions.md` with full personality |
| Domain Memory Files | ✅ Complete | 5 new memory files covering all creator lanes |
| HandBrakeCLI Path Fix | ✅ Complete | Fixed cron execution with full PATH |
| Requirements Audit | ✅ Complete | Organized, removed unused packages |
| Duplicate Detection | ✅ Complete | SHA256 hash-based system |
| Storage Alerts | ✅ Complete | Email + SMS configured |
| Performance Baseline | ✅ Complete | Benchmark script created |
| Documentation | ✅ Complete | All interfaces and commands documented |

## Storage Status

| Metric | Value |
|--------|-------|
| Total Project Size | ~44GB (down from 136GB) |
| Recordings Limit | 50GB |
| Clips Limit | 1GB |
| Disk Usage | ~11% (normal) |
| Compression Savings | ~75% average |

## Active Cron Jobs

| Schedule | Task | Status |
|----------|------|--------|
| `*/30 * * * *` | Video Compression | Active |
| `0 */3 * * *` | Storage Monitoring + Alerts | Active |
| `0 */6 * * *` | Media Rotation | Active |

## Websites (NEW - June 8, 2026)

Bolt now runs three live websites and a Cloudflare Worker API:

| Site | URL | Description |
|------|-----|-------------|
| **Bolt Command Center** | bolt.billythunderstorm.us | Terminal, clip queue, daily briefing, peak hours, brain activity |
| **Billy Thunderstorm** | billythunderstorm.us | Creator portfolio, hero image, milestones, storefront, social links |
| **Live Status** | billythunderstorm.live | Stream status, peak hours, social links |
| **API Worker** | api.billythunderstorm.us | JSON endpoints serving live data from GitHub |

### Architecture

```
Bolt (local) → scripts/site_data_writer.py → GitHub (site-data.json)
                                                    ↓
Cloudflare Worker (api.billythunderstorm.us) → reads GitHub raw
                                                    ↓
Three Cloudflare Pages sites → fetch from API every 60 seconds
```

### Key Details
- All sites deployed to Cloudflare Pages (direct upload)
- API Worker reads `site-data.json` from GitHub (30-second cache)
- Sites automatically fall back to localhost:8103 for local development
- Twitch username: ThunderstormBilly
- Domains: billythunderstorm.us and bolt.billythunderstorm.us on Cloudflare, billythunderstorm.live via Streamlabs/Namecheap with Cloudflare DNS

### Keeping Data Fresh
Run after each pipeline cycle:
```bash
python3 scripts/site_data_writer.py --push
```

Or add to cron for auto-updates every 15 minutes:
```bash
*/15 * * * * cd /Users/carter/developer/Bolt && python3 scripts/site_data_writer.py --push
```

### Redeploying Sites
```bash
wrangler pages deploy /tmp/sites/bolt  --project-name=bolt-fortress
wrangler pages deploy /tmp/sites/main   --project-name=billythunderstorm
wrangler pages deploy /tmp/sites/live   --project-name=billythunderstorm-live
cd /tmp/sites/bolt-api-worker && wrangler deploy
```
