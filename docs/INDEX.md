# Bolt Documentation Index

Use this page as the central map for Bolt.

## Start Here

| File | Description |
|------|-------------|
| `README.md` | High-level project overview and setup |
| `BOLT_COMMANDS.md` | Complete command reference with all user interfaces |
| `launch.py` | Startup checks and launcher |
| `bot.py` | Main runtime pipeline |
| `config.json` | Runtime configuration |
| `requirements.txt` | Python dependency list |
| `docs/PROJECT_STATUS.md` | Current build status and completed upgrades |
| `NEXT_UPGRADE_STEPS.md` | Upgrade completion status and next steps |
| `OPTIMIZATION_ROADMAP.md` | Long-term optimization plan |

## Canonical Runtime Docs

| File | Description |
|------|-------------|
| `docs/PROJECT_STATUS.md` | Current build status and next steps |
| `modules/Think_Learn_Decide.py` | Ingestion, reasoning, decisions, feedback loop, audit |
| `docs/think_learn_decide.md` | Canonical decision and memory schema |
| `memory/content/full-creator-vision.md` | North star across all creator lanes |
| `docs/Bolt_Checkup.html` | Local dashboard source from live stats |
| `data/Bolt_data.js` | Generated dashboard payload |
| `tests/test_think_learn_decide.py` | Regression tests for intelligence workflows |

## Setup and Integration

| File | Description |
|------|-------------|
| `docs/guides/SETUP_GUIDE.md` | Setup, prerequisites, and troubleshooting |
| `docs/guides/STREAM_DECK_SETUP.md` | Stream Deck setup notes |
| `docs/guides/TWITCH_INTEGRATION_GUIDE.md` | Twitch integration pointer |
| `scripts/setup.sh` | First-time setup and dependency install |
| `scripts/verify.py` | Project verification checks |
| `scripts/log_clip_performance.py` | Feed post metrics back into Bolt memory |
| `docs/daily-briefing-template.md` | Daily briefing prompt and structure |
| `docs/reports/DEBUG_REPORT.md` | Debug report and verification notes |
| `docs/architecture/SYSTEM_README.md` | System-level overview |
| `docs/upgrade/UPGRADE_INDEX.md` | Upgrade strategy and implementation map |

## Storage Management (NEW)

| File | Description |
|------|-------------|
| `scripts/clip_deduplicator.py` | SHA256 hash-based duplicate detection |
| `scripts/performance_baseline.py` | Performance benchmarking script |
| `scripts/monitoring/storage_monitor.sh` | Disk usage monitoring with alerts |
| `scripts/maintenance/media_rotation.sh` | Size-based media archival |
| `scripts/media_processing/compress_videos.sh` | HandBrake video compression |
| `configs/storage_alerts.env` | Email/SMS alert configuration |
| `configs/rotation_policy.yaml` | Media rotation configuration |

## Runtime Modules

| Module | Description |
|--------|-------------|
| `modules/Think_Learn_Decide.py` | Current intake, reasoning, decisions, feedback loop |
| `modules/Brain_Controller.py` | Legacy compatibility controller |
| `modules/Watcher.py` | Recording folder monitoring |
| `modules/Highlight_Detector.py` | Highlight detection |
| `modules/Clip_Generator.py` | Clip generation |
| `modules/Clip_Deduplicator.py` | Duplicate protection |
| `modules/Subtitle_Generator.py` | Subtitle generation |
| `modules/Title_Generator.py` | Local title generation |
| `modules/AI_Title_Generator.py` | AI title path |
| `modules/Clip_Ranker.py` | Ranking and tiering |
| `modules/Clip_Factory.py` | Vertical format conversion |
| `modules/Post_Queue.py` | Post queue integration |
| `modules/Peak_Hour_Notifier.py` | Timing alerts |
| `modules/Bolt_Chat.py` | Twitch personality layer |
| `modules/Bolt_Voice.py` | Spoken alerts and TTS |
| `modules/Bolt_Memory.py` | Long-term memory |
| `modules/Bolt_Search.py` | Memory search helper |
| `modules/Memory_Index.py` | Local searchable memory index |
| `modules/Multi_Publisher.py` | Multi-platform posting packets |

## Creator Memory

| File | Description |
|------|-------------|
| `memory/MEMORY.md` | Hot cache for Bolt's operational memory |
| `memory/people/billy.md` | Creator profile for content decisions |
| `memory/content/full-creator-vision.md` | Full creator north star |
| `memory/content/product-reviews.md` | Product testing and Amazon storefront |
| `memory/content/beauty-skincare.md` | Beauty and skincare testing |
| `memory/content/ai-development.md` | AI learning and Bolt teammate vision |
| `memory/content/brand-vision.md` | Searchable brand identity |
| `memory/content/daily-briefing.md` | Daily briefing memory |
| `memory/context/bolt-personality.md` | Bolt personality and voice |
| `memory/learning/` | Neural network learning notes |
| `llm/neural_model.py` | Cleaned runnable neural-network example |

## Status Surfaces

| File | Description |
|------|-------------|
| `briefings/daily/latest.md` | Latest generated daily briefing |
| `briefings/daily/latest_tasks.txt` | Current task handoff |
| `docs/reports/` | Debug reports and cleanup notes |
| `docs/Bolt_Checkup.html` | Live checkup dashboard |

## Data and Logs

| Directory | Description |
|-----------|-------------|
| `data/` | State files, decision model, unified memory |
| `logs/` | Runtime logs and decision audit trail |
| `logs/performance/` | Performance baseline results |
| `memory/` | Persistent context and memory files |
| `llm/` | AI learning material and experiments |
| `brand/` | Brand and logo vision docs |
| `teaching/rag/` | RAG study notes and experiments |
| `docs/upgrade/` | Upgrade strategy and code examples |
| `configs/` | Configuration files for alerts and rotation |

## User Interfaces Summary

Bolt provides multiple ways to interact:

### Primary Interfaces
| Interface | Command | Description |
|-----------|---------|-------------|
| CLI Launcher | `python3 launch.py` | Main entry point |
| Bot Runtime | `python3 bot.py` | Direct execution |
| Chat Module | `python3 -m modules.Bolt_Chat` | Local chat testing |
| Voice Module | `python3 -m modules.Bolt_Voice "text"` | TTS output |

### Memory Interfaces
| Interface | Command | Description |
|-----------|---------|-------------|
| Memory Index | `python3 -m modules.Memory_Index` | Searchable index |
| Memory Browser | `python3 -m modules.Bolt_Memory` | Full operations |
| Refresh Index | `python3 scripts/refresh_memory_index.py` | Rebuild index |

### Storage Interfaces
| Interface | Command | Description |
|-----------|---------|-------------|
| Duplicate Scanner | `python3 scripts/clip_deduplicator.py` | Hash-based dedup |
| Performance Baseline | `python3 scripts/performance_baseline.py` | Benchmarks |
| Storage Monitor | `scripts/monitoring/storage_monitor.sh` | Disk + alerts |
| Video Compressor | `scripts/media_processing/compress_videos.sh` | HandBrake |
| Media Rotator | `scripts/maintenance/media_rotation.sh` | Auto-archival |

### Monitoring Interfaces
| Interface | Path/Command | Description |
|-----------|--------------|-------------|
| Checkup Dashboard | `docs/Bolt_Checkup.html` | Live status |
| Storage Log | `logs/storage_monitor.log` | Alert history |
| Compression Log | `logs/video_compression.log` | Compression results |
| Cron Schedule | `crontab -l` | Active jobs |

## Legacy or Archived

| File | Description |
|------|-------------|
| `scripts/legacy/README.md` | Old script notes |
| `docs/guides/TWITCH_INTEGRATION_GUIDE_docs.md` | Older writeup for reference |

---

*Last updated: June 6, 2026 - Added storage management docs and user interfaces index*
