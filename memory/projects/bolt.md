# Project: Bolt

**What it is:** Billy's AI-powered content assistant / bot system
**Status:** Active — in development
**Also called:** "the bot", "Bolt"

## What Bolt Does

Bolt is Billy's personal AI assistant built to support his content creation workflow. It handles things like:
- Clip processing and automation (ClipBot)
- Twitch chatbot integration
- Content ideas and scripting assistance
- Briefings and daily updates

## Key Files

| File | Purpose |
|------|---------|
| bot.py | Main Twitch chatbot |
| bot_with_twitch.py | Extended bot with Twitch API integration |
| Bolt_brain.md | Creator profile / knowledge base for Bolt |
| config.json | Project configuration |
| launch.py | Launch script |
| dashboard.py | Dashboard interface |
| requirements.txt | Python dependencies |

## Directory Structure

```
Bolt/
  modules/       — Bot modules/features
  scripts/       — Utility scripts
  clips/         — Processed clips output
  vertical_clips/ — TikTok-format clips
  recordings/    — Raw stream recordings
  data/          — Data storage
  logs/          — Log files
  deploy/        — Deployment configs
  docker/        — Docker setup
  docs/          — Documentation
  assets/        — Media assets
  memory/        — This memory system
```

## Related Files

- `TWITCH_INTEGRATION_GUIDE.md` — Twitch API setup guide
- `Twitch_API.py` — Twitch API helper
- `get_twitch_token.py` — Token retrieval script
- `ClipBot Checklist.docx` — Checklist for clip processing workflow
