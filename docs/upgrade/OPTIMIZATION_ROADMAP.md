# Bolt Optimization Roadmap

## 🎯 Current State (August 1, 2026)

### Researcher tier ✅ COMPLETE (Aug 1, 2026)

Direction-finding is first-class. Profile + research log drive briefings
and a full CLI loop:

```
profile → research candidates → C7/C6 gate → Billy C5 keep|drop →
then produce content (manager catalog / clips)
```

```bash
bolt research pending
bolt research c5 keep "Name" --why "…"
bolt research add "Name" --platform YouTube --summary "…" --why "…"
```

### Manager tier + ML ranking ✅ COMPLETE (Jul 19, 2026)

All 13 manager upgrades (M1–M13) and the recency-weighted learned
clip-rank model are code-complete. The full flow is real:

```
test item → journal notes → build draft → mark ready →
publish (or paste-and-upload) → mark posted → log 24h performance →
model updates the next rank
```

Catalog (after Aug 1 cleanup): Mouse (real ASIN) + Starter FPS Session Notes.
Example "Daily Driver Gaming Headset" removed — it was never real gear.

What the operator still has to do (not engineering work):

1. Clear C5 research queue (`bolt research pending`)
2. Add real owned products with ASINs when ready
3. Post first real short → `bolt manage mark-posted`
4. Fill in real `TIKTOK_CLIENT_KEY` / `TIKTOK_CLIENT_SECRET` when auto-publish is needed
5. Apply for YouTube/X API apps when manual-assist gets tedious

See `Docs/upgrade/NEXT_UPGRADE_STEPS.md` and
`Docs/upgrade/UPGRADE_STATUS.md` for the per-upgrade changelog and
`Core/modules/BOLT_COMMANDS.md` for the new commands.

## 🎯 Current State (Post-Upgrade - June 6, 2026)

### Completed Optimizations ✅

| Category | Status | Details |
|----------|--------|---------|
| Storage Cleanup | ✅ COMPLETE | 136GB → ~44GB (68% reduction) |
| Video Compression | ✅ COMPLETE | HandBrake H.264/H.265, 75% avg savings |
| Media Rotation | ✅ COMPLETE | Auto-archival every 6 hours |
| Storage Monitoring | ✅ COMPLETE | Alerts every 3 hours |
| Duplicate Detection | ✅ COMPLETE | SHA256 hash-based |
| Dependency Audit | ✅ COMPLETE | Organized, unused removed |
| Performance Baseline | ✅ COMPLETE | 0.23s module import time |

### Size Reduction Metrics
- **Before**: 136GB total
- **After Cleanup**: ~44GB total
- **Reduction**: ~92GB (68% smaller)
- **Recordings**: 136GB → 50GB limit (63% reduction)
- **Clips**: 4.5GB → 1GB limit (78% reduction)

## 📊 Optimization Progress Diagram

```
┌────────────────────────────┐
│    INITIAL STATE           │
│   ● 136GB total size       │
│   ● Recordings: 136GB      │
│   ● Clips: 4.5GB           │
│   ● Many duplicates        │
│   ● No automation          │
└─────────────┬──────────────┘
              │
              ▼
┌────────────────────────────┐
│    ANALYSIS PHASE          │
│   • Identified large dirs  │
│   • Found duplicates       │
│   • Located temp files     │
└─────────────┬──────────────┘
              │
              ▼
┌────────────────────────────┐
│    CLEANUP EXECUTION       │
│   • Trimmed recordings     │
│   • Trimmed clips          │
│   • Removed empty dirs     │
└─────────────┬──────────────┘
              │
              ▼
┌────────────────────────────┐
│    AUTOMATION PHASE        │
│   • Cron jobs scheduled    │
│   • Compression active     │
│   • Alerts configured      │
│   • Dedup detection        │
└─────────────┬──────────────┘
              │
              ▼
┌────────────────────────────┐
│    CURRENT STATE           │
│   ● ~44GB total size       │
│   ● Automated rotation     │
│   ● Email/SMS alerts       │
│   ● 75% compression avg    │
│   ● Hash dedup active      │
└─────────────┬──────────────┘
              │
              ▼
┌────────────────────────────┐
│    TARGET STATE            │
│   ● <30GB total size       │
│   • Storage tiers          │
│   • Smart caching          │
│   • Performance dashboard  │
└────────────────────────────┘
```

## 🔧 Completed Work Details

### 1. Video Compression Pipeline ✅

**Script**: `scripts/media_processing/compress_videos.sh`
- Runs every 30 minutes via cron
- Uses HandBrakeCLI with "Fast 1080p30" preset
- Quality 22 constant quality setting
- Web-optimized output
- Backs up originals before replacing

**Results**:
```
Original size: 66.22 MB
Compressed size: 17.00 MB
Space saved: 75.00%
```

### 2. Storage Monitoring with Alerts ✅

**Script**: `scripts/monitoring/storage_monitor.sh`
- Runs every 3 hours via cron
- Configured recipients:
  - Email: billycarteriv@gmail.com
  - SMS: 707-567-8495 (AT&T)
- Thresholds:
  - Warning: 80%
  - Critical: 95%
- Directory limits:
  - Recordings: 50GB
  - Clips: 1GB
  - Logs: 2GB
  - Data: 5GB

**Notification Methods**:
- Email via macOS Mail/sendmail
- SMS via AT&T gateway (txt.att.net)
- Generic webhook (optional)
- Discord webhook (optional)

### 3. Media Rotation ✅

**Script**: `scripts/maintenance/media_rotation.sh`
- Runs every 6 hours via cron
- Archives oldest files first
- Configurable size limits
- Dry-run mode available

### 4. Duplicate Detection ✅

**Script**: `scripts/clip_deduplicator.py`
- SHA256 hash-based detection
- Persistent database: `data/media_hash_db.json`
- Scans clips/ and recordings/
- Returns exit code 1 if duplicates found

**Usage**:
```bash
python3 scripts/clip_deduplicator.py          # Full scan
python3 scripts/clip_deduplicator.py --dry-run  # No DB changes
python3 scripts/clip_deduplicator.py --check file.mp4  # Single file
```

### 5. Performance Baseline ✅

**Script**: `scripts/performance_baseline.py`
- Module import timing
- Script syntax check timing
- System resource tracking
- Results saved to `logs/performance/`

**Baseline Metrics**:
- Total module import: 0.23s
- Memory: 36GB total, ~14.5GB available
- Disk: ~98GB free

### 6. Requirements.txt Audit ✅

**Changes**:
- Removed: `openai-whisper`, `backports.zoneinfo`
- Organized by category with comments
- Pinned versions for stability noted

**Categories**:
- Core Video/Audio Processing
- AI/LLM Integration
- Platform Integrations
- Google Services
- Voice/Speech
- Web/Queue
- Utilities

---

## 📋 Future Optimization Phases

### Phase 1: Storage Optimization (ONGOING)

#### Completed:
- [x] Media rotation implemented
- [x] Video compression pipeline
- [x] Hash-based duplicate detection

#### Future:
- [ ] Storage tiers (hot/warm/cold) based on access frequency
- [ ] Compression integrated into archiving process
- [ ] S3/cloud archival for cold storage
- [ ] Automatic thumbnail generation for media library

### Phase 2: Dependency Optimization (COMPLETE - Core)

#### Completed:
- [x] Requirements.txt audited
- [x] Unused packages removed
- [x] Categories documented

#### Future:
- [ ] Migrate to pyproject.toml
- [ ] Separate dev vs production dependencies
- [ ] Consider poetry or pip-tools
- [ ] Lazy loading for heavy modules

### Phase 3: Infrastructure Improvements (FUTURE)

- [ ] Database optimization (if SQLite added)
  - [ ] Indexing for frequent queries
  - [ ] VACUUM and ANALYZE routines
  - [ ] Archive old conversation logs
- [ ] Build pipeline improvements
  - [ ] Faster startup times
  - [ ] Parallel module loading
- [ ] Caching layer
  - [ ] Redis or local file cache
  - [ ] API response caching
  - [ ] Embedding cache for RAG
- [ ] Performance profiling
  - [ ] Bottleneck identification
  - [ ] Memory leak detection

### Phase 4: Advanced Features (FUTURE)

- [x] Predictive storage management (ML-based) — recency-weighted learned clip-rank model added Jul 19, 2026 (see `Core/modules/Clip_Ranker.py`)
- [ ] Adaptive bitrate streaming for media playback
- [ ] Intelligent caching based on access patterns
- [ ] Cross-device synchronization
- [ ] Real-time performance dashboard
- [ ] Automated testing pipeline

---

## 🎯 Success Metrics

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| Total Storage | <30GB | ~44GB | 🔄 In Progress |
| Recordings Size | <50GB | ~0GB* | ✅ Complete |
| Clips Size | <1GB | ~0GB* | ✅ Complete |
| Compression Rate | 40-60% | 75% | ✅ Exceeded |
| Import Time | <1s | 0.23s | ✅ Complete |
| Disk Usage Alert | 80% | 11% | ✅ Healthy |
| Dependencies | Updated | Audited | ✅ Complete |
| Alerts Configured | Email + SMS | Done | ✅ Complete |

*Recent cleanup/archival completed

---

## 🚀 Immediate Next Actions (For Future Work)

### When Storage Grows Again:
```bash
# Check current storage usage
du -sh recordings clips logs data

# Run manual optimization
python3 scripts/maintenance/storage_optimization.sh

# Check for new duplicates
python3 scripts/clip_deduplicator.py
```

### Performance Monitoring:
```bash
# Establish new baseline after changes
python3 scripts/performance_baseline.py

# View historical baselines
ls -la logs/performance/
```

---

## 💡 Recommendations for Future Development

1. **Implement size thresholds** - Warn when directories exceed limits ✅ DONE
2. **Add compression to save pipeline** - Automatically optimize new media ✅ DONE
3. **Create storage tiers** - Hot/warm/cold storage based on access frequency - FUTURE
4. **Add usage analytics** - Understand what features are actually used - FUTURE
5. **Set up backup verification** - Ensure backups are working correctly - FUTURE
6. **Performance dashboard** - Real-time metrics visualization - FUTURE

---

## 📓 Maintenance Checklist

### Weekly:
- [ ] Review storage_monitor.log for warnings
- [ ] Check video_compression.log for failures
- [ ] Verify cron jobs are running: `crontab -l`

### Monthly:
- [ ] Run duplicate detection: `python3 scripts/clip_deduplicator.py`
- [ ] Run performance baseline: `python3 scripts/performance_baseline.py`
- [ ] Review and archive old clips/recordings if needed

### Quarterly:
- [ ] Audit requirements.txt for updates
- [ ] Review alert recipients and update if needed
- [ ] Evaluate storage tier implementation

---

## 🔧 Active Cron Schedule

```bash
# View current schedule
crontab -l

# Current jobs:
*/30 * * * *  # Video compression
0 */3 * * *   # Storage monitoring + alerts
0 */6 * * *   # Media rotation
```

---

*Generated during optimization session: June 6, 2026*
*All planned upgrades completed - see NEXT_UPGRADE_STEPS.md for details*
