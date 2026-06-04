# Bolt Documentation Index

Use this page as the central map for Bolt.

## Start Here

- `README.md` - high-level project overview and setup
- `BOLT_COMMANDS.md` - current command sheet
- `launch.py` - startup checks and launcher
- `bot.py` - main runtime pipeline
- `config.json` - runtime configuration
- `requirements.txt` - Python dependency list

## Canonical Runtime Docs

- `docs/PROJECT_STATUS.md` - current build status and next steps
- `modules/Think_Learn_Decide.py` - ingestion, reasoning, decisions, feedback loop, audit
- `docs/think_learn_decide.md` - canonical decision and memory schema
- `docs/planning/BOLT_PROCESS_ROADMAP.md` - visual map of Bolt's current process, workspace roles, and future architecture
- `memory/content/full-creator-vision.md` - north star across gaming, tech, AI, product testing, Amazon storefront, beauty/skincare, and Bolt-building
- `docs/Bolt_Checkup.html` - local dashboard source written from live stats
- `data/Bolt_data.js` - generated dashboard payload written at startup
- `tests/test_think_learn_decide.py` - regression tests for intelligence workflows

## Setup and Integration

- `docs/guides/SETUP_GUIDE.md` - setup, prerequisites, and troubleshooting
- `docs/guides/STREAM_DECK_SETUP.md` - Stream Deck setup notes
- `docs/guides/TWITCH_INTEGRATION_GUIDE.md` - Twitch integration pointer
- `docs/guides/TWITCH_INTEGRATION_GUIDE_docs.md` - legacy Twitch integration writeup
- `scripts/setup.sh` - first-time setup and dependency install
- `scripts/verify.py` - project verification checks
- `scripts/log_clip_performance.py` - feed post metrics back into Bolt memory
- `docs/daily-briefing-template.md` - future daily briefing prompt and structure
- `docs/reports/DEBUG_REPORT.md` - debug report and cleanup verification notes
- `docs/architecture/SYSTEM_README.md` - system-level readme material
- `docs/upgrade/UPGRADE_INDEX.md` - upgrade strategy and implementation map

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

## Creator Memory

- `memory/MEMORY.md` - hot cache for Bolt's operational memory
- `memory/people/billy.md` - creator profile for content decisions
- `memory/content/full-creator-vision.md` - full creator north star
- `memory/content/product-reviews.md` - product testing and Amazon storefront reviews
- `memory/content/beauty-skincare.md` - beauty and skincare testing memory
- `memory/content/ai-development.md` - AI learning and Bolt teammate vision
- `memory/content/brand-vision.md` - searchable brand identity summary
- `memory/content/daily-briefing.md` - daily briefing memory
- `memory/context/bolt-personality.md` - Bolt personality and voice notes
- `memory/learning/ch05-neural-network-basics.md` - PyTorch neural-network learning note
- `llm/neural_model.py` - cleaned runnable neural-network example

## Status Surfaces

- `briefings/daily/latest.md` - latest generated daily briefing
- `briefings/daily/latest_tasks.txt` - current task handoff for Shortcuts/reminders
- `docs/reports/` - debug reports and cleanup notes

## Data and Logs

- `data/` - state files, decision model, unified memory, pending proposals
- `logs/` - runtime logs and decision audit trail
- `memory/` - persistent context and memory markdown files
- `llm/` - AI learning material and local neural-model experiments
- `brand/` - brand and logo vision docs
- `teaching/rag/` - RAG study notes and helper experiments
- `docs/upgrade/` - upgrade strategy, status, and code examples

## Legacy or Archived

- `scripts/legacy/README.md` - old script notes
- `docs/guides/TWITCH_INTEGRATION_GUIDE_docs.md` - older writeup kept for reference
