# Bolt Commands To Remember

This file keeps the current Bolt commands in one place.
**Last major update:** Manager M9–M13 + ML ranking (recency-weighted learned model) — 2026-07-19.
**Previous milestone:** Content Manager OS for William (game/tech priority) — 2026-07-09.

## Color / Label Map (find things fast)

| Label | Color cue | Where it lives | What it's for |
|-------|-----------|----------------|---------------|
| 🟡 **CORE** | yellow / code | `Core/` | Source: bot, modules, config, brain |
| 🔵 **DATA** | blue / memory | `Data/data/` | Catalog, storefront, sponsors, memory |
| 🟢 **DOCS** | green / guides | `Docs/` | Commands, status, briefings, reviews |
| 🟣 **APP** | purple / UI | `App/` | Desktop/web UI, brand, overlays |
| 🟠 **MEDIA** | orange / clips | `media/` | Recordings, clips, vertical exports |
| ⚪ **SCRIPTS** | gray / tools | `scripts/` | Utility scripts (use `bolt` wrapper) |
| 🔴 **MANAGER** | red / daily use | `Core/modules/Content_Manager.py` | Creator manager commands below |

### Daily-use files (bookmark these)

| Label | Path |
|-------|------|
| 🔴 Commands (this file) | `Docs/BOLT_COMMANDS.md` |
| 🟢 Progress status | `Docs/PROJECT_STATUS.md` |
| 🟢 Upgrade tracker | `Docs/NEXT_UPGRADE_STEPS.md` |
| 🟢 Doc index | `Docs/INDEX.md` |
| 🔵 Catalog | `Data/data/content/catalog.json` |
| 🔵 Storefront | `Data/data/content/storefront.json` |
| 🔵 Sponsors | `Data/data/content/sponsors.json` |
| 🔵 Social | `Data/data/content/social_connections.json` |
| 🔵 Business playbook | `Data/data/business/business-playbook.md` |
| 🔵 Bolt advancement | `Data/data/business/bolt-advancement.md` |
| 🟢 Morning briefing | `Docs/briefings/daily/latest_morning.md` |
| 🟡 Manager module | `Core/modules/Content_Manager.py` |
| 🟡 Brain / creator profile | `Core/bolt_brain.md` |
| 🟡 CLI entry | `bin/bolt` |

## Top-Level Layout (Post-Reorg)

| Folder | Label | Holds |
|--------|-------|-------|
| `Core/` | 🟡 CORE | Source — `bot.py`, `config.json`, `src/launch.py`, `modules/`, brain |
| `App/` | 🟣 APP | Web/desktop — `BoltApp/`, `assets/`, `brand/`, `overlay/`, `Bolt.app` |
| `Data/` | 🔵 DATA | Catalog, storefront, sponsors, memory, tests, conversations |
| `Docs/` | 🟢 DOCS | Commands, status, guides, briefings, reviews, requirements |
| `3rd_Party/` | ⚪ SCRIPTS | Scripts, LLM tools, docker, vendor |
| `media/` | 🟠 MEDIA | Clips, recordings, vertical exports |
| `bin/` | 🔴 MANAGER | `bolt` CLI wrapper |

## Script Path Map

Most `scripts/` references in the previous version of this file are stale.
The scripts were re-homed under `scripts/`. Old → new:

| Old (in this doc) | New |
|-------------------|-----|
| `scripts/verify.py` | `scripts/verify.py` |
| `scripts/process_recordings.py` | `scripts/process_recordings.py` |
| `scripts/nexus_advice.py` | `scripts/nexus_advice.py` |
| `scripts/site_data_writer.py` | `scripts/site_data_writer.py` |
| `scripts/daily_briefing.py` | `scripts/daily_briefing.py` |
| `scripts/weekly_analysis.py` | `scripts/weekly_analysis.py` |
| `scripts/generate_calendar.py` | `scripts/generate_calendar.py` |
| `scripts/generate_thumbnails.py` | `scripts/generate_thumbnails.py` |
| `scripts/auto_clip_twitch.py` | `scripts/auto_clip_twitch.py` |
| `scripts/make_twitch_highlights.py` | `scripts/make_twitch_highlights.py` |
| `scripts/refresh_memory_index.py` | `scripts/refresh_memory_index.py` |
| `scripts/log_clip_performance.py` | `scripts/log_clip_performance.py` |
| `scripts/clip_deduplicator.py` | `scripts/clip_deduplicator.py` |
| `scripts/performance_baseline.py` | `scripts/performance_baseline.py` |
| `scripts/monitor_title_results.py` | `scripts/monitor_title_results.py` |
| `scripts/test_title_upgrade_10_clips.py` | `scripts/test_title_upgrade_10_clips.py` |
| `scripts/get_twitch_token.py` | `scripts/get_twitch_token.py` |
| `scripts/get_tiktok_token.py` | `scripts/get_tiktok_token.py` |
| `scripts/maintenance/storage_optimization.sh` | `scripts/maintenance/storage_optimization.sh` |
| `scripts/maintenance/media_rotation.sh` | `scripts/maintenance/media_rotation.sh` |
| `scripts/monitoring/storage_monitor.sh` | `scripts/monitoring/storage_monitor.sh` |
| `scripts/media_processing/compress_videos.sh` | `scripts/media_processing/compress_videos.sh` |
| `scripts/reorganize_bolt.sh` | `scripts/legacy/reorganize_bolt.sh` (archived; caused data loss 2026-07-07) |
| `scripts/REORGANIZE_MANUAL.md` | `scripts/legacy/REORGANIZE_MANUAL.md` (archived) |

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
> here were moved into `scripts/`, but most of them still
> compute `PROJECT_ROOT = Path(__file__).resolve().parents[1]` — which now
> resolves to `scripts/`, not the repo root. (To reach the repo root
> from `scripts/X.py` you need `parents[3]`, since
> `parents[0] = scripts/`, `parents[1] = colabs/`, `parents[2] = 3rd_Party/`,
> `parents[3] = repo root`.) They also still expect files at the old
> top-level layout (`bot.py` at root, `modules/` at root, `recordings/`,
|> `clips/`, `vertical_clips/`, `data/`, `memory/` at root). Running them
|> as-is will fail. See the **Stale-Internal-Paths** section at the bottom
|> of this file for the full list of affected scripts and the follow-up fix.
|
|## Content Manager (William's creator OS)

*Last major update: M9–M13 + ML ranking all wired up (July 19, 2026).*

### Daily use (use these every day)

```bash
bolt morning                 # Good Morning Bolt — spoken daily briefing
bolt manage add "Headset" --lane tech --status testing
bolt manage note "Headset" --day 1 --text "Mic is clear, clamp is tight"
bolt manage draft "Headset" --format short
bolt manage next
bolt manage list --lane game
bolt manage status           # one-screen snapshot of M-tier work
bolt store add --name "Mouse" --asin B0XXXX --category tech
bolt store feature-next
bolt social status
bolt social package "Headset" --platforms tiktok,youtube,x
bolt social queue            # items await approval; nothing auto-posts
bolt sponsors find --lane game
bolt sponsors pitch "Razer"
bolt sponsors next
bolt business lesson
bolt advance next
```

### M9–M13: real ASINs, shipped posts, multi-platform, sponsor research

```bash
# M9 — Real ASINs on owned gear
bolt store add "Daily Driver Gaming Headset" --asin B0XXXX --category tech --verify
# `manage status` will then show 0 M9 blockers

# M10 — First shipped game / tech review post
bolt manage mark-ready "Headset" --verdict "Honest budget pick" --note "Day 1 in daily use"
# (after uploading to one or more platforms)
bolt manage mark-posted "Headset" --platforms tiktok --where <video_url>
bolt manage shipped          # full review_tracker.json audit log

# M11 — TikTok API end-to-end publish (gated by TikTok video.publish scope)
bolt manage tiktok-status    # reports exactly what's blocking the real publish
bolt manage post-dry-run "Headset"   # preview title, hashtags, video resolution
bolt manage post "Headset" --approve  # actually calls TikTok_Publisher.publish_clip

# M12 — YouTube / X manual-assist packages (real API publishers pending platform approval)
bolt manage youtube-pkg "Headset"     # title, description, tags, disclosure — paste into YouTube
bolt manage x-pkg "Headset"           # 280-char X post body
bolt manage youtube-status
bolt manage x-status

# M13 — Live sponsor research enrichment
bolt manage sponsors-add "Razer" --lanes game,tech --fit 9 --note "Creator program page"
bolt manage sponsors-enrich "Razer" --note "DM'd on X" --link "https://x.com/razer/..." --mark-contacted
bolt manage sponsors-research "Razer" "Razer creator program contact email"
#   # runs web_search and attaches findings + auto-fills contact email
bolt manage sponsors-pipeline  # full per-stage breakdown with "next: pitch X" action
```

### ML ranking — see what the learned model thinks

```bash
bolt manage model-inspect              # per (game, trigger): samples, views, like_rate, boost
bolt manage model-inspect --game "Marvel Rivals"
bolt manage model-status               # compact summary: outcomes, last update, top boost
# `manage status` also shows the learning loop line + top boosted trigger
```

### How the M-tier fits together

```
test item → journal notes → build draft → mark ready →
publish (or paste-and-upload) → mark posted → log 24h performance →
model updates the next rank
```

Voice: say **Good Morning Bolt** in conversation mode (`python -m modules.Bolt_Conversation`).

Amazon tag: `billycarter-20`. Handles: TikTok @itssimplybilly, Twitch thunderstormbilly, YouTube @SimplyBilly, X @SimplyBilly_.

## `bolt` CLI Wrapper (NEW - July 7, 2026)
|
|A single entry-point command for every Bolt script and command lives at
|`bin/bolt`. It does the sys.path bootstrap once, then dispatches to the
|right script.
|
|Invoke directly (no setup required):
|
|```bash
|/Users/carter/developer/Bolt/bin/bolt verify
|/Users/carter/developer/Bolt/bin/bolt recordings
|/Users/carter/developer/Bolt/bin/bolt nexus "How do I title my clips?"
|/Users/carter/developer/Bolt/bin/bolt test              # full test suite
|/Users/carter/developer/Bolt/bin/bolt help              # show all subcommands
|```
|
|Or add a shell alias so you can just type `bolt <thing>` from any
|directory. Put this in `~/.zshrc` (or `~/.bashrc`):
|
|```bash
|alias bolt='/Users/carter/developer/Bolt/bin/bolt'
|```
|
|Then `source ~/.zshrc` (or open a new terminal) and:
|
|```bash
|bolt verify
|bolt recordings
|bolt thumbnails --dry-run
|bolt briefing --send
|bolt launch         # start the bot (Core/src/launch.py)
|bolt test           # run the full test suite
|bolt help           # show all subcommands
|```
|
|Every subcommand listed in this doc maps 1:1 to a `bolt <name>`
|invocation. The wrapper does the path setup, so the long
|`scripts/X.py` paths in the rest of this doc become
|short `bolt X` commands.
|
|## Local Paths

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
python3 scripts/verify.py
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
python3 -m compileall Core/bot.py Core/src/launch.py Core/modules scripts Data/tests
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

The process script lives at `scripts/process_recordings.py`
but **has stale internal paths** (see bottom of this file). The following
commands are the intended ones once the script is patched:

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

Bolt supports different content types with Gemini-optimized captions:

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
PYTHONPATH=scripts python3 scripts/refresh_memory_index.py
```

### Search Memory
Search memory through the index module:

```bash
PYTHONPATH=Core:scripts python3 -m modules.Memory_Index --refresh "Amazon Influencer storefront product testing"
```

Search memory through Bolt memory (the higher-level wrapper):

```bash
PYTHONPATH=Core:scripts python3 -m modules.Bolt_Memory --search "beauty skincare routine product test results"
```

## Content Results And Learning

### Log Performance
List logged performance outcomes:

```bash
PYTHONPATH=scripts python3 scripts/log_clip_performance.py --list
```

Log a posted clip result (note: `clips/` is now under `media/`):

```bash
PYTHONPATH=scripts python3 scripts/log_clip_performance.py --clip media/clips/example.mp4 --platform TikTok --note "Strong opening hook"
```

### Multi-Platform Posting
Build a no-cost posting packet:

```bash
PYTHONPATH=Core:scripts python3 -m modules.Multi_Publisher media/clips/example.mp4 "Working title" --hashtags gaming ai
```

## Nexus Creator — AI Content Strategy Consultant (NEW - July 3, 2026)

Nexus is Bolt's strategic brain, powered by Gemini (free tier). It provides
actionable advice on hooks, monetization, engagement, and content strategy.

```bash
PYTHONPATH=scripts python3 scripts/nexus_advice.py "How should I title my Hades 2 clips?"

# Get next content recommendations based on performance data
PYTHONPATH=scripts python3 scripts/nexus_advice.py --next

# Optimize a caption for a specific clip
PYTHONPATH=scripts python3 scripts/nexus_advice.py --caption "clip.mp4" --desc "Epic boss fight" -p tiktok

# Provide context with your question
PYTHONPATH=scripts python3 scripts/nexus_advice.py "skincare review strategy" --context "17 clips posted, low views"

# Use a different Gemini model
PYTHONPATH=scripts python3 scripts/nexus_advice.py "topic" --model gemini-2.5-pro
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
PYTHONPATH=scripts python3 scripts/monitor_title_results.py

# Run title upgrade test
PYTHONPATH=scripts python3 scripts/test_title_upgrade_10_clips.py
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
PYTHONPATH=scripts python3 scripts/get_twitch_token.py
```

Generate or refresh TikTok auth:

```bash
PYTHONPATH=scripts python3 scripts/get_tiktok_token.py
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
PYTHONPATH=scripts python3 scripts/site_data_writer.py --push
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
*/15 * * * * cd /Users/carter/developer/Bolt && PYTHONPATH=scripts python3 scripts/site_data_writer.py --push
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
PYTHONPATH=scripts python3 scripts/auto_clip_twitch.py --list

# Process the latest unprocessed VOD (downloads → clip pipeline → post queue)
PYTHONPATH=scripts python3 scripts/auto_clip_twitch.py

# Process all unprocessed VODs
PYTHONPATH=scripts python3 scripts/auto_clip_twitch.py --all

# Process a specific VOD by ID
PYTHONPATH=scripts python3 scripts/auto_clip_twitch.py --vod 2784630508

# Also create Twitch clips via API (requires user OAuth - not yet configured)
PYTHONPATH=scripts python3 scripts/auto_clip_twitch.py --twitch-clips
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
PYTHONPATH=scripts python3 scripts/make_twitch_highlights.py

# Compile top 15 clips
PYTHONPATH=scripts python3 scripts/make_twitch_highlights.py --count 15

# Filter clips by game keyword
PYTHONPATH=scripts python3 scripts/make_twitch_highlights.py --game "Hades"

# List top clips by score
PYTHONPATH=scripts python3 scripts/make_twitch_highlights.py --list

# Custom output filename (and a path under media/ keeps it tidy)
PYTHONPATH=scripts python3 scripts/make_twitch_highlights.py --output media/highlight_reel.mp4
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
bash scripts/maintenance/storage_optimization.sh --dry-run

# Run actual optimization (use with caution)
bash scripts/maintenance/storage_optimization.sh --skip-dedup

# Customize limits
bash scripts/maintenance/storage_optimization.sh --recordings-gb 40 --clips-gb 0.5
```

### Individual Maintenance Scripts
```bash
# Media rotation (size-based, runs every 6 hours via cron)
bash scripts/maintenance/media_rotation.sh

# Storage monitoring with alerts (runs every 3 hours via cron)
bash scripts/monitoring/storage_monitor.sh

# Video compression (runs every 30 minutes via cron)
bash scripts/media_processing/compress_videos.sh
```

### Duplicate Detection
```bash
PYTHONPATH=scripts python3 scripts/clip_deduplicator.py

# Dry run mode (no database changes)
PYTHONPATH=scripts python3 scripts/clip_deduplicator.py --dry-run

# Check a single file
PYTHONPATH=scripts python3 scripts/clip_deduplicator.py --check media/clips/example.mp4

# Clear the hash database
PYTHONPATH=scripts python3 scripts/clip_deduplicator.py --clear-db
```

### Performance Baseline
```bash
PYTHONPATH=scripts python3 scripts/performance_baseline.py
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
| **Duplicate Scanner** | `python3 scripts/clip_deduplicator.py` | Hash-based dedup |
| **Performance Baseline** | `python3 scripts/performance_baseline.py` | Benchmark metrics |
| **Storage Monitor** | `bash scripts/monitoring/storage_monitor.sh` | Disk usage + alerts |
| **Video Compressor** | `bash scripts/media_processing/compress_videos.sh` | HandBrake compression |
| **Media Rotator** | `bash scripts/maintenance/media_rotation.sh` | Auto-archival |
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
*/15 * * * * cd /Users/carter/developer/Bolt && PYTHONPATH=scripts python3 scripts/site_data_writer.py --push
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
PYTHONPATH=scripts python3 scripts/daily_briefing.py

# Print to stdout only
PYTHONPATH=scripts python3 scripts/daily_briefing.py --print

# Save to custom path
PYTHONPATH=scripts python3 scripts/daily_briefing.py --output /path/to/briefing.md

# Generate AND send via SMS/email (also refreshes calendar feeds
# and attaches them as text/calendar MIME parts).
PYTHONPATH=scripts python3 scripts/daily_briefing.py --send
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
PYTHONPATH=scripts python3 scripts/weekly_analysis.py --print

# Limit window to last N days
PYTHONPATH=scripts python3 scripts/weekly_analysis.py --days 14

# Generate AND send via SMS/email
PYTHONPATH=scripts python3 scripts/weekly_analysis.py --send
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
PYTHONPATH=scripts python3 scripts/generate_calendar.py

# Dry-run (plan without writing)
PYTHONPATH=scripts python3 scripts/generate_calendar.py --dry-run

# Limit scheduled_posts.ics to next N days
PYTHONPATH=scripts python3 scripts/generate_calendar.py --days 14

# Custom output directory
PYTHONPATH=scripts python3 scripts/generate_calendar.py --output-dir /tmp/cal
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
PYTHONPATH=scripts python3 scripts/generate_thumbnails.py

# Generate for a single video
PYTHONPATH=scripts python3 scripts/generate_thumbnails.py media/clips/example.mp4

# Strategy options: smart (default), first, middle
PYTHONPATH=scripts python3 scripts/generate_thumbnails.py --strategy first
PYTHONPATH=scripts python3 scripts/generate_thumbnails.py --strategy middle

# Force regenerate even if .jpg is newer than .mp4
PYTHONPATH=scripts python3 scripts/generate_thumbnails.py --force

# Plan without invoking ffmpeg
PYTHONPATH=scripts python3 scripts/generate_thumbnails.py --dry-run

# Save run summary to Data/data/thumbnail_state.json
PYTHONPATH=scripts python3 scripts/generate_thumbnails.py --save-state

# Custom output width (default: 1280px, height auto, aspect preserved)
PYTHONPATH=scripts python3 scripts/generate_thumbnails.py --width 1920
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
PYTHONPATH=scripts python3 scripts/auto_clip_twitch.py --list
PYTHONPATH=scripts python3 scripts/auto_clip_twitch.py
PYTHONPATH=scripts python3 scripts/auto_clip_twitch.py --all
```

Compile highlight reels for Twitch upload:
```bash
PYTHONPATH=scripts python3 scripts/make_twitch_highlights.py
PYTHONPATH=scripts python3 scripts/make_twitch_highlights.py --count 15 --game "Hades"
PYTHONPATH=scripts python3 scripts/make_twitch_highlights.py --list
```

Upload to Twitch:
1. Go to https://dashboard.twitch.tv/u/ThunderstormBilly/content/video-producer
2. Click Upload
3. Select the file (e.g. `media/highlight_reel.mp4`)
4. Title it and set to Public

---

## Stale-Internal-Paths Status (as of July 7, 2026)

The scripts in `scripts/` were moved on disk during the
color-coded folder reorg. Most used `Path(__file__).resolve().parents[1]`
(or `.parent.parent`), which now resolves to `scripts/` rather
than the repo root, and many also hardcoded old top-level subpath strings
(`data/`, `clips/`, `recordings/`, `bot.py`, `config.json`, etc.).

A `scripts/_paths.py` helper module exists that computes
the correct `REPO_ROOT = parents[3]` and exports every standard subpath
constant. Scripts that import from `_paths` automatically resolve
`REPO_ROOT`, `DATA_DIR`, `CLIPS_DIR`, `VERTICAL_CLIPS_DIR`, `MEDIA_DIR`,
`LOGS_DIR`, `DAILY_BRIEFINGS_DIR`, `DOCS_DIR`, `ARCHIVE_DIR`, `RECORDINGS_DIR`,
`CONFIG_FILE`, `BOT_FILE`, `BOLT_BRAIN_FILE`, `VOD_SAMPLES_DIR`, etc.

**Status (post-fix, all scripts migrated):**

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
| `generate_calendar.py`, `nexus_advice.py`, `refresh_memory_index.py`, `log_clip_performance.py`, `monitor_title_results.py`, `performance_baseline.py`, `test_title_upgrade_10_clips.py`, `get_tiktok_token.py`, `get_twitch_bot_token.py`, `get_twitch_token.py`, `send_notification.py`, `update_game_from_obs.py`, `start_obs_game_tracker.py`, `Filter_Backlog.py`, `bot_with_twitch.py`, `twitch_vod_downloader.py` | ✓ | All use the `_paths` bootstrap shim plus `ROOT = REPO_ROOT` and `PROJECT_ROOT = REPO_ROOT` backward-compat aliases. `from modules import X` and `from scripts import X` (tests) both work. |
| `Watcher.py`, `make_highlights.py`, `build_env.py`, `load_bolt_personality.py`, `setup_env.py`, `autostart.py` | n/a | CWD-relative only; no `from modules.X` import. Safe to run from repo root. |

**If you add or update a script in `scripts/`**, import
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
Scripts moved from `scripts/` to `scripts/`. Entries at the
repo root (`bot.py`, `launch.py`, `config.json`, `modules/`, `data/`,
`clips/`, `recordings/`) now live one level deeper. `Docs/Scratchpad:`
renamed to `Docs/Scratchpad_archive/`. `Docs/reorganize_bolt.sh` and
`Docs/REORGANIZE_MANUAL.md` moved to `scripts/legacy/`.
A `_paths.py` helper was added to the scripts folder and ALL scripts
were updated to use it (with `ROOT = REPO_ROOT` and
`PROJECT_ROOT = REPO_ROOT` backward-compat aliases for code that
still uses those names). Two syntax bugs in `Core/src/launch.py`
(indented code at column 0 inside a `try:` block and inside a
`notify(...)` call) were repaired, and `launch.py` now sets up
sys.path and uses `Core/bot.py` for the handoff. **`bin/bolt`
single-entry CLI wrapper added** — see the `bolt CLI Wrapper`
section above. **Full test suite: 215 tests, 0 failures.**
