# Bolt Documentation Index

Use this page as the central map for Bolt.

## Start Here

- `README.md` - high-level project overview and setup
- `launch.py` - startup checks and launcher
- `bot.py` - main runtime pipeline
- `config.json` - runtime configuration
- `requirements.txt` - Python dependency list

## Canonical Runtime Docs

- `docs/PROJECT_STATUS.md` - current build status and next steps
- `docs/think_learn_decide.md` - canonical decision and memory schema
- `docs/Bolt_Checkup.html` - local dashboard source written from live stats
- `data/Bolt_data.js` - generated dashboard payload written at startup

## Setup and Integration

- `docs/guides/SETUP_GUIDE.md` - setup, prerequisites, and troubleshooting
- `docs/guides/STREAM_DECK_SETUP.md` - Stream Deck setup notes
- `docs/guides/TWITCH_INTEGRATION_GUIDE.md` - Twitch integration pointer
- `docs/guides/TWITCH_INTEGRATION_GUIDE_docs.md` - legacy Twitch integration writeup
- `scripts/setup.sh` - first-time setup and dependency install
- `scripts/verify.py` - project verification checks
- `scripts/log_clip_performance.py` - feed post metrics back into Bolt memory

## Runtime Modules

- `modules/Think_Learn_Decide.py` - current intake, reasoning, decisions, feedback loop
- `modules/Brain_Controller.py` - legacy compatibility controller that mirrors the live tiers
- `modules/Watcher.py` - recording folder monitoring
- `modules/Highlight_Detector.py` - highlight detection
- `modules/Clip_Generator.py` - clip generation
- `modules/Clip_Deduplicator.py` - duplicate protection
- `modules/Subtitle_Generator.py` - subtitle generation
- `modules/Title_Generator.py` - local title generation
- `modules/AI_Title_Generator.py` - older AI title path
- `modules/Clip_Ranker.py` - ranking and tiering
- `modules/Clip_Factory.py` - vertical format conversion
- `modules/Post_Queue.py` - post queue integration
- `modules/Peak_Hour_Notifier.py` - timing alerts
- `modules/Bolt_Chat.py` - Twitch personality layer
- `modules/Bolt_Voice.py` - spoken alerts and TTS
- `modules/Bolt_Memory.py` - long-term memory
- `modules/Bolt_Search.py` - memory search helper

## Status Surfaces

- `docs/Bolt_Checkup.html` - canonical local dashboard
- `docs/site/Bolt_Checkup.html` - published mirror of the dashboard
- `docs/site/privacy-policy.html` - public privacy policy
- `docs/site/terms.html` - public terms page
- `docs/briefings/` - archived briefing notes

## Data and Logs

- `data/` - state files, decision model, unified memory, pending proposals
- `logs/` - runtime logs and decision audit trail
- `memory/` - persistent context and memory markdown files

## Public Site

- `BillyThunderstorm-site/index.html` - public main site
- `BillyThunderstorm-site/bolt/index.html` - Bolt-specific site page
- `BillyThunderstorm-site/BillyThunderstorm-site/deploy/index.html` - legacy deploy mirror

## Legacy or Archived

- `scripts/legacy/README.md` - old script notes
- `docs/guides/TWITCH_INTEGRATION_GUIDE_docs.md` - older writeup kept for reference
