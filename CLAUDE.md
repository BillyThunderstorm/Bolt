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
│   ├── Voice_Checklist.py    ← Voice-activated pre-stream task checker
│   ├── Stream_Monitor.py     ← OBS WebSocket integration
│   ├── Streamlabs_Monitor.py ← Streamlabs events (donations, raids, subs)
│   ├── Highlight_Detector.py ← Finds highlight moments in recordings
│   ├── Clip_Generator.py     ← Cuts 30-sec clips around highlights
│   ├── Title_Generator.py    ← AI-powered clip titles using Billy's profile
│   ├── Subtitle_Generator.py ← Whisper transcription + subtitle burn-in
│   ├── Clip_Ranker.py        ← Virality scoring (0-100)
│   ├── Clip_Factory.py       ← TikTok vertical formatting (9:16)
│   ├── Peak_Hour_Notifier.py ← Tracks ready clips, alerts Billy at peak posting hours
│   ├── TikTok_Publisher.py   ← DEPRECATED — kept for reference only, not used
│   ├── Post_Queue.py         ← Background peak-hour checker, wraps Peak_Hour_Notifier
│   ├── Bolt_Chat.py          ← Twitch chat bot with AI personality (Phase 3)
│   ├── Bolt_Voice.py         ← TTS spoken alerts for highlights/raids/subs (Phase 3)
│   ├── Watcher.py            ← Watches recordings/ for new files
│   ├── notifier.py           ← Terminal notifications with reasons
│   └── (others)              ← Error recovery, game config, deduplication
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
    ├── setup.sh              ← First-time setup on any Mac (installs packages, creates .env)
    ├── move_to_icloud.sh     ← Run ONCE on main Mac to move Bolt into iCloud Drive
    ├── cleanup_Bolt.sh       ← Deletes junk files (Bolt 2/, __pycache__, .DS_Store)
    ├── get_twitch_token.py   ← Generates TWITCH_BOT_TOKEN via Twitch device auth
    ├── setup_icloud.sh       ← (legacy) 2-step shared-folder migration method
    └── migrate_to_shared.sh  ← (legacy) 2-step shared-folder migration method
```

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
| Phase 3 | Voice + personality layer | 🔄 In progress (chat bot + TTS built, needs token setup) |
| Phase 4 | Self-improving memory | ⬜ Not started |

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
| TWITCH_BOT_TOKEN | ⬜ Needs setup | Go to twitchtokengenerator.com → Bot Chat Token, then run: python3 scripts/get_twitch_token.py |
| TWITCH_BOT_NAME | ⬜ Needs setup | The bot's Twitch username (e.g. BoltBot) |
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

# Post queue commands (new):
python3 -m modules.Peak_Hour_Notifier              # Check if it's peak time + show ready clips
python3 -m modules.Peak_Hour_Notifier --summary    # How many clips are queued
python3 -m modules.Peak_Hour_Notifier --mark-posted  # Mark all ready clips as posted (run after posting)

# Phase 3 commands (new):
python3 -m modules.Bolt_Chat                          # Test chat bot connection directly
python3 -m modules.Bolt_Voice                         # Test TTS voice (hear Bolt speak)
python3 -m modules.Bolt_Voice "say this out loud"     # Speak a custom line
python3 -m modules.Bolt_Voice --list-events           # Show all built-in event lines
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
- ⬜ Needs: Run `python3 scripts/get_twitch_token.py` to generate TWITCH_BOT_TOKEN (no third-party sites — uses Twitch's official device auth flow with existing TWITCH_CLIENT_ID)

*Last updated: 2026-04-13 — added iCloud sync system, cleanup script, fixed setup bugs*
