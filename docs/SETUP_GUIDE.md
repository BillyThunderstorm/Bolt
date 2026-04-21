# 🎮 Personal Streaming AI Assistant - Complete Guide

Your streaming AI assistant is now fully equipped to handle highlights, clips, titles, and TikTok automation!

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip3 install -r requirements.txt

# 2. Configure your settings
# Edit config.json and .env for your needs

# 3. Start the assistant
python3 bot.py
```

## 📋 Features

### ✅ Implemented
- **Real-time Highlight Detection** - Audio and visual analysis
- **Automated Clip Generation** - 30-second clips from highlights
- **AI Title Generation** - Context-aware titles based on clip analysis
- **Subtitle Generation** - Automatic transcription using Whisper
- **Clip Ranking** - Virality scoring (0-100 scale)
- **TikTok Formatting** - Automatic vertical video conversion (9:16)
- **TikTok Queue System** - Queue clips for posting
- **OBS Integration** - Real-time streaming control (optional)

## 🎯 How It Works

### Pipeline Flow
```
Recording Detected
    ↓
Audio/Visual Highlight Detection
    ↓
Clip Generation (30 sec clips)
    ↓
Parallel Processing:
  • AI Title Generation
  • Subtitle Generation
  • Virality Ranking
    ↓
TikTok Formatting (9:16 aspect)
    ↓
Queue for Posting
```

### 1. Folder Watching
- Automatically monitors `recordings/` folder
- Detects new `.mp4` files
- Processes them in the pipeline

### 2. Highlight Detection
- **Audio-based**: Detects energy spikes in audio (excitement)
- **Visual-based**: Detects scene changes and motion
- **Gaming-specific**: Template matching for victory screens

### 3. Clip Generation
- Creates 30-second clips from highlights
- `start = highlight_time - 15 seconds`
- `end = highlight_time + 15 seconds`
- Saved as `clips/highlight_0.mp4`, etc.

### 4. AI Title Generation
Analyzes the clip using:
- **Visual intensity**: Motion and brightness changes
- **Audio analysis**: Peak detection and transcription
- **Scene classification**: Determines emotion/category
- Generates contextual titles from 6 categories:
  - Reaction (high intensity)
  - Skill (multiple scene changes)
  - Lucky/Close moments
  - Competitive moments
  - Funny (based on laughter)
  - Comeback moments

### 5. Clip Ranking
Virality score based on:
- **Visual Energy** (25%) - Motion and activity
- **Audio Peaks** (20%) - Excitement in audio
- **Scene Changes** (20%) - Dynamic content
- **Optimal Length** (15%) - 30-45 seconds ideal
- **Engagement Score** (10%) - Transcription keywords
- **Historical Performance** (10%) - Previous views

Example scores:
- 90+ = Highly viral potential
- 70-89 = Good clip
- 50-69 = Average
- <50 = Needs improvement

### 6. TikTok Formatting
- Converts to 9:16 aspect ratio (vertical)
- Optimizes codec (libx264, AAC audio)
- Adds title overlay (optional)
- Max duration: 10 minutes
- Max file size: 287MB

### 7. Queue & Posting
- Videos are queued in `tiktok_session.json`
- Manual review before auto-posting
- Generates descriptions with hashtags
- Tracks upload history

## ⚙️ Configuration

### config.json
```json
{
  "game": "Marvel Rivals",           // Your game
  "auto_rank": true,                  // Auto rank clips
  "auto_format_tiktok": true,         // Convert to vertical
  "auto_post_tiktok": false,          // Auto post (manual review recommended)
  "min_clip_duration": 10,            // Minimum seconds
  "max_clip_duration": 120,           // Maximum seconds
  "use_obs_integration": false,       // Enable OBS control
  "highlight_sensitivity": 0.7,      // Detection sensitivity (0-1)
  "hashtags": ["#gaming", ...]       // Your hashtags
}
```

### .env Configuration
```bash
# OBS WebSocket (if streaming)
OBS_HOST=localhost
OBS_PORT=4455
OBS_PASSWORD=TzoUBPQM3759anMO

# TikTok (for automation)
TIKTOK_USERNAME=BillyandRandyGaming
TIKTOK_PASSWORD=FrostBiTTen23!
```

## 📱 TikTok Integration

### Setting Up TikTok Posting
1. Create a TikTok creator account
2. Enable API access or use session authentication
3. Configure credentials in `.env`
4. Set `auto_post_tiktok=true` in `config.json`

### Queue Management
```python3
from modules.TikTok_Poster import get_tiktok_queue

# View queued videos
queue = get_tiktok_queue()
for video in queue:
    print(f"- {video['title']}")
    print(f"  {video['description']}\n")
```

## 📡 OBS Integration

### Installation
1. Install OBS Studio
2. Install obs-websocket plugin: https://github.com/obsproject/obs-websocket
3. Configure in OBS: Tools → obs-websocket Settings
4. Set `use_obs_integration=true` in config

### Features
- Mark highlights during stream (Shift+H)
- Save replay buffer (Shift+R)
- Real-time stats monitoring
- Automatic recording control

### Usage
```python3
from modules.OBS_Integration import mark_highlight, save_replay_buffer

# Mark highlight during stream
mark_highlight("Clutch moment")

# Save replay buffer
save_replay_buffer("Amazing play")
```

## 📊 Monitoring & Output

### Generated Files
- `clips/` - Generated highlight clips
- `vertical_clips/` - TikTok-formatted clips
- `clip_rankings.json` - Virality scores and metrics
- `tiktok_session.json` - Upload queue and history

### View Rankings
```python
from modules.Clip_Ranker import get_top_clips

top_10 = get_top_clips(10)
for clip, data in top_10:
    print(f"{clip}: {data['score']:.1f}/100")
```

## 🎓 Advanced Usage

### Train Title Generator on Viral Titles
```python
from modules.AI_Title_Generator import train_on_titles

# Create a JSON file with successful titles
# [{"title": "This is insane", "views": 100000}, ...]
train_on_titles("viral_titles.json")
```

### Custom Highlight Detection
```python3
from modules.Gaming_Highlights import detect_victory

# Template matching for specific screen
victory_timestamps = detect_victory("gameplay.mp4")
```

### Batch Processing
```bash
# Process multiple recordings at once
python3 bot.py --batch recordings/
```

## 🐛 Troubleshooting

### OBS Not Connecting
- Check obs-websocket is installed in OBS
- Verify port 4455 is accessible
- Check password in OBS settings

### Low Highlight Detection
- Increase `highlight_sensitivity` in config
- Check video has clear audio
- Verify video codec is supported

### TikTok Upload Fails
- Verify credentials in .env
- Check file size < 287MB
- Ensure duration is 3-600 seconds
- Check internet connection

### Slow Processing
- Reduce video resolution before processing
- Disable audio transcription if not needed
- Process shorter clips
- Upgrade CPU/GPU

## 📈 Optimization Tips

1. **Better Highlight Detection**
   - Use gaming-specific detection with templates
   - Combine audio + visual analysis
   - Train on your game's UI elements

2. **Improved Title Generation**
   - Collect your best-performing titles
   - Train the model on viral titles
   - Customize templates for your game

3. **Better Clip Ranking**
   - Update with actual TikTok metrics
   - Train on viewer engagement
   - A/B test title variations

4. **Faster Processing**
   - Use GPU acceleration (CUDA/ROCm)
   - Batch process multiple clips
   - Cache detection results

## 🔐 Security Notes

- Store `.env` file securely (don't commit to git)
- Use app-specific passwords for TikTok
- Never share OBS password
- Rotate API keys regularly

## 📝 Log Files

All operations are logged with timestamps. Check the console output for:
- Processing status
- Detected highlights count
- Generated titles
- Virality scores
- Upload results

## 🚀 Next Steps

1. ✅ Set up folder watcher
2. ✅ Test highlight detection
3. ✅ Generate sample titles
4. ✅ Format for TikTok
5. ⏳ Configure TikTok credentials
6. ⏳ Set up OBS integration (optional)
7. ⏳ Deploy to production

## 📞 Support

For issues or improvements:
- Check troubleshooting section above
- Review module documentation in code
- Check configuration values
- Verify all dependencies installed

## 🎉 You're All Set!

Your streaming assistant is ready to:
- Detect highlights in real-time
- Generate AI titles
- Create viral clips
- Format for TikTok
- Rank content by engagement potential

Happy streaming! 🎮🚀
