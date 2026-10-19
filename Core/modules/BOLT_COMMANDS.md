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

Grok (the coding session) is Bolt’s teacher — see repo-root `AGENTS.md`. This section is Bolt’s **runtime** brain: how the student calls models. Conversation, titles, and Nexus go through `Core/modules/LLM_Handler.py` + `LLM_Budget.py`. OpenAI and Ollama are fallbacks, not other teachers.

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
Bolt_TTS_PROVIDER=macos          # macos = Siri Voice 3; edge = Andrew
Bolt_VOICE=Voice 3               # Siri Voice 3 (`say -v ?`)
Bolt_EDGE_VOICE=en-US-AndrewNeural
```

Quick health check:

```bash
bolt budget                      # mode, soft cap, alert channels
bolt alerts                      # Mac/Voice/email/iMessage readiness (PARTIAL)
bolt checklist                   # Pre-stream voice checklist readiness (PARTIAL)
bolt reminders                   # Apple Reminders.app delivery readiness (PARTIAL)
bolt photo-ocr                   # Photo/handwriting OCR readiness (PARTIAL)
bolt word                        # Dictionary / spellcheck / thesaurus (READY)
bolt compress                    # HandBrake clip compress readiness (PARTIAL)
bolt performance                 # Local import/startup baseline readiness (PARTIAL)
bolt filter-backlog               # Clip backlog score filter readiness (PARTIAL)
PYTHONPATH=Core python3 -m modules.LLM_Handler
bolt gemini status               # optional Gemini REST client (soft-fail; Nexus opt-in separate)
bolt obs status                 # OBS WebSocket readiness (soft-fail; folder-watch still works)
bolt streamlabs status          # Streamlabs Socket API readiness (soft-fail; optional)
bolt chat status                # Twitch chat readiness (soft-fail; respects use_twitch)
bolt vods status                # VOD / highlight deps (creds, yt-dlp, ffmpeg; soft-fail)
bolt store status               # Storefront + ASIN HTML verify readiness (soft-fail)
bolt sites status               # Local site-data + storage cron readiness (soft-fail)
bolt pages status               # Cloudflare Pages readiness (PARTIAL; soft-fail)
bolt license status             # Repo LICENSE / README placeholder (PARTIAL; soft-fail)
bolt brain status               # Legacy Brain_Controller readiness (compat; Think_Learn_Decide canonical)
bolt merge-py status            # Local .py source-dump readiness (soft-fail; Data/merged_bot.py)
bolt titles status              # Title A/B trainer readiness (soft-fail; Data/viral_titles_model.json)
```

## Core commands

Inspect, launch, and maintain Bolt itself.

```bash
bolt help                         # Show the CLI command summary
bolt version                      # Show the repository and Python in use
bolt verify                       # Check required files, folders, config, and environment
bolt doctor [--json]              # Live vs mocked vs stale path / missing key
bolt health [status|list|run]     # Lightweight health smoke (PARTIAL; soft-fail; prefer doctor)
bolt merge-py [status|run] [--dry-run|--list] [-o PATH]
                                      # Concatenate local .py → Data/merged_bot.py
                                      # aliases: merge_py, merge-sources; soft-fail
                                      # Bare merge-py = status; write: merge-py run
bolt titles [status|train|ab] [--json] [--dry-run] [--days N] [--game NAME]
                                      # Local title A/B trainer (AI_Title_Generator)
                                      # aliases: title-train, train-titles; soft-fail
                                      # Bare titles = status; train writes Data/viral_titles_model.json
bolt audit                        # Alias for doctor
bolt setup                        # Finite setup check (config + keys); exits when done
bolt day [--decide|--voice|--quiet|--open|--process]
                                      # Default morning flow; --decide → queue review
bolt day --decide                     # Preferred: brief → queue decide
bolt day --decide --voice             # Decide, then hands-free voice
bolt week                             # This week / last week / do not suggest
bolt week set "topic" [--note "…"]    # William picks; Bolt stays on it
bolt week done "what shipped"         # Mark progress so next week isn't day one
bolt week paper [--open]              # One-page fridge sheet (goal + checkboxes)
bolt week rotate                      # Archive this week → last week
bolt week ban "idea" [--why "C5 no"]  # Never suggest this again
bolt stats [status|sync|tiktok|youtube] [--dry-run] [--json] [--probe]
                                      # Social readiness + TikTok/YouTube pull
bolt sites status [--json] [--probe]   # Local site-data + storage cron readiness
                                      # aliases: sites-status, site-status, storage-cron
bolt analytics [--days N] [--top N]
                                      # Summarize clip performance from Data/performance_outcomes.jsonl
bolt anomaly latest [--game NAME] [--dry-run|--no-save] [--z N] [--json]
bolt anomaly media/Recordings/FILE.mkv
                                      # Score a recording vs audio baseline.
                                      # `latest` / `recordings` = newest file in media/Recordings.
                                      # Don't type the docs' <recording> brackets — zsh treats < as redirect.
                                      # Aliases: anomalies, anomaly-detect
bolt predict --game G --trigger T [--platform P] [--days N] [--json]
                                      # Forecast 24h views from performance_outcomes.jsonl
bolt predict --queue [--limit N] [--days N] [--json]
                                      # Forecast for ready queue clips (Peak_Hour_Notifier insight)
                                      # Aliases: forecast, views-predict, predictive
bolt multi [status|plan|show|publish] …
                                      # Manual multi-platform posting plans (no upload)
                                      # Aliases: platforms, multi-publish
bolt enhance [--dry-run] [--limit N]
                                      # Smart_Trim → Text_Overlay on media/vertical_clips/
                                      # Writes media/vertical_clips_trimmed/ then media/vertical_clips_final/
bolt checkup [--open] [--json]        # Refresh Data/Bolt_data.js; --open → App/Bolt_Checkup.html
                                      # (aliases: dashboard, checkup-dashboard)
                                      # Dashboard opens with the Good Morning Bolt card (local data only)
bolt menubar                          # macOS menu bar (App/app.py via rumps)
bolt mac-app                          # local dist/Bolt.app assemble (PARTIAL; not notarized)
bolt mac-auto                         # launchd/cron/Shortcuts status (PARTIAL; William-specific)
bolt icloud                           # iCloud Drive multi-Mac sync status (PARTIAL; William-specific)
bolt game-config                      # Per-game sensitivity profiles used by the clip pipeline (READY)
bolt error-recovery                  # Pipeline retry/quarantine (PARTIAL; soft-fail)
bolt memsearch "words"               # search Bolt's local memory (READY; auto-rebuilds stale index)
bolt alerts                            # Mac/Voice/email/iMessage alerts (PARTIAL; not Discord)
bolt checklist                          # Pre-stream voice checklist (PARTIAL; mic/STT gated)
bolt reminders                          # Apple Reminders.app delivery (PARTIAL; Darwin/TCC gated)
bolt photo-ocr                          # Photo/handwriting OCR → editable .txt (PARTIAL)
                                      # Soft-fail; distinct from bolt ocr (video HUD)
bolt compress                          # HandBrake clip compress (PARTIAL)
bolt performance                       # Local import/startup baseline (PARTIAL)
                                      # Soft-fail; logs/performance/ via performance_baseline.py
                                      # Soft-fail; media/clips via compress_videos.sh
                                      # (aliases: menu-bar, menu_bar). Needs: uv sync --extra menubar
bolt ocr <clip> [--verbose]           # On-screen game-stat OCR (Video_Intelligence)
                                      # Feeds titles in bot.py Step C; aliases: video-ocr, extract-stats
                                      # Needs: uv sync --extra ocr + brew install tesseract
bolt amazon <ASIN|URL> […] [--focus …] [--platform tiktok] [--fetch-only] [--json]
                                      # Amazon product fetch + review plan (Amazon_Analyzer)
                                      # Same enrichment as bolt recordings --content-type review
                                      # Aliases: amazon-review, review-plan

```bash
bolt store                        # Storefront + ASIN verify readiness (default)
bolt store status [--json]        # Same; verify counts + soft-fail hint
bolt store add --name "…" --asin B0… [--category tech] [--notes "…"]
                                  # Verifies ASIN via HTML scrape by default
                                  # Amazon block → soft-fail (item still saved)
bolt store add … --no-verify      # Skip HTML verify
bolt store list                   # Storefront items (+ verify_status)
bolt store feature-next           # Next storefront feature candidate
```

bolt search "question" [--raw|--long|--json] [--limit N]
                                      # Live DuckDuckGo web search (+ optional LLM summary)
                                      # Aliases: web-search, websearch. Powers !Bolt chat search.
bolt word [status|define|spell|syn|ant|check] [word]
                                      # Dictionary / spellcheck / thesaurus (READY)
                                      # Local spell: /usr/share/dict/words + Data/word_extras.txt
                                      # Define/syn: free no-key APIs (soft-fail)
                                      # Aliases: dict, dictionary, define, spell, spellcheck, thesaurus
                                      # Distinct from bolt search (DuckDuckGo)
bolt overlay [--port 8766]            # OBS overlay server (Stream Deck kill/win + cam frame)
                                      # Thunderstone also has Aitum Vertical 1080x1920; see Docs/guides/OBS_VERTICAL.md

bolt obs [status] [--json] [--probe]
                                      # OBS WebSocket readiness (Stream_Monitor)
                                      # Soft-fail when OBS closed / no password / no websocket-client
                                      # Aliases: obs-status, stream-monitor
bolt obs-game [status|list|run] [--json] [--probe]
                                      # OBS scene→Core/config.json game auto-update (PARTIAL)
                                      # Soft-fail prefix: Game tracker unavailable:
                                      # status (default) / list / run [--once|--background]
                                      # Distinct from READY bolt obs (WebSocket status/monitor)
                                      # Aliases: obs_game, game-tracker, game_tracker,
                                      #   obs-game-tracker, obs_game_tracker, obs-game-status
bolt game [status|refresh|set|unpin|history] [--json]
                                      # Current game freshness (READY; Game_Refresh)
                                      # Stale warning after game_stale_days (default 7)
                                      # Aliases: game-refresh, game-status
bolt motion <video> [--top N] [--fast] [--json]   # Visual high-action windows (READY)
bolt wrap [--vod FILE] [--dry-run]    # Post-stream wrap: VOD → clips/reel/captions (READY)
bolt release <folder> --artist NAME   # Package songs for DistroKid/TuneCore/CD Baby (READY; no upload)
bolt streamlabs [status] [--json] [--probe]
                                      # Streamlabs Socket API readiness (donations/raids/subs)
                                      # Soft-fail without STREAMLABS_SOCKET_TOKEN / python-socketio
                                      # Aliases: streamlabs-status, slabs, streamlabs-monitor
bolt chat [status|connect] [--json] [--probe] [--force] [--voice]
                                      # Twitch chat readiness / connect (Bolt_Chat)
                                      # status never connects; connect respects use_twitch (or --force)
                                      # Aliases: twitch-chat, chat-status, bolt-chat
bolt brain [status|test] [--json]
                                      # Legacy Brain_Controller readiness (compat event API)
                                      # Think_Learn_Decide is canonical; this is NOT a second brain
                                      # Soft-fail without Think_Learn_Decide; state: Data/brain_state.json
                                      # Aliases: brain-status, brain_status, brain-controller
bolt launch                       # Start live mode (folder watch + optional OBS)
bolt launch --no-checklist        # Live mode without the pre-stream voice checklist
bolt checklist status             # Pre-stream checklist readiness (PARTIAL; soft-fail)
bolt reminders status             # Apple Reminders readiness (PARTIAL; soft-fail)
bolt photo-ocr status             # Photo/handwriting OCR readiness (PARTIAL; soft-fail)
bolt compress status               # HandBrake clip compress readiness (PARTIAL; soft-fail)
bolt performance status          # Local import/startup baseline readiness (PARTIAL; soft-fail)
bolt status                       # Check the decision engine, vector DB, and Nexus
bolt intelligence                 # Alias for `status`
bolt budget                       # xAI spend / soft cap / alert channel status
bolt api-usage                    # Alias for budget
bolt budget --test-alert          # Test Mac + email + iMessage alerts
bolt alerts status               # Preferred alert channels (PARTIAL; soft-fail)
bolt alerts test                 # Soft-fail fan-out test (same module)
bolt storage status               # media/ sizes + disk free + sites/cron readiness
bolt storage monitor|rotate|optimize
bolt sites status                 # scripts + crontab advisory (no crontab install)
bolt test                         # Run the full test suite
bolt test <unittest-arguments>    # Run selected unittest targets
bolt layout status|list|run     # PARTIAL soft-fail Layout unavailable:
bolt migrate-layout status|list|run  # PARTIAL soft-fail Migrate unavailable:
```

| Command | What it does |
|---------|--------------|
| `bolt verify` | Files, folders, config keys, `.env`, module imports |
| `bolt doctor` | Live vs mocked vs stale path / missing key (alias: `audit`) |
| `bolt layout` | Misplaced files at the repo root only |
| `bolt migrate-layout` | Plan/apply layout moves (`_layout_rules`); dry-run default |

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
bolt research pending --decide        # Answer every pending item in one pass (2nd answer won't vanish)
bolt research find                    # Web search from this week's topic (one of the four lanes)
bolt research find --lane product     # Override: pop-culture | gaming-tech | skincare | product
bolt research find --dry-run          # Preview gated names; write nothing
bolt research find "honest product reviewer YouTube" --limit 5
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
bolt research c5 keep 1 --why "Want that event path"
bolt research c5 drop 1 --why "already in this / not a creator"   # numbers refresh; next is also 1
bolt research pending --decide        # walk 1 and 2 in one sitting
bolt research c5                      # same as pending --decide
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
bolt mission start "first Amazon review" --no-nexus   # local evidence only
bolt mission fill latest                  # rebuild strategy from current evidence
bolt mission fill latest --no-nexus
bolt mission update latest --hours 6 --budget 50 --assets "OBS, mic"
bolt mission list
bolt mission show latest
bolt mission next                         # Section 13 only

# Aliases
bolt command-center …                     # Alias for `mission`
bolt ccc …                                # Short alias for `mission`
```

`bolt mission start` writes a **filled** 13-section briefing from the week
card, catalog, C5-kept examples, and profile limits. Nexus may overlay
strategy JSON when available; `--no-nexus` uses local evidence only. It
does not invent program URLs, earnings, or approvals, and it does not
post or purchase anything.

`bolt mission checkin` **prints** the five questions. It does not collect
answers. Typing the answers in conversation is not saved. Fill them as flags
on `start`, `bolt mission update latest --hours …`, or edit the mission
markdown. Voice `mission status` reads the latest file (including section 13)
— it does not write check-in fields.

Measurable result and target date are **research outputs**, not homework.
William’s year-end bar (2026-12-31) is: know what success looks like in this
profession, or have a roadmap with proof the work is leading somewhere. Blank
outcome fields are expected. Do not treat them as a missed assignment. Daily
`bolt day` / week card does not require a mission.

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
bolt manage posted "Mouse" --amazon --where "https://…"
                                      # Amazon-only is a real ship (no social required)
bolt manage posted "Mouse" --tiktok --youtube --x
                                      # only if you actually posted there
bolt manage ship "Mouse" --amazon     # ship == posted

bolt manage shipped
bolt manage import                    # read Docs/reviews/inbox
bolt manage import --open             # open that folder in Finder
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
bolt manage import [--dry-run] [--no-storefront] [--open]
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
| `bolt manage import` | Import Amazon reviews dropped in `Docs/reviews/inbox/` (alias: `inbox`) |


### Multi-platform manual plans (`Multi_Publisher`)

No-cost planner for TikTok / YouTube Shorts / Instagram Reels / Kick. Manual plans are READY — Peak_Hour_Notifier embeds a `platform_plan` when a clip is queued, and persists it to `Data/multi_platform_queue.json`.

**Auto-upload** (Kick / Instagram and all platforms here) is PARTIAL: `bolt multi publish` **never uploads**; it soft-fails with `Kick unavailable:` / `Instagram unavailable:` (and similar) and points at `bolt multi plan` / manual upload. Exit 0 on soft-fail (informational). TikTok Content Posting API remains separately paused.

```bash
bolt multi                        # readiness + newest saved plans
bolt multi status [--limit N] [--json]   # --json → readiness dict + queue summary
bolt multi plan <clip> "<title>" [--hashtags …] [--save QUEUE_ID] [--json]
bolt multi show <queue_id> [--json]
bolt multi publish <platform> [--clip PATH] [--title TITLE] [--json]
# platform: kick|instagram|instagram_reels|reels|ig|tiktok|youtube|shorts|…
```

| Command | What it does |
|---|---|
| `bolt multi` / `bolt multi status` | Readiness (`ready` = manual planner; `auto_upload` false) + recent plans from `Data/multi_platform_queue.json` |
| `bolt multi status --json` | Readiness dict + `queue` / recent items summary |
| `bolt multi plan CLIP TITLE` | Build captions/instructions (optional `--save`) |
| `bolt multi show QUEUE_ID` | Show one saved plan |
| `bolt multi publish PLATFORM` | Soft-fail auto-upload (`Kick unavailable:` / `Instagram unavailable:`); exit 0 |
| Aliases | `platforms`, `multi-publish` |

### Publishing and platform readiness

`post-dry-run` previews a TikTok post. `post` remains a dry run unless `--approve` is present.

YouTube / X catalog packages are **manual paste by design** (Studio / compose UI). They do **not** call the YouTube Data API or X API.

```bash
bolt manage post-dry-run "Headset"
bolt manage post "Headset" [--video /path/to/video.mp4]
bolt manage post "Headset" --approve [--video /path/to/video.mp4]
bolt manage tiktok-status
bolt youtube-pkg "Headset"                 # paste-ready plain text (default)
bolt youtube-pkg "Headset" --json          # machine JSON
bolt youtube-pkg "Headset" --save          # also write Data/manual_packages/*.txt + .json
bolt manage youtube-pkg "Headset"          # same handlers
bolt manage youtube-status
bolt x-pkg "Headset"
bolt x-pkg "Headset" --json --save
bolt manage x-pkg "Headset"
bolt manage x-status
```

| Command | What it does |
|---------|--------------|
| `bolt manage post-dry-run "Name"` | Preview a TikTok post without sending anything live |
| `bolt manage post "Name"` | Default: dry-run only; refuses to publish |
| `bolt manage post "Name" --approve` | Actually publish to TikTok (still requires `--video` if no draft video) |
| `bolt manage tiktok-status` | Show whether the TikTok publisher is configured and ready |
| `bolt youtube-pkg "Name"` | Paste-ready YouTube Studio package (title, description, tags, upload URL, next step). Default = plain text |
| `bolt youtube-pkg "Name" --json` | Same package as JSON |
| `bolt youtube-pkg "Name" --save` | Write `.txt` + `.json` under `Data/manual_packages/` |
| `bolt manage youtube-pkg "Name"` | Same as `bolt youtube-pkg` |
| `bolt manage youtube-status` | Manual package path ready; API upload still pending app review |
| `bolt x-pkg "Name"` | Paste-ready X compose package (post body + hashtags, upload URL, next step). Default = plain text |
| `bolt x-pkg "Name" --json` / `--save` | JSON and/or `Data/manual_packages/` write |
| `bolt manage x-pkg "Name"` | Same as `bolt x-pkg` |
| `bolt manage x-status` | Manual package path ready; API upload still pending |
| Aliases | `yt-pkg` → youtube-pkg; `twitter-pkg` → x-pkg |

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
| \`bolt social package "Name" [--platforms …]\` | Queue approval-gated packages; youtube/youtube_shorts/x use rich \`build_*_package\` paste fields; other platforms keep a short caption |
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
bolt queue decide --open-each         # Same, and open every clip as you go
#  — or one-liners without ids —
bolt queue next --open                # Show next clip card + open the video
bolt queue package                    # Paste-ready TikTok + Shorts captions (next clip)
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
bolt doctor                           # What's live, mocked, or on a stale path

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
bolt queue package [id] [--open]      # Paste-ready TikTok + Shorts package
bolt queue decide                     # Interactive review (no JSON)
bolt queue decide --open-each         # Interactive review; open each clip
bolt queue help                       # Full queue CLI help

# In decide mode: o=open  a=approve  p=post now  m=mark posted
#                 h=hold  t=retitle  s=skip  1-9=jump  q=quit

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

bolt queue held                       # List held clips + reasons (not deleted)
bolt queue unhold 55a802e8            # Put a held clip back on the postable list
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
| `bolt queue package [id] [--open]` | Paste-ready TikTok + Shorts captions for a clip (manual upload) |
| `bolt queue decide [--open-each]` | Interactive open → approve / hold / post / skip |
| `bolt queue held` | List held clips and why they were held |
| `bolt queue unhold [clip_id]` | Restore a held clip to the postable list |
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

`bolt manage youtube-pkg` is for catalog **product reviews** only (Mouse, etc.). For gameplay clips, use `bolt queue package`.

## Clip review board

Local board for the ranked queue. It does **not** approve, post, or mark posted. Public auto-posting stays on; Keep must not trigger it.

```bash
bolt review                          # http://127.0.0.1:8767 and open a browser
bolt review --no-open                # print the URL only
bolt review --port 8767
```

| Control | What it does |
|---------|--------------|
| Keep | Records taste via `learn_from_feedback("queue_clip", accepted=True)`. Status and `auto_post` stay unchanged. |
| Toss | `reject_next_clip(reason, clip_id)` — hold, `Data/post_rejections.jsonl`, and the existing learning path. A reason is required. |
| Undo | `unhold_clip(clip_id)` puts a held clip back on the queue. |

Opened as a file (`App/Clip_Review.html`), the page is read-only. Toss copies `bolt dontpost <id> "<reason>"`. Undo copies `bolt queue unhold <id>`. Keep has no safe shell command — use `bolt review`.

Thumbnails are the `.jpg` `bolt thumbnails` writes next to a clip. Paths in the queue may be absolute Mac paths; the board resolves them inside the repo and will not serve a file outside it.

Checkup shows a Clip review card from `Bolt_DATA.review` after `bolt checkup`. Ranking does **not** read keep/toss yet. That is a later upgrade.

## Post-to-TikTok web UI

Local browser screen for a compliant TikTok export. Demo mode is safe without a token.

```bash
bolt tiktok-post                  # Auto: live creator if token ready, else honest DEMO mock
bolt tiktok-post --demo           # Force mock creator (audit film; publish is dry-run)
bolt tiktok-post --live           # Require real token; soft-fails with auth hint if not ready
bolt tiktok-post status           # Token / API readiness (no server)
bolt tiktok-post --no-open        # Print the URL only; do not open a tab
bolt tiktok-post --port 8080
```

Aliases: `post-ui`, `tiktok_post`, `tiktok-ui`. Demo mock uses username `bolt_demo_not_real` / nickname `[DEMO] Bolt Audit Mock` — never looks like a real account. Live publish still needs `TIKTOK_API_ENABLED=true` + approved Content Posting API + `bolt tiktok_token`.

| Command | What it does |
|---------|--------------|
| `bolt tiktok-post` | Open the local Post-to-TikTok UI (auto demo/live) |
| `bolt tiktok-post --demo` | Force mock creator; publish is dry-run (audit-safe) |
| `bolt tiktok-post --live` | Require a real token; exits with auth hint if not ready |
| `bolt tiktok-post status` | API/token readiness (no Flask server) |
| `bolt tiktok-post --no-open` | Start the server and print the URL only |

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

## How to reply to Bolt

Conversation, voice, and `## Comments` on a briefing are a **front-end** for
the same writes as the CLI. Intent router + `bolt week` / `bolt mission`
stay the source of truth. No second brain.

`bolt morning` and `bolt briefing` both write
`Docs/briefings/daily/latest_morning.md` (plus a dated `morning_YYYY-MM-DD.md`
copy). They overwrite each other. Comments on the *previous* file are applied
once (writes first, leftover as a memory note) when the next briefing runs.


## Source merge dump (`bolt merge-py`)

Maintenance / audit helper — concatenates local Bolt `.py` sources into one dump for LLM context or offline review. **Not** an executable bot.

```bash
bolt merge-py                         # status (default; safe)
bolt merge-py status [--json]
bolt merge-py --dry-run               # count files/bytes, no write
bolt merge-py --list                  # relative paths only
bolt merge-py run                     # write Data/merged_bot.py
bolt merge-py run -o /tmp/bolt_dump.py
```

| Command | What it does |
|---|---|
| `bolt merge-py` / `bolt merge-py status` | Readiness: file count + default output path (soft-fail `Merge unavailable:`) |
| `bolt merge-py --dry-run` | Preview merge size without writing |
| `bolt merge-py --list` | Print included relative `.py` paths |
| `bolt merge-py run` | Write `Data/merged_bot.py` (excludes vendor/cache/media/learning) |

Aliases: `merge_py`, `mergepy`, `merge-sources`. Soft-fail prefix: `Merge unavailable:`.

The **canonical** shared journal / briefing / todo / how-to is Google Drive, not a second markdown handbook. IDs: `Core/config.json` → `google_drive_handbook`. Pointer: `Docs/GOOGLE_DRIVE_HANDBOOK.md`. Daily loop: local `bolt briefing` / `bolt morning` write markdown **and** append a Bolt briefing section to today's Daily Log in `02_Daily_Operations` when Drive OAuth is present (one-time `bolt drive-auth`; check with `bolt drive status`). Lessons in `06_Learnings`.

| You want to… | Say this (or still use the CLI) |
|---|---|
| Unpause / say you’re back | “I’m ready to continue” (keeps this week’s topic) or “this week is tech” |
| Log what shipped | “this shipped: posted the earbuds hook” / “I posted the tech clip” |
| Fridge / show husband | `bolt week paper --open` then print. Goal + checkboxes. Not the mission. |
| Answer mission check-in | “hours: 6, budget 40” / “I have 6 hours” / “assets: OBS, iPhone” (latest mission) |
| Leave a note Bolt should remember tomorrow | “remember: filming after Randy’s lunch” |
| Comment on a briefing | Write under `## Comments` on `latest_morning.md`. Write-intent lines are applied on the next `bolt briefing`. Leftover lines stay a memory note. |

CLI still works: `bolt week set` / `bolt week done` / `bolt mission update latest`.

## How Bolt talks (`bolt voice` / `bolt voice --text`)

A clear command still runs the real action: "what's this week", "show the queue", "add task …" once that exists. A longer thought that only mentions those words goes to the conversation, not the command.

Bolt thinks first (a private plan William does not hear), then answers like a teammate: it says what it understood, adds an idea or a next step, and can offer to capture a task or page. It does not claim the vault write happened until William says yes.

Voice stays short and spoken. `bolt voice --text` can be longer and keep a little formatting. The running summary of older turns is stored next to the voice history.

```bash
bolt voice --text
# I keep meaning to film the K&F short but Thursday clashes with Randy's shift.
```

Quick capture waits for yes. Nothing is written on the preview.

```bash
bolt voice --text
# add task film the K&F short by Friday
# yes
# note: podcast idea about a gear episode
# no
# undo that
```

"change it to Saturday" edits the preview. "remember:" still goes to memory, not the vault. Unsure tasks land in `00 Inbox`. Times are spoken in CT.

After a conversation, Bolt can pull tasks or a page out of it. That uses a longer planning call (Ollama in light mode unless a paid planning call is allowed). Nothing is written until William picks.

```bash
bolt voice --text
# turn this into tasks
# only 1 and 3
# make a page from this
# yes
# none
```

"yes" saves the whole list. "only 1 and 3" or "just 2" saves those. "no" or "none" saves nothing. "undo that" parks the notes from that save together.

Filing uses rules first (review → Product Testing, podcast → Creator HQ, and the rest of the area table), then a correction William already taught, then a product name that matches an existing note title. Two matches means Inbox. The preview names related notes, and yes writes those as wikilinks.

```bash
bolt voice --text
# add task film the K&F short by Friday
# no, put that in Product Testing
# yes
# no, that's Personal
```

"no" alone cancels. "no, put that in …" or "no, that's …" changes the area and Bolt reuses that word next time. Tasks stay in `10 Bolt/Tasks/`. Notes and pages move to the area folder; the old file is parked, not deleted. `BOLT_VAULT_FILING_AI=on` lets the model pick when the rules are unsure (`auto` asks only if a provider is already reachable, `off` stays local). Corrections live in `BOLT_VAULT_FILING_PATH` or `Data/memory/vault_filing_memory.json`.

The kanban note `10 Bolt/Bolt Board.md` follows task status. Dragging a card in Obsidian wins the next time Bolt reads the board. "move X to Doing" previews first. Tasks Bolt adds show up as cards. Done is the complete lane. A note that is not a kanban board is left alone.

```bash
bolt voice --text
# what's on my board?
# move the K&F short to Doing
# yes
```

If two cards match, Bolt asks which number. "undo that" puts the card and the task status back.

Budget knobs, all optional: `BOLT_CHAT_THINK` (default on), `BOLT_CHAT_THINK_PAID` (`auto`, `on`, `off`), `BOLT_CHAT_REPLY_TASK` (default `chat`, so everyday replies stay on the light-mode model), `BOLT_CHAT_HISTORY_TURNS` (default 12), `BOLT_CHAT_MAX_TOKENS_TEXT`, `BOLT_CHAT_MAX_TOKENS_VOICE`.

## Obsidian vault (`bolt vault`)

William's notes live in the Obsidian vault, not in Notion. Bolt reads and writes them only through `Core/modules/Vault_Store.py`.

```bash
bolt vault                          # status: path, counts, last change
bolt vault list --kind task
bolt vault find "K&F"
bolt vault add "Film K&F short" --area "Product Testing" --due 2026-10-23
bolt vault undo                     # last change; new notes are parked, not deleted
```

Path: `BOLT_VAULT_PATH`, or `vault_path` in `Core/config.json`, or `/Users/carter/Documents/Obsidian/Bolt Vault`. Bolt does not create that folder. If the folder is there, Bolt creates any missing `10 Bolt/Tasks/`, `10 Bolt/Calendar/`, `10 Bolt/Bolt Board.md`, `10 Bolt/Plan Timeline.md`, and `10 Bolt/Bolt Activity Log.md`. Files that already exist are updated, never replaced.

Times Bolt says out loud use America/Chicago and the label CT. `10 Bolt/Bolt Calendar.md` is an index, not an event.

## Title A/B trainer (`bolt titles`)

Local learning loop: read titled rows from `Data/performance_outcomes.jsonl`,
update category/template averages in `Data/viral_titles_model.json`, then bias
`generate_title()` / `propose_ab()`.

```bash
bolt titles                           # status (default; safe)
bolt titles status [--json]
bolt titles train [--dry-run] [--days N]
bolt titles ab "your title" [--game "Hades 2"] [--json]
```

| Command | What it does |
|---|---|
| `bolt titles` / `bolt titles status` | Readiness: titled outcomes + model path (soft-fail `Title trainer unavailable:`) |
| `bolt titles train` | Learn from outcomes → write `Data/viral_titles_model.json` |
| `bolt titles train --dry-run` | Show category averages without writing |
| `bolt titles ab "…"` | Propose A/B title variants (optionally keep base as A) |

Aliases: `title-train`, `train-titles`. After posting, `bolt watch status               # Folder watch readiness (PARTIAL)
bolt log-perf` / `bolt stats` then `bolt titles train`.


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
bolt clip-dedupe                            # status (PARTIAL soft-fail; SHA256)
bolt clip-dedupe run [--dry-run] [--scan DIR] [--check FILE]
bolt filter-backlog                         # status (PARTIAL soft-fail)
bolt make-highlights                       # status (READY; soft-fail; former SHELL)
bolt make-highlights run [--list][--count N]   # → media/output/YYYY-MM-DD_highlight_reel.mp4
bolt reprocess                             # status (READY; soft-fail)
bolt reprocess run [NAME] [--dry-run] [--force]   # → media/vertical_clips + merged queue
bolt health                                # status (PARTIAL soft-fail; former SHELL)
bolt health run [--dry-run]
bolt watch                              # status (PARTIAL soft-fail)
bolt watch run [--once] [--folder PATH]  # start loop (prefer bolt launch)
```

`recordings` defaults to **`latest`** (not `all`) and gaming content. Same-stem
duplicates (`.mp4` / `.mov` / `.mkv`) are collapsed to one file. Already-processed
names in `Data/processed_recordings.json`
are skipped unless you pass `--force`.

`--content-type review|skincare|tech` injects `content_type` into config for
`bot.py`. Before titles, the pipeline runs a lane analyzer once per recording:

- **skincare** — **Skincare_Analyzer**; `config.skincare_products` +
  `skincare_goal` / `review_angle`, or Content_Manager `skincare` lane items.
- **tech** — **AI_Analyzer**; `config.tech_url` + `tech_query` / `tech_params`,
  or a tech-lane catalog item (ASIN → Amazon URL).
- **review** — **Amazon_Analyzer**; `config.review_products` / `review_asin` /
  `amazon_url`, or tech-lane catalog ASINs/URLs. Page fetch + Nexus review plan.
  Standalone: `bolt amazon <ASIN|URL> […]` (aliases: `amazon-review`,
  `review-plan`). `--fetch-only` skips Nexus. Store ASIN verify via
  `bolt manage` still uses the same fetch helper.
- Analyzer / Nexus / missing-input / Amazon-block failures **warn and continue**;
  clips still cut.
- Advice is passed into Title_Generator context (`content_analysis`).

Highlight detection is intentionally strict (local peaks, prominence, confidence
floor, min gap, candidate cap). Tune in `Core/config.json` under `highlight` and
`max_highlight_candidates` / `max_clips_per_session`.

`auto-clip-twitch` is an alias for `auto_clip_twitch`.
`vod_download` is an alias for `vods`. Soft-fail readiness: `bolt vods status`
(covers download + auto-clip deps). Missing yt-dlp on download paths →
`VOD unavailable: …` (exit 1, no traceback). Empty `media/clips/` on
`bolt highlights` → `Highlight reel unavailable: …` (points at `media/clips/` /
`bolt recordings`).

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
| `bolt highlights` | Compile the top clips into a Twitch highlight reel (READY thin SCRIPT_MAP → `make_twitch_highlights.py`; soft-fail status is `bolt make-highlights`) |
| `bolt thumbnails [dir…]` | Generate JPG thumbnails for clips in the given directories |
| `bolt clip-dedupe` | SHA256 media hash scan (**PARTIAL**; soft-fail `Hash dedupe unavailable:`) — `status` / `list` / `run [--dry-run]`; writes `Data/media_hash_db.json`; aliases `clip_dedupe`, `hash-dedupe`, `dedupe-status`, `sha-dedupe`; **distinct from** READY pipeline `Clip_Deduplicator` (`Data/seen_clips.json`) |
| `bolt filter-backlog` | Clip backlog score filter (**PARTIAL**; soft-fail `Backlog unavailable:`) — `status` / `list` / `run [--dry-run]`; aliases `filter_backlog`, `backlog-filter` |
| `bolt make-highlights` | Local highlight reel stitch (**READY**; soft-fail `Highlights unavailable:`) — `status` / `list` / `run [--list][--count N]`; aliases `make_highlights`, `stitch-highlights`; engine `make_twitch_highlights.py` (READY thin compile stays `bolt highlights`) |
| `bolt reprocess` | Vertical rebuild + multi-platform queue (**READY**; soft-fail `Reprocess unavailable:`) — `status` / `list` / `run [NAME] [--dry-run] [--force] [--limit N]`; aliases `reprocess_clips`, `reprocess-clips`, `reprocess-status`, `vertical-reprocess`, `tiktok-reprocess`; engine `reprocess_clips.py` (no TikTok auto-upload; distinct from READY `bolt recordings` / `enhance` / `multi`) |
| `bolt health` | Lightweight post-reorg health smoke (**PARTIAL**; soft-fail `Health check unavailable:`) — `status` / `list` / `run [--dry-run]`; aliases `health-check`, `health_check`, `health-status`, `system-health`; engine `health_check.py` (prefer READY `bolt doctor` / `bolt verify`) |
| `bolt watch` / `status` | Folder watch readiness (PARTIAL; soft-fail `Watch unavailable:`) |
| `bolt watch list` | Checklist + pending recordings (`Data/processed_recordings.json`) |
| `bolt watch run` | Start folder watch loop (prefer `bolt launch` for live mode) |

## Streamlabs Socket API

Optional live donation/raid/sub/bits/host events (`Streamlabs_Monitor`). Soft-fails without python-socketio / token. Folder-watch still works.

```bash
bolt streamlabs                       # status (default)
bolt streamlabs status [--json] [--probe]
```

| Command | What it does |
|---------|--------------|
| `bolt streamlabs` / `bolt streamlabs status` | python-socketio / `STREAMLABS_SOCKET_TOKEN` readiness (no long-lived connect) |
| `bolt streamlabs status --probe` | Short live Socket.IO connect (hard timeout; disconnects) |
| Aliases | `streamlabs-status`, `slabs`, `streamlabs-monitor` |

Token once: `STREAMLABS_SOCKET_TOKEN=…` from streamlabs.com/dashboard → Settings → API Settings → Socket API. Optional thresholds: `MIN_RAID_SIZE`, `MIN_BITS`, `MIN_DONATION_USD`.

## Twitch chat bot

Optional live IRC personality (`Bolt_Chat`). Off by default (`use_twitch: false`). Soft-fails without twitchio / token.

```bash
bolt chat                         # status (default; never connects)
bolt chat status [--json] [--probe]
bolt chat connect                 # start bot (needs use_twitch: true)
bolt chat connect --force         # ignore use_twitch: false
bolt chat connect --voice         # also speak reactions
```

| Command | What it does |
|---------|--------------|
| `bolt chat` / `bolt chat status` | twitchio / `use_twitch` / token / channel readiness (no IRC) |
| `bolt chat status --probe` | Same + local probe_ok detail (still no IRC login) |
| `bolt chat connect` | Start background IRC bot; Ctrl+C to stop |
| `bolt chat connect --force` | Connect even when `use_twitch` is false |
| Aliases | `twitch-chat`, `chat-status`, `bolt-chat` |

Token once: `TWITCH_BOT_TOKEN=oauth:…` from https://twitchapps.com/tmi/ plus `TWITCH_BOT_NAME` + `TWITCH_CHANNEL`. Enable in `Core/config.json` with `"use_twitch": true`.

## Brain_Controller (legacy event compat)

Compat wrapper around the older highlight/raid/sub decide + speak/chat/notify API.
**Think_Learn_Decide is the canonical decision path** — Brain_Controller is not a second brain.
Live bot path should keep calling Think_Learn_Decide. Soft-fails when Think_Learn_Decide is missing
(decide/record no-op). State file: `Data/brain_state.json`.

```bash
bolt brain                        # status (default)
bolt brain status [--json]
bolt brain test                   # event-test demo (legacy decide path)
```

| Command | What it does |
|---------|--------------|
| `bolt brain` / `bolt brain status` | Thresholds / TLD availability / state path readiness |
| `bolt brain status --json` | Same as JSON |
| `bolt brain test` | Run the legacy event-test demo |
| Aliases | `brain-status`, `brain_status`, `brain-controller` |

## Twitch VOD downloads and authentication

Readiness surface (soft-fail; never raises / never hangs):

```bash
bolt vods status                  # creds / channel / yt-dlp / ffmpeg (default readiness)
bolt vods status --json
bolt vods status --probe          # also ping Helix (informational if ready)
```

Needs `TWITCH_CLIENT_ID` + `TWITCH_CLIENT_SECRET` + `TWITCH_CHANNEL` in `.env`.
`ready` = those three present. yt-dlp is resolved from the Bolt venv first, then PATH
(`brew install yt-dlp` is fine). ffmpeg must **actually start** — Homebrew's PATH
`ffmpeg` often exists and then crashes on a missing dylib; Bolt uses `ffmpeg-full`
via `FFmpeg_Bin` (`BOLT_FFMPEG` override). Missing creds / channel / tools print
`VOD unavailable: …` and exit 1 on download (no traceback). Status always exits 0.

Do not type the docs' `<channel>` brackets — zsh treats `<` as a redirect.

Download / sample. Public archives go through yt-dlp (signed playlist). A Twitch
user token is **not** required for those. Raw ffmpeg HLS is a fallback and often
403s. `--user-token` is only for subscriber-only VODs / that fallback.

```bash
bolt vods status
bolt vods list --limit 10
bolt vods --dry-run --limit 10
bolt vods download --limit 3 --sample-minutes 5
bolt vods --channel itssimplybilly --type archive --limit 10 --sample-minutes 5
          [--output-dir directory] [--metadata-file file] [--skip-existing]
          [--user-token token]
bolt twitch_token
bolt twitch_bot_token
bolt tiktok_token [--client-key <key>] [--client-secret <secret>] [--redirect-uri <uri>]
                  [--scopes "user.info.basic,video.list,video.publish,video.upload"]
bolt youtube_token [--client-id <id>] [--client-secret <secret>] [--redirect-uri <uri>]
bolt drive-auth                      # one-time Google Drive/Docs consent (Daily Log)
bolt drive status                    # Drive/Docs readiness (--json|--probe; soft-fail)
bolt gcal-auth                       # one-time Google Calendar consent (briefing)
bolt gmail-auth                      # one-time Gmail read consent (briefing)
bolt gcal status                     # Calendar token readiness (no browser)
bolt gmail status                    # Gmail token readiness (no browser)
```

Token commands are interactive and may open a browser or prompt for credentials. Google Calendar / Gmail / Drive use `Core/credentials.json`; tokens live under `Data/` (`google_token.json`, `gmail_token.json`, `google_drive_token.json`). Briefing/morning never open a browser — soft-skip until the matching `bolt *-auth` has been run once.

| Command | What it does |
|---------|--------------|
| `bolt vods status` | Creds / channel / yt-dlp / **working** ffmpeg readiness (`--json` / `--probe`) |
| `bolt vods list` | List recent VODs and planned sample windows (no download). Alias: `--dry-run` |
| `bolt vods` / `bolt vods download` | Download VOD samples via yt-dlp + ffmpeg-full (not raw HLS) |
| `bolt twitch_token` | Get an OAuth token for the Twitch chat account (interactive) |
| `bolt twitch_bot_token` | Get an OAuth token for the Bolt bot account (interactive) |
| `bolt tiktok_token` | Get a TikTok OAuth token; include `video.list` scope for stats sync |
| `bolt youtube_token` | Get a Google/YouTube OAuth token (`youtube.readonly`) for stats sync |





## ICS calendar (`bolt calendar`) — PARTIAL

Local RFC 5545 feeds under `Data/calendar/` via soft-fail CLI. Prefix: `Calendar unavailable:`.

| Command | Purpose |
|---------|---------|
| `bolt calendar status` | Readiness (`--json` / `--probe`) |
| `bolt calendar list` | Engine + output dir + feed files |
| `bolt calendar run` | Write four `.ics` feeds |
| `bolt calendar run --dry-run` | Plan feeds without write |
| `bolt calendar run --days 14` | Limit scheduled_posts lookahead |

Aliases: `ics`, `ics-calendar`, `ics_calendar`, `generate-calendar`, `generate_calendar`, `calendar-status`.

**Distinct from** READY Google Calendar OAuth (`bolt gcal` / `bolt gcal-auth`). Stay PARTIAL (subscribe/host optional). Thumbnails stay READY via `bolt thumbnails`.

Former thin SCRIPT_MAP: `bolt calendar` → `scripts/generate_calendar.py`.

## Refresh memory (`bolt refresh-memory`) — READY

**READY (18 Oct 2026).** Rebuild `Data/memory_index.json` (local, no keys). Writes atomically (temp + swap), re-reads the file to verify the entry count, and prints before/after counts + time. `status` shows whether the index is stale vs the newest memory source (same check as `bolt memsearch`). Soft-fail prefix: `Memory refresh unavailable:`.

| Command | Purpose |
|---------|---------|
| `bolt refresh-memory status` | Readiness + freshness (`--json` / `--probe`) |
| `bolt refresh-memory list` | Engine + sources + index meta + fresh/stale |
| `bolt refresh-memory run` | Rebuild index |
| `bolt refresh-memory run --dry-run` | Count entries without write |
| `bolt refresh-memory run --if-stale` | Rebuild only when stale (else reports up to date) |

Aliases: `refresh_memory`, `memory-refresh`, `memory_refresh`, `refresh-index`, `refresh_index`, `refresh-memory-status`.

**Distinct from** READY in-process `Memory_Index.retrieve_memory` used by briefings and **READY `bolt memsearch`** (search CLI; rebuilds the index itself when stale). No sources → valid empty index + note.

Former thin SCRIPT_MAP: `bolt refresh_memory` → `scripts/refresh_memory_index.py`.

## Long-term memory (`bolt memory`) — READY

`Core/modules/Bolt_Memory.py` — Bolt's long-term memory. **READY (18 Oct 2026 ~11:40 PM CT).**
Prefix: `Bolt memory unavailable:`.
**Distinct from** READY in-process `Memory_Index.retrieve_memory` (briefings),
**READY `bolt refresh-memory`** (index rebuild → `Data/memory_index.json`), and
**READY `bolt memsearch`** (word search over the same index, no LLM).

```bash
bolt memory                         # status (default; safe)
bolt memory status [--json] [--probe]
bolt memory list [--json]
bolt memory recall "what game am I streaming?"          # answer from memory
bolt memory recall --provider ollama "question"         # pin xai|grok|ollama|openai
bolt memory recall --no-search --json "question"
bolt memory "question"                                  # bare text → recall
bolt memory remember "fact" [--section "Recent Notes"]
bolt memory remember --fact "..."
bolt memory load [--json]
bolt memory-status                  # alias → status
```

| Command | Purpose |
|---------|---------|
| `bolt memory` / `status` | Memory paths + recall readiness: budget mode, provider order (e.g. xai → ollama → openai), XAI_API_KEY / Ollama / OPENAI_API_KEY (redacted) |
| `bolt memory list` | Rows for each memory path + each provider |
| `bolt memory recall` | Answers from Data/ memory + live state (today, current game from `Core/config.json`) + matched `bolt memsearch` hits, via `LLM_Handler` (follows `BOLT_LLM_MODE`; falls through providers). Grok/OpenAI get the full tree (`BOLT_MEMORY_CLOUD_CHARS`, default 60000); Ollama gets a trimmed prompt (`BOLT_MEMORY_LOCAL_CHARS`, default 9000). Prints which provider/model answered. No provider → soft-fail with what to set |
| `bolt memory remember` | Dated fact at the top of the exact `## section` (created if missing); same-day duplicates skipped; verified temp write copied into place (Finder tags kept); refreshes the memory index |
| `bolt memory load` | Dump `load_all_memory` (local; no LLM) |

Aliases: `bolt-memory`, `bolt_memory`, `memory-status`, `memory_status`, `long-term-memory`, `ltm`.

Engines also used in-process by Intent_Router / Week_Card / Brain_Controller / Peak_Hour (`remember`). `LLM_Handler.ask_llm(..., provider=X, fallback=False)` tries only X (default `fallback=True` unchanged).

## Folder watch (`bolt watch`) — PARTIAL

Soft-fail CLI around `Core/modules/Watcher.py` (former thin SCRIPT_MAP `scripts/Watcher.py`). Soft-fail prefix: `Watch unavailable:`. **PARTIAL** — long-running / media gated. **Prefer READY `bolt launch`** for live mode and **`bolt recordings`** for one-shot process.

```bash
bolt watch                         # status (default; safe)
bolt watch status [--json] [--probe]
bolt watch list [--json] [--limit N]
bolt watch run [--once] [--folder PATH]
bolt watch-status                  # alias → status
```

| Command | What it does |
|---|---|
| `bolt watch` / `status` | Soft-fail readiness (engine / recordings folder / processed log) |
| `bolt watch list` | Checklist + pending recording paths |
| `bolt watch run` | Start watch loop (Ctrl+C to stop); `--once` prints pending only |

Aliases: `watch-status`, `folder-watch`, `watch-folder`. Engine persists processed names to `Data/processed_recordings.json`.

## Log perf — manual learning logger (`bolt log-perf`)

PARTIAL soft-fail CLI around `scripts/log_clip_performance.py` (former thin SCRIPT_MAP `log_perf`).
Writes `Data/performance_outcomes.jsonl` + `Data/clip_history.json` for Clip_Ranker.
**Distinct from READY `bolt stats`** (YouTube/TikTok API pull). While TikTok API is paused, this is the TT/X manual path.

```bash
bolt log-perf                         # status (default)
bolt log-perf status [--json] [--probe]
bolt log-perf list [--json]           # readiness checklist
bolt log-perf run --list              # recent logged rows
bolt log-perf run --trigger ace --views 15000 --likes 1200
bolt log-perf run                      # interactive prompt
bolt log_perf --trigger ace --views 15000   # back-compat (flags ⇒ run)
```

Soft-fail: `Log perf unavailable:`. Aliases: `log_perf`, `log-performance`, `log_performance`, `perf-log`, `log-perf-status`.

| Command | What it does |
|---|---|
| `bolt log-perf` / `status` | Soft-fail readiness (engine / Clip_Ranker / outcomes file) |
| `bolt log-perf list` | Checklist of logger gates |
| `bolt log-perf run …` | Log views/likes (or `--list` recent rows / interactive) |

Stay PARTIAL — manual learning input, not stranger-ready API sync.


## Platform stats sync (auto learning loop)

Pull real views/likes from TikTok or YouTube into `Data/performance_outcomes.jsonl`
(and clip history on first sight of each video). Preferred surface is **`bolt stats`**
(wraps the same Performance_Sync path as the older script aliases).

Missing YouTube tokens soft-fail with `Social stats unavailable: …` (status exits 0). While TikTok API is paused, use PARTIAL `bolt log-perf` for TT/X views (soft-fail `Log perf unavailable:`).

```bash
# Readiness + recent outcomes (default)
bolt stats
bolt stats status
bolt stats status --json             # machine-readable readiness
bolt stats status --probe            # optional YouTube dry-run ping

# Safe pull (no write) — preferred first try
bolt stats --dry-run                 # both platforms
bolt stats youtube --dry-run
bolt stats tiktok --dry-run          # soft-skips while TikTok API paused

# Live write into learning store
bolt stats sync                      # both (skips paused TikTok)
bolt stats youtube                   # YouTube only, live
bolt stats tiktok --min-age-hours 24

# Tokens (once)
bolt youtube_token                   # Google OAuth, youtube.readonly
bolt tiktok_token                    # needs video.list (not upload-only); API paused

# Legacy aliases (still work)
bolt sync_youtube_stats --dry-run
bolt sync_tiktok_stats --dry-run
```

| Command | What it does |
|---------|--------------|
| `bolt stats` / `bolt stats status` | Token readiness + recent outcomes (aliases: `social-stats`, `performance-sync`) |
| `bolt stats status --json` | Machine-readable readiness (soft-fail hints) |
| `bolt stats status --probe` | Same + optional YouTube dry-run ping |
| `bolt stats --dry-run` | Both platforms: fetch + match only; write nothing |
| `bolt stats youtube [--dry-run]` | YouTube/Shorts metrics → performance outcomes |
| `bolt stats tiktok [--dry-run]` | TikTok metrics (needs `video.list` scope) |
| `bolt stats sync` | Both platforms, live write |
| `bolt sync_tiktok_stats` | Legacy alias for TikTok pull |
| `bolt sync_youtube_stats` | Legacy alias for YouTube pull |

## Advice, reporting, and learning

```bash
bolt nexus status                    # Ollama / paid Grok / Gemini opt-in readiness
bolt nexus status --json
bolt nexus status --probe            # Optional live ping (uses a provider when ready)
bolt nexus "question" [--task-type <type>] [--complexity high|medium] [--paid]
# Free by default (Ollama). --paid allows xAI Grok API for that call.
# Soft-fails with error "LLM unavailable: …" (empty advice) when no provider.
# Gemini only if NEXUS_USE_GEMINI=true (off by default). Aliases: advice, nexus-status.
bolt gemini status                   # Gemini key / model / Nexus opt-in readiness
bolt gemini status --json            # Same as JSON
bolt gemini status --probe           # Optional live ping (uses quota when key set)
bolt gemini ask "one sentence tip for TikTok titles"
# Soft-fails with "LLM unavailable: …" when GEMINI_API_KEY missing (exit 1 on ask).
# Aliases: gemini-status, gemini_status. Nexus opt-in unchanged (NEXUS_USE_GEMINI=false).
bolt search "question" [--raw|--long|--json] [--limit N]
# Live DuckDuckGo (ddgs); summarizes for chat. --raw = hits only.
bolt word                                  # status (default; READY)
bolt word honest                           # spelling + definition + synonyms
bolt word define honest
bolt spell recieve
bolt word check "this sentance"
bolt thesaurus honest
bolt performance
bolt log_perf --trigger <trigger> --views <count> [--likes <count>] [--clip <file>]
              [--game "Game Name"] [--platform TikTok] [--note "text"]
bolt log_perf --list
bolt doctor [--json]
bolt weekly                                 # status (default; PARTIAL soft-fail)
bolt weekly status [--json] [--probe] [--days N]
bolt weekly list [--json]
bolt weekly run [--print] [--send] [--days N] [--dry-run] [--json]
bolt weekly --print|--send [--days N]        # legacy flags (same as run)
```

Running `bolt log_perf` without performance values starts its interactive prompt.
Prefer `bolt sync_tiktok_stats` / `bolt sync_youtube_stats` when tokens are configured;
use `log_perf` for manual entry or platforms without API pull (e.g. X).

| Command | What it does |
|---------|--------------|
| `bolt nexus status` | Nexus provider readiness (Ollama / paid Grok / `NEXUS_USE_GEMINI`; soft-fail) |
| `bolt nexus status --probe` | Optional live ping when a provider is configured |
| `bolt nexus "question"` | Ask Nexus for advice (free: Ollama; `--paid` = Grok API; Gemini opt-in only; soft-fail) |
| `bolt gemini status` | Gemini REST client readiness (key / model / `NEXUS_USE_GEMINI`; soft-fail) |
| `bolt gemini status --probe` | Optional live ping (quota only when key set) |
| `bolt gemini ask "…"` | Direct `ask_gemini`; exit 1 if reply starts with `LLM unavailable:` |
| `bolt search "question"` | Live web search (DuckDuckGo via `ddgs`) + optional LLM summary |
| `bolt word` / `status` | Dictionary / spellcheck / thesaurus readiness — local word list; **READY**. Aliases: `dict`, `spell`, `thesaurus`. Distinct from `bolt search`. |
| `bolt word honest` | Full card: spelling + definition + synonyms/antonyms |
| `bolt spell recieve` | Local spellcheck (edit-distance suggestions). `check` for a phrase |
| `bolt thesaurus honest` | Synonyms via Datamuse (soft-fail if offline) |
| `bolt performance status` | Local import/startup baseline readiness — `--json` / `--probe`; soft-fail `Baseline unavailable:`; **PARTIAL** (local diagnostic). Aliases: `baseline`, `perf-baseline`, `performance-baseline`. Distinct from `bolt analytics` / `bolt stats`. |
| `bolt performance list` | Checklist + recent `logs/performance/baseline_*.json` |
| `bolt performance run` | Soft-fail run engine → `logs/performance/`; `--dry-run` prints plan only |
| `bolt log-perf` / `status` | Soft-fail readiness for the manual learning logger (PARTIAL) |
| `bolt log-perf run …` | Manually log a clip's views/likes back to the ranker so it learns |
| `bolt log-perf run --list` | Show recent performance-log entries (most recent first) |
| `bolt doctor` | Audit live vs mocked vs stale paths / missing keys |
| `bolt weekly status` | Weekly insights readiness — `--json` / `--probe`; soft-fail `Weekly unavailable:`; **PARTIAL** (Memory/Nexus/alerts gated). Aliases: `monthly`, `week-insights`, `weekly-analysis`. Distinct from `bolt analytics` / `bolt briefing` / `bolt stats`. |
| `bolt weekly list` | Checklist + recent `Data/weekly_reports/weekly_*.md` |
| `bolt weekly run` | Soft-fail generate → print + save under `Data/weekly_reports/`; `--send` via Bolt_Alerts; `--dry-run` |
| `bolt learning status` | Browse local `Data/learning/` study notes readiness — `--json` / `--probe`; soft-fail `Learning unavailable:`; **study log only** (not product architecture). Aliases: `learn`, `notes`, `study-notes`. |
| `bolt learning list` | List chapter markdown stems/titles under `Data/learning/` (ignores `_TEMPLATE.md`) |
| `bolt learning show <slug>` | Print one chapter (`ch01`, stem, or unique substring); soft-fail if missing/ambiguous |
| `bolt domains status` | Browse creator-domain requirements readiness — `--json` / `--probe`; soft-fail `Domains unavailable:`; **spec browser only** (not a multi-domain runtime). Aliases: `domain`, `creator-domains`, `creator_domains`. |
| `bolt domains list` | List the 7 numbered domains (id / title / slug) from requirements |
| `bolt domains show <slug|N>` | Print one domain section from requirements (or `show instructions`); soft-fail if missing/ambiguous |
| `bolt pages status` | Cloudflare Pages / Worker deploy readiness — `--json` / `--probe`; soft-fail `Pages unavailable:`; **William-specific PARTIAL** (not stranger-ready). Aliases: `cloudflare-pages`, `cf-pages`, `pages-status`. |
| `bolt pages list` | List known Pages projects + worker (`bolt-fortress` / `billythunderstorm` / `billythunderstorm-live` / `bolt-api-worker`) and `/tmp/sites` path presence |
| `bolt pages deploy [project]` | Soft-fail wrangler pages deploy (needs auth + staging tree); `--dry-run` prints command only |
| `bolt license status` | Repo LICENSE / README placeholder — `--json` / `--probe`; soft-fail `License unavailable:`; **PARTIAL** (does not auto-pick SPDX). Aliases: `licence`, `spdx`, `license-status`. |

## Weekly analysis (`bolt weekly`)

Weekly performance insights from `Data/performance_outcomes.jsonl` + memory + optional Nexus. Soft-fail prefix: `Weekly unavailable:`. **PARTIAL** — Memory/Nexus/alerts gated; local markdown still saves under `Data/weekly_reports/`. Distinct from READY `bolt analytics` / `bolt briefing` / `bolt stats`.

```bash
bolt weekly                               # status (default; safe)
bolt weekly status [--json] [--probe] [--days N]
bolt weekly list [--json]
bolt weekly run [--print] [--send] [--days N] [--dry-run] [--json]
bolt weekly --print [--days N]            # legacy → run
bolt weekly --send [--days N]             # legacy → run + Bolt_Alerts
```

| Command | What it does |
|---------|--------------|
| `bolt weekly` / `status` | Readiness (`ready` = engine + writable reports dir) |
| `bolt weekly status --json` | Machine-readable readiness dict |
| `bolt weekly list` | Checklist + recent saved reports |
| `bolt weekly run` | Generate, print, and save markdown report |

Aliases: `monthly`, `week-insights`, `weekly-analysis`, `weekly-status`. Engine: `scripts/weekly_analysis.py`.

## Learning notes (`bolt learning`)

Local LLM textbook / study-log browser for `Data/learning/*.md`. **Not product architecture** — PARTIAL discoverability only. Soft-fail prefix: `Learning unavailable:`.

```bash
bolt learning                         # status (default; safe)
bolt learning status [--json] [--probe]
bolt learning list [--json]
bolt learning show ch01               # or stem / unique substring
bolt learning ch01                    # bare slug → show
```

| Command | What it does |
|---------|--------------|
| `bolt learning` / `status` | Readiness (`ready` = folder has chapter `.md` files; `is_study_log=true`) |
| `bolt learning status --json` | Machine-readable readiness dict |
| `bolt learning status --probe` | Read first chapter as a soft probe |
| `bolt learning list` | List chapter stems + titles |
| `bolt learning show <slug>` | Print chapter body (soft-fail if missing) |

Aliases: `learn`, `notes`, `study-notes`. Template `_TEMPLATE.md` is ignored in counts.

## Creator domains (`bolt domains`)

Browse `Docs/requirements/creator-domains-requirements.md` and
`.github/instructions/creator-domains.instructions.md`. **Not a multi-domain
runtime** — PARTIAL discoverability only. Soft-fail prefix: `Domains unavailable:`.

```bash
bolt domains                          # status (default; safe)
bolt domains status [--json] [--probe]
bolt domains list [--json]
bolt domains show 1                   # or slug / unique substring
bolt domains show content-creation
bolt domains show instructions        # or: bolt domains instructions
```

| Command | What it does |
|---------|--------------|
| `bolt domains` / `status` | Readiness (`ready` = both docs exist with content + parsed domains; `is_spec_browser=true`) |
| `bolt domains status --json` | Machine-readable readiness dict |
| `bolt domains status --probe` | Soft probe of requirements + domain_count |
| `bolt domains list` | List 7 domain ids / titles / slugs |
| `bolt domains show <slug|N>` | Print one domain section (soft-fail if missing) |
| `bolt domains show instructions` | Preview instructions file (first ~80 lines) |

Aliases: `domain`, `creator-domains`, `creator_domains`, `creator-domain`.

## Briefings, calendars, memory, and site data

```bash
bolt briefing                    # Generate and save the current daily briefing
                                  # also appends to today's Drive Daily Log if authorized
bolt briefing --print            # Print it in the terminal
bolt briefing --send             # Reminders list "Bolt" + Voice 3 alert + email
                                  # Cron: every day at 17:00
bolt drive-auth                  # One-time browser Allow for Drive/Docs Daily Log writes
                                  # aliases: drive_auth
bolt drive status                # Drive/Docs readiness (default; --json|--probe; soft-fail)
                                  # aliases: drive-status, gdrive, handbook; also: bolt drive push
bolt gcal-auth                   # One-time browser Allow for Calendar (briefing)
                                  # aliases: gcal_auth, calendar-auth, google-calendar-auth
bolt gmail-auth                  # One-time browser Allow for Gmail read (briefing)
                                  # aliases: gmail_auth, google-gmail-auth
bolt gcal status                 # Calendar credentials/token readiness (no browser)
bolt gmail status                # Gmail credentials/token readiness (no browser)
bolt calendar status                 # PARTIAL soft-fail ICS feeds
bolt calendar run [--dry-run] [--days 30] [--output-dir DIR]
bolt refresh-memory status       # READY memory index rebuild (run / --if-stale)
bolt memory status              # READY long-term memory (recall via Grok → Ollama → OpenAI)
bolt memsearch status           # READY memory search (index freshness + API)
bolt refresh_vector_db           # Rebuild Data/vector_db/ for Nexus (needs Ollama)
bolt vector_db                   # Alias for refresh_vector_db
bolt reindex                     # Alias for refresh_vector_db
bolt sites status [--json] [--probe]   # unified sites + storage cron readiness
                                      # aliases: site-status, sites-status, storage-cron
bolt site [--path <output-file>] [--push]
bolt site status [--json] [--probe]    # same as bolt sites status
```

Vector DB commands use Ollama embeddings (default `nomic-embed-text`) for *useful*
results. If Ollama is down they **fail soft** (warn + exit 1 / empty search / no-op add)
instead of raising or hanging — Nexus and other callers degrade gracefully:

```bash
ollama pull nomic-embed-text
bolt reindex
```

`bolt site` always writes local `Data/site-data.json` (REPO_ROOT via `_paths`). `bolt site --push` also attempts git commit + push; failures **soft-fail** with `Sites unavailable: …` (timeout / no remote) and never crash callers. Cloudflare Pages deploy is PARTIAL via `bolt pages` (William-specific; soft-fail `Pages unavailable:`; not stranger-ready). `bolt sites status` reports scripts, crontab (advisory), and git remote without pushing.

| Command | What it does |
|---------|--------------|
| `bolt briefing` | Generate (and save) the current daily briefing under `Docs/briefings/` |
| `bolt briefing --print` | Generate the briefing and print it to the terminal instead of saving |
| `bolt briefing --send` | Same, then write the **Bolt** Reminders list, speak Voice 3, Mac banner, email |
| `bolt drive-auth` | One-time Google Drive/Docs consent (`Data/google_drive_token.json`; needs `Core/credentials.json`) |
| `bolt drive status` | Drive/Docs readiness — `--json` / `--probe`; soft-fail `Drive unavailable:`; never opens a browser. Aliases: `drive-status`, `gdrive`, `handbook`. Also `bolt drive push`. |
| `bolt merge-py status` | Local `.py` source-dump readiness — `--json`; soft-fail `Merge unavailable:`; write via `bolt merge-py run` → `Data/merged_bot.py`. Aliases: `merge_py`, `merge-sources`. |
| `bolt titles status` | Title A/B trainer readiness — `--json`; soft-fail `Title trainer unavailable:`; `train` / `ab`; model `Data/viral_titles_model.json`. Aliases: `title-train`, `train-titles`. |
| `bolt discord status` | Optional Discord **webhook** readiness — `--json` / `--probe`; soft-fail `Discord unavailable:`; not a bot; `test` / `send`. Aliases: `discord-status`, `webhook`, `notify-discord`. |
| `bolt learning status` | Local `Data/learning/` study-note browser — `--json` / `--probe`; soft-fail `Learning unavailable:`; study log only. Aliases: `learn`, `notes`, `study-notes`. |
| `bolt domains status` | Creator-domain requirements browser — `--json` / `--probe`; soft-fail `Domains unavailable:`; spec only (not runtime). Aliases: `domain`, `creator-domains`. |
| `bolt pages status` | Cloudflare Pages deploy readiness — `--json` / `--probe`; soft-fail `Pages unavailable:`; William-specific PARTIAL (not stranger-ready). Aliases: `cloudflare-pages`, `cf-pages`, `pages-status`. |
| `bolt gcal-auth` | One-time Google Calendar consent (`Data/google_token.json`; needs `Core/credentials.json`) |
| `bolt gmail-auth` | One-time Gmail read consent (`Data/gmail_token.json`; same credentials file) |
| `bolt gcal status` | Calendar token readiness — never opens a browser |
| `bolt gmail status` | Gmail token readiness — never opens a browser |

Reply path for briefings: see **How to reply to Bolt** above. Write-intent lines
under `## Comments` are applied on the next `bolt briefing`; leftover is a note.
| `bolt calendar` | PARTIAL soft-fail ICS feeds under `Data/calendar/` (see section) |
| `bolt refresh-memory` | READY rebuild of `Data/memory_index.json` (atomic, verified, `--if-stale`; see section) |
| `bolt memory` | READY long-term memory: `recall "q"` + `remember "fact"` (see section) |
| `bolt memsearch` | READY local memory search; auto-rebuilds stale index (see section) |
| `bolt refresh_vector_db` | Rebuild the vector DB used by Nexus for retrieval (`Data/vector_db/`); soft-fails if Ollama down |
| `bolt vector_db` | Alias: same as `refresh_vector_db` |
| `bolt reindex` | Alias: same as `refresh_vector_db` |
| `bolt sites status` | Local site-data + storage cron readiness (`--json` / `--probe`; soft-fail) |
| `bolt site` | Write `Data/site-data.json` for the web dashboard (local only) |
| `bolt site --push` | Write + soft-fail git push (`Sites unavailable:` if remote/git fails) |

## SMS/email notify (`bolt send`) — PARTIAL

Soft-fail SMS/email notify. Prefers `Bolt_Alerts.notify` (same path as weekly `--send` /
`bolt alerts`). Falls back to `scripts/send_notification.py`. Prefix: `Notify unavailable:`.

```bash
bolt send                            # status (default; safe)
bolt send status [--json] [--probe]
bolt send list [--json]
bolt send "message" [--subject "…"] [--sms-only|--email-only]
```

`bolt notify` is an alias for `bolt send`.

Config: `Data/configs/storage_alerts.env`.

**Distinct from** PARTIAL `bolt alerts` (Mac/Voice/email/iMessage) and PARTIAL
`bolt discord` (webhooks). Stay PARTIAL (SMTP/phone gated).

Former thin SCRIPT_MAP: `bolt send` / `bolt notify` → `scripts/send_notification.py`.


## Cloudflare Pages (`bolt pages`)

William-specific Cloudflare Pages / Worker deploy readiness. **PARTIAL** — not stranger-ready
(no full in-repo site apps; needs wrangler + CF auth + `/tmp/sites` staging). Soft-fail prefix:
`Pages unavailable:`.

```bash
bolt pages                            # status (default; safe)
bolt pages status [--json] [--probe]
bolt pages list [--json]
bolt pages deploy bolt-fortress --dry-run
bolt pages deploy billythunderstorm --path /tmp/sites/main
```

| Command | What it does |
|---------|--------------|
| `bolt pages` / `status` | Readiness (`ready` = wrangler + auth + ≥1 deploy path; `is_stranger_ready=false`) |
| `bolt pages status --json` | Machine-readable readiness dict |
| `bolt pages status --probe` | Soft probe of wrangler auth / deploy paths |
| `bolt pages list` | Known projects + path presence |
| `bolt pages deploy [project]` | Soft-fail deploy (`--dry-run` safe); missing keys → `Pages unavailable:` |

Related: `bolt sites` (local site-data + storage cron — READY). Docs/site holds legal HTML stubs only.



## Mac .app assemble (`bolt mac-app`)

Local **thin** `dist/Bolt.app` wrapper that launches `bolt menubar` from this
checkout. **Not notarized. Not iOS. Not App Store.** Soft-fail prefix:
`Mac app unavailable:`.

```bash
bolt mac-app                        # status (default; safe)
bolt mac-app status [--json] [--probe]
bolt mac-app list [--json]
bolt mac-app build [--dry-run] [--json]
```

| Command | What it does |
|---|---|
| `bolt mac-app` / `status` | Pieces + whether `dist/Bolt.app` is valid |
| `bolt mac-app list` | Checklist (rumps, icons, launcher, notarized=never) |
| `bolt mac-app build` | Assemble thin app (Info.plist + MacOS/Bolt launcher) |

Aliases: `macapp`, `mac_app`, `bolt-app`, `app-bundle`, `app-status`.
Day-to-day: prefer `bolt menubar` after `uv sync --extra menubar`.
Legacy: `scripts/build_mac_app.sh` now calls this module.


## License (`bolt license`)

Repo LICENSE / README placeholder tooling (**PARTIAL**). Soft-fail `License unavailable:`.
Does **not** auto-pick a license — `set` is explicit.

```
bolt license                          # status (default; safe)
bolt license status [--json] [--probe]
bolt license list [--json]
bolt license show [--json]
bolt license set MIT                  # or Apache-2.0 / BSD-3-Clause / Unlicense / Proprietary
bolt license set MIT --dry-run
```

| Command | What it does |
|---|---|
| `bolt license status` | Readiness (`ready` = LICENSE present + README placeholder cleared; `readiness=PARTIAL`) |
| `bolt license list` | Supported SPDX ids |
| `bolt license show` | Print LICENSE body (soft-fail if missing) |
| `bolt license set <spdx>` | Write root `LICENSE` + replace README `[Add your preferred license here]` |

Aliases: `licence`, `spdx`, `license-status`.

## Discord webhook alerts (`bolt discord`)

Optional peak/error **webhook** alerts via `Core/modules/notifier.py` (also used by Peak_Hour_Notifier). **Not a Discord bot.** Soft-fail prefix: `Discord unavailable:`.

```bash
bolt discord                      # status (default; safe — no POST)
bolt discord status [--json] [--probe]
bolt discord test                 # soft-fail ping (POSTs when webhook set)
bolt discord send "hello"         # soft-fail send
```

| Command | What it does |
|---|---|
| `bolt discord` / `bolt discord status` | Readiness (`ready` = webhook URL configured; `is_discord_bot` always false) |
| `bolt discord status --json` | Machine-readable readiness dict |
| `bolt discord status --probe` | POST a tiny test ping when webhook set; soft-fail otherwise |
| `bolt discord test` | Same as a soft-fail test ping |
| `bolt discord send "…"` | Soft-fail webhook POST |

Aliases: `discord-status`, `webhook`, `notify-discord`. Env: `DISCORD_WEBHOOK_URL` (primary), optional `CAPTAIN_HOOK_WEBHOOK_URL` / `DISCORD_WEBHOOK_URLS`. Budget alerts stay Mac / Voice 3 / email / iMessage (`bolt alerts` / `Bolt_Alerts`; `BOLT_ALERT_DISCORD` defaults off).


Budget alerts (50% / 90% / 100% of soft cap) use **Mac banner + Voice 3 + email + iMessage**, not Discord.

Spoken alerts always use Siri **Voice 3** (`say -v "Voice 3"`, `Bolt_VOICE`). The same voice is used for `bolt say`, briefings, and Mac banners.

## Mac / Voice / email / iMessage alerts (`bolt alerts`)

Preferred budget/system fan-out via `Core/modules/Bolt_Alerts.py`. **Not a Discord bot.** Soft-fail prefix: `Alerts unavailable:`.

```bash
bolt alerts                            # status (default; safe)
bolt alerts status [--json] [--probe]
bolt alerts list [--json]
bolt alerts test [--json]
bolt alerts send "…" [--json]
```

| Command | What it does |
|---|---|
| `bolt alerts` / `status` | Channel readiness (`ready` if Mac banner **or** SMTP email/SMS path works) |
| `bolt alerts list` | Checklist (osascript / say / SMTP / ALERT_* / Discord-off) |
| `bolt alerts status --probe` | Mac banner only (no SMS/email spam) |
| `bolt alerts test` | Soft-fail fan-out (Mac + SMS + email when configured) |
| `bolt alerts send "…"` | Soft-fail notify |

Aliases: `alert`, `alert-status`, `notify-alerts`, `bolt-alerts`. Config: `Data/configs/storage_alerts.env` (template `storage_alerts.example.env`). `bolt budget --test-alert` and `bolt send` still use the same module. Discord webhooks: `bolt discord`.


## Apple Reminders (`bolt reminders`)

Evening / briefing inbox via `Core/modules/Apple_Reminders.py` (also used by `bolt briefing --send`). Soft-fail prefix: `Reminders unavailable:`. **PARTIAL** — macOS Reminders.app / JXA / TCC permission gated; not stranger-ready. Do not claim READY for the delivery channel alone (local briefing markdown stays READY).

```
bolt reminders                            # status (default; safe)
bolt reminders status [--json] [--probe]
bolt reminders list [--json]
bolt reminders test [--json]
bolt reminders send "message" [--json]
```

| Command | What it does |
|---------|----------------|
| `bolt reminders` / `status` | Darwin + osascript + list name (`BOLT_REMINDERS_LIST`, default `Bolt`) |
| `bolt reminders list` | Checklist of tooling / list / briefing wiring |
| `bolt reminders status --probe` | Soft list open-count via JXA (permission may prompt once) |
| `bolt reminders test` | Soft-fail write a tiny test reminder |
| `bolt reminders send "…"` | Soft-fail create one action reminder |

Aliases: `reminder`, `reminders-status`, `apple-reminders`, `remind`. Full briefing fan-out remains `bolt briefing --send` (Reminders + Voice 3 + banner + email).


## Filter backlog (`bolt filter-backlog`)

Clip backlog score filter via `Core/modules/Filter_Backlog.py` (wraps `scripts/Filter_Backlog.py`). Soft-fail prefix: `Backlog unavailable:`. **PARTIAL** — Clip_Ranker / media layout gated; moves low-scoring `media/clips/*.mp4` into `media/clips/_low_score/`. **Distinct from READY `bolt recordings` / `bolt queue`**.

```bash
bolt filter-backlog                         # status (default; safe)
bolt filter-backlog status [--json] [--probe]
bolt filter-backlog list [--json]
bolt filter-backlog run [--dry-run] [--threshold N] [--game NAME] [--json]
```

| Command | What it does |
|---|---|
| `bolt filter-backlog` / `status` | Script + Clip_Ranker + `media/clips` readiness |
| `bolt filter-backlog list` | Checklist + mp4 / `_low_score` counts |
| `bolt filter-backlog run` | Soft-fail score + move (use `--dry-run` first) |

Aliases: `filter_backlog`, `backlog-filter`, `filter-backlog-status`, `filter-clips`. Engine: `scripts/Filter_Backlog.py`.

## Make highlights (`bolt make-highlights`)

Local stitch of top `media/clips` into one reel at `media/output/YYYY-MM-DD_highlight_reel.mp4` (`--output NAME` lands in `media/output/`; an absolute path is used as-is). Soft-fail prefix: `Highlights unavailable:`. **READY** (18 Oct 2026) — every clip is normalised to 1920x1080 / 30 fps / AAC stereo (silent track added if missing) so mixed sources concat cleanly; uses the working ffmpeg from FFmpeg_Bin; zero clips / no ffmpeg soft-fail with what to do. Never moves or deletes source clips. Former SHELL `scripts/make_highlights.py` (IndentationError Twitch Helix paste) now forwards to `scripts/make_twitch_highlights.py`. Distinct from READY `bolt vods` (Helix). READY thin compile alias remains `bolt highlights`.

```bash
bolt make-highlights                         # status (default; safe)
bolt make-highlights status [--json] [--probe]
bolt make-highlights list [--json]
bolt make-highlights run [--list] [--count N] [--game NAME] [--output PATH] [--dry-run] [--json]
```

| Command | What it does |
|---------|--------------|
| `bolt make-highlights` / `status` | Readiness (`ready` = engine + ffmpeg + clips dir) |
| `bolt make-highlights status --json` | Machine-readable readiness dict |
| `bolt make-highlights list` | Checklist + engine `--list` preview |
| `bolt make-highlights run` | Stitch top N clips → dated reel in `media/output/` (or `--list` / `--dry-run` preview) |

Aliases: `make_highlights`, `make-highlights-status`, `stitch-highlights`, `highlight-stitch`. Engine: `scripts/make_twitch_highlights.py`.


## Reprocess clips (`bolt reprocess`)

Rebuild 9:16 verticals from existing `media/clips` into `media/vertical_clips/<stem>_tiktok.mp4` (config `tiktok_style`; output verified portrait; Finder purple) and **merge** manual-upload plans (Multi_Publisher: TikTok / Shorts / Reels / Kick) into `Data/multi_platform_queue.json` — other items kept, no duplicates, reruns don't reschedule, `.bak` first. Soft-fail prefix: `Reprocess unavailable:`. **READY** (18 Oct 2026) — needs a working ffmpeg. Former SHELL `scripts/reprocess_clips.py` (wrong PROJECT_ROOT under `scripts/`, legacy `clips/` / `vertical_clips/` / `data/` paths). Does **not** auto-upload to TikTok. Distinct from READY `bolt recordings` / `bolt enhance` / `bolt multi` and Clip_Factory `process_recording` vertical path.

```bash
bolt reprocess                               # status (default; safe)
bolt reprocess status [--json] [--probe]
bolt reprocess list [--json]
bolt reprocess run [NAME ...] [--dry-run] [--force] [--limit N] [--json]
```

| Command | What it does |
|---|---|
| `bolt reprocess` / `status` | Readiness (`ready` = engine + ffmpeg + clips dir + Clip_Factory) + built / to-build counts |
| `bolt reprocess status --json` | Machine-readable readiness dict |
| `bolt reprocess list` | Checklist of gates |
| `bolt reprocess run` | Build missing verticals + merge queue plans (`--dry-run` plan only; `NAME` filters by substring; `--force` rebuilds; `--limit N`) |

Aliases: `reprocess_clips`, `reprocess-clips`, `reprocess-status`, `vertical-reprocess`, `tiktok-reprocess`. Engine: `scripts/reprocess_clips.py`.

## Legacy health check (`bolt health`)

Lightweight post-reorg path + import smoke. Soft-fail prefix: `Health check unavailable:`. **PARTIAL** — prefer READY `bolt doctor` / `bolt verify` for the full live/mocked/stale audit. Former SHELL `scripts/health_check.py` (pre-reorg CWD-relative `config.json` / `bot.py` / `clips/` / `vertical_clips/` / `data/` / `modules/` paths). Optional deps/env gated.

```bash
bolt health                                  # status (default; safe)
bolt health status [--json] [--probe]
bolt health list [--json]
bolt health run [--dry-run] [--json]
```

| Command | What it does |
|---------|--------------|
| `bolt health` / `status` | Readiness (`ready` = fixed engine + Core paths) |
| `bolt health status --json` | Machine-readable readiness dict |
| `bolt health list` | Checklist of post-reorg gates |
| `bolt health run` | Soft-fail invoke engine smoke (or `--dry-run`) |

Aliases: `health-check`, `health_check`, `health-status`, `system-health`. Engine: `scripts/health_check.py` (via `scripts/_paths.py`). Prefer: `bolt doctor`.



## Word lookup (`bolt word`)

Dictionary, spellcheck, and thesaurus via `Core/modules/Word_Lookup.py`. **READY.** Local spell uses `/usr/share/dict/words` plus `Data/word_extras.txt` (offline). Definitions and synonyms/antonyms use Datamuse (free, no key). dictionaryapi.dev is an optional phonetic/example extra. Network lookups soft-fail with `Word lookup unavailable:` and still print local spelling. **Distinct from READY `bolt search`** (DuckDuckGo).

```
bolt word                                 # status (default; safe)
bolt word status [--json] [--probe]
bolt word list [--json]
bolt word honest                          # spelling + definition + synonyms
bolt word define honest [--json]
bolt spell recieve [--json]
bolt word check "this sentance" [--json]
bolt thesaurus honest [--json]
bolt word ant honest [--json]
```

| Command | What it does |
|---------|--------------|
| `bolt word` / `status` | Local word-list readiness (`ready` = system dict or extras loaded) |
| `bolt word list` | Checklist of spell / dictionary / thesaurus pieces |
| `bolt word <word>` | Full card: spelling + definition + synonyms + antonyms |
| `bolt word define <word>` | Definition only (network; soft-fail) |
| `bolt spell <word\|phrase>` | Local spellcheck; a phrase runs `check` |
| `bolt word check "…"` | Flag misspellings in a caption or title |
| `bolt thesaurus <word>` | Synonyms (Datamuse; soft-fail if offline) |

Aliases: `dict`, `dictionary`, `define`, `spell`, `spellcheck`, `thesaurus`, `synonym`, `syn`. Voice: "define honest", "how do you spell recieve", "synonym for honest". Add extra words in `Data/word_extras.txt`.

**Hear-through (conversation + CLI):** Bolt uses the same local spelling toward known commands and intent words. `bolt queu` runs `queue` (and prints that it did). In voice/text, "show the posting queu" is taken as queue status. Post / approve / hold / send are **not** auto-run from a typo — say those clearly.

## Photo OCR (`bolt photo-ocr`)

Photo / handwriting OCR → editable `.txt` via `Core/modules/Photo_OCR.py` (wraps `scripts/ocr_to_editable.py`). Soft-fail prefix: `Photo OCR unavailable:`. **PARTIAL** — Darwin Apple Vision and/or Tesseract gated; William utility — not stranger-ready. **Distinct from READY `bolt ocr`** (Video_Intelligence HUD OCR on clips).

```
bolt photo-ocr                            # status (default; safe)
bolt photo-ocr status [--json] [--probe]
bolt photo-ocr list [--json]
bolt photo-ocr run <images…> [--open] [--stdout] [-o PATH] [--json]
```

| Command | What it does |
|---------|----------------|
| `bolt photo-ocr` / `status` | Script present + Darwin Vision and/or tesseract on PATH |
| `bolt photo-ocr list` | Checklist of tooling / engines / default out dir |
| `bolt photo-ocr status --probe` | Light Vision import check (same as best-effort status on Darwin) |
| `bolt photo-ocr run …` | Soft-fail OCR → `~/Documents/Bolt OCR/` (or `-o` / `--stdout`); `--open` → TextEdit |

Aliases: `photo_ocr`, `photo-ocr-status`, `ocr-photos`, `ocr_photos`, `vision-ocr`. Advanced fallback: `python3 scripts/ocr_to_editable.py photo.jpg --open`.

## Video compress (`bolt compress`)

HandBrake clip compression via `Core/modules/Video_Compress.py` (wraps `scripts/compress_videos.sh`, paths fixed to `media/clips`). Soft-fail prefix: `Compress unavailable:`. **PARTIAL** — HandBrakeCLI gated; William cron / storage glue — not stranger-ready. Also reachable via `bolt storage optimize` (may `--skip-compress`).

```text
bolt compress                             # status (default; safe)
bolt compress status [--json] [--probe]
bolt compress list [--json]
bolt compress run [--dry-run] [--json]
```

| Command | What it does |
|---|---|
| `bolt compress` / `status` | Script present + HandBrakeCLI on PATH + `media/clips` |
| `bolt compress list` | Checklist (HandBrake / ffmpeg / clips / crontab mention) |
| `bolt compress run` | Soft-fail invoke `scripts/compress_videos.sh` |
| `bolt compress run --dry-run` | List candidate MP4s (>5 min old, not in `originals_backup`) |

Aliases: `video-compress`, `handbrake`, `compress-videos`, `compress_videos`. Advanced: `bash scripts/compress_videos.sh` (or cron `scripts/media_processing/compress_videos.sh` symlink).


## Performance baseline (`bolt performance`)

Local import/startup baseline via `Core/modules/Performance_Baseline.py` (wraps `scripts/performance_baseline.py`, paths fixed to `Core/launch.py` + `Core/bot.py`). Soft-fail prefix: `Baseline unavailable:`. **PARTIAL** — local diagnostic / optimization tooling — not stranger-ready product surface. **Distinct from READY `bolt analytics`** (outcomes summary) and **READY `bolt stats`** / `performance-sync` (social pull).

```text
bolt performance                          # status (default; safe)
bolt performance status [--json] [--probe]
bolt performance list [--json]
bolt performance run [--dry-run] [--json]
```

| Command | What it does |
|---------|----------------|
| `bolt performance` / `status` | Script + Core + writable `logs/performance/` |
| `bolt performance list` | Checklist + recent baseline JSON files |
| `bolt performance status --probe` | Same readiness (psutil presence noted) |
| `bolt performance run` | Soft-fail measure imports/startup → `logs/performance/baseline_*.json` |

Aliases: `baseline`, `perf-baseline`, `performance-baseline`, `baseline-status`. Raw: `python3 scripts/performance_baseline.py`.

## Pre-stream voice checklist (`bolt checklist`)

Pre-stream session tasks via `Core/modules/Voice_Checklist.py` (also used by `bolt launch`). Soft-fail prefix: `Checklist unavailable:`. **PARTIAL** — mic/STT/permission gated; William session tasks. Do not claim READY.

```
bolt checklist                            # status (default; safe)
bolt checklist status [--json] [--probe]
bolt checklist list [--json]
bolt checklist run [--keyboard|--text] [--timeout N] [--json]
```

| Command | What it does |
|---------|----------------|
| `bolt checklist` / `status` | Module + tasks file/defaults + SpeechRecognition/PyAudio + launch wiring |
| `bolt checklist list` | Session tasks from `Core/session_tasks.json` (else DEFAULT_TASKS) |
| `bolt checklist status --probe` | Optional timed mic open (never hangs status) |
| `bolt checklist run --keyboard` | Interactive keyboard path (needs TTY); bare `run` soft-fails non-interactive |

Aliases: `checklist-status`, `voice-checklist`, `prestream`, `pre-stream`. Skip on launch: `bolt launch --no-checklist` or `skip_checklist` in `Core/config.json`. Progress: `logs/checklist_progress.json`.

## Mac automation (`bolt mac-auto`)

William-specific macOS glue: launchd login watcher, 17:00 briefing cron, Apple Shortcuts.
**PARTIAL** — soft-fail `Mac automation unavailable:`. **Not stranger-ready.**
Evening inbox is Apple Reminders, not SMS.

```bash
bolt mac-auto                            # status (default; safe)
bolt mac-auto status [--json] [--probe]
bolt mac-auto list [--json]
bolt mac-auto install [launchd|cron|shortcuts|all] [--dry-run] [--json]
```

| Command | What it does |
|---|---|
| `bolt mac-auto` / `status` | Darwin + install script + plist / cron marks / signed Shortcuts |
| `bolt mac-auto list` | Checklist (launchd / cron / shortcuts / reminders) |
| `bolt mac-auto install …` | Soft-fail wrapper around install script (`--dry-run` prints only) |

Aliases: `mac_auto`, `mac-automation`, `automation`, `shortcuts-status`, `launchd-status`.

| Piece | What it does |
|---|---|
| launchd `com.streamer.ai-assistant` | Starts folder watch at login (`Core/launch.py live --no-checklist`) |
| cron `0 17 * * *` | Evening briefing → Reminders list **Bolt** |
| Shortcut **Bolt_Morning** | Terminal: `bolt day` |
| Shortcut **Bolt_Review_Queue** | Terminal: `bolt day --decide` |
| Shortcut **Bolt_Stats** | `bolt stats sync` |
| Shortcut **Bolt_Wrap-Up** | Asks what shipped → `bolt week done "…"` |
| Shortcut **Extract_Text_from_Photos** | OCR photos (print + handwriting) → editable `.txt` in `~/Documents/Bolt OCR/` |

Siri: open a shortcut → ⓘ → Add to Siri. Re-import signed files from `scripts/macos_shortcuts/signed/` if a shortcut is missing.

```bash
bolt briefing --send                                 # Reminders + Voice 3 + banner + email

# Advanced fallback (same installer `bolt mac-auto install` wraps)
python3 scripts/install_mac_automation.py            # all
python3 scripts/install_mac_automation.py launchd    # Core/launch.py live --no-checklist
python3 scripts/install_mac_automation.py cron       # 17:00 bolt briefing --send
python3 scripts/install_mac_automation.py shortcuts  # import dialogs

# Advanced fallback (prefer: bolt photo-ocr run photo.jpg --open)
python3 scripts/ocr_to_editable.py photo.jpg --open
```

## Per-game sensitivity profiles (`bolt game-config`)

CLI around `Core/modules/Game_Config.py` (built-in per-game highlight profiles +
`Data/configs/game_configs.json` overrides). Soft-fail prefix: `Game config unavailable:`.
**READY (19 Oct 2026)** — the profile is applied by `bot.py` process_recording (highlight
sensitivity, clip padding, TikTok style, min score), `bolt wrap` (sensitivity + padding) and the
live OBS StreamMonitor (spike multiplier). Per key, highest wins: per-game override in
`Data/configs/game_configs.json` > `Core/config.json` top-level > built-in profile > default.
The game is `Core/config.json` `game` (follows Twitch via `bolt game`). Each run logs
`game profile: <game> · overrides …`. **Distinct from** PARTIAL `bolt obs-game`
(OBS scene→`Core/config.json` game) and READY `bolt obs`.

```bash
bolt game-config                         # status (default; safe)
bolt game-config status [--json] [--probe]
bolt game-config list [--json]
bolt game-config show [game]             # what the pipeline uses + source of each value
bolt game-config set <game> KEY=VALUE …  # write Data/configs/game_configs.json
bolt game-config-status                  # alias → status
```

| Command | What it does |
|---|---|
| `bolt game-config` / `status` | Readiness: builtin count + overrides path + current game + `pipeline uses:` line |
| `bolt game-config list` | Builtin profiles + override checklist |
| `bolt game-config show` | What process_recording / wrap / OBS use for a game, each value tagged override / config / builtin / default (current game if omitted) |
| `bolt game-config set` | Merge KEY=VALUE overrides for one game (`--no-merge` replaces), e.g. `bolt game-config set "God of War Sons of Sparta" pad_after=15` |

Aliases: `game_config`, `gameconfig`, `games`, `game-profiles`, `game_profiles`, `game-config-status`.

Former unnamed IDEA: Docs/AI_Guide.md + CWD-relative `game_configs.json` / `config.json` (fixed to `Data/configs/` + `Core/config.json`).

## Error recovery / quarantine (`bolt error-recovery`)

Soft-fail CLI around `Core/modules/Error_Recovery.py` (pipeline `with_retry` + `ErrorTracker`
record/quarantine/session summary + optional Discord threshold alert). Soft-fail prefix:
`Error recovery unavailable:`. **PARTIAL** — not wired into bot.py; quarantine at
`Data/quarantine/` (was CWD-relative `quarantine/`). **Distinct from** PARTIAL
`bolt discord` (webhook) and PARTIAL `bolt alerts` (Mac/Voice/email/iMessage) — this
surface is pipeline retry/quarantine.

```bash
bolt error-recovery                         # status (default; safe)
bolt error-recovery status [--json] [--probe]
bolt error-recovery list [--json]
bolt error-recovery run [--json] [--dry-run] [--probe]
bolt error-recovery summary                 # alias of run
bolt error-recovery-status                  # alias → status
bolt recovery status                        # alias
```

| Command | What it does |
|---|---|
| `bolt error-recovery` / `status` | Readiness: module + MAX_ERRORS_BEFORE_ALERT + webhook present (redacted) + quarantine path/count + API importable |
| `bolt error-recovery list` | Quarantine files (if any) + tracker config checklist |
| `bolt error-recovery run` | Print tracker session summary; `--dry-run` skips summary; `--probe` runs `with_retry(lambda: True)` |

Aliases: `error_recovery`, `error-recovery-status`, `recovery`, `quarantine`, `error-tracker`, `error_tracker`.

Public API (in-process): `with_retry`, `ErrorTracker`, `get_tracker`, `record_error`, `session_summary`.

Former IDEA: Docs/AI_Guide.md "Failure handling helpers" + CWD-relative `quarantine/` (fixed to `Data/quarantine/`).


## Memory search (`bolt memsearch`) — READY

Soft-fail CLI around `Core/modules/Memory_Search.py` wrapping
`Memory_Index.retrieve_memory` / `format_retrieved_context` (hybrid vector+keyword
over `Data/memory_index.json`). Soft-fail prefix: `Memory search unavailable:`.
**READY (18 Oct 2026).** Local only (no keys/models). `run` auto-rebuilds the
index when it is missing or older than any memory source (~0.2 s), keeps only
hits that contain a real query word (the hashed vector alone matched filenames by
collision), and ranks by matched-word count then hybrid score. Each hit shows
when + matched words; no match prints `(no relevant memory found)` + a hint.
**Distinct from** READY `bolt search` (`Bolt_Search` — live web / DuckDuckGo),
READY `bolt memory` (LLM recall/remember), and READY `bolt refresh-memory`
(index rebuild only).

Owns the Phase 4 memory-search IDEA formerly mis-labeled on `Bolt_Search.py` in
Docs/AI_Guide.md (filename was reused for READY web search).

```bash
bolt memsearch                              # status (default; safe)
bolt memsearch status [--json] [--probe]
bolt memsearch list [--json]
bolt memsearch "Wolverine"                  # bare words → run
bolt memsearch run "pop culture" [--limit 5] [--refresh|--no-refresh] [--dry-run] [--json]
bolt memsearch search "…"                   # alias of run
bolt memsearch query "…"                    # alias of run
bolt memsearch-status                       # alias → status
bolt memory-search status                   # alias
```

| Command | What it does |
|---|---|
| `bolt memsearch` / `status` | Readiness: Memory_Index import + index file/entry count + freshness (stale vs newest source) + retrieve/format API |
| `bolt memsearch list` | Checklist rows (module, import, index, entries, freshness, retrieve API) |
| `bolt memsearch run` | Auto-rebuild if stale → word-matched hits ranked → formatted context (when + matched); `--refresh` forces rebuild, `--no-refresh` skips; `--dry-run` one line per hit |

Aliases: `memory-search`, `memory_search`, `mem-search`, `mem_search`, `search-memory`, `search_memory`, `memsearch-status`, `memsearch_status`.

Targeted tests: `Data/tests/test_memory_search.py` (temp files only).

Former IDEA: Docs/AI_Guide.md `Bolt_Search.py ← Phase 4 - semantic search over memory (WIP)`.

## iCloud Drive multi-Mac sync (`bolt icloud`)

**PARTIAL** — soft-fail `iCloud unavailable:`. **Not stranger-ready.** William multi-Mac glue (Docs/AI_Guide.md). Distinct from PARTIAL `bolt mac-auto` (launchd/cron/Shortcuts).

```bash
bolt icloud                              # status (default; safe)
bolt icloud status [--json] [--probe]
bolt icloud list [--json]
bolt icloud run [--dry-run|--apply] [--script move|shared|setup] [--json]
```

| Command | What it does |
|---|---|
| `bolt icloud` / `status` | Darwin + iCloud Drive folder + `scripts/move_to_icloud.sh` readiness |
| `bolt icloud list` | Checklist (engines, iCloud Bolt copy, repo under iCloud, legacy shared hop) |
| `bolt icloud run` | Dry-run by default; `--apply` runs helper (interactive confirm; skips `recordings/`) |

Aliases: `icloud-sync`, `icloud_sync`, `move-to-icloud`, `move_to_icloud`, `icloud-status`, `icloud_status`.

Preferred engine: `scripts/move_to_icloud.sh`. Legacy: `migrate_to_shared.sh`, `setup_icloud.sh`.

Stay PARTIAL — Darwin / iCloud Drive gated; does not claim stranger-ready or auto-sync magic.


## Game freshness (`bolt game`) — READY (18 Oct 2026)

Works end to end on Goddess (promoted PARTIAL → READY 18 Oct 2026). Follows the Twitch category (Live Scene → `__twitch__`): set the game on Twitch before streaming. Soft-fail CLI around `Core/modules/Game_Refresh.py`. Soft-fail prefix: `Game refresh unavailable:`.
Why: `Core/config.json` `game` sat on "007 First Light" for a month — it only changed on an OBS
scene switch or a Twitch fetch, and nothing recorded *when* it was last right.
`Data/configs/game_state.json` now stores `confirmed_at` / `checked_at` / history.

```bash
bolt game                           # status (default): game, last confirmed, STALE warning,
                                    #   + Twitch category check → DRIFT warning when unpinned (--no-twitch skips)
bolt game refresh [--dry-run]       # pinned Live Scene → else Twitch (__twitch__) → else keep + warn
bolt game set "Wolverine" [--pin]   # manual confirm (+ pin OBS Live Scene mapping)
bolt game unpin                     # Live Scene → __twitch__ (refresh follows Twitch)
bolt game history
```

| Trigger | What happens |
|---|---|
| `bolt launch` (live) | Refresh before OBS starts (`source=stream_start`) |
| `bolt obs-game run` | Refresh at tracker start + on OBS `StreamStateChanged` (stream start) |
| OBS scene change | Writes + stamps (pinned Live Scene is *checked*, not *confirmed*) |
| `bolt doctor` / `bolt obs-game status` | `game_freshness` row: FALL when older than `game_stale_days` (default 7; env `BOLT_GAME_STALE_DAYS`) |

`bolt game status` never writes; if config ≠ Twitch category it prints DRIFT + `bolt game refresh`.
If Twitch's channel category disagrees with a pinned Live Scene, refresh keeps the pin and prints
the exact `bolt game set "<Game>" --pin` / `bolt game unpin` fix.

## Motion detection (`bolt motion`) — READY (18 Oct 2026)

Works end to end on Goddess (promoted PARTIAL → READY 18 Oct 2026). Wraps `Core/modules/Motion_Detector.py` (former deferred IDEA).
Needs only ffmpeg (or opencv) + numpy from `uv sync`; missing/corrupt files soft-fail on one line with prefix `Motion unavailable:`.
Frame differencing on 160×90 grayscale samples (ffmpeg pipe via FFmpeg_Bin; OpenCV fallback),
cut damping, 4 s windows, robust z-score → top-N high-action windows.

```bash
bolt motion                                   # status (decoder: ffmpeg/opencv, numpy)
bolt motion media/Recordings/FILE.mp4         # top 10 windows + report JSON
bolt motion FILE --top 5 --window 3 --json    # machine output
bolt motion FILE --fast                       # keyframes only (long VODs; ~8 s for 33 min)
bolt motion FILE --start 600 --duration 120   # just a slice
bolt motion list                              # media/output/motion/*_motion.json
bolt motion FILE --backend opencv             # force the OpenCV decoder
```

Heuristic: fades/menus can score high. Used by `bolt wrap` to re-rank audio highlights.

## Post-stream wrap (`bolt wrap`) — READY

One command after a stream (`Core/modules/Bolt_Wrap.py`, prefix `Wrap unavailable:`):
latest VOD → Highlight_Detector (audio) + Motion_Detector → Clip_Generator clips → Whisper captions
burned with Clip_Factory drawtext → concat reel → dated folder with Finder tags.

```bash
bolt wrap                         # run on the newest VOD (recordings_folder, wrap_vod_dirs, vod_samples)
bolt wrap --dry-run               # show VOD + plan, write nothing
bolt wrap --vod FILE --top 8      # explicit VOD, more clips
bolt wrap --no-motion --no-captions --no-reel
bolt wrap status | list
```

Output: `media/output/wraps/YYYY-MM-DD_<vod>_wrap/` → `clips/*.mp4` (+ sidecar json),
`captions/*_captioned.mp4` + `.srt` (clips with speech), `<date>_<vod>_highlight_reel.mp4`, `motion.json`,
`wrap.json`, `WRAP.md`. Finder tags via `xattr` (or `tag` CLI): media **Purple**, md/srt **Blue**,
json **Orange**. Nothing is posted; the source VOD is never moved or deleted.
Captions use Whisper: the venv module (`uv sync --extra subtitles`) if present, else an existing
openai-whisper `whisper` CLI on the Mac (auto-detected; set `WHISPER_CLI=/path/to/whisper` to override).
`bolt wrap status` shows which backend. No Whisper at all = captions skipped with a note.

## Song release package (`bolt release`) — READY (18 Oct 2026)

`Core/modules/Song_Release.py`, prefix `Release unavailable:`. Packages finished songs for
DistroKid / TuneCore / CD Baby → Apple Music. **Never uploads.**

```bash
bolt release                                         # status
bolt release ~/Music/Weightless --artist "Your Artist Name" \
     --title "Weightless" --genre Pop --songwriter "Legal Name" --explicit no
bolt release ~/Music/Weightless --cover art.jpg --dry-run
bolt release list
```

Output `media/output/releases/YYYY-MM-DD_<title>_release/`: `audio/NN - Title.wav`
(44.1 kHz / 16-bit stereo), `cover.jpg|png` (checked ≥ 3000×3000 square, RGB),
`metadata.csv` / `metadata.json` (ISRC blank → distributor assigns), `CHECKLIST.md`
(first item: verify Suno plan commercial rights), `release.json` (peaks, warnings).
Missing art or ffmpeg → warnings; existing 44.1k/16-bit WAVs still package without ffmpeg.

Titles come from file names: track numbers (`01 Sinner`, `10 Break Your Spirit`, `1-01 Take You`),
hyphen exports (`06-I-Wont-Fold`) and Finder copies (`Song-2`) are cleaned. The same song in two
formats (`.aif` + `.m4a`) is packaged once, keeping the lossless file. Cover is found as
`cover|artwork|art|folder|front.*`, an image named after the release, or the only image in the folder.
Single / EP (≤ 6 tracks) / Album is auto-detected. Default release date = today + 21 days.

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
bolt voice status          # Mic / STT / TTS / LLM readiness (soft-fail friendly)
bolt voice status --probe  # Also timed-open the mic (optional; can be slow)
bolt voice                 # mic in, spoken replies out (free Google STT)
bolt voice --text          # type in, still speaks (Siri Voice 3) — stranger-safe
bolt talk "what's next?"   # one-shot spoken Q&A
bolt say "Clips are ready" # TTS only
bolt briefing --speak      # write briefing + speak a short summary
bolt morning               # Good Morning Bolt spoken *business* briefing
bolt stats                 # social performance readiness
```

Mic listen needs SpeechRecognition + PortAudio + macOS mic permission. If the
mic is missing, `bolt voice` **soft-fails** (exit 1, clear hint) — use
`bolt voice --text`. STT defaults to free Google; Whisper only with
`BOLT_USE_WHISPER=true`. TTS defaults to macOS Voice 3.

Same engine under the hood (`Core/bolt_live_voice.py` → `Bolt_Conversation`):

```bash
PYTHONPATH=Core python3 -m Bolt_Conversation
PYTHONPATH=Core python3 -m Bolt_Conversation --text
PYTHONPATH=Core python3 -m Bolt_Conversation status
PYTHONPATH=Core python3 Core/bolt_live_voice.py --once "What should I do next?"
PYTHONPATH=Core python3 -m Bolt_Conversation --clear
```

| Command / flag | What it does |
|----------------|--------------|
| `bolt day` | Daily kickoff: peak, queue, storage, API, social line; TTY offers decide |
| `bolt day --decide` | Same brief, then `queue decide` (default morning path) |
| `bolt day --voice` | Same brief, then voice loop |
| `bolt stats` | TikTok/YouTube token readiness + recent outcomes |
| `bolt voice status` | Mic / STT / TTS / LLM readiness (also `--status`; add `--probe` for timed mic open) |
| `bolt voice` | Voice-mode conversation loop (mic + TTS); soft-fails if mic unavailable |
| `bolt voice --text` | Text input, spoken replies (works without mic) |
| `bolt talk "…"` / `--once "…"` | One question, one spoken answer, exit |
| `bolt say "…"` | Speak a line only (no LLM) |
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
| status report / manager status | Catalog / manager status snapshot |
| storage / disk space | Disk free + media sizes |
| api budget / how much have I spent | Soft cap + estimated API spend |
| social stats / how did my posts do | Token readiness + recent TikTok/YouTube outcomes |
| Research status / Mission status | Research or mission summary |
| This week / current week | Week card (topic + do not suggest) |
| I’m ready / I’m back / unpause | `bolt week set` current topic, note “ready to continue” |
| this week is … / let’s do … this week | `bolt week set` |
| this shipped: … / I posted … | `bolt week done` |
| hours: … / budget … / I have 6 hours / assets: … | `bolt mission update latest` |
| remember: … | MEMORY.md Recent Notes |

Anything else is short free-form chat (Ollama by default in light mode). Spoken replies stay plain sentences — no markdown dumps.

Inside conversation mode:

- Ask Bolt a normal question or give a normal instruction in plain language.
- Type or say `exit`, `quit`, `bye`, or `goodbye` to end the conversation.

### Titles and hashtags

```bash
bolt queue title                      # suggest titles for next postable clip
bolt queue title <id> 1               # apply suggestion #1 (+ generated hashtags)
bolt queue title <id> "My hook 🔥"    # custom title (hashtags unchanged)
bolt queue package                    # paste-ready TikTok + Shorts package
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
| `weekly` | `monthly`, `week-insights`, `weekly-analysis`, `weekly-status` |
| `log_perf` | `log_performance` |
| `sync_tiktok_stats` | `sync_tiktok`, `tiktok_stats` |
| `sync_youtube_stats` | `sync_youtube`, `youtube_stats` |
| `refresh-memory` | `refresh_memory`, `memory-refresh`, `refresh-index` |
| `calendar` | `ics`, `ics-calendar`, `generate-calendar`, `calendar-status` |
| `stats` | `social-stats`, `performance-sync` |
| `budget` | `api-usage`, `api_usage`, `xai-usage`, `llm-budget` |
| `day` | `today`, `kickoff`, `start-day`, `morning-flow` |
| `storage` | `disk`, `media-rotation`, `storage-monitor` |
| `voice` | `talk`, `live-voice` |
| `research` | `researcher` |
| `queue` | `postqueue`, `post-queue`, `ready-queue` |
| `queue decide` | `queue review`, `queue triage`, `queue pick` |
| `queue next` | `queue show` |
| `queue package` | `queue pkg`, `queue pack` |
| `queue held` | `queue holds`, `queue list-held` |
| `queue unhold` | `queue release`, `queue restore`, `queue requeue` |
| `queue clean` | `queue prune` |
| `queue approve` | `approve` |
| `queue post-now` | `postnow`, `post-now` |
| `queue reject` | `dontpost`, `dont-post`, `hold-clip` |
| `queue mark-posted` | `mark-posted`, `markposted` |
| `tiktok-post` | `post-ui`, `tiktok_post`, `tiktok-ui` |
| `gemini` | `gemini-status`, `gemini_status` |
| `vods` | `vod_download` |
| `send` | `notify` |
| `layout` / `check-layout` / `layout-status` | `Layout_Check` (PARTIAL soft-fail) |
| `migrate-layout` / `migrate_layout` / `layout-migrate` / `migrate-status` | `Migrate_Layout` (PARTIAL soft-fail) |
| `game-config` / `game_config` / `games` / `game-profiles` / `game-config-status` | `Game_Config` (READY; used by clip pipeline) |
| `error-recovery` / `error_recovery` / `recovery` / `quarantine` / `error-tracker` / `error-recovery-status` | `Error_Recovery` (PARTIAL soft-fail) |
| `layout` (legacy thin) | `check_layout` |
| `filter-backlog` | `filter_backlog`, `backlog-filter`, `filter-clips` |
| `make-highlights` | `make_highlights`, `make-highlights-status`, `stitch-highlights`, `highlight-stitch` |
| `reprocess` | `reprocess_clips`, `reprocess-clips`, `reprocess-status`, `vertical-reprocess`, `tiktok-reprocess` |
| `refresh_vector_db` | `vector_db`, `reindex` |
| `status` | `intelligence` |
| `doctor` | `audit` |
| `morning` | `good-morning`, `goodmorning` |
| `mission` | `command-center`, `ccc` |
| `week` | `this-week`, `week-card` |
| `setup` | (routes to `Core/launch.py`) |
| `menubar` | `menu-bar`, `menu_bar`, `menu` |
| `amazon` | `amazon-review`, `review-plan` |
| `search` | `web-search`, `websearch` |
| `obs` | `obs-status`, `stream-monitor` |
| `streamlabs` | `streamlabs-status`, `slabs`, `streamlabs-monitor` |
| `chat` | `twitch-chat`, `chat-status`, `bolt-chat` |
| `brain` | `brain-status`, `brain_status`, `brain-controller` |

---

*Canonical path: `Core/modules/BOLT_COMMANDS.md` — this is the only BOLT_COMMANDS
file in the repo. Prefer editing this markdown over duplicate Pages copies.*

## `bolt personality` — Bolt system prompt

William's persona in `Data/context/bolt-personality.md`, loaded by `scripts/load_bolt_personality.py`. Voice and Twitch chat use the same text. `run` talks through `LLM_Handler` (Ollama first). Not a Gemini chat.

```bash
bolt personality status
bolt personality list
bolt personality run
bolt personality run --once "Hey Bolt, I have an idea"
```

Aliases: `personality`, `bolt-personality`, `personality-status`, `persona`, `load-personality`, `load_personality`.

Soft-fail prefix: `Personality unavailable:` (missing file, or no model answered).

Module: `Core/modules/Bolt_Personality.py`.

## layout / check-layout (PARTIAL)

Repo-root layout audit via `Core/modules/Layout_Check.py` (wraps `scripts/check_layout.py` + `_layout_rules.py`). Soft-fail prefix: `Layout unavailable:`. **PARTIAL** — report-only; never moves files; William allow-list gated. **Distinct from READY `bolt doctor` / `bolt verify`**.

```bash
bolt layout status [--json] [--probe]
bolt layout list
bolt layout run [--quiet] [--json]
bolt layout-status          # alias → status
bolt check-layout list      # alias
```

Aliases: `layout`, `check-layout`, `check_layout`, `layout-status`.

## migrate-layout (PARTIAL)

Repo-root layout drift migrator via `Core/modules/Migrate_Layout.py` (wraps `scripts/migrate_layout.py` + `_layout_rules.py`). Soft-fail prefix: `Migrate unavailable:`. **PARTIAL** — dry-run by default; `--apply` performs moves; William layout glue gated. **Companion to PARTIAL `bolt layout`** (report-only, never moves). **Distinct from READY `bolt doctor` / `bolt verify`**.

```bash
bolt migrate-layout status [--json] [--probe]
bolt migrate-layout list
bolt migrate-layout run                 # dry-run plan (safe default)
bolt migrate-layout run --apply         # actually move
bolt migrate-layout run --apply --yes   # conflicts fatal (no prompt)
bolt migrate-status                     # alias → status
bolt layout-migrate list                # alias
```

Aliases: `migrate-layout`, `migrate_layout`, `layout-migrate`, `migrate-status`.

