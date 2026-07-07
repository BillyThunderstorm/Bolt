# Bolt Commands To Remember

This file keeps the current Bolt commands in one place.

## Local Paths

Real Bolt repo:

```bash
cd "/Users/carter/developer/Bolt"
```

Helper workspace for side scaffolds and sibling tooling:

```bash
cd "/Users/carter/Documents/Codex/2026-05-13/im-trying-to-create-my-own"
```

Keep those workspaces separate unless you are intentionally copying a specific artifact.

## Setup

Run from `/Users/carter/developer/Bolt`:

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

```bash
python3 -m pip install --upgrade pip
```

```bash
python3 -m pip install -r requirements.txt
```

Create a local `.env` from the safe template:

```bash
cp .env.example .env
```

Back up `.env` before changing keys:

```bash
cp .env .env.backup
```

## Verify Bolt

Run the project verifier:

```bash
python3 scripts/verify.py
```

Run the unit tests:

```bash
python3 -m unittest
```

Run focused tests:

```bash
python3 -m unittest tests.test_memory_index
```

```bash
python3 -m unittest tests.test_think_learn_decide
```

```bash
python3 -m unittest tests.test_daily_briefing
```

```bash
python3 -m unittest tests.test_weekly_analysis
```

```bash
python3 -m unittest tests.test_generate_thumbnails
```

```bash
python3 -m unittest tests.test_generate_calendar
```

```bash
python3 -m unittest tests.test_creator_lanes_reachable
```

```bash
python3 -m unittest tests.test_lazy_imports
```

Run Python compile checks:

```bash
python3 -m compileall launch.py bot.py modules scripts tests
```

## Launch Bolt

Run the full launch flow:

```bash
python3 launch.py
```

Process the latest recording:

```bash
python3 launch.py process
```

Run the bot directly:

```bash
python3 bot.py
```

## Process Recordings

Drop recordings into `recordings/`, then run:

```bash
# Process all recordings (gaming mode — default)
python3 scripts/process_recordings.py

# Process latest recording only
python3 scripts/process_recordings.py latest

# Process specific recording by index
python3 scripts/process_recordings.py 3

# List recordings without processing
python3 scripts/process_recordings.py list
```

### Content-Type Routing (NEW - July 3, 2026)

Bolt now supports different content types with Gemini-optimized captions:

```bash
# Gaming clips (default — uses template titles)
python3 scripts/process_recordings.py --content-type gaming

# Product review content (Nexus/Gemini optimizes captions)
python3 scripts/process_recordings.py --content-type review

# Skincare/beauty content (Nexus/Gemini optimizes captions)
python3 scripts/process_recordings.py --content-type skincare

# Tech content (Nexus/Gemini optimizes captions)
python3 scripts/process_recordings.py --content-type tech

# Short form
python3 scripts/process_recordings.py latest -t review
```

**How it works:**
- `gaming` = local template titles (fast, free, no API calls)
- `review` / `skincare` / `tech` = Nexus Creator generates optimized captions via Gemini (free)
- All modes run the full pipeline: detect highlights → cut clips → titles → subtitles → rank → format 9:16 → queue

## Chat, Voice, And Local Controls

### Bolt Chat Module
Run Bolt chat locally:

```bash
python3 -m modules.Bolt_Chat
```

Run with voice responses enabled (speaks replies aloud via ElevenLabs):

```bash
python3 -m modules.Bolt_Chat --voice
```

### Voice Conversation (NEW)
Start a back-and-forth voice conversation with Bolt. Listens via mic, transcribes with Whisper, generates personality-driven responses, speaks them aloud, and remembers the thread:

```bash
python3 -m modules.Bolt_Conversation              # voice chat loop
python3 -m modules.Bolt_Conversation --text         # type instead of speak
python3 -m modules.Bolt_Conversation --once "What should I post today?"
python3 -m modules.Bolt_Conversation --status      # check setup status
python3 -m modules.Bolt_Conversation --clear       # clear conversation history
```

Conversation history is saved to `data/conversations/voice_history.json`.

### Voice Commands
Test voice:

```bash
python3 -m modules.Bolt_Voice "say this out loud"
```

List available voice event lines:

```bash
python3 -m modules.Bolt_Voice --list-events
```

### Chat Commands (when Bolt is running)
```text
!queue                    - One-line summary of the posting queue counts
!qstatus                  - Rich per-clip dashboard (id, score, plan status,
                            attempt count, hold reasons, ignored counter)
!recall <topic>           - Search memory for topic
!clip                     - Confirm last highlight count
!highlights               - How many highlights this session
!uptime                   - How long the stream has been live
!postnow [clip_id]        - Approve and publish the next ready clip
!dontpost [clip_id] <reason>  - Hold a clip and save why
!stopclip                 - Reject the next auto-post
!skip [clip_id]           - Skip the next post
!rank [score]             - Show or set the next clip's ranking score
!config                   - Show current config summary
```

### Auto-Posting Safeguards (Tier 4.1)
The posting queue runs in three states per clip: `scheduled` → `awaiting_approval` → `posted` (or `held`). The safeguards are:

```text
Review window:   30 min before scheduled peak time. Discord ping goes out,
                 Billy responds with !postnow / !dontpost, OR the
                 deadline passes and Bolt auto-posts (configurable).
Backoff:         If publish fails (e.g. TikTok rate limit), the clip is
                 retried on the next process tick after
                 min_retry_gap_minutes (default 5) and up to
                 max_publish_attempts times (default 3).
Auto-hold:       After max_publish_attempts failures the clip is held
                 with reason 'publish_failed_after_N_attempts: <error>'
                 so Billy can see what's stuck without it spinning.
De-dup lock:     A clip in 'publishing' state is locked — concurrent
                 !postnow and deadline auto-posts can't both fire.
Confirmation:    Successful publishes send a Discord message
                 '✅ Posted: <title> — <url>'.
Escalation:      3 consecutive ignored reviews prefix the next
                 Discord ping with '🚨 URGENT: N reviews ignored'.
Dashboard:       !qstatus shows the full state — see command list above.
```

Tunables (in `Data/data/config.json` → `auto_posting`):
```json
"auto_posting": {
  "enabled": true,
  "review_window_minutes": 30,
  "auto_post_if_deadline_missed": true,
  "max_publish_attempts": 3,
  "min_retry_gap_minutes": 5
}
```

## Memory Operations

### Refresh Memory Index
Refresh the local searchable memory index after editing memory files:

```bash
python3 scripts/refresh_memory_index.py
```

### Search Memory
Search memory through the index module:

```bash
python3 -m modules.Memory_Index --refresh "Amazon Influencer storefront product testing"
```

Search memory through Bolt memory:

```bash
python3 -m modules.Bolt_Memory --search "beauty skincare routine product test results"
```

## Content Results And Learning

### Log Performance
List logged performance outcomes:

```bash
python3 scripts/log_clip_performance.py --list
```

Log a posted clip result:

```bash
python3 scripts/log_clip_performance.py --clip clips/example.mp4 --platform TikTok --note "Strong opening hook"
```

### Multi-Platform Posting
Build a no-cost posting packet:

```bash
python3 -m modules.Multi_Publisher clips/example.mp4 "Working title" --hashtags gaming ai
```

## Nexus Creator — AI Content Strategy Consultant (NEW - July 3, 2026)

Nexus is Bolt's strategic brain, powered by Gemini (free tier). It provides
actionable advice on hooks, monetization, engagement, and content strategy.

```bash
# Ask for advice on a topic
python3 scripts/nexus_advice.py "How should I title my Hades 2 clips?"

# Get next content recommendations based on performance data
python3 scripts/nexus_advice.py --next

# Optimize a caption for a specific clip
python3 scripts/nexus_advice.py --caption "clip.mp4" --desc "Epic boss fight" -p tiktok

# Provide context with your question
python3 scripts/nexus_advice.py "skincare review strategy" --context "17 clips posted, low views"

# Use a different Gemini model
python3 scripts/nexus_advice.py "topic" --model gemini-2.5-pro
```

**Python API:**
```python
from modules.Nexus_Creator import NexusCreator

nexus = NexusCreator()
advice = nexus.consult(topic="Hades 2 strategy", context="2,393 views across 5 posts")
next_content = nexus.suggest_next_content(performance_data={...})
caption = nexus.optimize_caption(clip_name="clip.mp4", clip_description="...", platform="tiktok")
```

**Logs:** All advice saved to `data/nexus_advice.jsonl`

**API Key:** `GEMINI_API_KEY` in `.env` (get from Google AI Studios — free)

## Title Generation — Now Using Gemini (UPDATED - July 3, 2026)

Title generation switched from OpenAI (paid, quota exhausted) to Gemini (free):

```bash
# Monitor title generation results
python3 scripts/monitor_title_results.py

# Run title upgrade test
python3 scripts/test_title_upgrade_10_clips.py
```

**What changed:**
- `Title_Generator.py` now calls Gemini (gemini-2.5-flash) by default
- Falls back to OpenAI only if Gemini key is missing AND OpenAI has credits
- Falls back to local templates if both fail
- Config: `use_ai_titles: true`, `title_generation.enabled: true`
- Set `USE_GEMINI_TITLES=false` in `.env` to force OpenAI

## Skincare / Product Review / Tech Analysis (NEW - July 3, 2026)

Three formerly-placeholder modules are now wired to real Gemini intelligence:

### Skincare Analyzer
```bash
# Analyze skincare products and generate review content
python3 -c "
from modules.Skincare_Analyzer import analyze_skincare_routine
report = analyze_skincare_routine(
    product_list=[{'name': 'The Ordinary Niacinamide', 'ingredients': ['Niacinamide', 'Zinc'], 'type': 'Serum'}],
    user_goal='Budget barrier repair routine',
    target_platform='tiktok'
)
print(report['nexus_advice'])
"
```

### Amazon / Product Analyzer
```bash
# Analyze a product by URL or ASIN
python3 -c "
from modules.Amazon_Analyzer import analyze_product_review
report = analyze_product_review(
    product_links=['B08N5WRWNW'],
    comparison_focus='Best budget wireless headphones',
    target_platform='tiktok'
)
print(report['nexus_advice'])
"
```

### AI / Tech Analyzer
```bash
# Analyze a tech article URL
python3 -c "
from modules.AI_Analyzer import analyze_tech_source
report = analyze_tech_source(
    url='https://example.com/ai-article',
    query='What makes this chip different?',
    params=['Speed', 'Cost', 'Features']
)
print(report['nexus_advice'])
"
```

All three use real web fetching + Gemini analysis. No more placeholder data.

## Tokens And Auth

Generate or refresh the Twitch bot token:

```bash
python3 scripts/get_twitch_token.py
```

Generate or refresh TikTok auth:

```bash
python3 scripts/get_tiktok_token.py
```

## AI Learning

Run the cleaned neural-network learning example:

```bash
python3 llm/neural_model.py
```

## Websites (NEW)

Bolt runs three websites and an API on Cloudflare:

| Site | URL | Description |
|------|-----|-------------|
| **Bolt Command Center** | bolt.billythunderstorm.us | Terminal, clip queue, briefing, peak hours |
| **Billy Thunderstorm** | billythunderstorm.us | Creator portfolio, milestones, storefront, socials |
| **Live Status** | billythunderstorm.live | Stream status, peak hours, social links |
| **API Worker** | api.billythunderstorm.us | JSON endpoints for live data |

### Update Site Data

After each Bolt pipeline run, push fresh data to the websites:

```bash
python3 scripts/site_data_writer.py --push
```

Or add to bot.py as an import:

```python
from scripts.site_data_writer import write_site_data
write_site_data(push=True)
```

### Set Up Cron for Auto-Updates

```bash
crontab -e
# Add this line for every 15 minutes:
*/15 * * * * cd /Users/carter/developer/Bolt && python3 scripts/site_data_writer.py --push
```

### Redeploy Sites (After Content Changes)

Site files are in `/tmp/sites/`. If you modify the HTML/CSS/JS, redeploy:

```bash
wrangler pages deploy /tmp/sites/bolt  --project-name=bolt-fortress
wrangler pages deploy /tmp/sites/main   --project-name=billythunderstorm
wrangler pages deploy /tmp/sites/live   --project-name=billythunderstorm-live
```

API Worker (only if worker.js changed):

```bash
cd /tmp/sites/bolt-api-worker && wrangler deploy
```

### Local Development

For testing sites locally, run the API server:

```bash
python3 /tmp/sites/api_server.py
# Serves at http://localhost:8103
```

Then open site files in a browser — they'll fall back to localhost:8103 automatically.

### API Endpoints

| Endpoint | Returns |
|----------|---------|
| `api.billythunderstorm.us/api/status` | Clip counts, API key status |
| `api.billythunderstorm.us/api/queue` | Clip queue with titles |
| `api.billythunderstorm.us/api/briefing` | Daily briefing |
| `api.billythunderstorm.us/api/peaks` | Peak hour schedule |
| `api.billythunderstorm.us/api/all` | Everything in one request |

## Twitch VOD Auto-Clipping (NEW - July 1, 2026)

Automatically download Twitch VODs and run them through Bolt's clip pipeline:

```bash
# List all VODs and their processing status
python3 scripts/auto_clip_twitch.py --list

# Process the latest unprocessed VOD (downloads → clip pipeline → post queue)
python3 scripts/auto_clip_twitch.py

# Process all unprocessed VODs
python3 scripts/auto_clip_twitch.py --all

# Process a specific VOD by ID
python3 scripts/auto_clip_twitch.py --vod 2784630508

# Also create Twitch clips via API (requires user OAuth - not yet configured)
python3 scripts/auto_clip_twitch.py --twitch-clips
```

**What it does:**
- Downloads VODs from Twitch using yt-dlp
- Runs each VOD through Bolt's full clip pipeline (detect highlights → cut → title → format 9:16 → queue)
- Tracks processed VODs in `data/twitch_vods_processed.json` to avoid reprocessing
- Downloads to `vods/` directory
- All 15 existing VODs already processed (clips existed from local OBS recordings)
- Run after each stream to auto-process new VODs

**Twitch credentials (in .env):**
- `TWITCH_CLIENT_ID` — App client ID from dev.twitch.tv
- `TWITCH_CLIENT_SECRET` — App secret (rotated July 1, 2026)
- `TWITCH_CHANNEL` — ThunderstormBilly (user ID: 441598765)

## Twitch Highlight Reel Compiler (NEW - July 1, 2026)

Compile your best clips into a highlight VOD for uploading to Twitch:

```bash
# Compile top 10 clips into a highlight reel
python3 scripts/make_twitch_highlights.py

# Compile top 15 clips
python3 scripts/make_twitch_highlights.py --count 15

# Filter clips by game keyword
python3 scripts/make_twitch_highlights.py --game "Hades"

# List top clips by score
python3 scripts/make_twitch_highlights.py --list

# Custom output filename
python3 scripts/make_twitch_highlights.py --output my_reel.mp4
```

**Output:** `highlight_reels/YYYY-MM-DD_highlight_reel.mp4`
- 1920x1080 H.264 with AAC audio
- Title card intro + clips concatenated
- Upload to Twitch via Video Producer: https://dashboard.twitch.tv/u/ThunderstormBilly/content/video-producer

## Storage Management & Monitoring

**Current Status (June 15, 2026 - POST-MAINTENANCE)**:
- Disk: 87% used (776GB/926GB) - ✅ 10% freed
- Recordings: 0GB (deleted files >3 days old)
- Clips: 0GB (deleted files >3 days old)
- Archive: 49GB (old files preserved here)

**Maintenance Done June 15**:
- Deleted recordings older than 3 days (freed 91GB)
- Deleted clips older than 3 days (freed 6.7GB)
- Archived old clips and recordings to archive/ (49GB preserved)
- Fixed storage_optimization.sh archival bug
- Added nightly storage optimization cron job (3am)
- Updated langchain/openai packages

### Run Storage Optimization
```bash
# Dry run to see what would be done
./scripts/maintenance/storage_optimization.sh --dry-run

# Run actual optimization (use with caution)
./scripts/maintenance/storage_optimization.sh --skip-dedup

# Customize limits
./scripts/maintenance/storage_optimization.sh --recordings-gb 40 --clips-gb 0.5
```

**Bug Fix (June 15)**: Fixed archival path issue in `storage_optimization.sh` line 264 - changed `mv "$file" "$ARCHIVE_DIR/$file/"` to `mv "$file" "$ARCHIVE_DIR/$file"` (removed trailing slash).

### Individual Maintenance Scripts
```bash
# Media rotation (size-based, runs every 6 hours via cron)
scripts/maintenance/media_rotation.sh

# Storage monitoring with alerts (runs every 3 hours via cron)
scripts/monitoring/storage_monitor.sh

# Video compression (runs every 30 minutes via cron)
scripts/media_processing/compress_videos.sh
```

### Duplicate Detection
```bash
# Scan for duplicates in clips and recordings
python3 scripts/clip_deduplicator.py

# Dry run mode (no database changes)
python3 scripts/clip_deduplicator.py --dry-run

# Check a single file
python3 scripts/clip_deduplicator.py --check clips/example.mp4

# Clear the hash database
python3 scripts/clip_deduplicator.py --clear-db
```

### Performance Baseline
```bash
# Measure current performance metrics
python3 scripts/performance_baseline.py
```

## Storage Alert Configuration

Configure email and SMS alerts:

```bash
# Edit the configuration file
nano configs/storage_alerts.env
```

Configuration options:
- `ALERT_EMAIL` - Email address for alerts
- `ALERT_PHONE` - Phone number for SMS (digits only)
- `CARRIER` - Mobile carrier (att, verizon, tmobile, sprint, virgin, boost)
- `WEBHOOK_URL` - Generic webhook URL
- `DISCORD_WEBHOOK` - Discord webhook URL

## Docs To Check Before Upgrades

```bash
open README.md
open BOLT_COMMANDS.md
open docs/INDEX.md
open docs/PROJECT_STATUS.md
open memory/content/full-creator-vision.md
open NEXT_UPGRADE_STEPS.md
open OPTIMIZATION_ROADMAP.md
```

## Git Checks

```bash
git status --short
```

```bash
git diff --stat
```

```bash
git diff -- README.md BOLT_COMMANDS.md docs memory brand llm
```

## User Interfaces Summary

| Interface | Command/Path | Description |
|-----------|--------------|-------------|
| **CLI Launcher** | `python3 launch.py` | Main entry point for Bolt |
| **Bot Runtime** | `python3 bot.py` | Direct bot execution |
| **Chat Module** | `python3 -m modules.Bolt_Chat` | Local chat testing |
| **Chat + Voice** | `python3 -m modules.Bolt_Chat --voice` | Chat with spoken replies |
| **Voice Conversation** | `python3 -m modules.Bolt_Conversation` | Hands-free back-and-forth voice chat |
| **Voice Module** | `python3 -m modules.Bolt_Voice "text"` | TTS voice output |
| **Memory Search** | `python3 -m modules.Memory_Index` | Searchable memory index |
| **Memory Browser** | `python3 -m modules.Bolt_Memory` | Full memory operations |
| **Checkup Dashboard** | `docs/Bolt_Checkup.html` | Live status dashboard |
| **Duplicate Scanner** | `python3 scripts/clip_deduplicator.py` | Hash-based dedup |
| **Performance Baseline** | `python3 scripts/performance_baseline.py` | Benchmark metrics |
| **Storage Monitor** | `scripts/monitoring/storage_monitor.sh` | Disk usage + alerts |
| **Video Compressor** | `scripts/media_processing/compress_videos.sh` | HandBrake compression |
| **Media Rotator** | `scripts/maintenance/media_rotation.sh` | Auto-archival |
| **Site Data Writer** | `python3 scripts/site_data_writer.py --push` | Push live data to websites |
| **Daily Briefing** | `python3 scripts/daily_briefing.py [--print\|--send]` | Memory-aware morning briefing |
| **Weekly Analysis** | `python3 scripts/weekly_analysis.py [--print\|--send]` | Memory-aware weekly insights |
| **Calendar Feeds** | `python3 scripts/generate_calendar.py` | RFC 5545 ICS files for calendar subscribe |
| **Thumbnails** | `python3 scripts/generate_thumbnails.py` | JPG thumbnails for clips via ffmpeg |
| **Process Recordings** | `python3 scripts/process_recordings.py` | Process recordings → clips → queue |
| **Nexus Creator** | `python3 scripts/nexus_advice.py "topic"` | AI content strategy (Gemini) |
| **Twitch Auto-Clip** | `python3 scripts/auto_clip_twitch.py` | Download VODs → clip pipeline |
| **Highlight Reel** | `python3 scripts/make_twitch_highlights.py` | Compile best clips into VOD |
| **Bolt Website** | bolt.billythunderstorm.us | Command center |
| **Billy Website** | billythunderstorm.us | Creator portfolio |
| **Live Status** | billythunderstorm.live | Stream status page |

## Creator Domain Docs (NEW)

```bash
open docs/requirements/creator-domains-requirements.md   # system requirements
open .github/instructions/creator-domains.instructions.md  # behavior instructions
open memory/content/content-creation.md                  # content domain
open memory/content/assistant-productivity.md            # productivity domain
open memory/content/game-testing.md                      # game/tech review domain
open memory/content/live-streaming.md                    # streaming domain
open memory/content/social-media-management.md           # social domain
```

## Cron Jobs (Automated)

```bash
# View active cron jobs
crontab -l
```

Current schedule:
- `*/30 * * * *` - Video compression (HandBrakeCLI)
- `0 */3 * * *` - Storage monitoring with alerts
- `0 */6 * * *` - Media rotation/archival
- `0 3 * * *` - Storage optimization (nightly, skips dedup for speed)
- `0 5 * * *` - **Thumbnail refresh** for clips/ and vertical_clips/ (NEW)
- `*/15 * * * *` - Site data push to websites (recommended)
- `0 7 * * *` - **Daily briefing** → SMS/email (auto-refreshes calendar feeds)
- `0 */2 * * *` - **Auto-process** new recordings
- `0 9 * * 0` - **Weekly analysis** → SMS/email (Sundays)

## Quick Performance Check (NEW)

```bash
# Measure cold-import time for bot (should be < 200ms after the
# site_data push was moved into main()).
time python3 -c "import bot"

# Run unit test suite
python3 -m unittest discover -s tests
```

Before June 21, `import bot` took **2.2 seconds** because of a module-level
`write_site_data(push=True)` call. It's now **45ms** after the call was
moved into `main()`.

## Storage Alert Notifications

When disk usage exceeds thresholds, alerts are sent to:
- **Email**: billycarteriv@gmail.com
- **SMS**: 707-567-8495 (AT&T)

Thresholds:
- Warning: 80% disk usage
- Critical: 95% disk usage

## Daily Briefing (NEW: memory-aware)

Generate a morning briefing with queue status, storage, memory notes, and action items:

```bash
# Generate and save briefing (saves to briefings/daily/)
python3 scripts/daily_briefing.py

# Print to stdout only
python3 scripts/daily_briefing.py --print

# Save to custom path
python3 scripts/daily_briefing.py --output /path/to/briefing.md

# Generate AND send via SMS/email (also refreshes calendar feeds
# and attaches them as text/calendar MIME parts).
python3 scripts/daily_briefing.py --send
```

The briefing now retrieves memory through three topic queries
(recent clip performance, recent decisions, current focus) and surfaces
those as concrete action items instead of generic placeholders.

**Cron Schedule**: Runs automatically at 7:00 AM daily

**Briefing Includes**:
- Queue status (clips ready to post)
- Storage usage (recordings, clips, logs, disk %)
- Recent clips table
- Processing stats
- **Memory Notes** section (top retrieved memory hits with source + summary)
- **Memory-grounded Action Items** (deduped against universal reminders)
- SMS summary now includes `N memory notes` so you can see at a glance
  whether memory is shaping the briefing

## Weekly Analysis (NEW: memory-aware)

Generate Sunday-morning weekly insights with trigger breakdown, memory
highlights, and next-week recommendations:

```bash
# Print weekly report to stdout
python3 scripts/weekly_analysis.py --print

# Limit window to last N days
python3 scripts/weekly_analysis.py --days 14

# Generate AND send via SMS/email
python3 scripts/weekly_analysis.py --send
```

**Cron Schedule**: Runs automatically at 9:00 AM Sundays

**Report Includes**:
- Performance summary table (clips logged, total views, total likes, success rate)
- Top performing trigger types with avg views + success rate
- **🧠 Memory Highlights** section (top 8 retrieved hits per week)
- **Memory-grounded Recommendations** (max 2, deduped by title theme)
- SMS summary includes `N memory hits`

## Calendar Feeds (NEW)

Bolt writes four RFC 5545 (iCalendar) feeds to `data/calendar/`. Subscribe
from any calendar client (Apple Calendar, Google Calendar, Fantastical,
Outlook, Thunderbird) by opening the .ics file or hosting the directory
and subscribing via webcal:// URL.

```bash
# Refresh all four ICS feeds
python3 scripts/generate_calendar.py

# Dry-run (plan without writing)
python3 scripts/generate_calendar.py --dry-run

# Limit scheduled_posts.ics to next N days
python3 scripts/generate_calendar.py --days 14

# Custom output directory
python3 scripts/generate_calendar.py --output-dir /tmp/cal
```

**Feeds produced**:

| File | Content |
|------|---------|
| `daily_briefing.ics` | Recurring daily 7:00am event |
| `weekly_insights.ics` | Recurring Sunday 9:00am event |
| `peak_hours.ics` | Recurring daily 7:00-9:00pm posting window |
| `scheduled_posts.ics` | One VEVENT per queued post within lookahead window |

The 7am daily-briefing cron entry auto-refreshes these feeds and attaches
them to the briefing email — no separate cron needed.

## Thumbnail Generation (NEW)

Generate JPG thumbnails for clips and vertical_clips using ffmpeg:

```bash
# Generate thumbnails for default directories
python3 scripts/generate_thumbnails.py

# Generate for a single video
python3 scripts/generate_thumbnails.py clips/example.mp4

# Strategy options: smart (default), first, middle
python3 scripts/generate_thumbnails.py --strategy first
python3 scripts/generate_thumbnails.py --strategy middle

# Force regenerate even if .jpg is newer than .mp4
python3 scripts/generate_thumbnails.py --force

# Plan without invoking ffmpeg
python3 scripts/generate_thumbnails.py --dry-run

# Save run summary to data/thumbnail_state.json
python3 scripts/generate_thumbnails.py --save-state

# Custom output width (default: 1280px, height auto, aspect preserved)
python3 scripts/generate_thumbnails.py --width 1920
```

**Cron Schedule**: Runs automatically at 5:00 AM daily
**First run**: Generated 82 clip thumbs + 52 vertical thumbs in ~26 seconds.

## Decision Engine (NEW: think_and_propose bridge)

The decision engine now has a single-call bridge that ties memory
retrieval into proposal ranking without manual wiring:

```python
from modules.Think_Learn_Decide import ThinkLearnDecideEngine

engine = ThinkLearnDecideEngine()
candidates = [
    {"action": "queue_clip", "score": 82, "clip_path": "clips/ace.mp4"},
    {"action": "queue_clip", "score": 75, "clip_path": "clips/kill.mp4"},
]

# Old way (still works): think() → manually attach memory_influence → propose_actions()
# New way: think_and_propose() does it all
thought, proposals = engine.think_and_propose(
    {"game": "Marvel Rivals", "recording": "ace.mp4"},
    candidates,
)
# proposals[0] is the memory-aware top pick
```

If the caller already attached `memory_influence` to a candidate, the
bridge respects it. Old callers that call `propose_actions` directly are
unaffected.

### Twitch Integration Commands (NEW - July 1, 2026)

After streaming, auto-process new VODs:
```bash
# Check for new VODs to process
python3 scripts/auto_clip_twitch.py --list

# Process latest VOD
python3 scripts/auto_clip_twitch.py

# Process all new VODs
python3 scripts/auto_clip_twitch.py --all
```

Compile highlight reels for Twitch upload:
```bash
# Top 10 clips
python3 scripts/make_twitch_highlights.py

# Top 15 clips, filter by game
python3 scripts/make_twitch_highlights.py --count 15 --game "Hades"

# See ranking
python3 scripts/make_twitch_highlights.py --list
```

Upload to Twitch:
1. Go to https://dashboard.twitch.tv/u/ThunderstormBilly/content/video-producer
2. Click Upload
3. Select the file from `highlight_reels/`
4. Title it and set to Public

*Last updated: July 3, 2026 — Added Nexus Creator (Gemini-powered content consultant), content-type routing in process_recordings.py (--content-type gaming|review|skincare|tech), switched title generation from OpenAI to Gemini (free), rewired Skincare_Analyzer/AI_Analyzer/Amazon_Analyzer from placeholders to real Gemini intelligence, fixed ready_to_post.json key mismatch (items→clips), lowered highlight detection thresholds for off-stream recordings. Total test suite: 122 tests.*
