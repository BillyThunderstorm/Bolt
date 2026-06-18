# OBS Auto-Game Tracking Setup

## What This Does

When you switch scenes in OBS, Bolt automatically updates `config.json` with the correct game title.

**Example:**
- You switch OBS scene from "Marvel Rivals" to "Deadlock"
- Bolt detects the scene change via OBS WebSocket
- Bolt updates `config.json`: `"game": "Deadlock"`
- All future clips and performance logs use "Deadlock" automatically

---

## Files Created

| File | Purpose |
|------|---------|
| `configs/scene_game_mapping.json` | Maps OBS scene names → game titles |
| `modules/Stream_Monitor.py` | Updated with scene change detection |
| `scripts/update_game_from_obs.py` | Standalone runner for game tracking |

---

## Setup Steps

### 1. Edit the Scene Mapping

Open `configs/scene_game_mapping.json` and add your OBS scenes:

```json
{
  "scenes": {
    "Marvel Rivals": "Marvel Rivals",
    "Hades 2": "Hades 2",
    "Deadlock": "Deadlock",
    "Just Chatting": "Just Chatting",
    "Starting Soon": "Just Chatting",
    "BRB": "Just Chatting"
  }
}
```

**Important:** Scene names must match OBS **exactly** (case-sensitive).

### 2. Start the Game Tracker

**Option A: Run standalone**
```bash
python3 scripts/update_game_from_obs.py
```

**Option B: Add to launch.py** (recommended)

Add this to `launch.py` after OBS connects:
```python
from scripts.update_game_from_obs import start_game_tracker
start_game_tracker()
```

### 3. Test It

1. Start the tracker
2. Switch scenes in OBS
3. Watch for notifications:
   ```
   ℹ Scene changed to 'Deadlock' → Game: Deadlock
   ✓ Updated config.json: game = 'Deadlock' (was 'Marvel Rivals')
   ```

---

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│  1. You switch OBS scene to "Deadlock"                     │
│  2. OBS sends CurrentProgramSceneChanged event             │
│  3. Stream_Monitor receives event                          │
│  4. Looks up "Deadlock" in scene_game_mapping.json         │
│  5. Finds mapping → "Deadlock"                             │
│  6. Updates config.json: "game": "Deadlock"                │
│  7. Notifies you via Bolt                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Unmapped Scenes

If you switch to a scene that's **not** in the mapping:

```
ℹ Scene changed to 'New Game' (no game mapping)
→ Add 'New Game' to configs/scene_game_mapping.json to enable auto-tracking.
```

Bolt keeps the current game setting — it doesn't guess.

---

## Integration Points

The `on_game_changed` callback is available if you want to:

- Log game changes to a history file
- Trigger game-specific memory loading
- Send a notification when games change
- Auto-start game-specific overlays

Example:
```python
from modules.Stream_Monitor import StreamMonitor

monitor = StreamMonitor(
    on_game_changed=lambda game: print(f"Now playing: {game}")
)
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Scene changes not detected | Check OBS WebSocket is enabled (Tools → WebSocket Server Settings) |
| Wrong game being set | Verify scene name matches exactly (check for spaces, capitalization) |
| Config not updating | Check file permissions on config.json |
| No notifications | Ensure OBS_PASSWORD is set in .env |

---

*Created: June 15, 2026*
