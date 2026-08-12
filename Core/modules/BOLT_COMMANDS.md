# Bolt Command Reference

The current user-facing command list for Bolt. It contains every command the live CLI, conversation interface, and Twitch chat bot accept, with a one-line plain-English description per command. Run `bolt help` for the same list as printed at startup.

## Running Bolt commands

From any directory, use:

```bash
bolt <command> [options]
```

One-time shell setup (`~/.zshrc`) so `bolt` always hits the uv-managed venv:

```bash
alias bolt='/Users/carter/developer/Bolt/.venv/bin/bolt'
```

Then reload the shell:

```bash
source ~/.zshrc
type bolt
bolt help
```

Equivalents without the alias:

```bash
uv run --directory /Users/carter/developer/Bolt bolt <command> [options]
# or, from the repo:
uv run bolt <command> [options]
uv run python bin/bolt <command> [options]
```

Run `bolt help` to show the built-in summary. Commands that expose their own help accept `--help`.

## LLM provider (SuperGrok + light API)

Conversation, titles, and Nexus go through `Core/modules/LLM_Handler.py` + `LLM_Budget.py`.

```bash
# .env (local only — never commit real keys)
BOLT_LLM_MODE=light              # local | light | full
BOLT_LLM_PROVIDER=ollama         # ollama | xai | openai  (free-first)
BOLT_LLM_FALLBACK=none
OLLAMA_MODEL=llama3.1:8b
XAI_API_KEY=...                  # paid Grok API (console.x.ai) — not SuperGrok
# OPENAI_API_KEY=...             # optional; not needed for voice STT or titles
BOLT_XAI_MODEL=grok-4.5          # high-value strategy only in light mode
BOLT_XAI_MODEL_LIGHT=grok-4.3
BOLT_API_MONTHLY_CAP_USD=35      # soft cap → force local when hit
BOLT_BRIEFING_PROVIDER=auto      # auto | grok | local
BOLT_STT_PROVIDER=google         # free; never Whisper unless BOLT_USE_WHISPER=true
Bolt_EDGE_VOICE=en-US-AndrewNeural
Bolt_VOICE=Nathan (Enhanced)     # macOS say fallback
```

Quick health check:

```bash
bolt budget                      # mode, soft cap, alert channels
PYTHONPATH=Core python3 -m modules.LLM_Handler
```

## Core commands

Inspect, launch, and maintain Bolt itself.

```bash
bolt help                         # Show the CLI command summary
bolt version                      # Show the repository and Python in use
bolt verify                       # Check required files, folders, config, and environment
bolt setup                        # Finite setup check (config + keys); exits when done
bolt day [--decide|--voice|--quiet|--open|--process]
                                      # Default morning flow; --decide → queue review
bolt day --decide                     # Preferred: brief → queue decide
bolt day --decide --voice             # Decide, then hands-free voice
bolt stats [status|sync|tiktok|youtube] [--dry-run]
                                      # Social readiness + TikTok/YouTube pull
bolt launch                       # Start live mode (folder watch + optional OBS)
bolt launch --no-checklist        # Live mode without the pre-stream voice checklist
bolt status                       # Check the decision engine, vector DB, and Nexus
bolt intelligence                 # Alias for `status`
bolt budget                       # xAI spend / soft cap / alert channel status
bolt budget --test-alert          # Test Mac + email + iMessage alerts
bolt storage status               # media/ sizes + disk free
bolt storage monitor|rotate|optimize
bolt test                         # Run the full test suite
bolt test <unittest-arguments>    # Run selected unittest targets
bolt layout                       # Report misplaced root files; never moves them
bolt layout --quiet               # Print only the layout summary
bolt layout --json                # Return the layout report as JSON
```

## Direction-finding researcher

Profile-aware research role (C5/C6/C7 gates). Reads `Data/memory/user_profile.json`
and writes `Data/memory/research_log.jsonl`. Surfaces in `bolt briefing`.

```bash
bolt research                         # Status summary (default)
bolt research status                  # Same as above
bolt research questions               # Standing research questions from profile
bolt research candidates              # All gated candidates (newest first)
bolt research candidates --limit 10
bolt research pending                 # Only candidates still needing your C5 call
bolt research log                     # Recent findings
bolt research log --limit 15

# Add a candidate (auto C7/C6 gate; C5 still yours)
bolt research add "iJustine" --platform YouTube \
  --summary "Tech + lifestyle reviews; attends industry events" \
  --why "Path from reviewer to invited insider" \
  --signal "honest first impressions at Apple events"

# Free-form notes
bolt research note "Through-line: honest tangent reviews" --type pattern_note
bolt research note "Lane signal: skincare feels natural" --type lane_signal --title "Skincare"

# Your C5 decision (keep = fits, drop = no; maybe also allowed)
bolt research c5 keep "iJustine" --why "Want that event path"
bolt research c5 drop "Someone" --why "Not my voice"
bolt research c5 maybe "Name" --why "Revisit after 2 more samples"
```

C5 ("Would I want to be known for this?") is always Billy's call — Bolt only
gates C7 (hard block) and flags C6 (authenticity red flags). Name match is
case-insensitive substring when unique.

## Creator Command Center (missions)

Turns a broad goal into a printable mission briefing (check-in → options →
checklist). Playbook: `Core/skills/creator-command-center/SKILL.md`.
Missions save under `Data/memory/missions/`. Planning only — nothing is
posted or purchased without your approval.

```bash
bolt mission                              # Status / how to use
bolt mission checkin                      # 5 check-in questions (limits first)
bolt mission playbook                     # Print the full skill playbook
bolt mission start "fund a new mic" \
  --hours 6 --budget 50 \
  --assets "OBS, Mouse ASIN, clips" \
  --restrictions "no gimmick posts"
bolt mission start "first Amazon review" --no-nexus   # skip AI fill-in
bolt mission list
bolt mission show latest
bolt mission next                         # Section 13 only

# Aliases
bolt command-center …                     # Alias for `mission`
bolt ccc …                                # Short alias for `mission`
```

## Creator manager

Names containing spaces should be quoted. **Short aliases work** — you do not
need the long `mark-*` forms every time.

### Daily cheat sheet

```bash
bolt manage help                      # this cheat sheet
bolt manage status                    # snapshot
bolt manage next                      # top actions
bolt manage list

bolt manage add "Mouse" --lane tech --asin B0…
bolt manage note "Mouse" --text "Lightweight, easy to charge"
bolt manage draft "Mouse"

bolt manage ready "Mouse"             # alias for mark-ready
bolt manage posted "Mouse"            # alias for mark-posted (default: tiktok+yt+x)
bolt manage posted "Mouse" --tiktok --youtube --x
bolt manage posted "Mouse" --amazon --where "https://…"
bolt manage ship "Mouse" --amazon     # ship == posted

bolt manage shipped
bolt manage morning                   # Good Morning Bolt (+ voice)
```

Typos are auto-corrected when obvious (`mark-reade` → `mark-ready`).  
Platform flags accept any casing: `--Amazon`, `--YouTube`, `--tiktok`.

### Catalog and review workflow (full forms)

```bash
bolt manage status
bolt manage next
bolt manage add "Name" [--lane game|tech|product|skincare] [--status idea|queued|testing|drafting|ready|posted|shelved] [--asin <asin>] [--notes "text"]
bolt manage list [--lane <lane>] [--status <status>]
bolt manage note "Name" --text "Mic is clear" [--day 1]
bolt manage draft "Name" [--format short|long]
bolt manage mark-ready "Name"   # aliases: ready
bolt manage mark-posted "Name" [--platforms tiktok,youtube_shorts,x,amazon]
                               [--tiktok] [--youtube] [--x] [--amazon]
                               [--where <url>] [--note "text"]
                               # aliases: posted, ship
bolt manage shipped
```

| Command | What it does |
|---------|--------------|
| `bolt manage status` | Show shipped count + today's pending actions for the manager OS |
| `bolt manage next` | Print the top next-action stack across catalog, store, social, sponsors, business |
| `bolt manage add "Name" --lane …` | Create a new catalog item with optional ASIN and notes |
| `bolt manage list [--lane …] [--status …]` | List items filtered by lane and/or status |
| `bolt manage note "Name" --text "…"` | Append a day-keyed note to an item's history |
| `bolt manage draft "Name" --format short|long` | Build a draft post from notes (uses the LLM) |
| `bolt manage mark-ready "Name" [--verdict …]` | Mark an item as ready to post (requires a draft) |
| `bolt manage mark-posted "Name" --platforms … --where …` | Mark an item as posted, recording publish URLs |
| `bolt manage shipped` | List every item that has been marked posted |

### Publishing and platform readiness

`post-dry-run` previews a TikTok post. `post` remains a dry run unless `--approve` is present.

```bash
bolt manage post-dry-run "Headset"
bolt manage post "Headset" [--video /path/to/video.mp4]
bolt manage post "Headset" --approve [--video /path/to/video.mp4]
bolt manage tiktok-status
bolt manage youtube-pkg "Headset"
bolt manage youtube-status
bolt manage x-pkg "Headset"
bolt manage x-status
```

| Command | What it does |
|---------|--------------|
| `bolt manage post-dry-run "Name"` | Preview a TikTok post without sending anything live |
| `bolt manage post "Name"` | Default: dry-run only; refuses to publish |
| `bolt manage post "Name" --approve` | Actually publish to TikTok (still requires `--video` if no draft video) |
| `bolt manage tiktok-status` | Show whether the TikTok publisher is configured and ready |
| `bolt manage youtube-pkg "Name"` | Build a YouTube Shorts package (title + description + tags) |
| `bolt manage youtube-status` | Show whether the YouTube publisher is configured and ready |
| `bolt manage x-pkg "Name"` | Build an X (Twitter) package from the item's draft |
| `bolt manage x-status` | Show whether the X publisher is configured and ready |

### Learned ranking model

```bash
bolt manage model-status
bolt manage model-inspect [--game "Game Name"]
```

| Command | What it does |
|---------|--------------|
| `bolt manage model-status` | Show the trained ranker's stage, sample count, and last training time |
| `bolt manage model-inspect [--game …]` | Show per-trigger learned weights for a specific game (or aggregate if omitted) |

## Storefront

```bash
bolt store list
bolt store add --name "Mouse" [--asin <asin>] [--category tech] [--notes "text"]
bolt store feature-next
```

Running `bolt store` with no action is the same as `bolt store list`.

| Command | What it does |
|---------|--------------|
| `bolt store list` | List everything currently in the storefront catalog |
| `bolt store add --name "…" [--asin …]` | Add a storefront product (Amazon ASIN optional, category required if given) |
| `bolt store feature-next` | Recommend which storefront item to feature next, based on cadence and rotation |

## Social packages and queue

```bash
bolt social status
bolt social package "Headset" [--platforms tiktok,youtube,x]
bolt social queue
```

Running `bolt social` with no action is the same as `bolt social status`.

| Command | What it does |
|---------|--------------|
| `bolt social status` | Show queue counts and the next posting window status |
| `bolt social package "Name" --platforms …` | Build ready-to-publish packages for the listed platforms |
| `bolt social queue` | Print the full posting queue (status, clip path, scheduled time) |

## Ready-to-post clip queue (peak hours)

This is the **clip** ready queue used for peak-hour posting — **not a folder**.

| What | Where | Role |
|------|--------|------|
| Queue state | `Data/ready_to_post.json` | IDs, scores, approve/hold/schedule (**this is the queue**) |
| Vertical videos | `media/vertical_clips/` | Watch/export files only — **not** where you approve |
| Intermediate cuts | `media/clips/` | Raw cuts — not the posting list |

You do **not** need to open the JSON or remember ids for the normal path.

### Simplest path (recommended)

```bash
bolt queue clean                      # Clear ghost rows (ready but video file gone)
bolt queue list                       # Only clips with a real local file
bolt queue decide                     # Opens video, then: approve / hold / post / skip
#  — or one-liners without ids —
bolt queue next --open                # Show next clip card + open the video
bolt approve                          # Approve that next clip for peak auto-post
bolt dontpost "weak hook"             # Hold next + reason (Bolt learns)
bolt postnow                          # Publish next clip to TikTok now
```

### Hand-edited files already in `media/vertical_clips/`

Editing/renaming a video (e.g. `Stress.mp4`) does **not** put it in the post queue. Register it once, then approve/post:

```bash
# Register your final cuts (looks up bare names under media/vertical_clips/)
bolt queue add Stress.mp4 Hands.mp4 Leaving.mp4 Ate.mp4 close.mp4 almost.mp4 yes.mp4

# Or register + approve for peak in one step
bolt queue add Stress.mp4 --approve --title "When the stress hits"

# Titles
bolt queue title                      # Suggest captions for the next clip
bolt queue title 512bdfa4 1           # Apply suggestion #1
bolt queue title 512bdfa4 "My hook"   # Set a custom title
bolt queue add Hands.mp4 --suggest-title --approve   # generate title while adding
bolt monitor_titles                   # How past titles performed (learning)

# Then post when ready
bolt postnow                          # next approved/ready clip now
# or wait for peak after: bolt approve
bolt queue mark-posted <id|filename|#n>  # after manual upload (bare form refuses bulk)
bolt queue mark-posted --all             # mark every ready row (explicit only)
bolt mark-posted <id>                    # top-level alias
```

### Full command list

```bash
bolt queue                            # Peak window + summary counts
bolt queue status                     # Same as above
bolt queue list                       # Actionable clips (id, score, filename)
bolt queue list --all                 # Include ghost / missing-file rows
bolt queue next [--open]              # Next postable clip card
bolt queue decide                     # Interactive review (no JSON)
bolt queue help                       # Full queue CLI help

bolt queue approve                    # Approve next postable clip for peak auto-post
bolt queue approve 55a802e8           # Approve a specific clip id
bolt approve                          # Short alias for queue approve
bolt approve 55a802e8

bolt queue reject "weak moment"       # Hold next clip + reason
bolt queue reject 55a802e8 "bad title"
bolt dontpost "weak moment"           # Short alias for queue reject

bolt queue post-now                   # Publish next postable clip now
bolt queue post-now 55a802e8
bolt postnow                          # Short alias for queue post-now

bolt queue clean                      # Scrap ready rows whose video file is missing
bolt queue clean --dry-run            # Preview ghost cleanup
bolt queue mark-posted 55a802e8       # After you uploaded manually
bolt queue mark-posted 1              # list #1 / next postable
bolt queue mark-posted Hands.mp4      # exact filename stem
bolt mark-posted 55a802e8             # same, top-level alias
bolt queue check                      # Peak check + Discord alert if due
bolt queue tick                       # One auto-post scheduler pass
bolt queue review-window              # Force the 30-min pre-peak Discord ping
```

| Command | What it does |
|---------|--------------|
| `bolt queue` / `bolt queue status` | Peak window + how many you can actually post vs ghost rows |
| `bolt queue list` | Actionable clips only (id, score, plan, filename) |
| `bolt queue next [--open]` | Show the next postable clip; optional OS open |
| `bolt queue decide` | Interactive open → approve / hold / post / skip |
| `bolt queue clean` | Mark missing-file ready rows as scrapped (no media deleted) |
| `bolt queue approve [clip_id]` | Approve for peak auto-post (does **not** force publish now) |
| `bolt approve [clip_id]` | Alias for `bolt queue approve` |
| `bolt queue reject [clip_id] <reason>` | Hold a clip and log why (Bolt learns) |
| `bolt dontpost [clip_id] <reason>` | Alias for `bolt queue reject` |
| `bolt queue post-now [clip_id]` | Publish to TikTok **immediately** |
| `bolt postnow [clip_id]` | Alias for `bolt queue post-now` |
| `bolt queue mark-posted [clip_id\|#n\|file]` | Clear from ready after a manual upload |
| `bolt queue mark-posted --all` | Mark every ready clip (explicit bulk) |
| `bolt mark-posted …` | Top-level alias for queue mark-posted |
| `bolt queue check` | Peak-window check; alert if clips are waiting |
| `bolt queue tick` | Run one auto-post / review-window processing pass |
| `bolt queue review-window` | Send the pre-peak “awaiting approval” Discord alert now |

Typical flow:

1. `bolt queue clean` once if the count looks insanely high (ghosts)  
2. `bolt queue decide` — watch + approve/hold without touching JSON  
3. At peak, auto-post runs if enabled — or `bolt postnow` to force it

## Sponsors

### Everyday sponsor workflow

```bash
bolt sponsors find [--lane <lane>] [--limit 5]
bolt sponsors pitch "Razer"
bolt sponsors log "Razer" --status <status> [--note "text"]
bolt sponsors next
```

Running `bolt sponsors` with no action is the same as `bolt sponsors find`.

| Command | What it does |
|---------|--------------|
| `bolt sponsors find [--lane …] [--limit …]` | Find new sponsor candidates matching the given lane |
| `bolt sponsors pitch "Name"` | Build a pitch email for the named sponsor |
| `bolt sponsors log "Name" --status …` | Record an outreach status (contacted, replied, etc.) for an existing sponsor |
| `bolt sponsors next` | Show the next sponsor outreach action |

### Sponsor records and research

```bash
bolt manage sponsors-add "Razer" [--lanes game,tech] [--type brand] [--fit 9] [--contact <contact>] [--note "text"]
bolt manage sponsors-enrich "Name" [--note "text"] [--link <url>] [--mark-contacted]
bolt manage sponsors-pipeline
bolt manage sponsors-research "Razer" "Razer creator program" [--limit 5] [--no-update-contact] [--json]
```

Sponsor research requires the repository's search provider to be configured.

| Command | What it does |
|---------|--------------|
| `bolt manage sponsors-add "Name" --lanes …` | Add a new sponsor record with lanes, type, fit score, contact |
| `bolt manage sponsors-enrich "Name" [--note …]` | Add a note or contact link to an existing sponsor |
| `bolt manage sponsors-pipeline` | Show the full sponsor pipeline grouped by stage |
| `bolt manage sponsors-research "Name" "query" …` | Run a research query (uses configured search provider) and surface findings |

## Business guidance and daily briefing

```bash
bolt business lesson
bolt business next
bolt advance next
bolt morning
bolt morning --quiet
```

`bolt good-morning` and `bolt goodmorning` are aliases for `bolt morning`.

| Command | What it does |
|---------|--------------|
| `bolt business lesson` | Pull today's business-mindset lesson from the manager content |
| `bolt business next` | Show the next business move Bolt recommends |
| `bolt advance next` | Show the next concrete Bolt improvement to ship (roadmap pull) |
| `bolt morning` | Run the full "Good Morning Bolt" spoken daily briefing |
| `bolt morning --quiet` | Same as `morning`, but skip the spoken audio output |

## Recordings, clips, and highlights

```bash
bolt recordings                          # Default: latest unprocessed only
bolt recordings latest                   # Same as default
bolt recordings latest --force           # Reprocess even if already marked done
bolt recordings all                      # Every unique recording (skips already-done)
bolt recordings all --force              # Reprocess the full backlog
bolt recordings list                     # List found recordings (no processing)
bolt recordings 3                        # Process the Nth file from the list
bolt recordings [mode] --content-type gaming|review|skincare|tech
bolt auto_clip_twitch                    # Process the latest unprocessed Twitch VOD
bolt auto_clip_twitch --all
bolt auto_clip_twitch --list
bolt auto_clip_twitch --vod <vod-id>
bolt auto_clip_twitch --twitch-clips
bolt highlights [--count 10] [--game "Game Name"] [--list] [--output /path/to/reel.mp4]
bolt thumbnails [directory ...] [--strategy smart|first|middle] [--width 1280] [--force] [--dry-run] [--save-state]
bolt clip_dedupe [--dry-run] [--scan <directory>] [--check <file>] [--clear]
bolt filter_backlog
bolt watch
```

`recordings` defaults to **`latest`** (not `all`) and gaming content. Same-stem
duplicates (`.mp4` / `.mov` / `.mkv`) are collapsed to one file. Already-processed
names in `Core/data/processed_recordings.json` and `Data/processed_recordings.json`
are skipped unless you pass `--force`.

Highlight detection is intentionally strict (local peaks, prominence, confidence
floor, min gap, candidate cap). Tune in `Core/config.json` under `highlight` and
`max_highlight_candidates` / `max_clips_per_session`.

`auto-clip-twitch` is an alias for `auto_clip_twitch`.

| Command | What it does |
|---------|--------------|
| `bolt recordings` | Process the newest recording only (default mode: `latest`) |
| `bolt recordings latest` | Same as default |
| `bolt recordings latest --force` | Reprocess the newest even if already marked done |
| `bolt recordings all` | Process every unique recording; skips already-done |
| `bolt recordings all --force` | Reprocess the full backlog |
| `bolt recordings list` | List recordings with sizes; no processing |
| `bolt recordings <N>` | Process the Nth recording from that list |
| `bolt auto_clip_twitch` | Auto-clip highlights from the latest unprocessed Twitch VOD |
| `bolt auto_clip_twitch --all` | Run auto-clip for every unprocessed VOD |
| `bolt auto_clip_twitch --list` | Show which VODs are unprocessed, without running anything |
| `bolt auto_clip_twitch --vod <id>` | Process a single named VOD by ID |
| `bolt auto_clip_twitch --twitch-clips` | Pull Twitch's own Clip API highlights for the latest VOD |
| `bolt highlights` | Compile the top clips into a Twitch highlight reel |
| `bolt thumbnails [dir…]` | Generate JPG thumbnails for clips in the given directories |
| `bolt clip_dedupe` | Run duplicate detection across the clips folder (writes to `Data/seen_clips.json`) |
| `bolt filter_backlog` | Move low-scoring clips to `clips/_low_score/` |
| `bolt watch` | Watch the recordings folder for new files and trigger the pipeline |

## Twitch VOD downloads and authentication

```bash
bolt vods [--channel <channel>] [--type archive|highlight|upload] [--limit 10] [--sample-minutes 5]
          [--output-dir <directory>] [--metadata-file <file>] [--dry-run] [--skip-existing]
          [--user-token <token>]
bolt twitch_token
bolt twitch_bot_token
bolt tiktok_token [--client-key <key>] [--client-secret <secret>] [--redirect-uri <uri>]
                  [--scopes "user.info.basic,video.list,video.publish,video.upload"]
bolt youtube_token [--client-id <id>] [--client-secret <secret>] [--redirect-uri <uri>]
```

Token commands are interactive and may open a browser or prompt for credentials.

| Command | What it does |
|---------|--------------|
| `bolt vods` | Download Twitch VOD samples for a channel with type/limit/sample filters |
| `bolt twitch_token` | Get an OAuth token for the Twitch chat account (interactive) |
| `bolt twitch_bot_token` | Get an OAuth token for the Bolt bot account (interactive) |
| `bolt tiktok_token` | Get a TikTok OAuth token; include `video.list` scope for stats sync |
| `bolt youtube_token` | Get a Google/YouTube OAuth token (`youtube.readonly`) for stats sync |

## Platform stats sync (auto learning loop)

Pull real views/likes from TikTok or YouTube into `Data/performance_outcomes.jsonl`
(and clip history on first sight of each video). Preferred surface is **`bolt stats`**
(wraps the same Performance_Sync path as the older script aliases).

```bash
# Readiness + recent outcomes
bolt stats

# Safe pull (no write) — preferred first try
bolt stats --dry-run                 # both platforms
bolt stats youtube --dry-run
bolt stats tiktok --dry-run

# Live write into learning store
bolt stats sync                      # both
bolt stats youtube                   # YouTube only, live
bolt stats tiktok --min-age-hours 24

# Tokens (once)
bolt youtube_token                   # Google OAuth, youtube.readonly
bolt tiktok_token                    # needs video.list (not upload-only)

# Legacy aliases (still work)
bolt sync_youtube_stats --dry-run
bolt sync_tiktok_stats --dry-run
```

| Command | What it does |
|---------|--------------|
| `bolt stats` | Token readiness + recent outcomes one-liner |
| `bolt stats --dry-run` | Both platforms: fetch + match only; write nothing |
| `bolt stats youtube [--dry-run]` | YouTube/Shorts metrics → performance outcomes |
| `bolt stats tiktok [--dry-run]` | TikTok metrics (needs `video.list` scope) |
| `bolt stats sync` | Both platforms, live write |
| `bolt sync_tiktok_stats` | Legacy alias for TikTok pull |
| `bolt sync_youtube_stats` | Legacy alias for YouTube pull |

## Advice, reporting, and learning

```bash
bolt nexus "question" [--task-type <type>] [--complexity high|medium] [--paid]
# Free by default (Ollama). --paid allows xAI Grok API for that call.
# Gemini only if NEXUS_USE_GEMINI=true (off by default). SuperGrok app sub ≠ free API.
bolt performance
bolt log_perf --trigger <trigger> --views <count> [--likes <count>] [--clip <file>]
              [--game "Game Name"] [--platform TikTok] [--note "text"]
bolt log_perf --list
bolt monitor_titles
bolt test_titles
bolt weekly [--print] [--send] [--days <number>]
```

Running `bolt log_perf` without performance values starts its interactive prompt.
Prefer `bolt sync_tiktok_stats` / `bolt sync_youtube_stats` when tokens are configured;
use `log_perf` for manual entry or platforms without API pull (e.g. X).

| Command | What it does |
|---------|--------------|
| `bolt nexus "question"` | Ask Nexus for advice (free: Ollama; `--paid` = Grok API; Gemini opt-in only) |
| `bolt performance` | Run a performance baseline / snapshot of recent clip outcomes |
| `bolt log_perf …` | Manually log a clip's views/likes back to the ranker so it learns |
| `bolt log_perf --list` | Show recent performance-log entries (most recent first) |
| `bolt monitor_titles` | Summarize how generated titles are performing |
| `bolt test_titles` | Run the 10-clip title-upgrade smoke test |
| `bolt weekly` | Generate (and optionally send) the weekly performance insights |

## Briefings, calendars, memory, and site data

```bash
bolt briefing                    # Generate and save the current daily briefing
bolt briefing --print            # Print it in the terminal
bolt calendar [--output-dir <directory>] [--days 30] [--dry-run]
bolt refresh_memory              # Rebuild Data/memory_index.json
bolt refresh_vector_db           # Rebuild Data/vector_db/ for Nexus (needs Ollama)
bolt vector_db                   # Alias for refresh_vector_db
bolt reindex                     # Alias for refresh_vector_db
bolt site [--path <output-file>] [--push]
```

Vector DB commands require a running Ollama with an embedding model
(default `nomic-embed-text`). If Ollama is down they fail fast instead of hanging:

```bash
ollama pull nomic-embed-text
bolt reindex
```

`bolt site --push` writes site data and then attempts to commit and push it. Use it only when that is the intended action.

| Command | What it does |
|---------|--------------|
| `bolt briefing` | Generate (and save) the current daily briefing under `Docs/briefings/` |
| `bolt briefing --print` | Generate the briefing and print it to the terminal instead of saving |
| `bolt calendar` | Generate ICS calendar feeds for scheduled posts |
| `bolt refresh_memory` | Rebuild the clip memory index (`Data/memory_index.json`) |
| `bolt refresh_vector_db` | Rebuild the vector DB used by Nexus for retrieval (`Data/vector_db/`) |
| `bolt vector_db` | Alias: same as `refresh_vector_db` |
| `bolt reindex` | Alias: same as `refresh_vector_db` |
| `bolt site` | Write `site-data.json` for the web dashboard |
| `bolt site --push` | Write site data AND attempt to commit + push it (use carefully) |

## Notifications

```bash
bolt send "message" [--subject "subject"] [--sms-only|--email-only]
```

`bolt notify` is an alias for `bolt send`.

| Command | What it does |
|---------|--------------|
| `bolt send "msg"` | Send an SMS / email notification (config in `Data/configs/storage_alerts.env`) |
| `bolt send "msg" --sms-only` | Force phone path (iMessage on Mac for AT&T; email-to-SMS where still alive) |
| `bolt send "msg" --email-only` | Force email, ignore phone |
| `bolt send "msg" --subject "…"` | Override the email subject line |

Budget alerts (50% / 90% / 100% of soft cap) use **Mac banner + email + iMessage**, not Discord.

## Default morning flow (daily driver)

This is the intended start-of-day path — **queue decide + optional voice**, not a
fictional plan:

```bash
# Preferred one-liner (brief → interactive queue decide)
bolt day --decide

# Same brief, TTY offers "Start queue decide now?" (default Yes)
bolt day

# Decide, then hands-free voice for approve/hold/post
bolt day --decide --voice

# After posting (or any day): check social pull readiness / dry-run
bolt stats
bolt stats youtube --dry-run    # YouTube token ready → safe metrics pull
```

| Step | Command | Why |
|------|---------|-----|
| 1 | `bolt day --decide` | Peak window, postable queue, then review/retitle/approve |
| 2 | `bolt voice` (or `--voice`) | Hands-free approve next / hold / post next |
| 3 | `bolt postnow` | Publish #1 when ready |
| 4 | `bolt stats` / `--dry-run` | Pull views into learning store when tokens ready |

`bolt morning` is the separate **manager business briefing** (lessons / content OS).
Use `bolt day` for content production.

## Starting conversation mode

Preferred entry points (listen → interpret → speak via `Bolt_Voice`):

```bash
bolt day --decide          # content kickoff → queue decide (default morning)
bolt day                   # same brief; TTY offers decide (default Yes)
bolt voice                 # mic in, spoken replies out (free Google STT)
bolt voice --text          # type in, still speaks (Andrew edge-tts)
bolt talk "what's next?"   # one-shot spoken Q&A
bolt say "Clips are ready" # TTS only
bolt briefing --speak      # write briefing + speak short summary
bolt morning               # Good Morning Bolt spoken *business* briefing
bolt stats                 # social performance readiness
```

Same engine under the hood (`Core/bolt_live_voice.py` → `Bolt_Conversation`):

```bash
PYTHONPATH=Core python3 -m Bolt_Conversation
PYTHONPATH=Core python3 -m Bolt_Conversation --text
PYTHONPATH=Core python3 Core/bolt_live_voice.py --once "What should I do next?"
PYTHONPATH=Core python3 -m Bolt_Conversation --status
PYTHONPATH=Core python3 -m Bolt_Conversation --clear
```

| Command / flag | What it does |
|----------------|--------------|
| `bolt day` | Daily kickoff: peak, queue, storage, API, social line; TTY offers decide |
| `bolt day --decide` | Same brief, then `queue decide` (default morning path) |
| `bolt day --voice` | Same brief, then voice loop |
| `bolt stats` | TikTok/YouTube token readiness + recent outcomes |
| `bolt voice` | Voice-mode conversation loop (mic + TTS) |
| `bolt voice --text` | Text input, spoken replies |
| `bolt talk "…"` / `--once "…"` | One question, one spoken answer, exit |
| `bolt say "…"` | Speak a line only (no LLM) |
| `bolt voice --status` | Print conversation / STT / TTS / LLM status |
| `bolt voice --clear` | Wipe conversation history |

### Natural language intents (no exact CLI required)

In conversation mode, these phrases trigger **real** Bolt actions before free-form chat:

| You say | Bolt does |
|---------|-----------|
| bolt day / play bolt day / start my day | Real peak + queue kickoff + short plan |
| Good morning Bolt / morning briefing | Manager morning briefing |
| queue decide / bolt cue decide | Next postable clip brief (full review: terminal `bolt queue decide`) |
| approve next / hold next / post next | Approve, hold, or post the next postable clip |
| clean queue | Scrap ghost ready rows (missing files) |
| queue status / what can I post | Postable counts + next title |
| What should I do next? | Next actions stack |
| storage / disk space | Disk free + media sizes |
| api budget / how much have I spent | Soft cap + estimated API spend |
| Research status / Mission status | Research or mission summary |

Anything else is short free-form chat (Ollama by default in light mode). Spoken replies stay plain sentences — no markdown dumps.

Inside conversation mode:

- Ask Bolt a normal question or give a normal instruction in plain language.
- Type or say `exit`, `quit`, `bye`, or `goodbye` to end the conversation.

### Titles and hashtags

```bash
bolt queue title                      # suggest titles for next postable clip
bolt queue title <id> 1               # apply suggestion #1 (+ generated hashtags)
bolt queue title <id> "My hook 🔥"    # custom title (hashtags unchanged)
# In decide mode: press t to retitle
bolt queue decide
```

AI titles prefer **Ollama** when `BOLT_LLM_PROVIDER=ollama` (no OpenAI credits required).

## Twitch chat commands

These commands are available while the Bolt Twitch chat bot is connected:

```text
!Bolt <question>                  Ask Bolt a question (Grok via LLM_Handler)
!clip                             Check whether a highlight was detected
!uptime                           Show the current session uptime
!highlights                       Show the session highlight count
!queue                            Show posting queue counts
!qstatus                          Show detailed per-clip queue status
!postnow [clip_id]                Approve and publish the next ready clip
!dontpost [clip_id] <reason>      Hold a queued clip and record the reason
!stopclip [clip_id] <reason>      Emergency hold for a queued clip
!skip [clip_id] <reason>          Hold the next queued clip
!rank <score>                     Set the next clip's score
!rank <clip_id> <score>           Set a specific clip's score
!config <safe_key> <value>        Change an allowed live configuration value
!recall <query>                   Search Bolt's local memory
```

| Command | What it does |
|---------|--------------|
| `!Bolt <question>` | Ask Bolt anything; reply comes from Grok via LLM_Handler |
| `!clip` | Check whether the latest stream event was clipped |
| `!uptime` | Show how long the current Twitch session has been live |
| `!highlights` | Show how many highlights Bolt has detected this session |
| `!queue` | Show the current posting queue counts |
| `!qstatus` | Show per-clip status (channel-mod only) |
| `!postnow [clip_id]` | Approve and publish the next (or named) ready clip |
| `!dontpost <reason>` | Hold the next queued clip and record the reason |
| `!stopclip <reason>` | Emergency hold on a clip |
| `!skip <reason>` | Hold the next clip; rotate it later |
| `!rank <score>` / `!rank <clip_id> <score>` | Manually set a clip's score (channel-mod) |
| `!config <safe_key> <value>` | Change an allowed live configuration value (channel-mod) |
| `!recall <query>` | Search Bolt's local memory and surface the best hit |

Posting and configuration commands enforce the permissions and safeguards implemented by the running bot.

## Command aliases

These names perform the same actions as their primary commands:

| Primary command | Aliases |
|---|---|
| `auto_clip_twitch` | `auto-clip-twitch` |
| `highlights` | `twitch_highlights` |
| `briefing` | `briefings` |
| `nexus` | `advice` |
| `weekly` | `monthly` |
| `log_perf` | `log_performance` |
| `sync_tiktok_stats` | `sync_tiktok`, `tiktok_stats` |
| `sync_youtube_stats` | `sync_youtube`, `youtube_stats` |
| `queue` | `postqueue`, `post-queue`, `ready-queue` |
| `queue decide` | `queue review`, `queue triage`, `queue pick` |
| `queue next` | `queue show` |
| `queue clean` | `queue prune` |
| `queue approve` | `approve` |
| `queue post-now` | `postnow`, `post-now` |
| `queue reject` | `dontpost`, `dont-post`, `hold-clip` |
| `vods` | `vod_download` |
| `send` | `notify` |
| `layout` | `check_layout` |
| `refresh_vector_db` | `vector_db`, `reindex` |
| `status` | `intelligence` |
| `morning` | `good-morning`, `goodmorning` |
| `mission` | `command-center`, `ccc` |
| `setup` | (routes to `Core/launch.py`) |

---

*Canonical path: `Core/modules/BOLT_COMMANDS.md` — this is the only BOLT_COMMANDS
file in the repo. Prefer editing this markdown over duplicate Pages copies.*
