# Bolt — Billy's AI Producer

Bolt is Billy's behind-the-scenes content assistant for Twitch and clip creation.
It watches recordings, finds highlights, cuts clips, writes titles and subtitles,
formats vertical exports, and nudges Billy when clips are ready to post.

Current shape of the project:
- Phase 2 is in place: Twitch, OBS, Streamlabs, Discord, and launch-time checks.
- Phase 3 is active: Twitch chat personality and spoken alerts are wired in.
- Phase 4 is scaffolded: memory/search/controller modules exist, but the final
  decision layer is not yet the canonical runtime path.

## Project Layout

```text
Bolt/
├── bot.py                # Main runtime pipeline
├── launch.py             # Startup checks, OBS launch, handoff to bot.py
├── config.json           # Runtime configuration
├── requirements.txt      # Python dependencies
├── .env                  # API keys and secrets
├── Bolt_brain.md         # Billy's creator profile
│
├── modules/              # Runtime modules and helpers
├── scripts/              # Setup, utilities, maintenance, verification
├── docs/                 # Guides, status pages, and generated checkups
├── memory/               # Long-term memory notes and learning cache
├── data/                 # Rankings, queue state, generated runtime files
├── logs/                 # Runtime logs and audits
├── clips/                # Generated highlight clips
├── vertical_clips/       # Vertical TikTok-ready clips
├── recordings/           # Local-only source recordings
├── assets/               # Stream Deck keys and visual assets
├── brand/                # Brand assets and media kit
└── BillyThunderstorm-site/ # Public site pages that mention Bolt
```

## What Works Now

- Recording watcher and batch processing
- Hard confidence gate for highlight detection
- Per-clip failure recovery so one bad event does not stop the batch
- Clip ranking tiers: discard, mid, and queue
- Title generation, subtitles, and vertical formatting
- Peak-hour Discord alerts for queue-worthy clips
- Twitch chat bot and macOS spoken alerts
- Daily/runtime checkup dashboard generation

## Quick Start

```bash
pip3 install -r requirements.txt
python3 launch.py
```

If you want to process just the latest recording:

```bash
python3 launch.py process
```

Useful targeted checks:

```bash
python3 -m modules.Bolt_Chat
python3 -m modules.Bolt_Voice "say this out loud"
python3 scripts/log_clip_performance.py --list
python3 scripts/verify.py
```

## Configuration

The current config centers on:

- `highlight_sensitivity` for detection sensitivity
- `quality_tiers.discard_below` and `quality_tiers.queue_at`
- `min_post_score` as the canonical clip floor
- `auto_format_tiktok` for vertical output
- `peak_notifications` for Discord timing alerts
- `use_voice_checklist` for startup voice prompts

Suggested starting values in `config.json` already match the current tiering:
- discard below `60`
- queue at `80`

## Documentation

| Doc | What it covers |
|---|---|
| `docs/INDEX.md` | Navigation map for Bolt docs |
| `docs/PROJECT_STATUS.md` | Current build status and next steps |
| `docs/guides/SETUP_GUIDE.md` | Setup, config, and troubleshooting |
| `docs/guides/STREAM_DECK_SETUP.md` | Stream Deck layout |
| `docs/guides/TWITCH_INTEGRATION_GUIDE.md` | Twitch integration notes |
| `docs/Bolt_Checkup.html` | Local checkup dashboard |
| `docs/site/Bolt_Checkup.html` | Site-hosted checkup page |
| `docs/think_learn_decide.md` | Decision and memory schema |

## Troubleshooting

| Problem | First thing to check |
|---|---|
| No highlights found | Lower `highlight_sensitivity` a little |
| OBS will not connect | Confirm obs-websocket is enabled and the password is right |
| Clips are too noisy | Raise `quality_tiers.discard_below` |
| Clips are missing | Lower `quality_tiers.discard_below` or `min_post_score` |
| Chat bot is silent | Confirm `TWITCH_BOT_TOKEN` and `TWITCH_BOT_NAME` exist in `.env` |
| Voice does not speak | Check `Bolt_VOICE_MUTE` and macOS `say` availability |

## Suggestions For Completion

1. Align `Brain_Controller` with the current tier vocabulary or keep `Think_Learn_Decide` as canonical.
2. Build out the memory vector store so Bolt can retrieve past clips and decisions.
3. Add motion gating only if audio spikes alone keep missing good moments.
4. Keep logging TikTok performance back into `clip_history.json` after posting.

*Last updated: May 2026*
