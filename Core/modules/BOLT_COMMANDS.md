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

## LLM provider (Grok / OpenAI)

All conversation and `!Bolt` replies go through `Core/modules/LLM_Handler.py`.

```bash
# .env (local only — never commit real keys)
BOLT_LLM_PROVIDER=xai          # openai | xai
BOLT_LLM_FALLBACK=none         # openai | xai | none
XAI_API_KEY=...
# OPENAI_API_KEY=...           # optional; still used for Whisper if present
# BOLT_XAI_MODEL=grok-4.5
# BOLT_OPENAI_MODEL=gpt-4o-mini
```

Quick health check:

```bash
PYTHONPATH=Core python3 -m modules.LLM_Handler
```

## Core commands

Inspect, launch, and maintain Bolt itself.

```bash
bolt help                         # Show the CLI command summary
bolt version                      # Show the repository and Python in use
bolt verify                       # Check required files, folders, config, and environment
bolt setup                        # Finite setup check (config + keys); exits when done
bolt launch                       # Start live mode (folder watch + optional OBS)
bolt launch --no-checklist        # Live mode without the pre-stream voice checklist
bolt status                       # Check the decision engine, vector DB, and Nexus
bolt intelligence                 # Alias for `status`
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

Names containing spaces should be quoted.

### Catalog and review workflow

```bash
bolt manage status
bolt manage next
bolt manage add "Headset" [--lane game|tech|product|skincare] [--status idea|queued|testing|drafting|ready|posted|shelved] [--asin <asin>] [--notes "text"]
bolt manage list [--lane <lane>] [--status <status>]
bolt manage note "Headset" --text "Mic is clear" [--day 1]
bolt manage draft "Headset" [--format short|long]
bolt manage mark-ready "Headset" [--verdict "verdict"] [--note "text"]
bolt manage mark-posted "Headset" [--platforms tiktok,youtube_shorts,x] [--where <url-or-id>] [--note "text"]
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

| What | Where |
|------|--------|
| Queue state | `Data/ready_to_post.json` |
| Vertical videos | `media/vertical_clips/` |
| Intermediate cuts | `media/clips/` (not the approval list) |

Approve for the next peak window, or publish immediately. Same safeguards as Twitch `!postnow` / `!dontpost`.

```bash
bolt queue                            # Peak window + summary counts
bolt queue status                     # Same as above
bolt queue list                       # Per-clip dashboard
bolt queue help                       # Full queue CLI help

bolt queue approve                    # Approve next ready clip for peak auto-post
bolt queue approve 55a802e8           # Approve a specific clip id
bolt approve                          # Short alias for queue approve
bolt approve 55a802e8

bolt queue reject "weak moment"       # Hold next clip + reason
bolt queue reject 55a802e8 "bad title"
bolt dontpost "weak moment"           # Short alias for queue reject

bolt queue post-now                   # Publish next approved/ready clip now
bolt queue post-now 55a802e8
bolt postnow                          # Short alias for queue post-now

bolt queue mark-posted                # After you uploaded manually
bolt queue mark-posted 55a802e8
bolt queue check                      # Peak check + Discord alert if due
bolt queue tick                       # One auto-post scheduler pass
bolt queue review-window              # Force the 30-min pre-peak review ping
```

| Command | What it does |
|---------|--------------|
| `bolt queue` / `bolt queue status` | Show peak window + ready/alertable/approved counts |
| `bolt queue list` | Per-clip dashboard (id, score, plan status) |
| `bolt queue approve [clip_id]` | Mark clip approved for peak auto-post (does **not** force publish now) |
| `bolt approve [clip_id]` | Alias for `bolt queue approve` |
| `bolt queue reject [clip_id] <reason>` | Hold a clip and log why (Bolt learns) |
| `bolt dontpost [clip_id] <reason>` | Alias for `bolt queue reject` |
| `bolt queue post-now [clip_id]` | Publish to TikTok **immediately** |
| `bolt postnow [clip_id]` | Alias for `bolt queue post-now` |
| `bolt queue mark-posted [clip_id]` | Clear from ready after a manual upload |
| `bolt queue check` | Peak-window check; alert if clips are waiting |
| `bolt queue tick` | Run one auto-post / review-window processing pass |
| `bolt queue review-window` | Send the pre-peak “awaiting approval” alert now |

Typical night-before / peak flow:

1. `bolt queue` — see what’s ready  
2. Preview files under `media/vertical_clips/`  
3. `bolt approve` (or `bolt approve <id>`) before the window  
4. At peak, auto-post runs if enabled — or use `bolt postnow` to force it  
5. To block one: `bolt dontpost <id> "reason"`

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
bolt tiktok_token [--client-key <key>] [--client-secret <secret>] [--redirect-uri <uri>] [--scopes <scopes>]
```

Token commands are interactive and may open a browser or prompt for credentials.

| Command | What it does |
|---------|--------------|
| `bolt vods` | Download Twitch VOD samples for a channel with type/limit/sample filters |
| `bolt twitch_token` | Get an OAuth token for the Twitch chat account (interactive) |
| `bolt twitch_bot_token` | Get an OAuth token for the Bolt bot account (interactive) |
| `bolt tiktok_token` | Get a TikTok OAuth token with optional client overrides |

## Advice, reporting, and learning

```bash
bolt nexus "question" [--task-type <type>] [--complexity high|medium]
bolt performance
bolt log_perf --trigger <trigger> --views <count> [--likes <count>] [--clip <file>]
              [--game "Game Name"] [--platform TikTok] [--note "text"]
bolt log_perf --list
bolt monitor_titles
bolt test_titles
bolt weekly [--print] [--send] [--days <number>]
```

Running `bolt log_perf` without performance values starts its interactive prompt.

| Command | What it does |
|---------|--------------|
| `bolt nexus "question"` | Ask Nexus (an outside LLM wrapped by Bolt) for content-strategy advice |
| `bolt performance` | Run a performance baseline / snapshot of recent clip outcomes |
| `bolt log_perf …` | Log a clip's actual views/likes back to the ranker so it learns |
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
| `bolt send "msg"` | Send an SMS / email / Discord notification (chosen by config) |
| `bolt send "msg" --sms-only` | Force SMS, ignore email |
| `bolt send "msg" --email-only` | Force email, ignore SMS |
| `bolt send "msg" --subject "…"` | Override the email subject line |

## Starting conversation mode

The CLI exposes flags on `Bolt_Conversation` for three modes: persistent text chat, persistent voice chat, and one-shot prompts.

Text conversation:

```bash
PYTHONPATH=Core python3 -m Bolt_Conversation --text
```

Voice conversation:

```bash
PYTHONPATH=Core python3 -m Bolt_Conversation
```

One-shot:

```bash
PYTHONPATH=Core python3 -m Bolt_Conversation --once "What should I do next?"
```

Status / clear history:

```bash
PYTHONPATH=Core python3 -m Bolt_Conversation --status
PYTHONPATH=Core python3 -m Bolt_Conversation --clear
```

| Flag | What it does |
|------|--------------|
| `-m Bolt_Conversation` | Run the voice-mode conversation loop (uses configured TTS/STT) |
| `--text` | Run the same loop in text-only mode (no mic/speaker needed) |
| `--once "question"` | Ask Bolt a single question, get one answer, exit |
| `--status` | Print conversation-history state without sending a message |
| `--clear` | Wipe conversation history |

### Natural language intents (no exact CLI required)

In conversation mode, these phrases trigger real Bolt actions before free-form Grok chat:

| You say | Bolt does |
|---------|-----------|
| Good morning Bolt / morning briefing | Daily manager briefing (`morning`) |
| What should I do next? / what's next | Next actions stack |
| How are things? / status report | Manager status summary |
| Show the queue / posting queue | Queue status |
| Research status / research candidates | Research summary |
| Mission status / command center | Mission status |

Anything else is answered by Grok with personality + conversation history.

Inside conversation mode:

- Ask Bolt a normal question or give a normal instruction in plain language.
- Type or say `exit`, `quit`, `bye`, or `goodbye` to end the conversation.

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
| `queue` | `postqueue`, `post-queue`, `ready-queue` |
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
