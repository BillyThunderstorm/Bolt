# Bolt readiness audit

*31 August 2026 · Goddess.local · `/Users/carter/developer/Bolt`*
*Originally read-only 31 Aug 2026. Updated 3 Sep 2026: Analytics_Tracker → `bolt analytics`. Updated 4 Sep 2026: Subtitle_Generator → bot.py Step D; Smart_Trim/Text_Overlay → `bolt enhance`; Checkup dashboard → `bolt checkup` + `App/Bolt_Checkup.html`; Video_Intelligence OCR → bot.py Step C + `bolt ocr`. Updated 5 Sep 2026: Anomaly_Detector / Predictive_Analytics → `bolt anomaly` / `bolt predict` + Peak_Hour_Notifier / bot.py hooks.*

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
bolt morning / manage / research / mission / voice / budget / overlay / analytics / anomaly / predict / enhance / checkup / ocr
```

Live clip path: `launch.py` → `bot.py.process_recording`: Highlight_Detector → Clip_Generator → Clip_Deduplicator → Title_Generator → Subtitle_Generator → Clip_Ranker → Clip_Factory → Post_Queue / Peak_Hour_Notifier.

Not real launchers for a stranger: `python3 Core/src/launch.py` (empty `Core/src/`), `App/app.py` (stale `launch.py` path; rumps menu bar, not a shipping Mac/iOS app).

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
| Subtitles (local) | Subtitle_Generator + `bot.py` Step D | Whisper segments → `.srt` sidecar next to clip; segments passed to `Clip_Factory.format_for_tiktok`. Missing Whisper = warn + continue (`uv sync --extra subtitles`). |
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
| Thumbnails / ICS | generate_thumbnails, generate_calendar | ffmpeg + hand-rolled ICS. |
| Memory index | Memory_Index, refresh_memory_index | File-based retrieve; used by briefings. |
| Config / paths | Config_Loader, `_paths.py`, `Core/config.json` | Post-reorg canonical layout. |

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
| Google Calendar / Gmail | Real OAuth. Token path **stale** (`Core/data` not `Data/`). Needs `credentials.json`. |
| Multi_Publisher | Real *planner* (no upload). Writes pre-reorg `data/` path; live file is `Data/`. |
| macOS menu bar | rumps UI looks for repo-root `launch.py` (now `Core/launch.py`). `rumps` not in deps. |
| VOD / highlight reel | Real scripts; need Twitch creds + yt-dlp. |
| Sites / storage cron | William's Cloudflare/GitHub/machine paths, not portable. |
| Gemini_Client | Real REST; opt-in (`NEXUS_USE_GEMINI=false`). |
| Brain_Controller | Compat wrapper around Think_Learn_Decide — not a second brain. |
| Clip cleanup on launch | Deletes `clips/` at CWD, not live `media/clips/`. Harmless miss. |

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

A stranger also lacks William’s `.env`, `user_profile.json`, catalog notes, queue history, and Google `credentials.json`.

---

## SHELL — stub / canned / UI that goes nowhere

| Evidence | Fact |
|---|---|
| Bolt_Search | `search_and_answer()` **always `return None`**: “Live web search is disabled”. |
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

- README “titles, **subtitles**, ranked queues” — subtitles run when Whisper is installed (`uv sync --extra subtitles`); otherwise Step D skips gracefully.
- “Auto-post to TikTok” / M11 — **API paused**.
- “Creator Command Center” web UI — removed Base44 todo template (`App/BoltApp`). Real CCC is `bolt mission`.
- **Dashboard** — `bolt checkup --open` loads `App/Bolt_Checkup.html` from `Data/Bolt_data.js`.
- **Menu bar app** — wrong paths, missing `rumps`.
- **OCR “15 KILL STREAK” titles** — wired in `bot.py` Step C when pytesseract + tesseract are installed (`uv sync --extra ocr`); otherwise titles skip the HUD prefix.
- **Skincare / tech analyzers** look like features; they are library code or docs. (Anomaly + predictive are READY via CLI + queue/bot hooks.)
- Personal Cloudflare sites, Streamlabs, Google mail, Twitch chat will be blank without his keys.
- `Core/README.md` and `PROJECT_STATUS.md` oversell (“M1–M13 code-complete”, Discord integration, ElevenLabs as default). Voice default is **macOS Voice 3**.

**Top 5 unfinished things that look like features but aren’t**

1. **TikTok auto-publish** — real client, **hard-paused**.
2. **macOS menu bar** — `App/app.py` rumps paths are stale (`launch.py` vs `Core/launch.py`); `rumps` not in deps. Not a shipping Mac/iOS app. (Checkup HTML is ready via `bolt checkup`.)
3. **Burn-in captions in Clip_Factory** — Step D writes `.srt` + passes segments; `format_for_tiktok` accepts `transcript_segments` but does not burn them yet (Text_Overlay is a separate enhance path).
4. **Multi_Publisher / Google token paths** — still write pre-reorg `data/` / `Core/data` instead of `Data/`.
5. **Skincare_Analyzer / AI_Analyzer** — docs claim pipeline wiring; `bot.py` never calls them.

**Stranger-ready subset:** CLI + local clip factory + queue review + catalog/research/mission markdown. Everything that needs cloud APIs, TikTok app review, OBS, or a GUI is gated, paused, or a shell.
