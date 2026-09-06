# Bolt readiness audit

*31 August 2026 · Goddess.local · `/Users/carter/developer/Bolt`*
*Originally read-only 31 Aug 2026. Updated 3 Sep 2026: Analytics_Tracker → `bolt analytics`. Updated 4 Sep 2026: Subtitle_Generator → bot.py Step D; Smart_Trim/Text_Overlay → `bolt enhance`; Checkup dashboard → `bolt checkup` + `App/Bolt_Checkup.html`; Video_Intelligence OCR → bot.py Step C + `bolt ocr`. Updated 5 Sep 2026: Anomaly_Detector / Predictive_Analytics → `bolt anomaly` / `bolt predict` + Peak_Hour_Notifier / bot.py hooks. Updated 5 Sep 2026 (pm): Multi_Publisher → `bolt multi` + `Data/multi_platform_queue.json`; Google Calendar/Gmail/Drive tokens → `Data/`. Updated 5 Sep 2026 (later): Clip cleanup on launch → `media/clips` + `media/vertical_clips` via config. Updated 5 Sep 2026 (evening): macOS menu bar → `bolt menubar` + fixed `App/app.py` paths + `uv sync --extra menubar`. Updated 5 Sep 2026 (night): Clip_Factory burn-in captions from Step D `transcript_segments` → READY. Updated 5 Sep 2026 (late): Bolt_Search → live DuckDuckGo via `ddgs` + `bolt search` (!Bolt chat + CLI).*

If someone else used Bolt tomorrow, the **real product** is the CLI plus the local clip factory and queue — not the apps or auto-posting.

Color key: **READY** (works) · **PARTIAL** (real code, gated or incomplete) · **SHELL** (stub / goes nowhere) · **IDEA** (named, not built)

---

## How you actually run it

Canonical entry: `bin/bolt` (`uv sync`, then `uv run bolt …` or the venv shim).

```bash
cd /Users/carter/developer/Bolt
uv sync
bolt setup          # Core/launch.py — finite, must exit
bolt verify / bolt doctor
bolt recordings     # scripts/process_recordings.py → Core/bot.py
bolt day --decide   # Core/bolt_day.py → queue review
bolt launch         # Core/launch.py → exec Core/bot.py
bolt queue decide   # Peak_Hour_Notifier
bolt morning / manage / research / mission / voice / budget / overlay / analytics / anomaly / predict / enhance / checkup / ocr / menubar / search
```

Live clip path: `launch.py` → `bot.py.process_recording`: Highlight_Detector → Clip_Generator → Clip_Deduplicator → Title_Generator → Subtitle_Generator → Clip_Ranker → Clip_Factory → Post_Queue / Peak_Hour_Notifier.

Not real launchers for a stranger: `python3 Core/src/launch.py` (empty `Core/src/`). Menu bar is real via `bolt menubar` (rumps; not a shipping Mac/iOS `.app` bundle).

---

## READY — another person could use this

| Surface | Path | Why |
|---|---|---|
| CLI | `bin/bolt`, `bolt_cli/` | Subcommands map to real scripts; `uv run bolt` works after `uv sync`. |
| Setup / live launcher | `Core/launch.py` | Config wizard, env check, OBS wait, then exec `Core/bot.py`. |
| Clip pipeline | `Core/bot.py` + Highlight_Detector, Clip_Generator, Clip_Factory, Clip_Deduplicator, Watcher | Real ffmpeg/librosa/moviepy; folder-watch + `bolt recordings`. |
| Ranker | `Core/modules/Clip_Ranker.py` | Trigger bonuses + recency-weighted `learned_boost()`; called from `bot.py`. |
| Queue / review | Peak_Hour_Notifier, Post_Queue | `bolt queue status\|decide\|approve\|hold\|mark-posted\|package` writes `Data/ready_to_post.json`. |
| Titles (local) | Title_Generator | Templates always work; AI path optional. |
| Subtitles (local) | Subtitle_Generator + `bot.py` Step D + Clip_Factory burn-in | Whisper segments → `.srt` sidecar; `format_for_tiktok` burns timed drawtext captions into the vertical/TikTok output. Missing Whisper / no segments / ffmpeg drawtext failure = warn + continue without burn-in (`uv sync --extra subtitles`; prefer `ffmpeg-full` for drawtext). |
| LLM routing | LLM_Handler, LLM_Budget, XAI_Usage | Real OpenAI-compatible clients, light/local/full, monthly cap. |
| Decision engine | Think_Learn_Decide | Local `think_and_propose`, queue_clip auto-approve; wired in `bot.py`. |
| Content Manager | Content_Manager | Real JSON catalog CRUD: `bolt manage/store/social/sponsors/morning`. |
| Researcher | Researcher | `bolt research add\|note\|c5\|find`; DDG via `scripts/_research.py`. |
| Missions | Command_Center + creator-command-center skill | Scaffolds markdown under `Data/memory/missions/`. |
| Day / week / voice | bolt_day, Week_Card, Intent_Router, bolt_live_voice, Bolt_Voice | Grounded in queue/peak; macOS `say` TTS. |
| Briefing + Reminders | daily_briefing, Apple_Reminders | `bolt briefing --send` is a real JXA path. |
| Overlay | overlay_server + `App/overlay/*.html` | Local HTTP on :8766; Stream Deck scripts. |
| Doctor / verify / tests | doctor.py, verify.py, `Data/tests/` | `bolt doctor`, `bolt verify`, `bolt test`. |
| Analytics summary | `Core/modules/Analytics_Tracker.py` + `bolt analytics` | Reads `Data/performance_outcomes.jsonl`; `bolt analytics [--days N] [--top N]`. |
| Clip enhance | Smart_Trim + Text_Overlay + `bolt enhance` | `bolt enhance [--dry-run] [--limit N]` runs Smart_Trim → Text_Overlay on `media/vertical_clips/`; outputs under `media/vertical_clips_trimmed/` and `media/vertical_clips_final/`. |
| Checkup dashboard | `Checkup_Writer` + `App/Bolt_Checkup.html` + `bolt checkup` | Writes `Data/Bolt_data.js`; `bolt checkup [--open]` refreshes + opens the local HTML dashboard. Also refreshed on `launch` and after each `bot.py` pipeline run. |
| OCR titles | `Video_Intelligence` + `bot.py` Step C + `bolt ocr` | `extract_stats(clip)` → `on_screen_stats` → Title_Generator prepends strongest HUD line. `bolt ocr <clip> [--verbose]`. Missing pytesseract/tesseract = warn + continue (`uv sync --extra ocr`). |
| Anomaly detection / view forecasting | `Anomaly_Detector` + `Predictive_Analytics` + `bolt anomaly` / `bolt predict` | Anomaly: `detect_and_record` in `bot.py` before highlights (warn + continue). Predict: `queue_clip` / clip cards in Peak_Hour_Notifier; CLI `--queue` / `--game`+`--trigger`. Degrades when profiles/outcomes are thin. |
| Multi-platform plans | `Multi_Publisher` + `bolt multi` | Manual TikTok/Shorts/Reels/Kick captions + stagger times; Peak_Hour embeds `platform_plan` on queue; persists `Data/multi_platform_queue.json`. No upload (by design). |
| Thumbnails / ICS | generate_thumbnails, generate_calendar | ffmpeg + hand-rolled ICS. |
| Memory index | Memory_Index, refresh_memory_index | File-based retrieve; used by briefings. |
| Config / paths | Config_Loader, `_paths.py`, `Core/config.json` | Post-reorg canonical layout. |

| Clip cleanup on launch | `Core/launch.py` `_cleanup_old_clips` | Deletes aged clips from config `media/clips` + `media/vertical_clips` (legacy `clips/` / `vertical_clips/` swept if still present). Wizard + Config_Loader defaults match. |
| macOS menu bar | `App/app.py` + `bolt menubar` | Paths use `Core/launch.py`, `App/Bolt_Checkup.html`, `Core/config.json`. Launch = `bolt launch --no-checklist`; process = `bolt recordings latest`; dashboard refreshes via checkup. Needs `uv sync --extra menubar` (rumps). Not a shipping `.app` / iOS build. |
| Live web search | `Bolt_Search` + `bolt search` | DuckDuckGo via `ddgs` (+ HTML/lite/Instant Answer fallbacks in `scripts/_research.py`). `search_and_answer()` summarizes for !Bolt chat; CLI: `bolt search "…" [--raw|--long|--json]`. Empty/network fail → None / local LLM fallback. Needs `ddgs` (`uv sync`). |

**Most real core (not shells):** LLM_Handler, LLM_Budget, Clip_Ranker, Think_Learn_Decide.

---

## PARTIAL — real code, incomplete / gated / stranger-blocked

| Surface | What's missing |
|---|---|
| Nexus | Real consult + vector enrich. Dead-ish without Ollama *or* `XAI_API_KEY` + `NEXUS_ALLOW_PAID`. |
| Vector DB | Real Chroma; **raises if Ollama down**. Nexus skips enrich then. |
| TikTok publish | Real Content Posting API. **Paused:** `TIKTOK_API_ENABLED=false` (app denied). Auto-post / `postnow` skip. |
| TikTok Post UI | Real Flask UI; `MOCK_CREATOR_INFO` when no token. |
| YouTube / X | `build_youtube_package` / `build_x_package` = paste text. Comment: real API publisher pending app review. |
| Social stats | YouTube OAuth can work; TikTok stats paused; stranger needs tokens. |
| Amazon ASIN verify | HTML scrape (no PA-API). Fragile / blocked by Amazon. |
| OBS live | Real WS 5.x. Needs OBS + password. Folder-watch still works without it. |
| Twitch chat | Real twitchio bot. Needs `TWITCH_BOT_TOKEN`. `use_twitch: false`. |
| Voice loop | Mic→STT→intent/LLM→TTS. Needs mic, PortAudio, macOS. STT defaults to free Google. |
| Google Calendar / Gmail | Real OAuth. Tokens now under `Data/` (`google_token.json`, `gmail_token.json`); credentials still `Core/credentials.json`. Needs `credentials.json` + consent. |
| VOD / highlight reel | Real scripts; need Twitch creds + yt-dlp. |
| Sites / storage cron | William's Cloudflare/GitHub/machine paths, not portable. |
| Gemini_Client | Real REST; opt-in (`NEXUS_USE_GEMINI=false`). |
| Brain_Controller | Compat wrapper around Think_Learn_Decide — not a second brain. |

### Services

- **ffmpeg** — required for clips. Missing = pipeline fails.
- **Ollama** — titles/Nexus/vector *degrade* (templates / skip). Clip cutter still runs.
- **XAI/Grok** — strategy/research/morning degrade to Ollama; both down → “LLM unavailable”.
- **OpenAI** — optional fallback.
- **Twitch / OBS / Streamlabs** — optional; folder-watch still works.
- **TikTok API** — auto-post **dead** until `TIKTOK_API_ENABLED=true` + approved app.
- **Google Calendar/Gmail** — briefing extra only.
- **Tesseract** — optional for OCR titles (`uv sync --extra ocr` + `brew install tesseract`). Missing = Step C skips stats; titles continue.
- **openai-whisper** — optional (`uv sync --extra subtitles`). Missing = Step D skips; clip pipeline continues.
- **ddgs** — web search for `bolt search` / !Bolt / `research find`. In core deps after `uv sync`; without it HTML/lite/IA fallbacks still try.

A stranger also lacks William’s `.env`, `user_profile.json`, catalog notes, queue history, and Google `credentials.json`.

---

## SHELL — stub / canned / UI that goes nowhere

| Evidence | Fact |
|---|---|
| Core/src/ | Empty except `.DS_Store` + `__pycache__`. `Docs/PROJECT_STATUS.md` still says `python3 Core/src/launch.py`. |
| TikTok demo creator | `MOCK_CREATOR_INFO` (`"demo_creator"`, `"demo": True`). |
| merge_py.py | Walk-the-tree helper, not a product surface. |

`OBS_Integration.py` is a thin shim to `Stream_Monitor` — wrapper, not a shell.

---

## IDEA — named / documented, little or no product implementation

- `Data/learning/` — LLM textbook notes. Study log, not Bolt architecture.
- Skincare_Analyzer / AI_Analyzer — docs claim pipeline wiring when `--content-type skincare|tech`. `bot.py` never calls them.
- Creator-domains requirements / `.github/instructions` — prompts and spec, not runtime.
- Title trainer / A/B loop — `doctor.py`: “no trainer or A/B loop exists.”
- Kick / Instagram auto-post — Multi_Publisher metadata only (“Upload manually…”).
- Websites as a product — Cloudflare trio is William’s deploy, not in-repo apps a stranger can run.
- License — README still says `[Add your preferred license here]`.
- Discord-first bot — Core README says Bolt is not this; `.env.example` still has webhooks.

---

## If someone else used this tomorrow

**What works**

- After `uv sync` + `.env.example` → `.env`, they can run **`bolt recordings` / `bolt launch`** on local video: detect spikes, cut, rank, 9:16, enqueue.
- **`bolt queue decide`** is the real posting OS (manual upload + mark-posted).
- **`bolt manage` / `research` / `mission` / `day` / `morning` / `briefing`** are usable as local JSON/markdown tools.
- **`bolt doctor` / `verify` / `test`** will tell them what’s missing.
- With **Ollama** (`llama3.1:8b` + `nomic-embed-text`), Nexus/titles/memory get smarter. Without it, clip factory still runs on templates.

**What will disappoint**

- README “titles, **subtitles**, ranked queues” — subtitles + vertical burn-in when Whisper is installed (`uv sync --extra subtitles`); otherwise Step D skips and Clip_Factory continues without captions.
- “Auto-post to TikTok” / M11 — **API paused**.
- “Creator Command Center” web UI — removed Base44 todo template (`App/BoltApp`). Real CCC is `bolt mission`.
- **Dashboard** — `bolt checkup --open` loads `App/Bolt_Checkup.html` from `Data/Bolt_data.js`.
- **Menu bar app** — works via `bolt menubar` after `uv sync --extra menubar`. Still rumps (not a notarized Mac/iOS `.app`).
- **OCR “15 KILL STREAK” titles** — wired in `bot.py` Step C when pytesseract + tesseract are installed (`uv sync --extra ocr`); otherwise titles skip the HUD prefix.
- **Skincare / tech analyzers** look like features; they are library code or docs. (Anomaly + predictive are READY via CLI + queue/bot hooks.)
- Personal Cloudflare sites, Streamlabs, Google mail, Twitch chat will be blank without his keys.
- `Core/README.md` and `PROJECT_STATUS.md` oversell (“M1–M13 code-complete”, Discord integration, ElevenLabs as default). Voice default is **macOS Voice 3**.

**Top unfinished things that look like features but aren’t**

1. **TikTok auto-publish** — real client, **hard-paused**.
2. **Skincare_Analyzer / AI_Analyzer** — docs claim pipeline wiring; `bot.py` never calls them.
3. **Config_Loader / Clip_Generator legacy defaults** — live `Core/config.json` uses `media/…`; some module fallbacks still mention bare `clips/` / `vertical_clips/` when config is missing (wizard + Config_Loader defaults now match media/).
4. **TikTok Post UI demo mode** — Flask UI still falls back to `MOCK_CREATOR_INFO` without a live token.

~~Burn-in captions in Clip_Factory~~ — **DONE / READY** (5 Sep 2026 night): Step D segments are burned via drawtext in `format_for_tiktok`; graceful degrade if empty/ffmpeg fails. Text_Overlay remains the separate `bolt enhance` hook path.

**Stranger-ready subset:** CLI + local clip factory + queue review + catalog/research/mission markdown. Everything that needs cloud APIs, TikTok app review, OBS, or a GUI is gated, paused, or a shell.
