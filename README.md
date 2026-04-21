Bolt - Personal Streaming AI Assistant

Your complete streaming enhancement platform with AI-powered highlights, automated clips, intelligent titles, and TikTok integration.

Features You Now Have

Real-Time Highlight Detection
Audio Analysis: Detects excitement and energy peaks
Visual Analysis: Tracks motion and scene changes
Gaming Detection: Template matching for victory screens
OBS Integration: Mark highlights during live streams (Shift+H)

Automated Clip Pipeline
Auto-detects highlight moments
Generates 30-second clips
Maintains original quality
Organized output structure

AI Title Generation
- Context-aware titles from clip analysis
- 6 title categories (Reaction, Skill, Lucky, Competitive, Funny, Comeback)
- Trained on viral gaming content patterns
- Customizable templates

Intelligent Ranking System
- Virality scoring (0-100)
- Multi-metric analysis:
  - Visual energy (motion detection)
  - Audio peaks (excitement)
  - Scene changes (dynamic content)
  - Length optimization
  - Engagement potential
  - Historical performance

TikTok Automation
- Automatic vertical formatting (9:16)
- Title overlays
- Description generation with hashtags
- Upload queue system
- Performance tracking

Subtitle Generation
- Automatic speech-to-text (Whisper)
- Full transcription
- Engagement keyword detection

What's Included

Modules:
├── Watcher.py                 # Folder monitoring
├── Highlight_Detector.py      # Audio-based detection
├── Gaming_Highlights.py       # Vision-based detection
├── Clip_Generator.py          # Clip creation
├── Subtitle_Generator.py      # Speech-to-text
├── AI_Title_Generator.py      # New: AI titles
├── Clip_Ranker.py             # New: Virality scoring
├── TikTok_Poster.py           # New: TikTok integration
└── OBS_Integration.py         # New: Real-time control

Configuration:
├── config.json               # Main settings
├── .env.example             # Credentials template
└── setup.sh                 # Quick setup script

Documentation:
├── SETUP_GUIDE.md           # Comprehensive guide
├── PROJECT_STATUS.md        # Current status
└── README.md                # This file
```

Quick Start (3 Steps)

1. Setup
```bash
chmod +x setup.sh
./setup.sh
```

2. Configure
Edit `config.json` and `.env` with your settings

3. Run
```bash
python bot.py
```

Pipeline Overview

```
Setup
├── Place recordings in recordings/ folder
└── Configure settings in config.json

Processing (Automatic)
├── Detect highlights
├── Generate 30-sec clips
├── Analyze & rank clips
├── Generate AI titles
├── Create subtitles
└── Format for TikTok

Output
├── clips/ → Raw clips
├── vertical_clips/ → TikTok-ready
├── clip_rankings.json → Scores
└── tiktok_session.json → Upload queue
```

## 📊 Virality Scoring Example

```
High Energy Moment (95/100 score)
├── Visual Energy: 0.89 (lots of motion)
├── Audio Peaks: 0.85 (exciting audio)
├── Scene Changes: 0.92 (dynamic)
├── Length: 1.00 (perfect 35 seconds)
├── Engagement: 0.78 (good keywords)
└── Potential: ⭐⭐⭐⭐⭐ VIRAL

Normal Moment (62/100 score)
├── Visual Energy: 0.55
├── Audio Peaks: 0.48
├── Scene Changes: 0.60
├── Length: 0.85
├── Engagement: 0.52
└── Potential: ⭐⭐⭐ GOOD
```

Configuration Examples

For Gaming Highlights
```json
{
  "game": "Marvel Rivals",
  "highlight_sensitivity": 0.7,
  "auto_rank": true,
  "auto_format_tiktok": true
}
```

For High Volume
```json
{
  "min_clip_duration": 15,
  "max_clip_duration": 60,
  "auto_post_tiktok": false,
  "use_obs_integration": false
}
```

For Professional Output
```json
{
  "highlight_sensitivity": 0.5,
  "auto_rank": true,
  "auto_format_tiktok": true,
  "auto_post_tiktok": false,
  "hashtags": ["#ProGaming", "#Esports"]
}
```

TikTok Setup

Option 1: Manual Review (Recommended)
1. System queues videos
2. Review titles/descriptions
3. Post manually
4. Track metrics

Option 2: Auto-Posting
1. Configure TikTok credentials in `.env`
2. Set `auto_post_tiktok: true`
3. System posts automatically
4. Check `tiktok_session.json` for results

OBS Real-Time Integration

Setup OBS
1. Install OBS WebSocket plugin
2. Tools → obs-websocket Settings
3. Set password if needed
4. Note the port (default: 4455)

Use in Config
```json
{
  "use_obs_integration": true
}
```

Use During Stream
- **Shift+H**: Mark highlight at current moment
- **Shift+R**: Save replay buffer as clip
- **Auto-detect**: Scene changes trigger highlights

Advanced Features

Train on Your Viral Titles
```python
python
>>> from modules.AI_Title_Generator import train_on_titles
>>> train_on_titles("my_viral_titles.json")
```

Query Top Clips
```python
python
>>> from modules.Clip_Ranker import get_top_clips
>>> top = get_top_clips(10)
>>> for name, data in top:
...     print(f"{name}: {data['score']:.1f}")
```

Check TikTok Queue
```python
python
>>> from modules.TikTok_Poster import get_tiktok_queue
>>> queue = get_tiktok_queue()
>>> for video in queue:
...     print(video['title'])
```

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| No highlights found | Lower `highlight_sensitivity` in config |
| OBS not connecting | Install obs-websocket plugin, check port |
| Slow processing | Disable OBS, use faster GPU, reduce video size |
| TikTok upload fails | Check credentials, verify file size < 287MB |
| Long processing time | Disable audio transcription if not needed |

Performance Tips

1. **Better Detection**: Use template matching for your game's UI
2. **Faster Processing**: Process clips in parallel
3. **Better Titles**: Train on your best-performing clips
4. **Viral Content**: Combine high audio energy + visual motion
5. **Optimization**: Use GPU acceleration in config

Security

- Store `.env` file safely (don't commit to git)
- Use app-specific passwords for TikTok
- Rotate credentials regularly
- Don't share OBS password

Generated Files

After processing, check:
- `clips/highlight_*.mp4` - Generated clips
- `vertical_clips/` - TikTok format
- `clip_rankings.json` - Rankings database
- `tiktok_session.json` - Upload history
- `viral_titles_model.json` - AI model data

Example Workflow

```bash
1. Copy your recording to recordings/
cp my_stream.mp4 recordings/

2. Start bot
python bot.py

Processing output:
Processing: my_stream.mp4
Detecting highlights...
Found 12 potential highlights
Generating clips...
Generated 12 clips
Top 5 Clips:
1. This clip is INSANE (Score: 92.3)
2. Wait... WHAT?! (Score: 88.7)
...

Check results
ls clips/
ls vertical_clips/
cat clip_rankings.json

4. Review TikTok queue
Videos ready at: vertical_clips/

5. Post manually or auto-post if configured

Next Level

Coming Soon (You Can Add)
- [ ] Discord integration (auto-post highlights)
- [ ] YouTube Shorts automation
- [ ] Twitch VOD processing
- [ ] Performance analytics dashboard
- [ ] Community voting on clips
- [ ] Custom highlight templates
- [ ] API endpoint for external apps

Support & Documentation

- **Setup**: See `SETUP_GUIDE.md`
- **Status**: See `PROJECT_STATUS.md`
- **Config**: See `config.json`
- **Modules**: Check inline documentation

You're Ready!

Your streaming AI assistant is fully configured with:
- ✅ Real-time highlight detection
- ✅ Automated clip pipeline  
- ✅ AI title generation
- ✅ Virality ranking
- ✅ TikTok automation
- ✅ Optional OBS integration

**Start streaming smarter:**
```bash
python bot.py
```

---

*Built for gamers who want to lighten the weight of content creation*
*March 24, 2026 - Version 1.0*
