# Bolt Commands To Remember

This file keeps the current Bolt commands in one place. Updated after the
July 2026 color-coded folder reorganization.

## Top-Level Layout (Post-Reorg)

| Folder | Holds |
|--------|-------|
| `Core/` | Source code — `bot.py`, `config.json`, `requirements.txt`, `src/launch.py`, `modules/`, `data/` (memory index, decision model) |
| `App/` | Web/desktop app — `BoltApp/` (React/Vite), `assets/`, `brand/`, `overlay/`, `Bolt.app` |
| `Data/` | App data — `data/` (config, memory, content, projects, people), `tests/`, `archive/`, `conversations/` |
| `Docs/` | Documentation — `BOLT_COMMANDS.md`, `INDEX.md`, `PROJECT_STATUS.md`, `guides/`, `architecture/`, `planning/`, `reviews/`, `requirements/`, `upgrade/`, `site/`, `briefings/`, `reports/`, `Scratchpad_archive/` |
| `3rd_Party/` | Vendor + utilities — `colabs/scripts/` (Bolt's main scripts), `google-cloud-sdk/`, `llm/` (neural_model.py), `integrations/`, `vendor/`, `docker/`, `vod_samples/`, `my_agent/` |
| `media/` | Media — `clips/`, `output/` (videos, vertical variants) |
| `purple/`, `green/`, `dist/`, `logs/`, `New Folder With Items/` | Reserved / leftover from the reorg |

## Script Path Map

Most `scripts/` references in the previous version of this file are stale.
The scripts were re-homed under `3rd_Party/colabs/scripts/`. Old → new:

| Old (in this doc) | New |
|-------------------|-----|
| `scripts/verify.py` | `3rd_Party/colabs/scripts/verify.py` |
| `scripts/process_recordings.py` | `3rd_Party/colabs/scripts/process_recordings.py` |
| `scripts/nexus_advice.py` | `3rd_Party/colabs/scripts/nexus_advice.py` |
| `scripts/site_data_writer.py` | `3rd_Party/colabs/scripts/site_data_writer.py` |
| `scripts/daily_briefing.py` | `3rd_Party/colabs/scripts/daily_briefing.py` |
| `scripts/weekly_analysis.py` | `3rd_Party/colabs/scripts/weekly_analysis.py` |
| `scripts/generate_calendar.py` | `3rd_Party/colabs/scripts/generate_calendar.py` |
| `scripts/generate_thumbnails.py` | `3rd_Party/colabs/scripts/generate_thumbnails.py` |
| `scripts/auto_clip_twitch.py` | `3rd_Party/colabs/scripts/auto_clip_twitch.py` |
| `scripts/make_twitch_highlights.py` | `3rd_Party/colabs/scripts/make_twitch_highlights.py` |
| `scripts/refresh_memory_index.py` | `3rd_Party/colabs/scripts/refresh_memory_index.py` |
| `scripts/log_clip_performance.py` | `3rd_Party/colabs/scripts/log_clip_performance.py` |
| `scripts/clip_deduplicator.py` | `3rd_Party/colabs/scripts/clip_deduplicator.py` |
| `scripts/performance_baseline.py` | `3rd_Party/colabs/scripts/performance_baseline.py` |
| `scripts/monitor_title_results.py` | `3rd_Party/colabs/scripts/monitor_title_results.py` |
| `scripts/test_title_upgrade_10_clips.py` | `3rd_Party/colabs/scripts/test_title_upgrade_10_clips.py` |
| `scripts/get_twitch_token.py` | `3rd_Party/colabs/scripts/get_twitch_token.py` |
| `scripts/get_tiktok_token.py` | `3rd_Party/colabs/scripts/get_tiktok_token.py` |
| `scripts/maintenance/storage_optimization.sh` | `3rd_Party/colabs/scripts/maintenance/storage_optimization.sh` |
| `scripts/maintenance/media_rotation.sh` | `3rd_Party/colabs/scripts/maintenance/media_rotation.sh` |
| `scripts/monitoring/storage_monitor.sh` | `3rd_Party/colabs/scripts/monitoring/storage_monitor.sh` |
| `scripts/media_processing/compress_videos.sh` | `3rd_Party/colabs/scripts/media_processing/compress_videos.sh` |
| `scripts/reorganize_bolt.sh` | `3rd_Party/colabs/scripts/legacy/reorganize_bolt.sh` (archived; caused data loss 2026-07-07) |
| `scripts/REORGANIZE_MANUAL.md` | `3rd_Party/colabs/scripts/legacy/REORGANIZE_MANUAL.md` (archived) |

Top-level entry points that did NOT move, but now live one level deeper:

| Old | New |
|-----|-----|
| `bot.py` (root) | `Core/bot.py` |
| `launch.py` (root) | `Core/src/launch.py` |
| `config.json` (root) | `Core/config.json` |
| `requirements.txt` (root) | `Docs/requirements.txt` |
| `Bolt_brain.md` / `bolt_brain.md` (root) | `Core/bolt_brain.md` |
| `llm/neural_model.py` (root) | `3rd_Party/llm/neural_model.py` |
| `modules.X` (Python import) | `Core.modules.X` |
| `tests.test_X` (unittest path) | `Data.tests.test_X` |
| `data/` (root) | `Data/data/` |
| `clips/` (root) | `media/clips/` |
| `recordings/` (root) | `Data/archive/recordings` (archived; live folder was deleted during 2026-07-07 reorg) |
| `briefings/daily/` | `Docs/briefings/daily/` |
| `memory/` (root) | merged into `Data/data/` (memory content lives in `Data/data/content/`, hot notes in `Data/data/MEMORY.md`) |
| `docs/` (root) | `Docs/` (casing) |
| `vertical_clips/`, `vods/`, `highlight_reels/` | not present in the new layout (delete these references) |

> **PATH WARNING — read before running anything below.** The scripts listed
> here were moved into `3rd_Party/colabs/scripts/`, but most of them still
> compute `PROJECT_ROOT = Path(__file__).resolve().parents[1]` — which now
> resolves to `3rd_Party/colabs/`, not the repo root. (To reach the repo root
> from `3rd_Party/colabs/scripts/X.py` you need `parents[3]`, since
> `parents[0] = scripts/`, `parents[1] = colabs/`, `parents[2] = 3rd_Party/`,
> `parents[3] = repo root`.) They also still expect files at the old
> top-level layout (`bot.py` at root, `modules/` at root, `recordings/`,
> `clips/`, `vertical_clips/`, `data/`, `memory/` at root). Running them
> as-is will fail. See the **Stale-Internal-Paths** section at the bottom
> of this file for the full list of affected scripts and the follow-up fix.

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
python3 -m pip install -r Docs/requirements.txt
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

Run the project verifier. **NOTE: this script has stale internal paths from
before the reorg — see Stale-Internal-Paths at the bottom.**

```bash
# Expected (post-reorg) location, but it currently expects the old layout:
python3 3rd_Party/colabs/scripts/verify.py
```

Run the unit tests (these paths are correct — tests live at `Data/tests/`):

```bash
python3 -m unittest discover -s Data/tests -t .
```

Run focused tests:

```bash
python3 -m unittest Data.tests.test_memory_index
```

```bash
python3 -m unittest Data.tests.test_think_learn_decide
```

```bash
python3 -m unittest Data.tests.test_daily_briefing
```

```bash
python3 -m unittest Data.tests.test_weekly_analysis
```

```bash
python3 -m unittest Data.tests.test_generate_thumbnails
```

```bash
python3 -m unittest Data.tests.test_generate_calendar
```

```bash
python3 -m unittest Data.tests.test_creator_lanes_reachable
```

```bash
python3 -m unittest Data.tests.test_lazy_imports
```

Run Python compile checks:

```bash
python3 -m compileall Core/bot.py Core/src/launch.py Core/modules 3rd_Party/colabs/scripts Data/tests
```

## Launch Bolt

`launch.py` moved to `Core/src/`. Run from the repo root so its imports resolve:

```bash
python3 -m Core.src.launch
# equivalent to:
PYTHONPATH=Core python3 Core/src/launch.py
```

`launch.py` accepts a `process` subcommand for one-shot pipeline runs:

```bash
python3 -m Core.src.launch process
```

Run the bot directly:

```bash
python3 Core/bot.py
```

## Process Recordings

The process script lives at `3rd_Party/colabs/scripts/process_recordings.py`
but **has stale internal paths** (see bottom of this file). The following
commands are the intended ones once the script is patched:

```bash
# Process all recordings (gaming mode — default)
python3 3rd_Party/colabs/scripts/process_recordings.py

# Process latest recording only
python3 3rd_Party/colabs/scripts/process_recordings.py latest

# Process specific recording by index
python3 3rd_Party/colabs/scripts/process_recordings.py 3

# List recordings without processing
python3 3rd_Party/colabs/scripts/process_recordings.py list
```

### Content-Type Routing (NEW - July 3, 2026)

Bolt supports different content types with Gemini-optimized captions:

```bash
# Gaming clips (default — uses template titles)
python3 3rd_Party/colabs/scripts/process_recordings.py --content-type gaming

# Product review content (Nexus/Gemini optimizes captions)
python3 3rd_Party/colabs/scripts/process_recordings.py --content-type review

# Skincare/beauty content (Nexus/Gemini optimizes captions)
python3 3rd_Party/colabs/scripts/process_recordings.py --content-type skincare

# Tech content (Nexus/Gemini optimizes captions)
python3 3rd_Party/colabs/scripts/process_recordings.py --content-type tech

# Short form
python3 3rd_Party/colabs/scripts/process_recordings.py latest -t review
```

**How it works:**
- `gaming` = local template titles (fast, free, no API calls)
- `review` / `skincare` / `tech` = Nexus Creator generates optimized captions via Gemini (free)
- All modes run the full pipeline: detect highlights → cut clips → titles → subtitles → rank → format 9:16 → queue

**Note on output paths** (post-reorg): the script's internal `clips/` and
`vertical_clips/` defaults no longer exist at the repo root. After the script
is patched, clips will land in `media/clips/` and `media/vertical_clips/`
(vertical_clips does not exist yet — create it before first use, or update
`Core/config.json` to point `clips_folder`/`vertical_clips_folder` at your
real location).

## Chat, Voice, And Local Controls

### Bolt Chat Module
Run Bolt chat locally. Modules moved to `Core/modules/`:

```bash
PYTHONPATH=Core python3 -m modules.Bolt_Chat
```

Run with voice responses enabled (speaks replies aloud via ElevenLabs):

```bash
PYTHONPATH=Core python3 -m modules.Bolt_Chat --voice
```

### Voice Conversation
Start a back-and-forth voice conversation with Bolt. Listens via mic,
transcribes with Whisper, generates personality-driven responses, speaks
them aloud, and remembers the thread:

```bash
PYTHONPATH=Core python3 -m modules.Bolt_Conversation              # voice chat loop
PYTHONPATH=Core python3 -m modules.Bolt_Conversation --text       # type instead of speak
PYTHONPATH=Core python3 -m modules.Bolt_Conversation --once "What should I post today?"
PYTHONPATH=Core python3 -m modules.Bolt_Conversation --status     # check setup status
PYTHONPATH=Core python3 -m modules.Bolt_Conversation --clear      # clear conversation history
```

Conversation history is saved to `Data/conversations/voice_history.json`.

### Voice Commands
Test voice:

```bash
PYTHONPATH=Core python3 -m modules.Bolt_Voice "say this out loud"
```

List available voice event lines:

```bash
PYTHONPATH=Core python3 -m modules.Bolt_Voice --list-events
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
Refresh the local searchable memory index after editing memory files.
The memory index lives in `Data/data/memory_index.json` and `Core/data/memory_index.json`.

```bash
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/refresh_memory_index.py
```

### Search Memory
Search memory through the index module:

```bash
PYTHONPATH=Core:3rd_Party/colabs python3 -m modules.Memory_Index --refresh "Amazon Influencer storefront product testing"
```

Search memory through Bolt memory (the higher-level wrapper):

```bash
PYTHONPATH=Core:3rd_Party/colabs python3 -m modules.Bolt_Memory --search "beauty skincare routine product test results"
```

## Content Results And Learning

### Log Performance
List logged performance outcomes:

```bash
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/log_clip_performance.py --list
```

Log a posted clip result (note: `clips/` is now under `media/`):

```bash
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/log_clip_performance.py --clip media/clips/example.mp4 --platform TikTok --note "Strong opening hook"
```

### Multi-Platform Posting
Build a no-cost posting packet:

```bash
PYTHONPATH=Core:3rd_Party/colabs python3 -m modules.Multi_Publisher media/clips/example.mp4 "Working title" --hashtags gaming ai
```

## Nexus Creator — AI Content Strategy Consultant (NEW - July 3, 2026)

Nexus is Bolt's strategic brain, powered by Gemini (free tier). It provides
actionable advice on hooks, monetization, engagement, and content strategy.

```bash
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/nexus_advice.py "How should I title my Hades 2 clips?"

# Get next content recommendations based on performance data
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/nexus_advice.py --next

# Optimize a caption for a specific clip
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/nexus_advice.py --caption "clip.mp4" --desc "Epic boss fight" -p tiktok

# Provide context with your question
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/nexus_advice.py "skincare review strategy" --context "17 clips posted, low views"

# Use a different Gemini model
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/nexus_advice.py "topic" --model gemini-2.5-pro
```

**Python API:**
```python
from Core.modules.Nexus_Creator import NexusCreator
# or, with the right PYTHONPATH:
# from modules.Nexus_Creator import NexusCreator

nexus = NexusCreator()
advice = nexus.consult(topic="Hades 2 strategy", context="2,393 views across 5 posts")
next_content = nexus.suggest_next_content(performance_data={...})
caption = nexus.optimize_caption(clip_name="clip.mp4", clip_description="...", platform="tiktok")
```

**Logs:** All advice saved to `Data/data/nexus_advice.jsonl`
**API Key:** `GEMINI_API_KEY` in `.env` (get from Google AI Studios — free)

## Title Generation — Now Using Gemini (UPDATED - July 3, 2026)

Title generation switched from OpenAI (paid, quota exhausted) to Gemini (free):

```bash
# Monitor title generation results
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/monitor_title_results.py

# Run title upgrade test
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/test_title_upgrade_10_clips.py
```

**What changed:**
- `Core/modules/Title_Generator.py` now calls Gemini (gemini-2.5-flash) by default
- Falls back to OpenAI only if Gemini key is missing AND OpenAI has credits
- Falls back to local templates if both fail
- Config: `use_ai_titles: true`, `title_generation.enabled: true` (in `Data/data/config.json`)
- Set `USE_GEMINI_TITLES=false` in `.env` to force OpenAI

## Skincare / Product Review / Tech Analysis (NEW - July 3, 2026)

Three formerly-placeholder modules are now wired to real Gemini intelligence.
All three live in `Core/modules/`:

### Skincare Analyzer
```bash
PYTHONPATH=Core python3 -c "
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
PYTHONPATH=Core python3 -c "
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
PYTHONPATH=Core python3 -c "
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
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/get_twitch_token.py
```

Generate or refresh TikTok auth:

```bash
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/get_tiktok_token.py
```

## AI Learning

Run the cleaned neural-network learning example. `llm/` moved to
`3rd_Party/llm/`:

```bash
PYTHONPATH=3rd_Party/llm python3 3rd_Party/llm/neural_model.py
```

## Websites

Bolt runs three websites and an API on Cloudflare:

| Site | URL | Description |
|------|-----|-------------|
| **Bolt Command Center** | bolt.billythunderstorm.us | Terminal, clip queue, briefing, peak hours |
| **Billy Thunderstorm** | billythunderstorm.us | Creator portfolio, milestones, storefront, socials |
| **Live Status** | billythunderstorm.live | Stream status, peak hours, social links |
| **API Worker** | api.billythunderstorm.us | JSON endpoints for live data |

### Update Site Data

After each Bolt pipeline run, push fresh data to the websites. The site
data file is now at `Data/data/site-data.json`:

```bash
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/site_data_writer.py --push
```

Or add to `Core/bot.py` as an import:

```python
from scripts.site_data_writer import write_site_data
write_site_data(push=True)
```

### Set Up Cron for Auto-Updates

```bash
crontab -e
# Add this line for every 15 minutes:
*/15 * * * * cd /Users/carter/developer/Bolt && PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/site_data_writer.py --push
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
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/auto_clip_twitch.py --list

# Process the latest unprocessed VOD (downloads → clip pipeline → post queue)
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/auto_clip_twitch.py

# Process all unprocessed VODs
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/auto_clip_twitch.py --all

# Process a specific VOD by ID
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/auto_clip_twitch.py --vod 2784630508

# Also create Twitch clips via API (requires user OAuth - not yet configured)
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/auto_clip_twitch.py --twitch-clips
```

**What it does:**
- Downloads VODs from Twitch using yt-dlp
- Runs each VOD through Bolt's full clip pipeline (detect highlights → cut → title → format 9:16 → queue)
- Tracks processed VODs in `Data/data/twitch_vods_processed.json` to avoid reprocessing
- Downloads to `3rd_Party/vod_samples/` (was `vods/` at root; that path no longer exists)

**Twitch credentials (in .env):**
- `TWITCH_CLIENT_ID` — App client ID from dev.twitch.tv
- `TWITCH_CLIENT_SECRET` — App secret (rotated July 1, 2026)
- `TWITCH_CHANNEL` — ThunderstormBilly (user ID: 441598765)

## Twitch Highlight Reel Compiler (NEW - July 1, 2026)

Compile your best clips into a highlight VOD for uploading to Twitch.
Output goes to a directory you specify (`--output`); there is no longer a
dedicated `highlight_reels/` folder:

```bash
# Compile top 10 clips into a highlight reel (writes to ./highlight_reel_<date>.mp4)
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/make_twitch_highlights.py

# Compile top 15 clips
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/make_twitch_highlights.py --count 15

# Filter clips by game keyword
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/make_twitch_highlights.py --game "Hades"

# List top clips by score
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/make_twitch_highlights.py --list

# Custom output filename (and a path under media/ keeps it tidy)
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/make_twitch_highlights.py --output media/highlight_reel.mp4
```

**Output:** an MP4 in the location you pass to `--output`
- 1920x1080 H.264 with AAC audio
- Title card intro + clips concatenated
- Upload to Twitch via Video Producer: https://dashboard.twitch.tv/u/ThunderstormBilly/content/video-producer

## Storage Management & Monitoring

**Current Status (post-2026-07-07 reorg)**:
- Live `recordings/`, `clips/`, and `vertical_clips/` at the repo root no longer exist.
- Live recordings were deleted by the reorg on 2026-07-07 (see warning in memory).
- Archived recordings live in `Data/archive/recordings/`; archived clips in `Data/archive/clips/`.
- Disk usage is reported by `scripts/monitoring/storage_monitor.sh`; check
  `logs/storage_monitor.log` for the latest snapshot.

### Run Storage Optimization
```bash
# Dry run to see what would be done
bash 3rd_Party/colabs/scripts/maintenance/storage_optimization.sh --dry-run

# Run actual optimization (use with caution)
bash 3rd_Party/colabs/scripts/maintenance/storage_optimization.sh --skip-dedup

# Customize limits
bash 3rd_Party/colabs/scripts/maintenance/storage_optimization.sh --recordings-gb 40 --clips-gb 0.5
```

### Individual Maintenance Scripts
```bash
# Media rotation (size-based, runs every 6 hours via cron)
bash 3rd_Party/colabs/scripts/maintenance/media_rotation.sh

# Storage monitoring with alerts (runs every 3 hours via cron)
bash 3rd_Party/colabs/scripts/monitoring/storage_monitor.sh

# Video compression (runs every 30 minutes via cron)
bash 3rd_Party/colabs/scripts/media_processing/compress_videos.sh
```

### Duplicate Detection
```bash
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/clip_deduplicator.py

# Dry run mode (no database changes)
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/clip_deduplicator.py --dry-run

# Check a single file
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/clip_deduplicator.py --check media/clips/example.mp4

# Clear the hash database
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/clip_deduplicator.py --clear-db
```

### Performance Baseline
```bash
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/performance_baseline.py
```

## Storage Alert Configuration

Configure email and SMS alerts:

```bash
# Edit the configuration file
nano Data/data/configs/storage_alerts.env
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
open Docs/BOLT_COMMANDS.md
open Docs/INDEX.md
open Docs/PROJECT_STATUS.md
open Data/data/content/full-creator-vision.md
open Docs/NEXT_UPGRADE_STEPS.md
open Docs/OPTIMIZATION_ROADMAP.md
```

## Git Checks

```bash
git status --short
```

```bash
git diff --stat
```

```bash
git diff -- README.md Docs/ Data/ Core/ 3rd_Party/
```

## User Interfaces Summary

| Interface | Command/Path | Description |
|-----------|--------------|-------------|
| **CLI Launcher** | `python3 -m Core.src.launch` | Main entry point for Bolt |
| **Bot Runtime** | `python3 Core/bot.py` | Direct bot execution |
| **Chat Module** | `PYTHONPATH=Core python3 -m modules.Bolt_Chat` | Local chat testing |
| **Chat + Voice** | `PYTHONPATH=Core python3 -m modules.Bolt_Chat --voice` | Chat with spoken replies |
| **Voice Conversation** | `PYTHONPATH=Core python3 -m modules.Bolt_Conversation` | Hands-free back-and-forth voice chat |
| **Voice Module** | `PYTHONPATH=Core python3 -m modules.Bolt_Voice "text"` | TTS voice output |
| **Memory Search** | `PYTHONPATH=Core python3 -m modules.Memory_Index` | Searchable memory index |
| **Memory Browser** | `PYTHONPATH=Core python3 -m modules.Bolt_Memory` | Full memory operations |
| **Checkup Dashboard** | `Docs/Bolt_Checkup.html` | Live status dashboard |
| **Duplicate Scanner** | `python3 3rd_Party/colabs/scripts/clip_deduplicator.py` | Hash-based dedup |
| **Performance Baseline** | `python3 3rd_Party/colabs/scripts/performance_baseline.py` | Benchmark metrics |
| **Storage Monitor** | `bash 3rd_Party/colabs/scripts/monitoring/storage_monitor.sh` | Disk usage + alerts |
| **Video Compressor** | `bash 3rd_Party/colabs/scripts/media_processing/compress_videos.sh` | HandBrake compression |
| **Media Rotator** | `bash 3rd_Party/colabs/scripts/maintenance/media_rotation.sh` | Auto-archival |
| **Site Data Writer** | `python3 3rd_Party/colabs/scripts/site_data_writer.py --push` | Push live data to websites |
| **Daily Briefing** | `python3 3rd_Party/colabs/scripts/daily_briefing.py [--print\|--send]` | Memory-aware morning briefing |
| **Weekly Analysis** | `python3 3rd_Party/colabs/scripts/weekly_analysis.py [--print\|--send]` | Memory-aware weekly insights |
| **Calendar Feeds** | `python3 3rd_Party/colabs/scripts/generate_calendar.py` | RFC 5545 ICS files for calendar subscribe |
| **Thumbnails** | `python3 3rd_Party/colabs/scripts/generate_thumbnails.py` | JPG thumbnails for clips via ffmpeg |
| **Process Recordings** | `python3 3rd_Party/colabs/scripts/process_recordings.py` | Process recordings → clips → queue |
| **Nexus Creator** | `python3 3rd_Party/colabs/scripts/nexus_advice.py "topic"` | AI content strategy (Gemini) |
| **Twitch Auto-Clip** | `python3 3rd_Party/colabs/scripts/auto_clip_twitch.py` | Download VODs → clip pipeline |
| **Highlight Reel** | `python3 3rd_Party/colabs/scripts/make_twitch_highlights.py` | Compile best clips into VOD |
| **Bolt Website** | bolt.billythunderstorm.us | Command center |
| **Billy Website** | billythunderstorm.us | Creator portfolio |
| **Live Status** | billythunderstorm.live | Stream status page |

## Creator Domain Docs

```bash
open Docs/requirements/creator-domains-requirements.md      # system requirements
open .github/instructions/creator-domains.instructions.md    # behavior instructions
open Data/data/content/content-creation.md                   # content domain
open Data/data/content/assistant-productivity.md             # productivity domain
open Data/data/content/game-testing.md                       # game/tech review domain
open Data/data/content/live-streaming.md                     # streaming domain
open Data/data/content/social-media-management.md            # social domain
```

## Cron Jobs (Automated)

```bash
# View active cron jobs
crontab -l
```

Current schedule (each entry now needs the right PYTHONPATH / `cd` since
scripts moved):
- `*/30 * * * *` - Video compression (HandBrakeCLI)
- `0 */3 * * *` - Storage monitoring with alerts
- `0 */6 * * *` - Media rotation/archival
- `0 3 * * *` - Storage optimization (nightly, skips dedup for speed)
- `0 5 * * *` - **Thumbnail refresh** for `media/clips/` and `media/vertical_clips/` (NEW: vertical_clips must be created first)
- `*/15 * * * *` - Site data push to websites (recommended)
- `0 7 * * *` - **Daily briefing** → SMS/email (auto-refreshes calendar feeds)
- `0 */2 * * *` - **Auto-process** new recordings
- `0 9 * * 0` - **Weekly analysis** → SMS/email (Sundays)

Suggested pattern for the post-reorg cron entries:
```bash
*/15 * * * * cd /Users/carter/developer/Bolt && PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/site_data_writer.py --push
```

## Quick Performance Check

```bash
# Measure cold-import time for bot (should be < 200ms after the
# site_data push was moved into main()).
time PYTHONPATH=Core python3 -c "import sys; sys.path.insert(0, 'Core'); import bot"

# Run unit test suite
python3 -m unittest discover -s Data/tests -t .
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

## Daily Briefing (memory-aware)

Generate a morning briefing with queue status, storage, memory notes, and action items.
**The daily_briefing script has stale internal paths — see the warning below.**

```bash
# Generate and save briefing to Docs/briefings/daily/
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/daily_briefing.py

# Print to stdout only
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/daily_briefing.py --print

# Save to custom path
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/daily_briefing.py --output /path/to/briefing.md

# Generate AND send via SMS/email (also refreshes calendar feeds
# and attaches them as text/calendar MIME parts).
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/daily_briefing.py --send
```

The briefing now retrieves memory through three topic queries
(recent clip performance, recent decisions, current focus) and surfaces
those as concrete action items instead of generic placeholders.

**Cron Schedule**: Runs automatically at 7:00 AM daily (cron entry must be updated to use the new path + PYTHONPATH)

**Briefing Includes**:
- Queue status (clips ready to post)
- Storage usage (recordings, clips, logs, disk %)
- Recent clips table
- Processing stats
- **Memory Notes** section (top retrieved memory hits with source + summary)
- **Memory-grounded Action Items** (deduped against universal reminders)
- SMS summary now includes `N memory notes` so you can see at a glance
  whether memory is shaping the briefing

## Weekly Analysis (memory-aware)

Generate Sunday-morning weekly insights with trigger breakdown, memory
highlights, and next-week recommendations:

```bash
# Print weekly report to stdout
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/weekly_analysis.py --print

# Limit window to last N days
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/weekly_analysis.py --days 14

# Generate AND send via SMS/email
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/weekly_analysis.py --send
```

**Cron Schedule**: Runs automatically at 9:00 AM Sundays

**Report Includes**:
- Performance summary table (clips logged, total views, total likes, success rate)
- Top performing trigger types with avg views + success rate
- **🧠 Memory Highlights** section (top 8 retrieved hits per week)
- **Memory-grounded Recommendations** (max 2, deduped by title theme)
- SMS summary includes `N memory hits`

## Calendar Feeds

Bolt writes four RFC 5545 (iCalendar) feeds to `Data/data/calendar/`. Subscribe
from any calendar client (Apple Calendar, Google Calendar, Fantastical,
Outlook, Thunderbird) by opening the .ics file or hosting the directory
and subscribing via webcal:// URL.

```bash
# Refresh all four ICS feeds
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/generate_calendar.py

# Dry-run (plan without writing)
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/generate_calendar.py --dry-run

# Limit scheduled_posts.ics to next N days
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/generate_calendar.py --days 14

# Custom output directory
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/generate_calendar.py --output-dir /tmp/cal
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

## Thumbnail Generation

Generate JPG thumbnails for `media/clips/` and `media/vertical_clips/` using
ffmpeg. **The script has stale internal paths — see warning below.**

```bash
# Generate thumbnails for default directories
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/generate_thumbnails.py

# Generate for a single video
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/generate_thumbnails.py media/clips/example.mp4

# Strategy options: smart (default), first, middle
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/generate_thumbnails.py --strategy first
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/generate_thumbnails.py --strategy middle

# Force regenerate even if .jpg is newer than .mp4
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/generate_thumbnails.py --force

# Plan without invoking ffmpeg
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/generate_thumbnails.py --dry-run

# Save run summary to Data/data/thumbnail_state.json
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/generate_thumbnails.py --save-state

# Custom output width (default: 1280px, height auto, aspect preserved)
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/generate_thumbnails.py --width 1920
```

**Cron Schedule**: Runs automatically at 5:00 AM daily (cron entry needs path + PYTHONPATH update)
**First run**: Generated 82 clip thumbs + 52 vertical thumbs in ~26 seconds.

## Decision Engine (think_and_propose bridge)

The decision engine now has a single-call bridge that ties memory
retrieval into proposal ranking without manual wiring. Module lives at
`Core/modules/Think_Learn_Decide.py`:

```python
import sys
sys.path.insert(0, "Core")
from modules.Think_Learn_Decide import ThinkLearnDecideEngine

engine = ThinkLearnDecideEngine()
candidates = [
    {"action": "queue_clip", "score": 82, "clip_path": "media/clips/ace.mp4"},
    {"action": "queue_clip", "score": 75, "clip_path": "media/clips/kill.mp4"},
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

### Twitch Integration Commands

After streaming, auto-process new VODs:
```bash
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/auto_clip_twitch.py --list
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/auto_clip_twitch.py
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/auto_clip_twitch.py --all
```

Compile highlight reels for Twitch upload:
```bash
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/make_twitch_highlights.py
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/make_twitch_highlights.py --count 15 --game "Hades"
PYTHONPATH=3rd_Party/colabs python3 3rd_Party/colabs/scripts/make_twitch_highlights.py --list
```

Upload to Twitch:
1. Go to https://dashboard.twitch.tv/u/ThunderstormBilly/content/video-producer
2. Click Upload
3. Select the file (e.g. `media/highlight_reel.mp4`)
4. Title it and set to Public

---

## Stale-Internal-Paths Status (as of July 7, 2026)

The scripts in `3rd_Party/colabs/scripts/` were moved on disk during the
color-coded folder reorg. Most used `Path(__file__).resolve().parents[1]`
(or `.parent.parent`), which now resolves to `3rd_Party/colabs/` rather
than the repo root, and many also hardcoded old top-level subpath strings
(`data/`, `clips/`, `recordings/`, `bot.py`, `config.json`, etc.).

A `3rd_Party/colabs/scripts/_paths.py` helper module exists that computes
the correct `REPO_ROOT = parents[3]` and exports every standard subpath
constant. Scripts that import from `_paths` automatically resolve
`REPO_ROOT`, `DATA_DIR`, `CLIPS_DIR`, `VERTICAL_CLIPS_DIR`, `MEDIA_DIR`,
`LOGS_DIR`, `DAILY_BRIEFINGS_DIR`, `DOCS_DIR`, `ARCHIVE_DIR`, `RECORDINGS_DIR`,
`CONFIG_FILE`, `BOT_FILE`, `BOLT_BRAIN_FILE`, `VOD_SAMPLES_DIR`, etc.

**Status (post-fix):**

| Script | Fixed? | How |
|--------|--------|-----|
| `verify.py` | ✓ | Uses `_paths`, required_files/dirs list rewritten for new layout. PASSes. |
| `process_recordings.py` | ✓ | Uses `_paths`. `--help` and `--list` work. |
| `auto_clip_twitch.py` | ✓ | Uses `_paths`. `--list` works. |
| `make_twitch_highlights.py` | ✓ | Uses `_paths`. `--list` works. |
| `daily_briefing.py` | ✓ | Uses `_paths`. `--help` works. |
| `generate_thumbnails.py` | ✓ | Uses `_paths`. `--help` works. |
| `site_data_writer.py` | ✓ | Uses `_paths`. Wrote `Data/data/site-data.json` successfully. |
| `weekly_analysis.py` | ✓ | Uses `_paths`. `--help` works. |
| `Watcher.py`, `Filter_Backlog.py`, `bot_with_twitch.py`, `make_highlights.py`, `build_env.py`, `load_bolt_personality.py`, `setup_env.py`, `autostart.py`, `get_twitch_token.py`, `get_twitch_bot_token.py`, `update_game_from_obs.py`, `start_obs_game_tracker.py` | not yet | All use CWD-relative or single-level `parent.parent` patterns; safe to run from repo root but not from arbitrary CWDs. |
| `nexus_advice.py`, `refresh_memory_index.py`, `generate_calendar.py`, `log_clip_performance.py`, `clip_deduplicator.py`, `performance_baseline.py`, `monitor_title_results.py`, `test_title_upgrade_10_clips.py`, `get_tiktok_token.py`, `send_notification.py`, `twitch_vod_downloader.py` | not yet | These compute `ROOT = parents[1]` and walk old top-level paths. Will fail when run as `python3 3rd_Party/colabs/scripts/X.py`. |

**If you add or update a script in `3rd_Party/colabs/scripts/`**, import
`REPO_ROOT` and the standard subpaths from `_paths` rather than computing
`PROJECT_ROOT` locally:

```python
from _paths import (  # noqa: E402
    REPO_ROOT, DATA_DIR, CLIPS_DIR, LOGS_DIR, MEDIA_DIR,
    DAILY_BRIEFINGS_DIR, CONFIG_FILE, BOT_FILE,
)

# Make _paths importable in BOTH direct invocation and
# `from scripts import X` (tests).
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
```

The other post-reorg cleanups (test import shims, source-file path
constants, syntax repair from a bad move) are described in the
`post-migration-code-cleanup` skill — load it before doing this work.

---

*Last updated: July 7, 2026 — Path map rewritten after the color-coded folder
reorg. Top-level layout: Core / App / Data / Docs / 3rd_Party / media.
Scripts moved from `scripts/` to `3rd_Party/colabs/scripts/`. Entries at the
repo root (`bot.py`, `launch.py`, `config.json`, `modules/`, `data/`,
`clips/`, `recordings/`) now live one level deeper. `Docs/Scratchpad:`
renamed to `Docs/Scratchpad_archive/`. `Docs/reorganize_bolt.sh` and
`Docs/REORGANIZE_MANUAL.md` moved to `3rd_Party/colabs/scripts/legacy/`.
A `_paths.py` helper was added to the scripts folder and 8 of the scripts
were updated to use it. Two syntax bugs in `Core/src/launch.py` (indented
code at column 0 inside a `try:` block and inside a `notify(...)` call)
were repaired, and `launch.py` now sets up sys.path and uses
`Core/bot.py` for the handoff. **Full test suite: 215 tests, 0 failures.**
