# Bolt — AI Session Guide
*Read this at the start of every session. It tells you who Billy is, what Bolt does, and where things stand.*

---

## What Bolt Is

Bolt is Billy's personal AI producer — a behind-the-scenes system that handles the technical side of content creation so Billy can focus on creating. Think Jarvis, but for streaming.

**Read `Bolt_brain.md` next** — it has Billy's full creator profile, platforms, vibe, blockers, and how to communicate with him.

---

## Folder Structure (what's where and why)

```
Bolt/
├── launch.py           ← START HERE. Runs on every session. Shows Twitch stats,
│                          voice checklist, launches OBS, then hands off to bot.py
├── bot.py              ← Main pipeline. Watches recordings/, detects highlights,
│                          generates clips, titles, subtitles, ranks, notifies Billy at peak hours
├── autostart.py        ← Registers Bolt to run at Mac startup (optional)
│
├── config.json         ← Settings: game, sensitivity, OBS, peak notification windows
├── session_tasks.json  ← Pre-stream checklist tasks (edit to customize)
├── .env                ← ALL API keys live here. Never share or commit this file.
├── requirement.txt     ← Python packages. Install with: pip3 install -r requirement.txt
│
├── Bolt_brain.md       ← Billy's creator profile. Read this before generating
│                          ANY content, titles, suggestions, or advice.
├── CLAUDE.md           ← This file. AI session guide.
├── README.md           ← Human-readable project overview.
│
├── modules/            ← All Python modules. Don't move these.
│   ├── Twitch_Stats.py       ← Fetches live Twitch data (followers, stream status, clips)
│   ├── Twitch_API.py         ← Lower-level Twitch REST helpers (get_follower_count, etc.)
│   ├── Voice_Checklist.py    ← Voice-activated pre-stream task checker
│   ├── Stream_Monitor.py     ← OBS WebSocket integration
│   ├── OBS_Integration.py    ← Real-time OBS scene control
│   ├── Streamlabs_Monitor.py ← Streamlabs events (donations, raids, subs)
│   ├── Highlight_Detector.py ← Audio-spike detection. NEW: hard MIN_CONFIDENCE
│   │                          gate drops weak spikes before clipping (Apr 28 2026)
│   ├── Clip_Generator.py     ← Cuts clips around highlights. NEW: per-clip
│   │                          try/except so one bad event can't kill the batch
│   ├── Title_Generator.py    ← AI-powered clip titles using Billy's profile
│   ├── AI_Title_Generator.py ← Newer Anthropic-backed title generator
│   ├── Subtitle_Generator.py ← Whisper transcription + subtitle burn-in
│   ├── Clip_Ranker.py        ← Virality scoring (0-100). NEW: Quality
│   │                          Controller tiers (discard/mid/queue) attached
│   │                          to each clip via clip.tier
│   ├── Clip_Factory.py       ← TikTok vertical formatting (9:16)
│   ├── Clip_Deduplicator.py  ← Prevents re-processing the same recording
│   ├── Peak_Hour_Notifier.py ← Tracks ready clips, alerts Billy at peak hours.
│   │                          NEW: only tier='queue' clips trigger Discord pings
│   ├── TikTok_Publisher.py   ← DEPRECATED — kept for reference only, not used
│   ├── Post_Queue.py         ← Background peak-hour checker, wraps Peak_Hour_Notifier
│   ├── Bolt_Chat.py          ← Twitch chat bot with AI personality (Phase 3)
│   ├── Bolt_Voice.py         ← TTS spoken alerts for highlights/raids/subs (Phase 3)
│   ├── Bolt_Memory.py        ← Phase 4 — long-term memory store (WIP)
│   ├── Bolt_Search.py        ← Phase 4 — semantic search over memory (WIP)
│   ├── Brain_Controller.py   ← Phase 4 — central decision engine (WIP, NOT yet
│   │                          wired into bot.py). Has its own tier constants
│   │                          (TIER_1_THRESHOLD=80, TIER_2_THRESHOLD=50) that
│   │                          must be reconciled with Clip_Ranker's tiers
│   │                          (discard<60, queue>=80) before wiring it in
│   ├── Think_Learn_Decide.py ← Phase 4 — intelligence layer used by bot.py
│   │                          to gate which clips proceed through the queue
│   ├── Checkup_Writer.py     ← Generates Bolt_Checkup.html from runtime state
│   ├── Watcher.py            ← Watches recordings/ for new files
│   ├── Error_Recovery.py     ← Failure handling helpers
│   ├── Game_Config.py        ← Per-game tuning profiles
│   ├── notifier.py           ← Terminal notifications with reasons
│   └── (others)              ← misc support
│
├── recordings/         ← Drop .mp4 or .mkv files here. Auto-processed.
│                          ⚠ NOT synced to iCloud — stays on local Mac only (too large)
├── clips/              ← Generated highlight clips (output) — synced via iCloud
├── vertical_clips/     ← TikTok-formatted 9:16 clips (output) — synced via iCloud
├── data/               ← Runtime data: rankings.json, post queue, etc.
├── logs/               ← Auto-generated logs. daily_log.txt is the main one.
├── docs/               ← Setup guides, Stream Deck layout, project status
├── assets/             ← Bolt icon, Stream Deck keys, app bundle
└── scripts/
    ├── setup.sh                  ← First-time setup on any Mac (installs packages, creates .env)
    ├── move_to_icloud.sh         ← Run ONCE on main Mac to move Bolt into iCloud Drive
    ├── cleanup_Bolt.sh           ← Deletes junk files (Bolt 2/, __pycache__, .DS_Store)
    ├── get_twitch_token.py       ← Generates TWITCH_BOT_TOKEN via twitchtokengenerator.com
    ├── log_clip_performance.py   ← NEW: log TikTok views/likes back into clip_history.json
    │                              so Clip_Ranker._history_boost actually has data to work with
    ├── Filter_Backlog.py         ← Move low-scoring clips into clips/_low_score/
    ├── process_recordings.py     ← Process all recordings/ files in batch
    ├── verify.py                 ← Sanity-check the install
    ├── build_env.py              ← Bootstrap a fresh .env file
    ├── autostart.py              ← Register Bolt to run at Mac startup
    ├── setup_icloud.sh           ← (legacy) 2-step shared-folder migration method
    └── migrate_to_shared.sh      ← (legacy) 2-step shared-folder migration method
```

---

## Compatibility shims (NOT stubs — these are intentional)

A few files at the root forward to canonical locations in `modules/` or `scripts/`.
These exist so old commands and imports keep working. **Do not delete them.**

| Root file                       | Forwards to                          |
|---------------------------------|--------------------------------------|
| `Twitch_API.py`                 | `from modules.Twitch_API import *`   |
| `Brain_Controller.py`           | `from modules.Brain_Controller import *` |
| `Filter_Backlog.py`             | `runpy → scripts/Filter_Backlog.py`  |
| `get_twitch_token.py`           | `from scripts.get_twitch_token import main` |
| `TWITCH_INTEGRATION_GUIDE.md`   | "moved to docs/" pointer             |

---

## iCloud Sync (Multi-Mac Setup)

Bolt is designed to sync across Macs via iCloud Drive. Here's how it works:

**To move Bolt into iCloud (run once on your main Mac):**
```bash
cd /path/to/Bolt
bash scripts/move_to_icloud.sh
```
This copies everything *except* `recordings/` (too large for iCloud) into your iCloud Drive. iCloud then syncs it automatically to your other MacBook.

**On the other MacBook (after iCloud syncs):**
```bash
cd ~/Library/"Mobile Documents"/com~apple~CloudDocs/Bolt
bash scripts/setup.sh        # installs packages, .env is already synced
python3 launch.py            # go
```

**What syncs / what doesn't:**
| Folder | iCloud | Why |
|--------|--------|-----|
| modules/ | ✅ Yes | Python code |
| clips/ | ✅ Yes | Ready-to-post clips |
| vertical_clips/ | ✅ Yes | TikTok-format clips |
| docs/, assets/, scripts/ | ✅ Yes | Project files |
| .env | ✅ Yes | API keys (already encrypted by iCloud) |
| recordings/ | ❌ No | Too large — stays on streaming Mac |
| logs/ | ❌ No | Local-only runtime logs |

---

## Phase Status

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1 | Dashboard + personality shell | ✅ Done (Bolt_Checkup.html in docs/) |
| Phase 2 | Live API connections | ✅ Done |
| Phase 3 | Voice + personality layer | 🔄 Almost there (Apr 28 2026) — env verified via `--check`, TWITCH_BOT_TOKEN active, Claude reachable. Still needs live `!Bolt hi` test in chat to confirm twitchio connection works. |
| Phase 4 | Self-improving memory | 🔄 Started — Bolt_Memory.py / Bolt_Search.py / Brain_Controller.py / Think_Learn_Decide.py scaffolded, NOT yet integrated |
| Quality Gating | Hard confidence + tier system | ✅ Done Apr 28 2026 |
| Performance Loop | log_clip_performance.py CLI | ✅ Done Apr 28 2026 (Billy must run it after each posting session for Bolt to learn) |

**Phase 2 progress:**
- ✅ Twitch API connected (Client ID + Secret in .env, channel: BillyandRandy)
- ✅ Voice checklist built and wired into launch.py
- ✅ Streamlabs monitor connected (token in .env)
- ✅ OBS WebSocket connected (password in .env)
- ✅ Discord webhook connected (in .env) — used for peak-hour posting alerts
- ✅ TikTok auto-posting REMOVED by design — replaced with Peak_Hour_Notifier
  - Bolt now alerts Billy at peak hours (7–9AM, 12–2PM, 7–10PM) via Discord
  - Billy posts manually — no TikTok API token needed

---

## API Keys (what's set, what's missing)

| Key | Status | Where to Get It |
|-----|--------|----------------|
| ANTHROPIC_API_KEY | ✅ Set | Already in .env |
| TWITCH_CLIENT_ID | ✅ Set | dev.twitch.tv |
| TWITCH_CLIENT_SECRET | ✅ Set | dev.twitch.tv → Your App → Manage |
| TWITCH_CHANNEL | ✅ Set (BillyandRandy) | — |
| OBS_PASSWORD | ✅ Set | OBS → Tools → WebSocket Server Settings |
| TIKTOK_ACCESS_TOKEN | 🚫 Not needed | Auto-posting removed — Billy posts manually |
| STREAMLABS_SOCKET_TOKEN | ✅ Set | streamlabs.com → Settings → API Settings |
| DISCORD_WEBHOOK_URL | ✅ Set | Discord → Channel Settings → Integrations |
| TWITCH_BOT_TOKEN | ✅ Set | Generated via twitchtokengenerator.com (Bot Chat Token scope) |
| TWITCH_BOT_NAME | ✅ Set | Bot's Twitch username |
| TWITCH_OAUTH_TOKEN | ✅ Set | User OAuth for Twitch_API (follower count, stream info) |
| TWITCH_REFRESH_TOKEN | ✅ Set | For refreshing the OAuth token when it expires |
| Bolt_VOICE | ⬜ Optional | macOS voice name — default: Samantha (run: say -v ?) — ElevenLabs skipped, edge-tts is a free upgrade option |
| Bolt_VOICE_MUTE | ⬜ Optional | Set to "true" to silence TTS |

---

## How to Start a Session

At the top of every conversation, read this file and `Bolt_brain.md`, then ask Billy where he left off.

**Common commands:**
```bash
python3 launch.py                 # Full startup (Twitch stats + checklist + OBS + bot)
python3 launch.py process         # Process most recent recording only
python3 launch.py --no-checklist  # Skip voice checklist
python3 -m modules.Twitch_Stats   # Quick Twitch stats check
python3 autostart.py install      # Register Bolt to run at boot

# Post queue commands:
python3 -m modules.Peak_Hour_Notifier              # Check if it's peak time + show ready clips
python3 -m modules.Peak_Hour_Notifier --summary    # How many clips are queued
python3 -m modules.Peak_Hour_Notifier --mark-posted  # Mark all ready clips as posted (run after posting)

# Performance feedback loop (Apr 28 2026):
python3 scripts/log_clip_performance.py                                # interactive
python3 scripts/log_clip_performance.py --trigger kill --views 12500   # direct
python3 scripts/log_clip_performance.py --list                         # show learned data

# Phase 3 commands:
python3 -m modules.Bolt_Chat                          # Test chat bot connection directly
python3 -m modules.Bolt_Voice                         # Test TTS voice (hear Bolt speak)
python3 -m modules.Bolt_Voice "say this out loud"     # Speak a custom line
python3 -m modules.Bolt_Voice --list-events           # Show all built-in event lines
```

**Quality gating knobs (config.json):**
```json
{
  "highlight": {
    "min_confidence": 0.15            // raise to be pickier about audio spikes
  },
  "quality_tiers": {
    "discard_below": 60,              // < this = never auto-flow, never ping
    "queue_at": 80                    // >= this = auto-flow + Discord alert
                                       // between = "mid" tier (saved, silent)
  }
}
```

---

## Billy's Communication Style

- Self-taught — explain the *why* behind every change, not just the *what*
- Gets frustrated when things feel overwhelming — keep next steps simple and clear
- Learns by doing — always leave something working and runnable
- Wants to grow alongside Bolt — this is a collaboration, not just a tool

**Phase 3 progress:**
- ✅ Bolt_Chat.py — Twitch chat bot with Claude-powered personality, session memory, greets viewers, reacts to highlights/raids/subs/bits, answers !Bolt questions
- ✅ Bolt_Voice.py — TTS voice using macOS `say` command, speaks for highlights/raids/subs, ElevenLabs upgrade path ready
- ✅ bot.py updated — starts chat bot, wires highlight events into Bolt_Chat + Bolt_Voice
- ✅ launch.py updated — checks Phase 3 config at startup, speaks "Bolt online" line
- ⬜ Needs: `pip3 install twitchio anthropic --break-system-packages`
- ✅ Done: TWITCH_BOT_TOKEN generated and saved to .env (Apr 2026)
- ⬜ Final smoke test: `python3 -m modules.Bolt_Chat` to verify it connects to chat

*Last updated: 2026-04-28 — Quality gating shipped (hard confidence floor in
Highlight_Detector, three-tier classifier in Clip_Ranker, per-clip failure
recovery in Clip_Generator, tier-aware queue + alerts in Peak_Hour_Notifier,
performance feedback CLI at scripts/log_clip_performance.py). Documented the
compatibility shims at root. Phase 4 modules scaffolded but not yet wired.*

## Open architectural decisions (for next session)

1. **Reconcile tier vocabularies.** `Clip_Ranker` uses discard/mid/queue with
   thresholds 60/80. `Brain_Controller` uses Tier 1/2/3 with thresholds 80/50.
   Pick one and align before wiring Brain_Controller into bot.py.

2. **Wire Brain_Controller into bot.py.** Right now bot.py uses
   `Think_Learn_Decide.py` as the intelligence layer. Brain_Controller is
   scaffolded but unused. Decide which is canonical.

3. **Langchain memory build (per Upgrade_thoughts doc).** `memory/` folder
   exists but is empty of indexed data. Run `pip install langchain
   langchain-community langchain-text-splitters chromadb` and then build
   the vectorstore — but swap `OpenAIEmbeddings` for `HuggingFaceEmbeddings`
   to avoid needing an OpenAI key on top of Anthropic.

4. **Motion detection** to complete the "no audio peaks AND no motion"
   filter from Upgrade_thoughts. Audio gate is live; motion would require
   cv2 + optical flow on each candidate window. Defer until you find audio
   alone is missing real moments.
