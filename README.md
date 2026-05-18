# Bolt - Billy's AI Producer

Bolt is Billy's behind-the-scenes content assistant for Twitch and clip creation.
It watches recordings, finds highlights, cuts clips, writes titles and subtitles,
formats vertical exports, and nudges Billy when clips are ready to post.

## Current Shape

- Phase 2 is in place: Twitch, OBS, Streamlabs, Discord, and launch-time checks.
- Phase 3 is active: Twitch chat personality and spoken alerts are wired in.
- Phase 4 is scaffolded: `Think_Learn_Decide` is the active decision layer,
  while `Brain_Controller` now mirrors the same thresholds as a compatibility wrapper.
- Clip quality uses three tiers: `discard`, `mid`, and `queue`.
- `min_post_score` is the current pipeline floor in `config.json`; it is separate
  from the tier thresholds in `quality_tiers`.

## Project Layout

```text
Bolt/
├── launch.py             # Startup checks, OBS launch, handoff to bot.py
├── bot.py                # Main pipeline: detect, clip, rank, format, queue
├── config.json           # Runtime configuration
├── requirements.txt      # Python dependencies
├── Bolt_brain.md         # Billy's creator profile
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
- Hard highlight confidence gate
- Per-clip failure recovery so one bad event does not stop the batch
- Deduplication before titles, subtitles, and ranking
- Clip ranking tiers: discard, mid, and queue
- Title generation, subtitles, and vertical formatting
- Peak-hour Discord alerts for queue-worthy clips
- Twitch chat bot and macOS spoken alerts
- Live checkup dashboard generation

## Quick Start

```bash
pip3 install -r requirements.txt
python3 launch.py
```

To process just the latest recording:

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
- `min_post_score` as the pipeline cutoff for queueing and formatting
- `auto_format_tiktok` for vertical output
- `peak_notifications` for Discord timing alerts
- `use_voice_checklist` for startup voice prompts
- `use_obs_integration`, `obs_host`, and `obs_port` for OBS launch/connect

Suggested baseline values in `config.json`:

- discard below `60`
- queue at `80`
- pipeline floor `65`

That means:

- below `60`: discard
- `60-64`: keep on disk, no queue
- `65-79`: format and queue silently
- `80+`: queue and alert Billy at peak hours

## Documentation

| Doc | What it covers |
|---|---|
| `docs/INDEX.md` | Canonical navigation map for Bolt docs |
| `docs/PROJECT_STATUS.md` | Current build status and next steps |
| `docs/guides/SETUP_GUIDE.md` | Setup, config, and troubleshooting |
| `docs/guides/STREAM_DECK_SETUP.md` | Stream Deck layout |
| `docs/guides/TWITCH_INTEGRATION_GUIDE.md` | Twitch integration pointer |
| `docs/Bolt_Checkup.html` | Local checkup dashboard source |
| `docs/site/Bolt_Checkup.html` | Published mirror of the checkup dashboard |
| `docs/site/privacy-policy.html` | Public site privacy policy |
| `docs/site/terms.html` | Public site terms |
| `docs/think_learn_decide.md` | Decision and memory schema |

## Troubleshooting

| Problem | First thing to check |
|---|---|
| No highlights found | Lower `highlight_sensitivity` a little |
| OBS will not connect | Confirm obs-websocket is enabled and the password is right |
| Clips are too noisy | Raise `quality_tiers.discard_below` |
| Clips are missing | Lower `min_post_score` or `quality_tiers.discard_below` |
| Chat bot is silent | Confirm `TWITCH_BOT_TOKEN` and `TWITCH_BOT_NAME` exist in `.env` |
| Voice does not speak | Check `Bolt_VOICE_MUTE` and macOS `say` availability |

## Suggestions For Advancement

1. Keep `Think_Learn_Decide` as canonical and treat `Brain_Controller` as the legacy compatibility wrapper.
2. Finish the memory vector store so Bolt can reuse past clip and decision context.
3. Keep the setup templates in `launch.py` and `scripts/setup.sh` aligned with
   the live `config.json` schema after every config change.
4. Refresh `docs/site/Bolt_Checkup.html` whenever the dashboard source changes.

*Last updated: May 2026*
