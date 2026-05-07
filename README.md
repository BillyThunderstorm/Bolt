# Bolt — ThunderStorm Billy's Streaming AI Assistant

Your complete streaming enhancement platform: AI-powered highlight detection, automated clip pipeline, intelligent title generation, and TikTok-ready output. Built to run in the background while you stream, so you can focus on playing.

---

## Project Layout

```
Bolt/
├── bot.py               # Main chatbot entry point
├── launch.py            # Clip pipeline entry point
├── config.json          # All your settings live here
├── .env                 # API keys and secrets (never commit this)
├── requirements.txt     # Python dependencies
│
├── modules/             # Every Python module (the brains)
├── scripts/             # Setup, automation, and utility scripts
│   └── legacy/          # Old scripts kept for reference
├── data/                # Runtime state: clip history, rankings, queue
├── memory/              # Bolt's persistent memory and context
├── logs/                # Event and audit logs
│
├── docs/                # All documentation
│   ├── guides/          # Setup and integration guides
│   ├── briefings/       # Bolt's daily briefing files
│   └── planning/        # Design docs and planning notes
│
├── brand/               # ThunderStorm Billy brand assets
│   ├── media_kit/       # Roadmaps, affiliate kits, strategy docs
│   ├── music/           # Theme MIDIs, MP3s, sheet music
│   └── logo/            # Logo and visual brand files
│
├── assets/              # Stream overlays and Stream Deck keys
├── docker/              # Docker setup and compose files
├── llm/                 # Local neural model experiments
├── tests/               # Automated tests
├── clips/               # Raw generated clips
├── vertical_clips/      # TikTok-formatted clips (9:16)
├── recordings/          # Drop your OBS recordings here
└── archive/             # Duplicate/retired files (safe to ignore)
```

---

## Modules

```
modules/
├── Brain_Controller.py      # Orchestrates the full pipeline
├── Think_Learn_Decide.py    # Bolt's reasoning + decision engine
│
├── Bolt_Chat.py             # Twitch chat interaction
├── Bolt_Memory.py           # Persistent memory system
├── Bolt_Search.py           # Search capabilities
├── Bolt_Voice.py            # Voice output
│
├── Highlight_Detector.py    # Audio/energy-based highlight detection
├── Clip_Generator.py        # Creates 30-second clips from highlights
├── Clip_Factory.py          # Batch clip production
├── Clip_Deduplicator.py     # Removes duplicate clips
├── Clip_Ranker.py           # Virality scoring (0-100)
│
├── AI_Title_Generator.py    # Context-aware AI title generation
├── Title_Generator.py       # Template-based titles
├── Subtitle_Generator.py    # Whisper speech-to-text subtitles
│
├── OBS_Integration.py       # Live stream control (Shift+H to mark clips)
├── Stream_Monitor.py        # Stream health monitoring
├── Streamlabs_Monitor.py    # Streamlabs event tracking
│
├── TikTok_Publisher.py      # Vertical format + upload queue
├── Post_Queue.py            # Manages the posting queue
├── Peak_Hour_Notifier.py    # Notifies you when it's best to post
│
├── Twitch_API.py            # Twitch API connection
├── Twitch_Stats.py          # Channel stats and metrics
├── Game_Config.py           # Per-game settings
│
├── Watcher.py               # Watches folders for new recordings
├── Error_Recovery.py        # Self-healing on failures
├── Checkup_Writer.py        # Generates daily status briefings
├── Voice_Checklist.py       # Pre-stream voice checklist
└── notifier.py              # Discord webhook notifications
```

---

## Quick Start

**1. Install dependencies**
```bash
pip install -r requirements.txt
```

**2. Configure your settings**

Edit `config.json` — set your game, sensitivity, and clip preferences.
Copy `.env.example` to `.env` and fill in your API keys.

**3. Run**

For the full clip pipeline (drop a recording in `recordings/` first):
```bash
python launch.py
```

For Bolt's live chatbot and assistant:
```bash
python bot.py
```

---

## How the Clip Pipeline Works

```
You drop a recording into recordings/
          ↓
Watcher.py notices the new file
          ↓
Highlight_Detector.py scans for energy peaks
          ↓
Clip_Generator.py cuts 30-second clips
          ↓
Clip_Ranker.py scores each clip (0-100)
          ↓
AI_Title_Generator.py writes titles
          ↓
TikTok_Publisher.py formats to 9:16 vertical
          ↓
Peak_Hour_Notifier.py tells you when to post
          ↓
You review and post manually
```

Clips scoring below `discard_below` (default: 60) are thrown out.
Clips scoring above `queue_at` (default: 80) are auto-queued for you to review.
Everything in between is saved to disk but not flagged.

---

## Virality Scoring

Each clip gets a score from 0-100 based on:

| Signal | What it measures |
|---|---|
| Visual energy | How much motion is in the clip |
| Audio peaks | Excitement spikes in the audio |
| Scene changes | How dynamic the content is |
| Length | How close to the ideal clip length |
| Engagement potential | Keywords and pacing |
| Historical performance | What has worked before |

---

## OBS Integration

1. Install the OBS WebSocket plugin
2. Go to Tools → obs-websocket Settings, set a password
3. Set `"use_obs_integration": true` in `config.json`

During a stream:
- **Shift+H** — mark the current moment as a highlight
- **Shift+R** — save the replay buffer as a clip
- Bolt auto-detects scene changes as potential highlights too

---

## TikTok Workflow

Bolt does **not** auto-post. It queues videos and notifies you at peak hours via Discord webhook. You review and post yourself.

Peak posting windows (configurable in `config.json`):
- Morning: 7–9am
- Lunch: 12–2pm
- Prime Time: 7–10pm

---

## Configuration Examples

**For Marvel Rivals (current setup)**
```json
{
  "game": "Marvel Rivals",
  "highlight_sensitivity": 0.55,
  "min_clip_score": 65,
  "auto_format_tiktok": true
}
```

**Tighter quality bar**
```json
{
  "min_clip_score": 80,
  "quality_tiers": {
    "discard_below": 70,
    "queue_at": 85
  }
}
```

**Higher clip volume**
```json
{
  "max_clips_per_session": 10,
  "highlight_sensitivity": 0.4
}
```

---

## Documentation

| Doc | What it covers |
|---|---|
| `docs/guides/SETUP_GUIDE.md` | Full environment setup |
| `docs/guides/STREAM_DECK_SETUP.md` | Stream Deck button layout |
| `docs/guides/TWITCH_INTEGRATION_GUIDE.md` | Twitch API connection |
| `docs/PROJECT_STATUS.md` | Current build status |
| `docs/INDEX.md` | Navigation map for all docs |
| `bolt_brain.md` | How Bolt thinks and makes decisions |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| No highlights found | Lower `highlight_sensitivity` in config (try 0.4) |
| OBS not connecting | Install obs-websocket plugin, check port 4455 |
| Slow processing | Reduce `max_clips_per_session`, disable whisper if not needed |
| Clips look wrong | Check `tiktok_style` — try "letterbox" vs "crop" |
| Discord notifications not arriving | Check your webhook URL in `.env` |

---

## Security

- Never commit `.env` to git — it's already in `.gitignore`
- Rotate your Twitch and TikTok credentials if they're ever exposed
- The `archive/` folder contains old duplicate files — safe to delete once confirmed

---

*Built for ThunderStorm Billy — a self-taught programmer and content creator building smarter*
*Last updated: May 2026*
