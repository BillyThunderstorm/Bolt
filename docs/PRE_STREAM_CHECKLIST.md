# Bolt Pre-Stream Checklist

## What It Is

A pre-stream ritual that ensures you're ready before going live. Bolt shows you a checklist and you check items off by **saying them out loud** or **typing**.

## Default Tasks

| Task | Say/Type | Why It Matters |
|------|----------|----------------|
| Set up OBS — scenes, sources, audio levels | "obs", "scene", "audio" | Ensures your stream looks/sounds good |
| Set Twitch title and game category | "title", "twitch", "game" | Helps viewers find your stream |
| Check Streamlabs alerts are on | "streamlabs", "alerts", "donations" | Don't miss donation alerts |
| Review content plan for this session | "content", "plan", "review" | Stay focused, avoid dead air |
| Pick a TikTok clip idea to aim for | "tiktok", "clip", "idea", "viral" | Create clip-worthy moments intentionally |
| Announce the stream on socials | "tweet", "post", "announced", "social" | Drive traffic to your stream |
| Do a quick test stream check | "test", "check", "delay", "quality" | Catch technical issues before going live |

## How to Use

### Voice Mode (Hands-Free)

1. Run `python3 launch.py`
2. When checklist appears, say tasks out loud:
   - "OBS is good" → ✅ OBS setup
   - "Title set" → ✅ Twitch title
   - "Streamlabs on" → ✅ Streamlabs alerts
3. Bolt plays a sound and marks each task complete
4. When all done, Bolt congratulates you and continues launch

### Keyboard Mode (Default)

1. Run `python3 launch.py`
2. Type part of a task name and press Enter:
   - `obs` → ✅ OBS setup
   - `title` → ✅ Twitch title
   - `streamlabs` → ✅ Streamlabs alerts
3. Press Ctrl+C to skip and continue

## Configuration

### Enable/Disable Voice

In `config.json`:
```json
{
  "use_voice_checklist": false,  // Keyboard mode (recommended)
  "checklist_timeout_minutes": 15,
  "skip_checklist": false
}
```

### Skip Entirely

**Option 1:** Add to `config.json`:
```json
{
  "skip_checklist": true
}
```

**Option 2:** Use command-line flag:
```bash
python3 launch.py --no-checklist
```

### Customize Tasks

Edit `session_tasks.json` in the Bolt root directory:

```json
{
  "tasks": [
    {
      "id": "my_custom_task",
      "task": "My custom pre-stream task",
      "keywords": ["custom", "task", "keywords"],
      "done": false
    }
  ]
}
```

If the file doesn't exist, Bolt uses the default tasks.

## Progress Tracking

Checklist progress is saved to `logs/checklist_progress.json` after each session. This lets you:
- See which tasks you consistently skip
- Track your pre-stream routine over time
- Resume if Bolt crashes mid-checklist

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Checklist doesn't appear | Check `skip_checklist` is false in config.json |
| Voice not working | Default is keyboard mode; set `use_voice_checklist: true` to enable voice |
| Voice not recognizing me | Install dependencies: `pip3 install SpeechRecognition pyaudio --break-system-packages` |
| Task not matching | Say/type more keywords (e.g., "OBS setup done" instead of just "obs") |
| Want to skip mid-checklist | Press Ctrl+C to continue launch |

## Why This Exists

Most streamers skip pre-flight checks and regret it mid-stream. Bolt makes the checklist:
- **Fast** — voice means you can walk around and set things up while checking off
- **Frictionless** — no clicking, just talk or type
- **Consistent** — same routine every stream, so you never forget something important

---

*Created: June 15, 2026*
