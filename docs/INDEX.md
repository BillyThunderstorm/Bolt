# Bolt Documentation Index

Use this page as the central map for Bolt.

## Start Here

- `README.md` - high-level project overview and setup
- `launch.py` - startup checks and launcher
- `bot.py` - main runtime pipeline
- `config.json` - runtime configuration
- `requirements.txt` - Python dependency list

## Core Intelligence

- `modules/Think_Learn_Decide.py` - ingestion, reasoning, decisions, feedback loop, audit
- `modules/Brain_Controller.py` - alternate decision controller scaffold
- `docs/think_learn_decide.md` - canonical schema, safety, and learning store docs
- `tests/test_think_learn_decide.py` - regression tests for intelligence workflows

## Setup and Status Docs

- `docs/guides/SETUP_GUIDE.md` - setup and prerequisites
- `docs/guides/STREAM_DECK_SETUP.md` - Stream Deck setup notes
- `docs/guides/TWITCH_INTEGRATION_GUIDE.md` - Twitch integration pointer
- `docs/guides/TWITCH_INTEGRATION_GUIDE_docs.md` - legacy Twitch integration writeup
- `docs/PROJECT_STATUS.md` - current build status and next steps
- `docs/Bolt_Checkup.html` - local runtime checkup dashboard
- `docs/site/Bolt_Checkup.html` - site-hosted checkup page

## Integrations and Briefings

- `scripts/get_twitch_token.py` - canonical Twitch bot token setup
- `scripts/log_clip_performance.py` - feed post metrics back into Bolt memory
- `docs/briefings/daily-briefing-2026-04-16.md` - archived daily briefing note
- `docs/briefings/bolt_briefing_2026-04-14.md` - archived Bolt briefing note

## Operational Scripts

- `scripts/setup.sh` - first-time setup and dependency install
- `scripts/setup_icloud.sh` - legacy iCloud mover for the shared-folder flow
- `scripts/Filter_Backlog.py` - filter low-scoring clips from backlog
- `scripts/process_recordings.py` - batch recording processing helper
- `scripts/build_env.py` - environment setup utility
- `scripts/verify.py` - project verification checks
- `scripts/autostart.py` - autostart utility
- `scripts/legacy/README.md` - legacy script notes

## Key Runtime Modules

- `modules/Watcher.py` - recording folder monitoring
- `modules/Highlight_Detector.py` - highlight detection
- `modules/Clip_Generator.py` - clip generation
- `modules/Subtitle_Generator.py` - subtitle generation
- `modules/Title_Generator.py` - title generation
- `modules/AI_Title_Generator.py` - AI title generation
- `modules/Clip_Ranker.py` - ranking and scoring
- `modules/Clip_Factory.py` - vertical format conversion
- `modules/Post_Queue.py` - post queue integration
- `modules/Peak_Hour_Notifier.py` - timing alerts
- `modules/Bolt_Chat.py` - Twitch personality layer
- `modules/Bolt_Voice.py` - spoken alerts and TTS
- `modules/Bolt_Memory.py` - long-term memory
- `modules/Bolt_Search.py` - memory search helper
- `modules/Brain_Controller.py` - event decision controller scaffold

## Data and Logs

- `data/` - state files, decision model, unified memory, pending proposals
- `logs/` - runtime logs and decision audit trail
- `memory/` - persistent context and memory markdown files

## Public Site

- `BillyThunderstorm-site/index.html` - public main site
- `BillyThunderstorm-site/bolt/index.html` - Bolt-specific site page
- `docs/site/` - generated static copies and checkup pages
