# Bolt

William’s (Billy / SimplyBilly) **local-first AI teammate**: a content manager and business assistant for a real creator business.

The clip pipeline is one subsystem. The job is bigger: help William create, learn, test, post, and grow a sustainable creative life.

If uncertain, Bolt asks: *Will this help William grow, create, learn, or succeed?*

**Decision priority:** Safety → Truth → Long-Term Benefit → Helpfulness → Efficiency → Entertainment.

**Financial work stays fully manual.** Everything else is do-and-notify: Bolt acts, then leaves an Apple Reminder, spoken alert, or file link so William can review or revise. Nothing financial (affiliate codes, deal terms, payments) goes out on its own.

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
- A multi-domain runtime engine (creator-domain specs are browsable and searchable via `bolt domains` — READY as a spec browser only)
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
bolt briefing --send    # evening inbox: Reminders + spoken line + email
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
| Voice | `bolt voice` / `bolt talk` / `bolt say` — the ElevenLabs voice Clyde first, then Nathan (Enhanced); never Siri. Alerts use the same order. |
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
- Alerts via Mac banner + spoken line (**ElevenLabs → Nathan (Enhanced)**, never Siri) + iMessage + email by default. Discord **webhooks** are READY via `bolt discord` / Peak_Hour (21 Oct 2026: one shared sender, sends logged to `logs/discord.jsonl`, `--probe` posts nothing; not a Discord bot).

STT is free Google by default. Whisper/OpenAI speech-in stays off unless both flags are set on purpose.

## Configuration

Tunable in `config.json`:

- `highlight_sensitivity`, `energy_multiplier`, `min_gap_seconds`, `min_confidence`
- `max_highlight_candidates` (pre-cut cap) and `max_clips_per_session`
- `quality_tiers.discard_below` / `quality_tiers.queue_at` / `min_post_score`
- `auto_format_tiktok` for vertical output
- `use_voice_checklist`, `use_obs_integration`
- Pre-stream checklist CLI: `bolt checklist check` / `run` (READY since 20 Oct 2026; soft-fail `Checklist unavailable:`)
- Apple Reminders CLI: `bolt reminders status` (PARTIAL; soft-fail `Reminders unavailable:`)
- Photo OCR CLI: `bolt photo-ocr run <photo or folder>` (READY; one editable `.txt` per photo in `~/Documents/Bolt OCR`; soft-fail `Photo OCR unavailable:`; not `bolt ocr` video HUD)
- Clip compress: `bolt compress run` (READY; ffmpeg-full, keeps frame rate; `bolt compress clean-backups` frees space; soft-fail `Compress unavailable:`)
- Pipeline errors: `bolt error-recovery run` (READY; what failed + what to try; log `Data/pipeline_errors.jsonl`; `quarantine FILE` / `restore` for broken recordings)
- Performance baseline (READY, 20 Oct 2026): `bolt performance run` — Bolt speed check in fresh processes, plain report + comparison with last baseline, JSON in `logs/performance/`; `last` reprints it (soft-fail `Baseline unavailable:`; not analytics/stats)
- Weekly analysis: `bolt weekly run` (READY; real-data report saved to `Data/weekly_reports/`, `--send` emails it; cron Sundays 9 AM; soft-fail `Weekly unavailable:`; not analytics/briefing/stats)
- Duplicate finder: `bolt clip-dedupe run` (READY; read-only SHA256 report of byte-identical media copies + reclaimable space; `run --check FILE`; soft-fail `Hash dedupe unavailable:`; not pipeline Clip_Deduplicator pHash)

Alerts: `bolt alerts status` (READY; `--probe` checks Gmail + ElevenLabs silently) + `Data/configs/storage_alerts.env` (email + iMessage). Template: `Data/configs/storage_alerts.example.env`. Discord webhooks stay `bolt discord`.

Storage: `bolt storage status` / `monitor` / `rotate` / `optimize`.

Mac automation (READY, 20 Oct 2026): `bolt mac-auto` shows every cron job, the launchd watcher and the Bolt Shortcuts — what each does, when it runs, whether its script exists, last log write vs schedule, last error and the fix; `install` is a dry run unless `--apply` (soft-fail `Mac automation unavailable:`). iCloud Drive multi-Mac sync (READY, 22 Oct 2026): `bolt icloud run` shows what would be copied into iCloud Drive/Bolt (files, MB, what's skipped); `run --apply` copies it with no prompts — copy-only, never overwrites a changed iCloud file, skips .env/.env.local + tokens, recordings/media, .git, .venv, caches, logs; log `logs/icloud_sync.jsonl` (soft-fail `iCloud unavailable:`). Advanced: `python3 scripts/install_mac_automation.py` (launchd / cron / Shortcuts). Preferred alerts (PARTIAL): `bolt alerts` (Mac/Voice/email/iMessage; soft-fail `Alerts unavailable:`). Pre-stream checklist (PARTIAL): `bolt checklist` (soft-fail `Checklist unavailable:`; mic/STT gated). Apple Reminders (PARTIAL): `bolt reminders` (soft-fail `Reminders unavailable:`; Darwin/TCC gated). Photo OCR (PARTIAL): `bolt photo-ocr` status/list/run (soft-fail `Photo OCR unavailable:`; Darwin/Vision or Tesseract gated; distinct from `bolt ocr` video HUD). Advanced: `python3 scripts/ocr_to_editable.py photo.jpg --open`. Video compress (PARTIAL): `bolt compress` status/list/run (soft-fail `Compress unavailable:`; HandBrake gated; `media/clips`). Advanced: `bash scripts/compress_videos.sh`. Performance baseline (READY, 20 Oct 2026): `bolt performance run [--quick]` times Bolt startup + each module in fresh processes, compares with the last baseline, saves `logs/performance/` JSON; `last` reprints (soft-fail `Baseline unavailable:`). Advanced: `python3 scripts/performance_baseline.py`. Weekly analysis (PARTIAL): `bolt weekly` status/list/run (soft-fail `Weekly unavailable:`; `Data/weekly_reports/`). Advanced: `python3 scripts/weekly_analysis.py --print`. Filter backlog (READY, 19 Oct 2026): `bolt filter-backlog run [--dry-run]` moves clips below the game profile's `min_clip_score` (with their sidecar/thumbnail/captions) to `media/clips/_low_score/`; keeps queued and unscorable clips; `bolt filter-backlog restore [NAME|--all]` undoes (soft-fail `Backlog unavailable:`). Advanced: `python3 scripts/Filter_Backlog.py --dry-run`. Make highlights (READY): `bolt make-highlights` status/list/run (top clips → `media/output/YYYY-MM-DD_highlight_reel.mp4`; soft-fail `Highlights unavailable:`; former SHELL Helix paste; engine `make_twitch_highlights.py`). Advanced: `python3 scripts/make_twitch_highlights.py --list`. Reprocess clips (READY, 18 Oct 2026): `bolt reprocess run [NAME] [--force]` → verified 9:16 verticals in `media/vertical_clips` + plans merged into `Data/multi_platform_queue.json` (soft-fail `Reprocess unavailable:`; engine `reprocess_clips.py`; no TikTok auto-upload). Advanced: `python3 scripts/reprocess_clips.py --dry-run`. Quick health check (READY, 21 Oct 2026): `bolt health run` checks in about a second whether Bolt is ready to make clips (files, folders, ffmpeg/ffprobe, Whisper venv or Mac CLI, packages, pipeline modules, config, Grok/Ollama/OpenAI, disk) and prints the fix for every problem; `--json`, `--no-network` (soft-fail `Health check unavailable:`; full audit: `bolt doctor`). Advanced: `python3 scripts/health_check.py`. Layout check (READY, 21 Oct 2026): `bolt layout run` lists everything at the top of the Bolt folder (in place / wrong spot / to look at / notes); report only. Layout migrate (READY, 21 Oct 2026): `bolt migrate-layout run --apply` moves stray top-folder files home, never overwrites (duplicates to the Trash, different files skipped with the fix), `--tidy-empty`, `undo` puts the last run back (soft-fail `Migrate unavailable:`; dry run unless `--apply`). SMS/email notify (PARTIAL): `bolt send` status/list/send (soft-fail `Notify unavailable:`; prefers Bolt_Alerts; distinct from `bolt alerts` / `bolt discord`). ICS calendar (READY): `bolt calendar` status/list/run (correct Chicago times, posted skipped, refreshed + upcoming posts emailed by the 5 PM briefing; soft-fail `Calendar unavailable:`). Refresh memory (READY): `bolt refresh-memory` status/list/run (atomic + verified; `--if-stale`; soft-fail `Memory refresh unavailable:`). Long-term memory (READY, 18 Oct 2026): `bolt memory recall "question"` answers from Data/ memory + live game via LLM_Handler (Grok → Ollama → OpenAI; `--provider` pins one); `bolt memory remember "fact"` saves a dated fact (no same-day duplicates); status/list/load (soft-fail `Bolt memory unavailable:`). Memory search (READY): `bolt memsearch` status/list/run (soft-fail `Memory search unavailable:`; wraps Memory_Index retrieve; distinct from READY `bolt search` web + READY `bolt memory` / `bolt refresh-memory`). Log perf (READY, 19 Oct 2026): `bolt log-perf run --clip <queue id> --views N` (re-log updates the row) (soft-fail `Log perf unavailable:`; former thin SCRIPT_MAP `log_perf`; manual TT/X learning; distinct from READY `bolt stats`). Hash dedupe (PARTIAL): `bolt clip-dedupe` status/list/run (soft-fail `Hash dedupe unavailable:`; former thin SCRIPT_MAP `clip_dedupe` with `parents[3]` wrong root; SHA256 → `Data/media_hash_db.json`; distinct from READY pipeline `Clip_Deduplicator` / `Data/seen_clips.json`). Advanced: `python3 scripts/clip_deduplicator.py --dry-run`.

Post-stream + music (18 Oct 2026; `bolt motion` + `bolt game` + `bolt wrap` + `bolt release` READY): `bolt game` (READY: follows your Twitch category; refresh at stream start; status flags drift vs Twitch + stale warning in doctor), `bolt motion <video>` (frame-difference high-action windows → JSON), `bolt wrap` (READY: latest VOD → highlights + motion → clips / reel / Whisper captions → `media/output/wraps/<date>_<vod>_wrap/`, Finder-tagged; `--dry-run`), `bolt release <folder>` (READY: WAV 44.1k/16-bit + metadata CSV/JSON + cover check + checklist for DistroKid/TuneCore/CD Baby; never uploads). Details: `Core/modules/BOLT_COMMANDS.md`.

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
- Bolt.app (menu bar) is READY via `bolt mac-app install` (21 Oct 2026: copies to `~/Applications`, open from Spotlight; menu bar only; logs to `logs/menubar.log`; `bolt mac-app open` never starts a second copy; not notarized / not iOS).
- Mac automation is READY via `bolt mac-auto` (20 Oct 2026: per-job status for every cron line, launchd `com.streamer.ai-assistant` and the 6 Bolt Shortcuts — OK / LATE / STALE / FAILING / BROKEN with the exact fix; `install` dry-run unless `--apply`, no duplicate cron lines, crontab backed up first).
- iCloud Drive multi-Mac sync is READY via `bolt icloud` (22 Oct 2026; `run` dry-run report, `run --apply` copy-only into iCloud Drive/Bolt for Magneto; soft-fail `iCloud unavailable:`; distinct from READY mac-auto — William-specific, not stranger-ready).
- Mac / Voice / email / iMessage alerts are READY via `bolt alerts` (20 Oct 2026: ElevenLabs → Nathan voice, channel picking on test/send, silent `--probe`, `logs/alerts.jsonl`; soft-fail `Alerts unavailable:`; not a Discord bot).
- Pre-stream checklist is READY via `bolt checklist` (status/list/check/run/reset; typing works alongside voice; resumes an unfinished session after a relaunch).
- Apple Reminders delivery is PARTIAL via `bolt reminders` (status/list/test/send; soft-fail `Reminders unavailable:`; Darwin/TCC gated).
- Photo OCR is READY via `bolt photo-ocr` (status/list/run; Apple Vision first, tesseract fallback, HEIC ok; skips done photos unless `--force`; soft-fail `Photo OCR unavailable:`; not `bolt ocr` video HUD).
- Clip compress is READY via `bolt compress` (20 Oct 2026: status/list/run/clean-backups; ffmpeg-full; originals kept in `media/clips/originals_backup/` until cleaned).
- Error recovery is READY via `bolt error-recovery` (20 Oct 2026: clip pipeline errors logged by `notify_error`; `run` report; unreadable recordings skipped; `quarantine` / `restore`).
- Folder watch is READY via `bolt watch run` (clips each new recording in `media/Recordings`; `--once` / `--dry-run`; soft-fail `Watch unavailable:`). Log perf is READY via `bolt log-perf run --clip <queue id|name> --views N` (fills trigger/game from the queue + sidecar; re-log updates the row; soft-fail `Log perf unavailable:`; manual TikTok/X/IG/Kick learning; distinct from READY `bolt stats`).
- Hash dedupe is READY via `bolt clip-dedupe` (status/list/run; read-only, never deletes; soft-fail `Hash dedupe unavailable:`; SHA256 `Data/media_hash_db.json`; not pipeline pHash / `Data/seen_clips.json`).

| `bolt layout` | READY | Tidy-top-folder check (`Layout_Check`): in place / wrong spot / to look at / notes; `run --all`; report only |
| `bolt migrate-layout` | READY | Move stray top-folder files home (`Migrate_Layout`); dry run unless `--apply`; never overwrites; `undo` |
| `bolt calendar` | READY | Local ICS feeds (`ICS_Calendar`): briefing, weekly, peak windows, upcoming posts; soft-fail `Calendar unavailable:` |
| `bolt monday` | READY | Vault ↔ Monday phone board (`Monday_Sync`): `sync`, `sync --dry-run`, `watch`; off without `MONDAY_API_TOKEN`; soft-fail `Monday unavailable:` |
| `bolt send` | READY | Text + email yourself in one command (`Send_Notify` via Bolt_Alerts); `--dry-run`, `status --probe`; soft-fail `Notify unavailable:` |
| `bolt refresh-memory` | READY | Memory index rebuild (`Refresh_Memory`; atomic + verified, `--if-stale`, status shows stale/fresh); soft-fail `Memory refresh unavailable:` |
| `bolt memory` | READY | Long-term memory: `recall "q"` via LLM_Handler (Grok → Ollama → OpenAI) + `remember "fact"` (`Bolt_Memory`); soft-fail `Bolt memory unavailable:` |
| `bolt memsearch` | READY | Local memory search (`Memory_Search`): `bolt memsearch "words"`; auto-rebuilds a stale index; word-matched hits only |
| `bolt log-perf` | READY | Log a hand-posted clip's views (`--clip <queue id> --views N`); re-log updates; soft-fail `Log perf unavailable:` |
| `bolt personality` | READY | System prompt (`Data/context/bolt-personality.md` via `LLM_Handler`, not Gemini); soft-fail `Personality unavailable:` |
