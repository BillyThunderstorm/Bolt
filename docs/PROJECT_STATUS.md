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
- **Twitch VOD auto-clipping** — downloads VODs and runs full clip pipeline automatically
- **Highlight reel compiler** — stitches best clips into a VOD for Twitch upload
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
python3 scripts/auto_clip_twitch.py --list
python3 scripts/auto_clip_twitch.py
python3 scripts/make_twitch_highlights.py --list
python3 scripts/make_twitch_highlights.py
python3 llm/neural_model.py
```

## Calendar Feeds

```bash
# Refresh all four ICS feeds in data/calendar/
python3 scripts/generate_calendar.py

# Dry-run
python3 scripts/generate_calendar.py --dry-run

# Limit scheduled_posts.ics to next 14 days
python3 scripts/generate_calendar.py --days 14

# Send today's briefing via SMS/email (auto-refreshes calendar feeds and
# attaches them as text/calendar MIME parts).
python3 scripts/daily_briefing.py --send
```

Subscribe from your mail client (Apple Calendar, Google Calendar,
Fantastical, Outlook) by opening the .ics file, or host the
`data/calendar/` directory and subscribe via `webcal://` URL.

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

### June 21, 2026 - Lazy Loading + Startup Perf Fix ✅
- **Bug fix**: `bot.py` was calling `write_site_data(push=True)` at
  module-import time, which meant every `from bot import …` triggered a
  GitHub push. `import bot` took **2.2 seconds** before this fix.
  - Moved the call into `main()` so it only runs when bot.py is executed
    as a script (`python3 bot.py`) or via `launch.py`.
  - Wrapped in try/except so a site-data push failure never blocks the
    pipeline.
  - **Result**: `import bot` now takes **45ms** (48x speedup).
  - Tests/scripts that import from `bot.py` no longer pay the push cost.
- **New helper module**: `modules/_lazy_imports.py` provides
  `lazy_import(name)` proxy for deferring heavy third-party imports
  (moviepy, librosa, opencv, PIL, etc.) until first attribute access.
  - Caches resolved attributes for O(1) subsequent access.
  - `force_load`, `is_loaded`, `is_module_loaded`, and `tracked_lazy_import`
    helpers for diagnostics.
  - Process-wide `registered_proxies()` registry for tests/benchmarks.
- **Tests**: 12 new tests in `tests/test_lazy_imports.py` covering
  proxy deferral, attribute caching, force_load, repr/bool state,
  iteration, the registry, and (via subprocess) the bot.py side-effect
  removal + import-speed regression guard.
- **Full suite**: 122/122 passing.

### June 21, 2026 - Memory-Aware Decision Engine Bridge ✅
- **New `ThinkLearnDecideEngine.think_and_propose(context, candidates)`**
  method: single-call bridge that runs `think(context)` to retrieve memory
  and compute `memory_influence`, then automatically threads that
  influence into every candidate that doesn't already carry one before
  calling `propose_actions(candidates)`.
- **Why this matters**: until now, callers had to manually attach
  `memory_influence` to each candidate for memory-aware ranking to kick
  in. The bridge removes that hand-wiring so the full
  think → retrieve → boost → rank pipeline flows naturally.
- **Back-compat preserved**: existing callers that pass `memory_influence`
  on individual candidates are NOT overwritten — the bridge only fills in
  what's missing. Old callers calling `propose_actions` directly are
  unaffected (8 existing tests confirm no regression).
- **Failure-safe**: if retrieval returns nothing, `think_and_propose`
  returns proposals identical to a plain `propose_actions` call.
- **Tests**: 6 new tests in `tests/test_think_learn_decide.py` covering
  supportive boost, cautionary reduction, no-match parity, caller
  influence preservation, ranking order, and back-compat.
- **Full suite**: 110/110 passing.

### June 21, 2026 - Calendar/Email Automation ✅
- **New `scripts/generate_calendar.py`** writes four RFC 5545 (iCalendar)
  feeds to `data/calendar/`:
  - `daily_briefing.ics` — recurring daily 7am VEVENT
  - `weekly_insights.ics` — recurring Sunday 9am VEVENT
  - `peak_hours.ics` — recurring daily 7-9pm posting window VEVENT
  - `scheduled_posts.ics` — one VEVENT per queued post within a 30-day
    lookahead, sourced from `data/multi_platform_queue.json`
- **No new dependencies** — hand-rolled ICS writer with proper RFC 5545
  escaping (`;`, `,`, `\n`, `\\`).
- **Validated** against the official `icalendar` Python library (all four
  feeds parse cleanly).
- **`scripts/daily_briefing.py --send` now refreshes the calendar feeds
  before emailing** and attaches them as `text/calendar` MIME parts so
  Billy can subscribe with one click from his mail client.
- **`scripts/send_notification.py`** gained `attachments=` on `send_email`
  and `send_briefing`. MIME envelope switched from `multipart/alternative`
  to `multipart/mixed` to support attachments.
- **Tests**: new `tests/test_generate_calendar.py` (19 tests, all passing).
  Full suite: 104/104.

### June 21, 2026 - Creator-Lane Reachability Tests ✅
- **New regression suite**: `tests/test_creator_lanes_reachable.py` locks in
  that all 7 creator lanes from `full-creator-vision.md` remain reachable
  through Bolt's memory retrieval: gaming, tech, AI development, product
  testing, Amazon storefront, beauty/skincare, Bolt-building.
- **Tests force an index rebuild** in `setUpClass`, so they catch BOTH file
  drift (someone deletes/renames a lane file) AND stale-index drift (the
  index wasn't refreshed after memory edits).
- **Three test classes**:
  - `CreatorLaneReachabilityTests` — one test per lane, queries with each
    lane's natural vocabulary, asserts the right file surfaces in the top 8.
  - `CreatorLaneFilesExistTests` — 9 expected memory files must exist.
  - `CreatorLaneContentQualityTests` — lane files must contain expected
    keywords (`direction`, `north star`, `risk`, etc.) and be > 200 chars.
- **Verified the test fails when a lane file is deleted** (sanity check):
  moving `memory/content/game-testing.md` away makes the gaming test fail
  with an actionable error message showing query, expected source, and
  the actual top results.
- **Tests**: 9 new tests, all passing on a clean index. Full suite: 85/85.

### June 21, 2026 - Auto-Thumbnail Generation ✅
- **New script**: `scripts/generate_thumbnails.py` — extracts a JPG thumbnail
  for every video in `clips/` and `vertical_clips/` using ffmpeg.
- **Smart frame selection** (default): seeks to 1/3 of duration, measures
  average luma, and falls back to 1/2 then 2/3 if the frame is mostly
  black. Frame-0 always available as last-resort fallback. Also supports
  `--strategy first` and `--strategy middle`.
- **Aspect-preserving**: keeps source aspect (16:9 horizontal, 9:16 vertical),
  rescales width to 1280px by default.
- **Incremental**: skips clips whose `.jpg` is newer than the source;
  `--force` overrides.
- **Dry-run mode** (`--dry-run`): plan the work without invoking ffmpeg.
- **State persistence**: `--save-state` writes a JSON summary to
  `data/thumbnail_state.json` for audit.
- **Generated 81 clip thumbs + 52 vertical thumbs** on first run (~26s total).
- **Tests**: new `tests/test_generate_thumbnails.py` (24 tests, all passing).
  Full suite: 76/76.

### June 21, 2026 - Memory-Aware Weekly Analysis ✅
- **`scripts/weekly_analysis.py`** now retrieves memory via four weekly-themed
  queries (creator vision, post performance, recent decisions, live streaming).
- **New "🧠 Memory Highlights" section** in the report renders the top 8
  retrieved hits with source, kind, title, and summary.
- **Recommendations now start with memory-grounded items** (max 2, deduped
  by title theme) before the existing generic recommendations, so creator
  notes and recent decisions shape next-week planning without making the
  section noisy.
- **SMS summary** now includes `N memory hits` alongside the existing facts.
- **Bug fix**: same `PROJECT_ROOT` / `sys.path` pattern as the daily
  briefing — direct CLI invocation now resolves `from modules import …`.
- **Tests**: new `tests/test_weekly_analysis.py` (8 tests, all passing).
  Full suite: 52/52.

### June 21, 2026 - Memory-Aware Daily Briefing ✅
- **Briefing now pulls from `Memory_Index.retrieve_memory`** using three topic
  queries: recent clip performance, recent decisions/actions, current focus.
- **New "Memory Notes" section** in `scripts/daily_briefing.py` renders the
  top retrieved hits with source file, title, and summary.
- **Action Items are now memory-grounded** when memory is available: a
  canonical "Review last clip performance" item replaces the generic one,
  decision events become "Follow up on recent decision: …", and content
  memory becomes "Creator note active: …". Falls back to generic items if
  retrieval returns nothing.
- **SMS summary** now includes `N memory notes` so Billy can see at a glance
  whether memory is shaping the briefing.
- **Bug fix**: `PROJECT_ROOT` is now resolved and added to `sys.path` at
  module load, so `from modules import …` works whether the script is run
  directly (`python3 scripts/daily_briefing.py`) or imported.
- **Tests**: new `tests/test_daily_briefing.py` (10 tests, all passing).
  Full suite: 44/44.
- **Memory index**: refreshed — now 3032 entries.

## Troubleshooting Notes

- If clips are too sparse, lower `highlight_sensitivity`
- If the queue is too noisy, raise `quality_tiers.discard_below`
- If clips are missing, lower `min_post_score` first, then `discard_below`
- If no chat responses appear, confirm Twitch env vars are set in `.env`
- If voice does not speak, check `Bolt_VOICE_MUTE`, `use_voice_checklist`, and macOS `say`
- If memory search feels stale, run `python3 scripts/refresh_memory_index.py`
- If storage alerts aren't sending, verify `configs/storage_alerts.env` is configured

## Last Updated
July 1, 2026

## Recent Updates (July 2026)

### July 1, 2026 - Twitch VOD Auto-Clip Pipeline + Highlight Reel Compiler ✅
- **`scripts/auto_clip_twitch.py`**: Downloads Twitch VODs via yt-dlp, runs them through Bolt's full clip pipeline (detect highlights → cut → title → format 9:16 → queue), and tracks processed VODs in `data/twitch_vods_processed.json`.
  - Commands: `--list`, `--all`, `--vod <ID>`, `--twitch-clips`
  - All 15 existing VODs already processed (clips existed from local OBS recordings, dedup system confirmed)
  - Twitch client secret rotated July 1, 2026
  - Next stream → run `auto_clip_twitch.py` to auto-process new VODs
- **`scripts/make_twitch_highlights.py`**: Compiles best clips into a 1920x1080 H.264 highlight reel video for Twitch upload.
  - Commands: `--count N`, `--game "keyword"`, `--list`, `--output filename`
  - Output: `highlight_reels/YYYY-MM-DD_highlight_reel.mp4`
  - Title card intro + clips concatenated with audio
  - Upload to Twitch via Video Producer
- **Content posted today**: Ehkay.mp4 (Marvel Rivals — ult fail) and Bam.mp4 (Marvel Rivals — Storm double kill) to TikTok, YouTube Shorts, and X
- **Queue updated**: 84 clips total in `ready_to_post.json` (13 posted)

## Recent Updates (June 2026)

### June 22, 2026 - Documentation Sync ✅
- **`README.md`**: added 4 new interface rows (Daily Briefing, Weekly Analysis,
  Calendar Feeds, Thumbnails), updated all "What Works Now" sections with the
  June 21 features, added 5am thumbnail row to the cron table, replaced the
  Recent Updates section with a comprehensive June 21 entry.
- **`BOLT_COMMANDS.md`**: added command blocks for daily briefing, weekly
  analysis, calendar feeds, thumbnail generation, and the decision engine
  bridge. Expanded the User Interfaces Summary table with 4 new rows and
  the Cron Jobs section with the 5am entry. Added a "Quick Performance
  Check" block documenting the 2.2s → 45ms bot import win.
- **`docs/INDEX.md`**: added 4 new rows to the User Interfaces Summary table,
  added a new Active Cron Schedule section with all 9 jobs, kept the
  Legacy or Archived section.
- **"Last Updated"** bumped from June 21 to June 22 throughout.

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
| `0 3 * * *` | Storage Optimization Cleanup | Active |
| `0 5 * * *` | Thumbnail Refresh (clips/ + vertical_clips/) | Active (added Jun 21) |
| `0 7 * * *` | Daily Briefing via SMS/Email | Active |
| `0 */2 * * *` | Auto-Process New Recordings | Active |
| `0 9 * * 0` | Weekly Performance Insights | Active |
| After each stream | **Twitch VOD auto-clip** (manual trigger) | Run `python3 scripts/auto_clip_twitch.py` |

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
