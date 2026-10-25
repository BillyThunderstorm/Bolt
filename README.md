# Bolt

Bolt is Billy Carter’s local-first creator operations system: a Python CLI and companion local interfaces for product testing, media processing, research, planning, and review.

It is a personal project, not a hosted SaaS product. Creator data and generated media stay on the machine. Paid model calls and publishing stay explicit and reviewable. William approves anything that posts or spends money.

The live command reference, including the use chart below, is [Core/modules/BOLT_COMMANDS.md](Core/modules/BOLT_COMMANDS.md). This page is the GitHub copy of that chart, the current plan, and a one-line rundown of every primary command.

## Command chart — how to use Bolt

One owned product, one short you approve, then a log line so tomorrow cannot assign it again. You upload the file yourself. Everyday conversation stays on the local model. Paid Grok is for strategy (`bolt nexus --paid`).

`bolt morning --quiet` is the product-testing day. `bolt day --decide` is the clip queue. A gaming clip you already held does not replace the product post.

### The week

| When | Do this | Leave closed |
|---|---|---|
| Wake window | `bolt morning --quiet` and do the one step it prints | A second product, a new lane, a Bolt rebuild |
| Mon | `bolt manage add "Item" --lane tech --status testing` for one product you already own | Picking three at once |
| Tue–Thu | `bolt manage note "Item" --day N --text "what was true"` | Filming a product that has no verdict yet |
| Fri | Finish the assessment, `bolt manage draft "Item" --format short`, approve it in chat | Auto-publish |
| Sat | Post that one short yourself, then `bolt manage posted "Item" --tiktok --where URL` and `bolt week done "what shipped"` | Redrafting the other catalog items |
| Sun | `bolt log-perf run --clip "Item" --views N` when numbers exist. Ten minutes. | A new mission |

Hands-only footage counts. Comments are optional. `bolt week` beats an old briefing. The morning names whatever `briefing_focus.focus_item` is in `Core/config.json`. On 2026-10-24 that item is the K&F Concept Neck Phone Holder.

### Where each surface fits

| Surface | Use it for |
|---|---|
| Terminal `bolt …` | Catalog, drafts, queue review, logging a post |
| `bolt morning --quiet` | The one product step, without spoken audio |
| `bolt voice --text` | A question when the mic is unavailable. Same writes as the CLI |
| `bolt menubar` | Launch, stop, dashboard, logs, config. Needs `uv sync --extra menubar` |
| Apple Reminders | The evening briefing, after you ask for `bolt briefing --send` |
| Twitch chat `!Bolt` | A question while you are live. Clip decisions stay in the terminal |

`bolt day` with no flags can sit on text-to-speech. Prefer `bolt morning --quiet` on this lane.

### After a stream

`bolt wrap` turns the latest VOD into clips, a reel, and captions. `bolt recordings latest` runs the same pipeline on one file. `bolt queue decide` is where you approve, hold, or retitle. You still upload, then `bolt queue mark-posted` or `bolt manage posted`. `bolt postnow` calls the paused TikTok API, so the manual upload is the path that finishes.

### Potential when this loop is finished

The commands below are largely built. The result shows up when the loop runs the roadmap in [Data/business/product-testing-plan.md](Data/business/product-testing-plan.md).

| Horizon | What a finished loop produces |
|---|---|
| **Now → Nov 4, 2026 · Foundation** | Three public honest assessments of products you already own, each with one short. The writing is done. The posts are not. |
| **Nov 5, 2026 → Jan 31, 2027 · Proof** | About ten public assessments and a portfolio page a stranger can open. Floor after the first three: two posts a week, and never zero two weeks in a row. |
| **Feb–Apr 2027 · Credibility** | One testing or honest-review program, disclosed affiliate links, and a portfolio worth taking back to Amazon Influencer. Vine stays invite-only. |
| **May–Jul 2027 · Outreach** | A one-page media kit. `bolt sponsors pitch "Brand"` prints a draft you send. First gifted unit, reviewed honestly. |
| **Aug 2027 → · Career** | A paid review, a testing contract, a retainer, or a tester job. **$1,000 / month** is the first proof. **$3,000 / month** is the job. Often 12–24 months if the reviews continue. |
| **By 2026-12-31** | You know what success looks like in this work, or the roadmap plus the public posts are the proof. The roadmap is written. The missing proof is the public record. |

Used on that path, Bolt remembers every test, packages one short, holds the week to one lane, and learns which posts landed. Pitches stay drafts until a portfolio exists. Nothing posts and nothing spends without approval.

The further north star is the one in the profile: companies send products, some tests happen on site, the work can reach a stage like Dream Con or a Marvel-adjacent collaboration, and income comes from sponsors, partnerships, and disclosed affiliate links. The posts are how that direction collects evidence. Saturday’s job is still one short.

A second CLI in `bolt/command.py` (`pipeline`, `serve`, and overlapping names like `morning`) is not this loop. Use the commands on this page.

## This week and today

**Week of Mon Oct 19 – Sun Oct 25, 2026.** Lane: product testing (started Oct 11). Phase 1 runs through Nov 4.

**Today, Saturday Oct 24:** post the K&F Concept Neck Phone Holder short. The script was approved Oct 19. Desk footage from Oct 20–21 covers the strap and the flip. Film a 10–20 second POV from the holder if it is in reach. If it is not, post the desk cut. Then:

```bash
bolt manage posted "K&F Concept Neck Phone Holder" --tiktok --where "URL"
bolt week done "Posted the K&F neck phone holder short"
```

The Rybozen capture card (10/10) and the Facmogu Pink Mic Holder (7/10) are drafted and wait until this short is public. Full write-up: [Data/business/product-testing-plan.md](Data/business/product-testing-plan.md). Living status: [Docs/BOLT_NOW.md](Docs/BOLT_NOW.md).

### Career roadmap

| Phase | Window | Exit |
|---|---|---|
| 1 Foundation | Oct 11 – Nov 4, 2026 | 3 posted assessments |
| 2 Proof | Nov 5, 2026 – Jan 31, 2027 | ~10 public assessments and a portfolio page |
| 3 Credibility | Feb – Apr 2027 | A panel or honest-review program, disclosed affiliates |
| 4 Outreach | May – Jul 2027 | Media kit, first gifted unit |
| 5 Career | Aug 2027 → | First paid test |

Career bar on the short card: $1,000 / month is first proof, $3,000 / month is the job. Image: `Data/business/product-testing-roadmap.png`.

## Command rundown

Names in the tables are the primary commands. Aliases (`audit` for `doctor`, `postnow` for `queue post-now`, `goodmorning` for `morning`, and the rest) are listed in [Core/modules/BOLT_COMMANDS.md](Core/modules/BOLT_COMMANDS.md). Add `--help` on a command that has its own modes. Most maintenance commands use `status`, `list`, and `run`, and they soft-fail when a key or an app is missing.

### Day, plan, and memory

| Command | What it does | Efficient use |
|---|---|---|
| `bolt help` | Print the built-in command summary | When you forget a name |
| `bolt morning --quiet` | Write and show today’s one product step | Start of the wake window |
| `bolt briefing --print` | Regenerate the daily briefing in the terminal | Add `--send` only when you want Reminders and email |
| `bolt day --decide --quiet` | Peak window, queue, then review clips | Clip days, not product-post days |
| `bolt week` | Show this week, last week, and do-not-suggest | Read before inventing a plan |
| `bolt week set "topic"` | Lock the lane | Once, when the lane changes |
| `bolt week done "what shipped"` | Record finished work | The same night you post |
| `bolt week paper` | One-page fridge sheet | When you want it off the screen |
| `bolt week rotate` | Archive this week and clear the card | Sunday, after the post is logged |
| `bolt week ban "idea"` | Never suggest that idea again | When a leftover keeps returning |
| `bolt checkin` | Up to three evening questions on gaps | End of the session, not a second morning |
| `bolt mission start "goal"` | A named goal with hours, budget, and assets | Only when the week card is too small |
| `bolt mission next` | The next concrete action on the latest mission | Days can run with no mission |
| `bolt research find "name"` | Web search into a pending C5 decision | Creator examples, not brands you already track |
| `bolt research c5 keep "Name"` | Record your own keep or drop | The decision stays yours |
| `bolt business next` | Next business move from the manager | After the product step, if you still have time |
| `bolt advance next` | Next Bolt improvement worth shipping | When a real posting friction shows up |
| `bolt calendar run` | Write `.ics` feeds for briefing, peaks, and posts | Double-click a file to add it to Calendar |
| `bolt stats` | TikTok and YouTube pull readiness | `--dry-run` before a live pull |
| `bolt analytics` | Summarize `performance_outcomes.jsonl` | After a few posts have numbers |
| `bolt predict --game G --trigger T` | Forecast 24h views from past posts | Once the log has history |
| `bolt weekly run` | Weekly report from real numbers | Sunday |
| `bolt nexus "question"` | Advice from Ollama | `--paid` only for a real strategy call |
| `bolt search "question"` | Live web search, short summary | `--raw` when you want the hits only |
| `bolt memory recall "question"` | Answer from Bolt’s local memory | Before guessing at old decisions |
| `bolt memory remember "fact"` | Append a dated fact | One sentence, specific |
| `bolt memsearch run "words"` | Search the memory index | Rebuilds the index when it is stale |
| `bolt refresh-memory run` | Rebuild that index on purpose | `--if-stale` in cron |

### Product testing and sponsors

| Command | What it does | Efficient use |
|---|---|---|
| `bolt manage next` | The top catalog action | When the morning line is not enough |
| `bolt manage list --status drafting` | Items with a short in progress | See the three current drafts |
| `bolt manage add "Item" --lane tech --status testing` | Start one owned product | Monday |
| `bolt manage note "Item" --day N --text "…"` | Journal a test day | Tue–Thu, five minutes |
| `bolt manage draft "Item" --format short` | Package the short | After the verdict |
| `bolt manage posted "Item" --tiktok --where URL` | Record a manual post | Immediately after you upload |
| `bolt manage youtube-pkg "Item"` | Paste-ready YouTube package | When that platform is the one you are opening |
| `bolt manage x-pkg "Item"` | Paste-ready X package | Same |
| `bolt amazon ASIN` | Fetch a product and draft a review plan | Before you test something new |
| `bolt store status` | Storefront readiness | Amazon Influencer is rejected; this is a check, not a lane |
| `bolt sponsors pitch "Brand"` | Print a pitch draft in the terminal | Phase 4. It does not email |
| `bolt sponsors next` | Next sponsor action already on file | After a portfolio exists |
| `bolt social package` | Manual social packet | When you are about to paste |
| `bolt multi plan` | Multi-platform plan, no auto-upload | Kick and Instagram stay manual |
| `bolt log-perf run --clip ID --views N` | Teach the ranker what happened | One row per post, update later in place |

### Clips, queue, and games

| Command | What it does | Efficient use |
|---|---|---|
| `bolt recordings latest` | Clip the newest recording | Default. `all` is the long run |
| `bolt recordings NAME --force` | Re-run one already-processed file | When it produced no clips |
| `bolt watch run --once` | Clip whatever just finished writing | `--dry-run` first on a big folder |
| `bolt wrap` | Post-stream package: highlights, reel, captions | One command after you go offline |
| `bolt highlights` | Compile a Twitch highlight reel | When you want the reel only |
| `bolt make-highlights run --count N` | Stitch top clips into one reel | Output lands in `media/output/` |
| `bolt reprocess run` | Rebuild vertical copies and manual upload plans | Nothing posts |
| `bolt enhance` | Trim and overlay vertical clips | `--dry-run` first |
| `bolt compress run` | Shrink finished clips, keep a 7-day backup | Cron already runs this |
| `bolt filter-backlog run --dry-run` | Show clips under the game’s score floor | Drop `--dry-run` only when the list looks right |
| `bolt clip-dedupe run` | List byte-identical copies and wasted space | It never deletes |
| `bolt thumbnails` | JPG thumbnails for clips | After a batch of new clips |
| `bolt queue decide` | Open, approve, hold, retitle, skip | The review session. Needs a terminal |
| `bolt queue next` | The next postable card | A glance |
| `bolt queue package` | Paste-ready caption | The moment you open the upload page |
| `bolt queue clean` | Drop rows whose files are gone | When the count looks haunted |
| `bolt queue mark-posted ID` | Record a manual clip upload | The closer for a gaming clip |
| `bolt review` | Local keep/toss board on port 8767 | Keep never posts |
| `bolt tiktok-post` | Local Post-to-TikTok page | Demo is valid. Live API posting stays paused |
| `bolt motion VIDEO` | Score visual action in a file | Wrap already calls this |
| `bolt ocr CLIP` | Read on-screen stats | Needs tesseract |
| `bolt anomaly latest` | Compare a recording with the usual audio | When a VOD feels dead or blown out |
| `bolt game status` | Is the configured game still what you stream | Refresh at stream start |
| `bolt game-config show` | Sensitivity, padding, and style for this game | `set` one game without editing `config.json` |
| `bolt obs-game run` | Follow the OBS scene into the configured game | While OBS is open |
| `bolt error-recovery run` | Recent pipeline failures and what to try | `quarantine` moves a broken file aside |

### Stream, voice, and the Mac

| Command | What it does | Efficient use |
|---|---|---|
| `bolt setup` | One-shot readiness check, then it exits | Install day |
| `bolt launch` | Long-running folder watch | Leave it running. It is not the morning |
| `bolt checklist check` | OBS, title, category, queue, Discord, output | Before you go live |
| `bolt obs status` | OBS WebSocket readiness | Soft-fails when OBS is closed |
| `bolt streamlabs status` | Streamlabs socket readiness | Needs `STREAMLABS_SOCKET_TOKEN` |
| `bolt chat connect` | Twitch chat bot | When you want `!Bolt` in chat |
| `bolt overlay` | Local overlay HTTP on port 8766 | Leave the terminal open |
| `bolt vods list` | Dry-run the Twitch VOD downloader | `download` when the list looks right |
| `bolt voice status` | Mic, speech-to-text, speech, model | `--probe` opens the mic |
| `bolt voice --text` | Type, and Bolt speaks | Works with no microphone |
| `bolt talk "question"` | One spoken answer, then exit | A single question |
| `bolt say "line"` | Speak only. No model | A cue |
| `bolt menubar` | Menu-bar controls | Daily Mac control surface |
| `bolt mac-app build` | Assemble `dist/Bolt.app` so it launches the menu bar | Local only. Not notarized |
| `bolt vault add` | Write a task into the Obsidian vault | The vault wins over Monday |
| `bolt monday sync` | Push vault tasks to the phone board | Once the API token is in `.env` |
| `bolt monday watch` | Pull phone edits back | Or leave `bolt launch` to do it |
| `bolt reminders send "msg"` | Apple Reminders delivery | Evening briefing uses this |
| `bolt send "msg"` | Text and email you, quietly | `--dry-run` to see the path |
| `bolt alerts test --no-sms` | Banner, voice, and email | Check the pipes without a text |
| `bolt discord status` | Last webhook send | `--probe` checks without posting |
| `bolt photo-ocr run photo.jpg` | Handwriting or a photo into text | `--open` to edit the `.txt` |

### Health, files, and accounts

| Command | What it does | Efficient use |
|---|---|---|
| `bolt doctor` | Live, mocked, stale, and missing-key audit | When something feels wrong |
| `bolt verify` | Files, folders, config, environment | After install or a move |
| `bolt health run` | Quick “can I clip?” check with a fix per failure | Faster than a full doctor |
| `bolt budget` | Model spend against the monthly soft cap | Before a paid call |
| `bolt storage status` | Disk and media folder sizes | `rotate` only when you mean to clean |
| `bolt layout run` | Report what is in the wrong top-level folder | It never moves files |
| `bolt migrate-layout run` | Dry-run the move home | `--apply` when the dry run looks right |
| `bolt mac-auto status` | Cron, launchd, and Shortcuts | `install` is a dry run until `--apply` |
| `bolt icloud run` | Report what would sync to iCloud Drive | `--apply` copies |
| `bolt performance run` | Timed speed report | When the pipeline feels slow |
| `bolt word spell recieve` | Dictionary, spelling, thesaurus | Explicit lookup |
| `bolt personality status` | Is the persona file loading | `run` for a one-off in that voice |
| `bolt learning list` | Study notes in `Data/learning` | Your own reading log |
| `bolt domains list` | Creator-domain specs | Read-only browser |
| `bolt pages status` | Cloudflare Pages readiness | Partial. Deploy is explicit |
| `bolt license status` | Whether a LICENSE file exists | None selected yet |
| `bolt site` | Write local `site-data.json` | `--push` soft-fails without a target |
| `bolt drive status` | Daily Log write readiness | `bolt drive-auth` once, in a browser |
| `bolt gcal today` | Today’s calendar events | `bolt gcal-auth` once |
| `bolt gmail status` | Gmail token readiness | Read-only briefing use |
| `bolt merge-py status` | Could Bolt dump its Python into one file | `run` only when you want that dump |
| `bolt titles status` | Local title A/B model | `train` after you have posted titles |
| `bolt version` | Repo path and Python | When two installs might be in play |
| `bolt test` | The test suite | After a code change |
| `bolt twitch_token` | Twitch chat token flow | Once per account |
| `bolt twitch_bot_token` | Bot account token | The chat bot’s login |
| `bolt tiktok_token` | TikTok OAuth | Stats need `video.list`. Posting stays paused |
| `bolt youtube_token` | YouTube readonly OAuth | Then `bolt stats youtube --dry-run` |

### Twitch chat, while the bot is connected

| Command | What it does |
|---|---|
| `!Bolt <question>` | Ask Bolt. The reply comes through the model handler |
| `!clip` | Was a highlight just detected |
| `!uptime` | How long this session has been live |
| `!highlights` | Highlight count this session |
| `!queue` / `!qstatus` | Queue counts, then per-clip detail |
| `!postnow` | Approve and try to publish. The API path is paused, so prefer a manual upload |
| `!dontpost <reason>` / `!skip <reason>` | Hold a clip and record why |
| `!rank <score>` | Set a score by hand |
| `!config <key> <value>` | Change an allowed live setting |
| `!recall <query>` | Search local memory |

## Quick start

Requirements: Python 3.11 or 3.12 and [uv](https://docs.astral.sh/uv/). macOS is the home for voice, OBS, Reminders, and the menu bar.

```bash
git clone https://github.com/BillyThunderstorm/Bolt.git
cd Bolt
uv sync

# Optional feature groups
uv sync --extra subtitles
uv sync --extra ocr
uv sync --extra menubar

cp .env.example .env
# Add only the credentials you plan to use; never commit .env.

uv run bolt verify
uv run bolt doctor
uv run bolt help
uv run bolt morning --quiet
```

If you use pip instead, install the dependencies declared in `pyproject.toml`. This repository does not maintain a separate `requirements.txt`.

## Monday board on your phone

Bolt's notes stay in the Obsidian vault. With a Monday API token, the same tasks, events, and pages show up on the phone board.

1. On monday.com, open your avatar, then **Developers**, and copy the API token.
2. Put it in `.env` as `MONDAY_API_TOKEN`. Leave `MONDAY_BOARD_ID` as `18436882096` unless you made a new board.
3. Run `bolt monday sync` once. After that, Bolt updates Monday when it saves a task, and `bolt monday watch` (or a live `bolt launch`) pulls phone edits back into the vault.

The vault wins if both sides change at the same moment. Bolt will not delete a note because a Monday card disappeared. Details: [Docs/MONDAY.md](Docs/MONDAY.md).

## Safety and publishing

- William approves purchases and publishing.
- TikTok API auto-publishing is paused. Use the manual upload, then `bolt manage posted` or `bolt queue mark-posted`.
- Secrets, credentials, tokens, generated media, and runtime state stay out of Git.
- Optional integrations soft-fail with a clear status and leave local work usable.

## Project map

- [Docs/INDEX.md](Docs/INDEX.md) — documentation map
- [Docs/BOLT_NOW.md](Docs/BOLT_NOW.md) — living status and next steps
- [Docs/READINESS.md](Docs/READINESS.md) — ready vs. partial capabilities
- [Core/bolt_brain.md](Core/bolt_brain.md) — creator context
- [Data/MEMORY.md](Data/MEMORY.md) — current operating memory
- [AGENTS.md](AGENTS.md) — repository operating rules

## Status

Actively developed. On 2026-10-24 the focus is still product testing: three detailed assessments are written, and the next proof is posting them, starting with the K&F neck phone holder. See [Docs/BOLT_NOW.md](Docs/BOLT_NOW.md).

## License

No license has been selected yet. Do not reuse or redistribute this repository until a license is added.

## Author

Built by Billy Carter (@SimplyBilly_).

Navy veteran · independent developer · content creator
