# Bolt

William’s (Billy / SimplyBilly) **local-first AI teammate**: a content manager and business assistant for a real creator business.

The clip pipeline is one subsystem. The job is bigger: help William create, learn, test, post, and grow a sustainable creative life.

If uncertain, Bolt asks: *Will this help William grow, create, learn, or succeed?*

**Decision priority:** Safety → Truth → Long-Term Benefit → Helpfulness → Efficiency → Entertainment.

**Posting always requires William’s approval.** Nothing publishes because a file landed in a folder.

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
- A Discord-first bot
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

Preferred day-to-day path: `bolt day --decide` → review → post. If you posted outside Bolt, `bolt queue mark-posted`.

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
| Voice | `bolt voice` / `bolt talk` / `bolt say` — Siri Voice 3 (`say -v "Voice 3"`) |
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
- Alerts via Mac banner + iMessage + email. **No Discord.**

STT is free Google by default. Whisper/OpenAI speech-in stays off unless both flags are set on purpose.

## Configuration

Tunable in `config.json`:

- `highlight_sensitivity`, `energy_multiplier`, `min_gap_seconds`, `min_confidence`
- `max_highlight_candidates` (pre-cut cap) and `max_clips_per_session`
- `quality_tiers.discard_below` / `quality_tiers.queue_at` / `min_post_score`
- `auto_format_tiktok` for vertical output
- `use_voice_checklist`, `use_obs_integration`

Alerts: `Data/configs/storage_alerts.env` (email + iMessage). Template: `Data/configs/storage_alerts.example.env`.

Storage: `bolt storage status` / `monitor` / `rotate` / `optimize`.

## Documentation

| Doc | What it covers |
|---|---|
| [`modules/BOLT_COMMANDS.md`](modules/BOLT_COMMANDS.md) | **All live commands** |
| [`SYSTEM_README.pages`](SYSTEM_README.pages) | Purpose and current shape (Pages) |
| [`../Docs/architecture/SYSTEM_README.md`](../Docs/architecture/SYSTEM_README.md) | Same, in markdown |
| [`../Docs/INDEX.md`](../Docs/INDEX.md) | Doc map |
| [`../Docs/PROJECT_STATUS.md`](../Docs/PROJECT_STATUS.md) | Build status |
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

*Last updated: August 15, 2026 — aligned with current purpose, `bolt` CLI, and light LLM stack.*
