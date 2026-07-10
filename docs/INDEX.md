# Bolt Documentation Index

Use this page as the central map for Bolt.

## Color / Label Map

| Label | Path root | Use for |
|-------|-----------|---------|
| 🟡 CORE | `Core/` | Code, modules, brain, config |
| 🔵 DATA | `Data/data/` | Catalog, storefront, sponsors, memory |
| 🟢 DOCS | `Docs/` | Commands, status, briefings, reviews |
| 🟣 APP | `App/` | UI / brand |
| 🟠 MEDIA | `media/` | Clips / recordings |
| 🔴 MANAGER | `Content_Manager` + `bin/bolt` | Daily creator OS |

## Start Here

| Label | File | Description |
|-------|------|-------------|
| 🔴 | `Docs/BOLT_COMMANDS.md` | **All commands** (manager + pipeline) |
| 🟢 | `Docs/PROJECT_STATUS.md` | Current build status + manager progress |
| 🟢 | `Docs/NEXT_UPGRADE_STEPS.md` | Upgrade tracker (manager M1–M13) |
| 🟢 | `Docs/INDEX.md` | This map |
| 🟡 | `Core/modules/Content_Manager.py` | Creator manager implementation |
| 🟡 | `Core/bolt_brain.md` | William creator profile |
| 🟡 | `bin/bolt` | Single CLI entry |
| 🔵 | `Data/data/business/business-playbook.md` | How to grow the creator business |
| 🔵 | `Data/data/business/bolt-advancement.md` | How to advance Bolt itself |
| 🟢 | `Docs/briefings/daily/latest_morning.md` | Latest Good Morning briefing |
| 🟢 | `Docs/requirements.txt` | Python dependencies |
| 🟢 | `Docs/OPTIMIZATION_ROADMAP.md` | Long-term optimization plan |

## Canonical Runtime Docs

| File | Description |
|------|-------------|
| `docs/PROJECT_STATUS.md` | Current build status and next steps |
| `modules/Think_Learn_Decide.py` | Ingestion, reasoning, decisions, feedback loop, audit |
| `docs/think_learn_decide.md` | Canonical decision and memory schema |
| `memory/content/full-creator-vision.md` | North star across all creator lanes |
| `docs/requirements/creator-domains-requirements.md` | System requirements for 7 creator domains (NEW) |
| `.github/instructions/creator-domains.instructions.md` | Behavioral instructions with full personality (NEW) |
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
| `modules/Bolt_Conversation.py` | Voice conversation engine — mic, Whisper, OpenAI, TTS (NEW) |
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
| `modules/Bolt_Chat.py` | Twitch personality layer with optional voice replies |
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
| `memory/content/content-creation.md` | Content creation domain (NEW) |
| `memory/content/assistant-productivity.md` | Assistant productivity domain (NEW) |
| `memory/content/game-testing.md` | Game and tech testing/review domain (NEW) |
| `memory/content/live-streaming.md` | Live streaming domain (NEW) |
| `memory/content/social-media-management.md` | Social media management domain (NEW) |
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
| Bot Runtime | `python3 bot.py` | Direct execution (45ms import after June 21 fix) |
| Chat Module | `python3 -m modules.Bolt_Chat` | Local chat testing |
| Voice Module | `python3 -m modules.Bolt_Voice "text"` | TTS output |
| Voice Conversation | `python3 -m modules.Bolt_Conversation` | Hands-free voice chat with memory |
| Chat with Voice | `python3 -m modules.Bolt_Chat --voice` | Twitch chat with spoken replies |
| Daily Briefing | `python3 scripts/daily_briefing.py [--print\|--send]` | Memory-aware morning briefing |
| Weekly Analysis | `python3 scripts/weekly_analysis.py [--print\|--send]` | Memory-aware Sunday insights |
| Calendar Feeds | `python3 scripts/generate_calendar.py` | RFC 5545 ICS feeds |
| Thumbnails | `python3 scripts/generate_thumbnails.py` | JPG thumbnails via ffmpeg |
| Twitch Auto-Clip | `python3 scripts/auto_clip_twitch.py` | Download VODs → clip pipeline (NEW) |
| Highlight Reel | `python3 scripts/make_twitch_highlights.py` | Compile best clips into VOD (NEW) |

### Memory Interfaces
| Interface | Command | Description |
|-----------|---------|-------------|
| Memory Index | `python3 -m modules.Memory_Index` | Searchable index |
| Memory Browser | `python3 -m modules.Bolt_Memory` | Full operations |
| Refresh Index | `python3 scripts/refresh_memory_index.py` | Rebuild index |
| Creator-Lane Tests | `python3 -m unittest tests.test_creator_lanes_reachable` | 9 tests, all 7 lanes reachable |

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
| Voice Conversation | `python -m modules.Bolt_Conversation` | Voice chat loop with memory (NEW) |
| Chat (with Voice) | `python -m modules.Bolt_Chat --voice` | Twitch chat with voice replies (NEW) |


## Websites

| File / URL | Description |
|-------------|-------------|
| `scripts/site_data_writer.py` | Pushes live data to GitHub for websites |
| `site-data.json` | Current site data snapshot (auto-updated) |
| [bolt.billythunderstorm.us](https://bolt.billythunderstorm.us) | Command center |
| [billythunderstorm.us](https://billythunderstorm.us) | Creator portfolio |
| [billythunderstorm.live](https://billythunderstorm.live) | Live status page |
| [api.billythunderstorm.us](https://api.billythunderstorm.us) | Live data API |
| `/tmp/sites/` | Site source files and deploy configs |

## Legacy or Archived

| File | Description |
|------|-------------|
| `scripts/legacy/README.md` | Old script notes |
| `docs/guides/TWITCH_INTEGRATION_GUIDE_docs.md` | Older writeup for reference |

## Active Cron Schedule

```bash
crontab -l
```

| Schedule | Task | Description |
|----------|------|-------------|
| `*/30 * * * *` | Video Compression | HandBrake H.264/H.265 |
| `0 */3 * * *` | Storage Monitor | Disk usage + email/SMS alerts |
| `0 */6 * * *` | Media Rotation | Size-based archival |
| `0 3 * * *` | Storage Optimization | Nightly cleanup (3-day retention) |
| `0 5 * * *` | **Thumbnail Refresh** | JPGs for clips/ + vertical_clips/ |
| `*/15 * * * *` | Site Data Push | Recommended (not in default crontab) |
| `0 7 * * *` | **Daily Briefing** | Memory-aware briefing + calendar feeds |
| `0 */2 * * *` | **Auto-Process** | New recordings pipeline |
| `0 9 * * 0` | **Weekly Analysis** | Sunday insights + recommendations |

---

*Last updated: July 1, 2026 - Added Twitch VOD auto-clipping pipeline and highlight reel compiler. Total test suite: 122 passing.*
