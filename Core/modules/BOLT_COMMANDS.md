# Bolt Command Reference

This is the current user-facing command list for Bolt. It contains the commands accepted by the live CLI, conversation interface, and Twitch chat bot.

## Running Bolt commands

From any directory, use:

```bash
uv run --directory /Users/carter/developer/Bolt bolt <command> [options]
```

For the shorter `bolt <command>` form, add this alias to `~/.zshrc`:

```bash
alias bolt='uv run --directory /Users/carter/developer/Bolt bolt'
```

Then reload the shell:

```bash
source ~/.zshrc
type bolt
bolt help
```

When working inside `/Users/carter/developer/Bolt`, this also works without an alias:

```bash
python3 bin/bolt <command> [options]
```

Run `bolt help` to show the built-in summary. Commands that expose their own help accept `--help`.

## Core commands

```bash
bolt help                         # Show the CLI command summary
bolt version                      # Show the repository and Python in use
bolt verify                       # Check required files, folders, config, and environment
bolt setup                        # Run first-time setup
bolt launch                       # Start Bolt
bolt status                       # Check the decision engine, vector DB, and Nexus
bolt intelligence                 # Alias for status
bolt test                         # Run the full test suite
bolt test <unittest-arguments>     # Run selected unittest targets
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
bolt command-center …
bolt ccc …
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

### Learned ranking model

```bash
bolt manage model-status
bolt manage model-inspect [--game "Game Name"]
```

## Storefront

```bash
bolt store list
bolt store add --name "Mouse" [--asin <asin>] [--category tech] [--notes "text"]
bolt store feature-next
```

Running `bolt store` with no action is the same as `bolt store list`.

## Social packages and queue

```bash
bolt social status
bolt social package "Headset" [--platforms tiktok,youtube,x]
bolt social queue
```

Running `bolt social` with no action is the same as `bolt social status`.

## Sponsors

### Everyday sponsor workflow

```bash
bolt sponsors find [--lane <lane>] [--limit 5]
bolt sponsors pitch "Razer"
bolt sponsors log "Razer" --status <status> [--note "text"]
bolt sponsors next
```

Running `bolt sponsors` with no action is the same as `bolt sponsors find`.

### Sponsor records and research

```bash
bolt manage sponsors-add "Razer" [--lanes game,tech] [--type brand] [--fit 9] [--contact <contact>] [--note "text"]
bolt manage sponsors-enrich "Razer" [--note "text"] [--link <url>] [--mark-contacted]
bolt manage sponsors-pipeline
bolt manage sponsors-research "Razer" "Razer creator program" [--limit 5] [--no-update-contact] [--json]
```

Sponsor research requires the repository's search provider to be configured.

## Business guidance and daily briefing

```bash
bolt business lesson
bolt business next
bolt advance next
bolt morning
bolt morning --quiet
```

`bolt good-morning` and `bolt goodmorning` are aliases for `bolt morning`.

## Recordings, clips, and highlights

```bash
bolt recordings [all|latest|list|<number>] [--content-type gaming|review|skincare|tech]
bolt auto_clip_twitch                 # Process the latest unprocessed Twitch VOD
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

`recordings` defaults to `all` and gaming content. `auto-clip-twitch` is an alias for `auto_clip_twitch`.

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

## Briefings, calendars, memory, and site data

```bash
bolt briefing                    # Generate and save the current daily briefing
bolt briefing --print            # Print it in the terminal
bolt calendar [--output-dir <directory>] [--days 30] [--dry-run]
bolt refresh_memory
bolt site [--path <output-file>] [--push]
```

`bolt site --push` writes site data and then attempts to commit and push it. Use it only when that is the intended action.

## Notifications

```bash
bolt send "message" [--subject "subject"] [--sms-only|--email-only]
```

`bolt notify` is an alias for `bolt send`.

## Starting conversation mode

Start a text conversation:

```bash
uv run --directory /Users/carter/developer/Bolt python Core/Bolt_Conversation.py --text
```

Start voice conversation mode:

```bash
uv run --directory /Users/carter/developer/Bolt python Core/Bolt_Conversation.py
```

Inside conversation mode:

- Ask Bolt a normal question or give a normal instruction in plain language.
- Say or type `Good Morning Bolt`, `Good morning`, or `Morning Bolt` for the daily manager briefing.
- Type or say `exit`, `quit`, `bye`, or `goodbye` to end the conversation.

## Twitch chat commands

These commands are available while the Bolt Twitch chat bot is connected:

```text
!Bolt <question>                  Ask Bolt a question
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
| `vods` | `vod_download` |
| `send` | `notify` |
| `layout` | `check_layout` |
