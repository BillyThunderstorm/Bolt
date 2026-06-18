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
python3 scripts/process_recordings.py
```

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
!queue                    - Show current clip queue status
!recall <topic>           - Search memory for topic
!clip                     - Confirm last highlight count
!highlights               - How many highlights this session
!uptime                   - How long the stream has been live
!postnow [clip_id]        - Approve and publish the next ready clip
!dontpost [clip_id] <reason>  - Hold a clip and save why
!stopclip                 - Reject the next auto-post
!skip [clip_id]           - Skip the next post
!rank                     - Show current clip ranking settings
!config                   - Show current config summary
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

## Title Generation

Monitor title generation results:

```bash
python3 scripts/monitor_title_results.py
```

Run the local title upgrade test helper:

```bash
python3 scripts/test_title_upgrade_10_clips.py
```

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
- `0 3 * * *` - **Storage optimization** (nightly, skips dedup for speed)
- `*/15 * * * *` - Site data push to websites (recommended)
- `0 7 * * *` - Daily briefing

## Storage Alert Notifications

When disk usage exceeds thresholds, alerts are sent to:
- **Email**: billycarteriv@gmail.com
- **SMS**: 707-567-8495 (AT&T)

Thresholds:
- Warning: 80% disk usage
- Critical: 95% disk usage

## Daily Briefing

Generate a morning briefing with queue status, storage, and action items:

```bash
# Generate and save briefing (saves to briefings/daily/)
python3 scripts/daily_briefing.py

# Print to stdout only
python3 scripts/daily_briefing.py --print

# Save to custom path
python3 scripts/daily_briefing.py --output /path/to/briefing.md
```

**Cron Schedule**: Runs automatically at 7:00 AM daily

**Briefing Includes**:
- Queue status (clips ready to post)
- Storage usage (recordings, clips, logs, disk %)
- Recent clips table
- Processing stats
- Dynamic action items
- Quick command references

*Last updated: June 15, 2026 - CRITICAL MAINTENANCE: Deleted recordings/clips >3 days old (freed 98GB total), disk now 86% (was 97%). **AUTOMATION ADDED**: Auto-process recordings every 2hrs, daily briefing → SMS/email, **weekly analysis Sundays at 9am**.*
