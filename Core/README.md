# Bolt

William’s (Billy / SimplyBilly) **local-first AI teammate**: a content manager and business assistant for a real creator business.

The clip pipeline is one subsystem. The job is bigger: help William create, learn, test, post, and grow a sustainable creative life.

If uncertain, Bolt asks: *Will this help William grow, create, learn, or succeed?*

**Decision priority:** Safety → Truth → Long-Term Benefit → Helpfulness → Efficiency → Entertainment.

**Financial work stays fully manual.** Everything else is do-and-notify: Bolt acts, then leaves an Apple Reminder, Voice 3 alert, or file link so William can review or revise. Nothing financial (affiliate codes, deal terms, payments) goes out on its own.

**Commands live in one place:** [`modules/BOLT_COMMANDS.md`](modules/BOLT_COMMANDS.md)

Purpose and architecture: [`SYSTEM_README.pages`](SYSTEM_README.pages) and [`../Docs/architecture/SYSTEM_README.md`](../Docs/architecture/SYSTEM_README.md)

## What Bolt is — and is not

**Bolt is**

- A local CLI (`bolt`) plus voice, Twitch chat, and a checkup dashboard
- A daily production OS: brief → decide the queue → post
- A clip factory with a hard candidate cap and a ranked ready-queue
- A catalog / storefront / sponsor / research / mission planner
- A memory system that learns from what actually posted

**Bolt is not**

- An auto-poster that skips review
- A Discord-first bot (optional **webhook** alerts only — `bolt discord`; not a bot)
- A shipping curriculum product (`Data/learning/` is a personal study log; browse via `bolt learning`)
- A multi-domain runtime engine (creator-domain specs are browsable via `bolt domains`; PARTIAL discoverability only)
- A stranger-ready Cloudflare Pages product (`bolt pages` is PARTIAL William-specific deploy soft-fail only)
- A gaming-only clip factory
- Calendar theater or fake productivity
- A system that treats every saved moment as post-worthy

## Quick start

From the repo root (`/Users/carter/developer/Bolt`):

```bash
uv sync
alias bolt='/Users/carter/developer/Bolt/.venv/bin/bolt'

bolt setup              # one-shot readiness check; exits
bolt day --decide       # daily production path
bolt briefing --send    # evening inbox: Reminders + Voice 3 + email
bolt launch             # live folder-watch
bolt queue              # what you can post
bolt help               # command summary
bolt verify             # files, folders, config, env
bolt test               # test suite
```

Without the alias: `uv run bolt <command>`.

| Command | Meaning |
|---|---|
| `bolt setup` | Finite config/key check. Prints “Setup complete” and **exits**. Does not start live watch. |
| `bolt launch` | Long-running live watcher |
| `bolt day` | Morning brief + next clip. `--decide` runs queue review. `--quiet` for non-interactive use. |
| `bolt week` | This week / last week / do not suggest. Read before any new plan. |
| `bolt queue decide` | Interactive review: open / approve / post now / hold / retitle / skip |
| `bolt word` | Dictionary / spellcheck / thesaurus. Local spell; free define/syn. Aliases: `dict`, `spell`, `thesaurus`. |

Preferred day-to-day path: `bolt day --decide` → review → post. Evening inbox is `bolt briefing --send` (cron 17:00 → Reminders list **Bolt**). If you posted outside Bolt, `bolt queue mark-posted`.

## Creator lanes

**Priority now:** games + tech testing / reviews.

**Expansion:** general product testing, Amazon Influencer (`billycarter-20`), beauty / skincare, AI learned in public, and building Bolt itself.

Gaming is one strong lane. It is not the whole mission.

| Platform | Handle | Role |
|---|---|---|
| TikTok | @itssimplybilly | Primary short-form |
| Twitch | ItsSimplyBilly | Live source material |
| YouTube | @SimplyBilly | Shorts now, long-form later |
| X | @SimplyBilly_ | Presence / takes |
| Amazon Influencer | tag `billycarter-20` | Storefront + affiliate |

## Layout

Paths are from the repo root, not this folder.

```text
Bolt/
├── bin/bolt                 # Real CLI implementation
├── bolt_cli/                # Thin installer entry (uv run bolt)
├── Core/                    # Runtime: bot, modules, config, brain
│   ├── bot.py               # Clip pipeline + Twitch bot
│   ├── launch.py            # Live-watch handoff (prefer: bolt launch)
│   ├── bolt_day.py          # Morning flow (prefer: bolt day)
│   ├── config.json          # Runtime config
│   ├── bolt_brain.md        # Creator profile
│   └── modules/             # Detectors, queue, manager, LLM, voice
├── Data/                    # Queue state, memory, catalogs
│   └── ready_to_post.json   # The ready-queue (not a folder)
├── media/
│   ├── Recordings/          # Source VODs
│   ├── clips/               # Intermediate / horizontal cuts
│   └── vertical_clips/      # 9:16 files only — not the approval surface
├── Docs/                    # Status, guides, briefings
├── scripts/                 # Maintenance, tokens, processing helpers
├── App/                     # UI, brand, sites
└── pyproject.toml           # uv / bolt console script
```

**Two stores stay separate.** Disk files are media. `Data/ready_to_post.json` is the queue. Editing or renaming a file under `media/vertical_clips/` does not enqueue or approve it. Register hand-edited finals with `bolt queue add`.

## How the pieces fit

1. **Detect** — `Highlight_Detector` (energy + prominence, min-gap, hard candidate cap)
2. **Cap** — `max_highlight_candidates` (default 12) **before** any cutting
3. **Cut** — `Clip_Generator` → `media/clips/`
4. **Dedup** — against seen-clips / hash db
5. **Rank** — `Clip_Ranker` (quality tiers + recency-weighted learned boost)
6. **Enrich** — titles, subtitles, vertical 9:16 → `media/vertical_clips/`
7. **Queue** — rows in `Data/ready_to_post.json`
8. **Review** — `bolt queue decide` (approve / hold / post now / skip)
9. **Learn** — performance outcomes feed the ranker

Caps matter. Uncapped long VODs explode into hundreds of spikes and hang the machine.

**Quality tiers** (`config.json`):

- Below 60: discard
- 60–64: keep on disk, no queue
- 65–79: format and queue
- 80+: queue and alert at peak hours

Peak windows (America/New_York): 7–9 AM, 12–2 PM, 7–10 PM. About 30 minutes of review before peak.

Around the pipeline:

- **`Think_Learn_Decide`** is the canonical reasoning path. `Brain_Controller` is a compatibility wrapper.
- **`Memory_Index`** indexes markdown memory, queue/history, decisions, and posted performance.
- **Content Manager** — `bolt manage` / `store` / `social` / `sponsors`
- **Researcher** — `bolt research` (C5 keep/drop is always William’s call)
- **Missions** — `bolt mission` (planning only; nothing posts or buys without approval)

## Interfaces

| Interface | How |
|---|---|
| CLI | `bolt …` |
| Voice | `bolt voice` / `bolt talk` / `bolt say` — Siri Voice 3 (`say -v "Voice 3"`). Alerts use the same voice. |
| Reminders | List **Bolt** — daily 17:00 briefing + action items with a link to `Docs/briefings/daily/latest_morning.md` |
| Shortcuts | Bolt Morning / Review Queue / Stats / Wrap-Up, plus Extract Text from Photos |
| Twitch chat | `!queue` `!qstatus` `!postnow` `!dontpost` `!skip` |
| Dashboard | `Checkup_Writer` → `Data/Bolt_data.js` |
| Sites | bolt.billythunderstorm.us · billythunderstorm.us · billythunderstorm.live |

Voice **does** run: day kickoff, queue status, approve/hold/post next, budget, storage one-liner, research/mission status.

Voice **does not** run: recordings processing, TikTok OAuth, queue add/retitle, setup, site deploy. Full queue review stays in the terminal.

## LLM and cost

Light mode by default (`BOLT_LLM_MODE=light`).

- **Ollama** for chat, titles, everyday status
- **Grok API** only for high-value strategy / research / decisions
- SuperGrok subscription is app/web chat only — it does **not** cover the API
- Soft cap **$35/month** → force local when hit (`bolt budget`)
- Alerts via Mac banner + **Voice 3** + iMessage + email by default. Optional Discord **webhooks** via `bolt discord` / Peak_Hour (not a Discord bot).

STT is free Google by default. Whisper/OpenAI speech-in stays off unless both flags are set on purpose.

## Configuration

Tunable in `config.json`:

- `highlight_sensitivity`, `energy_multiplier`, `min_gap_seconds`, `min_confidence`
- `max_highlight_candidates` (pre-cut cap) and `max_clips_per_session`
- `quality_tiers.discard_below` / `quality_tiers.queue_at` / `min_post_score`
- `auto_format_tiktok` for vertical output
- `use_voice_checklist`, `use_obs_integration`
- Pre-stream checklist CLI: `bolt checklist status` (PARTIAL; soft-fail `Checklist unavailable:`)
- Apple Reminders CLI: `bolt reminders status` (PARTIAL; soft-fail `Reminders unavailable:`)
- Photo OCR CLI: `bolt photo-ocr status` (PARTIAL; soft-fail `Photo OCR unavailable:`; not `bolt ocr` video HUD)
- Video compress CLI: `bolt compress status` (PARTIAL; soft-fail `Compress unavailable:`; HandBrake gated)
- Performance baseline CLI: `bolt performance status` (PARTIAL; soft-fail `Baseline unavailable:`; not analytics/stats)
- Weekly analysis CLI: `bolt weekly status` (PARTIAL; soft-fail `Weekly unavailable:`; not analytics/briefing/stats)
- Hash dedupe CLI: `bolt clip-dedupe status` (PARTIAL; soft-fail `Hash dedupe unavailable:`; not pipeline Clip_Deduplicator pHash)

Alerts: `bolt alerts status` (PARTIAL) + `Data/configs/storage_alerts.env` (email + iMessage). Template: `Data/configs/storage_alerts.example.env`. Discord webhooks stay `bolt discord`.

Storage: `bolt storage status` / `monitor` / `rotate` / `optimize`.

Mac automation (PARTIAL): `bolt mac-auto` status/list/install (soft-fail `Mac automation unavailable:`; William-specific). iCloud Drive multi-Mac sync (PARTIAL): `bolt icloud` status/list/run (soft-fail `iCloud unavailable:`; William-specific; distinct from mac-auto). Advanced: `python3 scripts/install_mac_automation.py` (launchd / cron / Shortcuts). Preferred alerts (PARTIAL): `bolt alerts` (Mac/Voice/email/iMessage; soft-fail `Alerts unavailable:`). Pre-stream checklist (PARTIAL): `bolt checklist` (soft-fail `Checklist unavailable:`; mic/STT gated). Apple Reminders (PARTIAL): `bolt reminders` (soft-fail `Reminders unavailable:`; Darwin/TCC gated). Photo OCR (PARTIAL): `bolt photo-ocr` status/list/run (soft-fail `Photo OCR unavailable:`; Darwin/Vision or Tesseract gated; distinct from `bolt ocr` video HUD). Advanced: `python3 scripts/ocr_to_editable.py photo.jpg --open`. Video compress (PARTIAL): `bolt compress` status/list/run (soft-fail `Compress unavailable:`; HandBrake gated; `media/clips`). Advanced: `bash scripts/compress_videos.sh`. Performance baseline (PARTIAL): `bolt performance` status/list/run (soft-fail `Baseline unavailable:`; `logs/performance/`). Advanced: `python3 scripts/performance_baseline.py`. Weekly analysis (PARTIAL): `bolt weekly` status/list/run (soft-fail `Weekly unavailable:`; `Data/weekly_reports/`). Advanced: `python3 scripts/weekly_analysis.py --print`. Filter backlog (PARTIAL): `bolt filter-backlog` status/list/run (soft-fail `Backlog unavailable:`; `media/clips/_low_score/`). Advanced: `python3 scripts/Filter_Backlog.py --dry-run`. Make highlights (PARTIAL): `bolt make-highlights` status/list/run (soft-fail `Highlights unavailable:`; former SHELL Helix paste; engine `make_twitch_highlights.py`). Advanced: `python3 scripts/make_twitch_highlights.py --list`. Reprocess clips (PARTIAL): `bolt reprocess` status/list/run (soft-fail `Reprocess unavailable:`; former SHELL wrong PROJECT_ROOT; engine `reprocess_clips.py`; no TikTok auto-upload). Advanced: `python3 scripts/reprocess_clips.py --dry-run`. Legacy health check (PARTIAL): `bolt health` status/list/run (soft-fail `Health check unavailable:`; former SHELL pre-reorg CWD paths; prefer `bolt doctor`). Advanced: `python3 scripts/health_check.py`. Layout check (PARTIAL): `bolt layout` status/list/run (soft-fail `Layout unavailable:`; report-only `check_layout.py`; never moves). Layout migrate (PARTIAL): `bolt migrate-layout` status/list/run (soft-fail `Migrate unavailable:`; dry-run default; `--apply` moves; companion to `bolt layout`). SMS/email notify (PARTIAL): `bolt send` status/list/send (soft-fail `Notify unavailable:`; prefers Bolt_Alerts; distinct from `bolt alerts` / `bolt discord`). ICS calendar (PARTIAL): `bolt calendar` status/list/run (soft-fail `Calendar unavailable:`). Refresh memory (PARTIAL): `bolt refresh-memory` status/list/run (soft-fail `Memory refresh unavailable:`). Long-term memory (PARTIAL): `bolt memory` status/list/remember/recall/load (soft-fail `Bolt memory unavailable:`; distinct from READY briefing retrieve + PARTIAL `bolt refresh-memory`). Memory search (PARTIAL): `bolt memsearch` status/list/run (soft-fail `Memory search unavailable:`; wraps Memory_Index retrieve; distinct from READY `bolt search` web + PARTIAL `bolt memory` / `bolt refresh-memory`). Log perf (PARTIAL): `bolt log-perf` status/list/run (soft-fail `Log perf unavailable:`; former thin SCRIPT_MAP `log_perf`; manual TT/X learning; distinct from READY `bolt stats`). Hash dedupe (PARTIAL): `bolt clip-dedupe` status/list/run (soft-fail `Hash dedupe unavailable:`; former thin SCRIPT_MAP `clip_dedupe` with `parents[3]` wrong root; SHA256 → `Data/media_hash_db.json`; distinct from READY pipeline `Clip_Deduplicator` / `Data/seen_clips.json`). Advanced: `python3 scripts/clip_deduplicator.py --dry-run`.

## Documentation

| Doc | What it covers |
|---|---|
| [`modules/BOLT_COMMANDS.md`](modules/BOLT_COMMANDS.md) | **All live commands** |
| [`SYSTEM_README.pages`](SYSTEM_README.pages) | Purpose and current shape (Pages) |
| [`../Docs/architecture/SYSTEM_README.md`](../Docs/architecture/SYSTEM_README.md) | Same, in markdown |
| [`../Docs/INDEX.md`](../Docs/INDEX.md) | Doc map |
| [`../Docs/BOLT_NOW.md`](../Docs/BOLT_NOW.md) | Living status / plan / future |
| [`bolt_brain.md`](bolt_brain.md) | Creator profile |
| [`../Data/context/bolt-personality.md`](../Data/context/bolt-personality.md) | Persona |
| [`../Data/content/full-creator-vision.md`](../Data/content/full-creator-vision.md) | Creator north star |

## Troubleshooting

| Problem | First thing to check |
|---|---|
| `bolt setup` starts watching folders | That is a bug. Setup must exit. Use `bolt launch` for live watch. |
| No highlights / too many clips | Caps first (`max_highlight_candidates`). Then `highlight_sensitivity` / `min_gap_seconds`. |
| Queue count looks high, files missing | `bolt queue clean` — ghosts are JSON rows, not media |
| Hand-edited vertical clip not in queue | `bolt queue add <file>` — the folder is not the queue |
| Posted outside Bolt, still “ready” | `bolt queue mark-posted <id\|filename>` |
| Voice speaks but does the wrong thing | Use a wired phrase, or `bolt voice --text`, or the terminal command |
| Vector DB / Nexus hangs | Ollama down — should fail fast. Start Ollama, `ollama pull nomic-embed-text`, `bolt reindex` |
| API spend surprise | SuperGrok ≠ API. Check `bolt budget`. Light mode should keep chat/titles on Ollama. |
| Storage alerts silent | Uncommented lines in `Data/configs/storage_alerts.env`; iMessage, not AT&T email-to-SMS |
| Tests / verify | `bolt verify` then `bolt test` |

*Last updated: August 17, 2026 — evening Reminders briefing, Voice 3 alerts, Shortcuts, do-and-notify except financial.*

- License tooling is PARTIAL via `bolt license` (status/list/show/set; soft-fail `License unavailable:`; does not auto-pick SPDX).
- Mac `.app` packaging is PARTIAL via `bolt mac-app` (status/list/build; soft-fail `Mac app unavailable:`; thin local wrapper — not notarized / not iOS; prefer `bolt menubar`).
- Mac automation is PARTIAL via `bolt mac-auto` (status/list/install; soft-fail `Mac automation unavailable:`; launchd/cron/Shortcuts — William-specific, not stranger-ready).
- iCloud Drive multi-Mac sync is PARTIAL via `bolt icloud` (status/list/run; soft-fail `iCloud unavailable:`; distinct from mac-auto — William-specific, not stranger-ready).
- Mac / Voice / email / iMessage alerts are PARTIAL via `bolt alerts` (status/list/test/send; soft-fail `Alerts unavailable:`; not a Discord bot).
- Pre-stream voice checklist is PARTIAL via `bolt checklist` (status/list/run; soft-fail `Checklist unavailable:`; mic/STT gated).
- Apple Reminders delivery is PARTIAL via `bolt reminders` (status/list/test/send; soft-fail `Reminders unavailable:`; Darwin/TCC gated).
- Photo OCR is PARTIAL via `bolt photo-ocr` (status/list/run; soft-fail `Photo OCR unavailable:`; Darwin/Vision or Tesseract gated; not `bolt ocr` video HUD).
- Video compress is PARTIAL via `bolt compress` (status/list/run; soft-fail `Compress unavailable:`; HandBrakeCLI gated; `media/clips`).
- Folder watch is PARTIAL via `bolt watch` (soft-fail `Watch unavailable:`). Log perf is PARTIAL via `bolt log-perf` (status/list/run; soft-fail `Log perf unavailable:`; manual TT/X learning; distinct from READY `bolt stats`).
- Hash dedupe is PARTIAL via `bolt clip-dedupe` (status/list/run; soft-fail `Hash dedupe unavailable:`; SHA256 `Data/media_hash_db.json`; not pipeline pHash / `Data/seen_clips.json`).

| `bolt layout` | PARTIAL | Layout audit (`Layout_Check`); soft-fail `Layout unavailable:` |
| `bolt migrate-layout` | PARTIAL | Layout migrator (`Migrate_Layout`); soft-fail `Migrate unavailable:`; dry-run default |
| `bolt calendar` | PARTIAL | Local ICS feeds (`ICS_Calendar`); soft-fail `Calendar unavailable:` |
| `bolt send` | PARTIAL | SMS/email notify (`Send_Notify`); soft-fail `Notify unavailable:` |
| `bolt refresh-memory` | PARTIAL | Memory index rebuild (`Refresh_Memory`); soft-fail `Memory refresh unavailable:` |
| `bolt memory` | PARTIAL | Long-term memory store (`Bolt_Memory`); soft-fail `Bolt memory unavailable:` |
| `bolt memsearch` | PARTIAL | Phase 4 semantic memory search (`Memory_Search`); soft-fail `Memory search unavailable:` |
| `bolt log-perf` | PARTIAL | Manual learning logger (`Log_Perf`); soft-fail `Log perf unavailable:` |
| `bolt personality` | READY | System prompt (`Data/context/bolt-personality.md` via `LLM_Handler`, not Gemini); soft-fail `Personality unavailable:` |
