# Bolt Setup Guide

This guide covers first-time install, config, and the current runtime shape of Bolt.

## Quick Start

```bash
pip3 install -r requirements.txt
python3 launch.py
```

## What Bolt Does Now

- Watches `recordings/` for new captures
- Detects highlights with an audio confidence gate
- Cuts clips and deduplicates them
- Scores clips with the current tier system
- Burns subtitles and writes titles
- Formats vertical clips for manual posting
- Notifies Billy at peak hours instead of auto-posting

## Config Files

- `config.json` for runtime behavior
- `.env` for API keys and secrets
- `requirements.txt` for dependencies

## Safe `.env` Skeleton

Use placeholders only:

```bash
ANTHROPIC_API_KEY=your_key_here
TWITCH_CLIENT_ID=your_client_id_here
TWITCH_CLIENT_SECRET=your_client_secret_here
TWITCH_CHANNEL=BillyandRandy
OBS_PASSWORD=your_obs_password_here
STREAMLABS_SOCKET_TOKEN=your_streamlabs_token_here
DISCORD_WEBHOOK_URL=your_discord_webhook_here
TWITCH_BOT_TOKEN=
TWITCH_BOT_NAME=
Bolt_VOICE=Nathan (Enhanced)
Bolt_VOICE_MUTE=false
```

## Current Config Pattern

The important runtime keys are:

- `highlight_sensitivity`
- `quality_tiers.discard_below`
- `quality_tiers.queue_at`
- `min_post_score`
- `auto_format_tiktok`
- `peak_notifications`
- `use_voice_checklist`

The current defaults are tuned around:
- discard below `60`
- queue at `80`
- manual posting after Discord peak-hour alerts

## Troubleshooting

- If OBS does not connect, verify obs-websocket is enabled and the password is correct.
- If no chat responses appear, check `TWITCH_BOT_TOKEN`, `TWITCH_BOT_NAME`, and `ANTHROPIC_API_KEY`.
- If voice does not speak, confirm Bolt is not muted and that the Mac `say` command works.
- If highlights are sparse, lower `highlight_sensitivity` a little.

## Notes

- `docs/PROJECT_STATUS.md` is the best place to check what still needs work.
- `docs/INDEX.md` is the fastest map for the repo.
- `scripts/verify.py` is the quickest sanity check.
