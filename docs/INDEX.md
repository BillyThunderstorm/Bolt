# Bolt Documentation Index

Use this page as the central map for Bolt.

## Start Here

- `README.md` - high-level project overview
- `launch.py` - startup checks and launcher
- `bot.py` - main runtime pipeline
- `config.json` - runtime configuration

## Core Intelligence (Think/Learn/Decide)

- `modules/Think_Learn_Decide.py` - ingestion, reasoning, decisions, feedback loop, audit
- `docs/think_learn_decide.md` - canonical schema, safety, and learning store docs
- `tests/test_think_learn_decide.py` - regression tests for intelligence workflows

## Setup and Status Docs

- `docs/SETUP_GUIDE.md` - setup and prerequisites
- `docs/PROJECT_STATUS.md` - current status and milestones
- `docs/STREAM_DECK_SETUP.md` - Stream Deck setup notes

## Integrations and Briefings

- `docs/TWITCH_INTEGRATION_GUIDE.md` - Twitch API + dashboard integration guide
- `docs/daily-briefing-2026-04-16.md` - archived daily briefing note
- `docs/bolt_briefing_2026-04-14.md` - archived Bolt briefing note

## Operational Scripts

- `scripts/get_twitch_token.py` - canonical Twitch bot token setup
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
- `modules/Clip_Ranker.py` - ranking and scoring
- `modules/Clip_Factory.py` - vertical format conversion
- `modules/Post_Queue.py` - post queue integration
- `modules/Peak_Hour_Notifier.py` - timing alerts
- `modules/Bolt_Memory.py` - long-term memory
- `modules/Brain_Controller.py` - event decision controller

## Data and Logs

- `data/` - state files, decision model, unified memory, pending proposals
- `logs/` - runtime logs and decision audit trail
- `memory/` - persistent context and memory markdown files
