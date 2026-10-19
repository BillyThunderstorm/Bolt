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
| `Data/configs/scene_game_mapping.json` | Maps OBS scene names → game titles |
| `Core/modules/Stream_Monitor.py` | Scene change detection + READY `bolt obs` |
| `scripts/update_game_from_obs.py` | Engine: scene→`Core/config.json` game update |
| `Core/modules/OBS_Game_Tracker.py` | Soft-fail CLI (`bolt obs-game`) — PARTIAL |

---

## Setup Steps

### 1. Edit the Scene Mapping

Open `Data/configs/scene_game_mapping.json` and add your OBS scenes:

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

**Preferred: soft-fail CLI (PARTIAL)**
```bash
bolt obs-game status            # readiness (engine + mapping + config)
bolt obs-game status --json     # machine-readable
bolt obs-game status --probe    # short OBS WebSocket probe (soft-fail, no hang)
bolt obs-game list              # checklist rows
bolt obs-game run --once        # dry readiness (no long connect)
bolt obs-game run               # foreground loop (Ctrl+C stops)
bolt obs-game run --background  # spawn via scripts/start_obs_game_tracker.py
```
Soft-fail prefix: `Game tracker unavailable:`. Distinct from READY `bolt obs` (WebSocket status).

**Option A: Run standalone engine**
```bash
python3 scripts/update_game_from_obs.py
```

**Option B: Add to launch.py** (optional)

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
→ Add 'New Game' to Data/configs/scene_game_mapping.json to enable auto-tracking.
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

## Staleness and refresh (`bolt game`, 18 Oct 2026)

`game` once stayed on "007 First Light" for a month: it only changed on a scene switch or a Twitch
fetch, and the Live Scene can be pinned to a fixed name. Now:

- `Data/configs/game_state.json` records when the game was last **confirmed** (Twitch, `bolt game set`,
  or a non-live scene) vs merely **checked** (pinned Live Scene).
- Refresh runs at `bolt launch` (stream start), at tracker start, and on OBS stream start.
- `bolt game status` also asks Twitch (when the Live Scene follows `__twitch__`) and prints DRIFT if the config game
  differs from the channel category (`--no-twitch` skips). READY since 18 Oct 2026.
- `bolt game status`, `bolt obs-game status`, and `bolt doctor` warn when the last confirmation is
  older than `game_stale_days` (default 7).
- Pinned Live Scene wins over Twitch, but refresh warns when Twitch's category differs.
  Fix with `bolt game set "<Game>" --pin` or follow Twitch with `bolt game unpin`.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Scene changes not detected | Check OBS WebSocket is enabled (Tools → WebSocket Server Settings) |
| Wrong game being set | Verify scene name matches exactly (check for spaces, capitalization) |
| Config not updating | Check file permissions on Core/config.json |
| No notifications | Ensure OBS_PASSWORD is set in .env |

---

*Created: June 15, 2026*
