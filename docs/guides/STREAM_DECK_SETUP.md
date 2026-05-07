# 🎮 BillyandRandyGaming — Stream Deck Setup Guide
## Stream Deck MK.2 / Standard (15 buttons, 5×3)

---

## Button Layout

```
┌─────────────┬─────────────┬─────────────┬─────────────┬─────────────┐
│  1          │  2          │  3          │  4          │  5          │
│  ⚡️         │  💾         │  🔴         │  🎬         │  🎥         │
│  Launch     │  Save       │  Go Live /  │  Scene:     │  Scene:     │
│  Bolt       │  Replay     │  End Stream │  Gaming     │  Just Chat  │
├─────────────┼─────────────┼─────────────┼─────────────┼─────────────┤
│  6          │  7          │  8          │  9          │  10         │
│  ☕         │  🎬         │  🔇         │  ⚡         │  📊         │
│  Scene:     │  Scene:     │  Mute /     │  Process    │  Queue      │
│  BRB        │  Starting   │  Unmute Mic │  Recording  │  Status     │
├─────────────┼─────────────┼─────────────┼─────────────┼─────────────┤
│  11         │  12         │  13         │  14         │  15         │
│  🏁         │  🤫         │  📢         │  🔁         │  ⏹         │
│  Scene:     │  Shh Game   │  Clip Alert │  Replay     │  Stop       │
│  End Screen │  (Game Mute)│  Sound      │  Buffer On  │  Bolt       │
└─────────────┴─────────────┴─────────────┴─────────────┴─────────────┘
```

---

## Step-by-Step Setup in Stream Deck App

### FIRST: Install Required Plugins
Open Stream Deck app → click the **≡ icon** (bottom right) → **Plugin Store**

Install these (all free):
- ✅ **OBS Studio** (by Elgato) — for scenes, stream control
- ✅ **System** (already built in) — for running scripts
- ✅ **Audio Mixer** (by Elgato) — for mic mute toggle

---

### Button 1 — 🦊 Launch Bolt
1. Drag **System → Open** onto button 1
2. Set **App/File** → browse to:
   `~/Desktop/Bolt/streamdeck_scripts/Bolt_launch.sh`
3. Label: `Bolt`
4. Icon: Use your Bolt Cleopatra logo (`~/Desktop/Bolt/Bolt_icon.png`)

---

### Button 2 — 💾 Save Replay Now
1. Drag **System → Open** onto button 2
2. Set **App/File** →
   `~/Desktop/Bolt/streamdeck_scripts/Bolt_save_replay.sh`
3. Label: `Save Clip`

> **Tip:** This saves the OBS replay buffer AND sends a macOS notification
> confirming the save. Bolt picks it up automatically.

---

### Button 3 — 🔴 Go Live / End Stream
1. Drag **System → Open** onto button 3
2. Set **App/File** →
   `~/Desktop/Bolt/streamdeck_scripts/obs_toggle_stream.sh`
3. Label: `Stream`

> This script checks if you're live and toggles — one button does both.

---

### Button 4 — 🎮 Scene: Gaming
1. Drag **OBS Studio → Switch Scene** onto button 4
2. Set **Scene** → the name of your main gameplay scene in OBS
   (e.g. "Gaming", "Gameplay", "Marvel Rivals")
3. Label: `Gaming`

---

### Button 5 — 💬 Scene: Just Chatting
1. Drag **OBS Studio → Switch Scene** onto button 5
2. Set **Scene** → your Just Chatting / cam scene name
3. Label: `Chat`

---

### Button 6 — ☕ Scene: BRB
1. Drag **OBS Studio → Switch Scene** onto button 6
2. Set **Scene** → your BRB / Be Right Back scene
3. Label: `BRB`

---

### Button 7 — 🎬 Scene: Starting Soon
1. Drag **OBS Studio → Switch Scene** onto button 7
2. Set **Scene** → your starting soon / waiting screen scene
3. Label: `Starting`

---

### Button 8 — 🔇 Mute / Unmute Mic

> ⚠️ **Skip the Audio Mixer plugin** — it only works with Elgato Wave mics,
> not MacBook audio or most third-party mics. Use OBS directly instead.

**Option A — Mute inside OBS (recommended for streaming):**
1. Drag **OBS Studio → Mute/Unmute** onto button 8
2. Set **Source** → your microphone source name in OBS
   (check your OBS Audio Mixer panel at the bottom for the exact name —
   usually "Mic/Aux", "MacBook Microphone", or your mic's name)
3. The button lights up red when muted ✅
4. Label: `Mic`

**Option B — Mute the whole Mac system mic (affects all apps):**
1. Drag **System → Open** onto button 8
2. Set **App/File** →
   `~/Desktop/Bolt/streamdeck_scripts/toggle_mic_mute.sh`
   (this script is in your streamdeck_scripts folder)
3. Label: `Mic`

Option A is better for streaming — it only mutes what your audience hears
and leaves your Discord/headphone audio untouched.

---

### Button 9 — ⚡ Process Recording
1. Drag **System → Open** onto button 9
2. Set **App/File** →
   `~/Desktop/Bolt/streamdeck_scripts/Bolt_process_latest.sh`
3. Label: `Process`

> Use this after a stream ends to manually kick off Bolt's pipeline on
> your latest recording. Generates clips, ranks them, queues for TikTok.

---

### Button 10 — 📊 Queue Status
1. Drag **System → Open** onto button 10
2. Set **App/File** →
   `~/Desktop/Bolt/streamdeck_scripts/Bolt_queue_status.sh`
3. Label: `Queue`

> Sends a notification showing how many clips are queued and when
> the next one posts.

---

### Button 11 — 🏁 Scene: End Screen
1. Drag **OBS Studio → Switch Scene** onto button 11
2. Set **Scene** → your end screen / outro scene
3. Label: `End`

---

### Button 12 — 🤫 Shh Game
- **Action:** Audio Device Mute Toggle
- **Source:** Game capture card audio source in OBS
- **Label:** `Shh Game`

> Disables/enables the game audio going to your stream without stopping
> the capture itself. Perfect for when you need to talk to chat, take
> a call, or just want a quiet moment on stream without cutting your mic.
> Your game keeps running — only the sound being broadcast is toggled.

---

### Button 13 — 📢 Clip Alert Sound
1. Drag **System → Open** onto button 13
2. Set **App/File** → `/usr/bin/afplay`
3. Set **Arguments** → `/System/Library/Sounds/Glass.aiff`
4. Label: `Alert`

> Optional — play a sound to signal to chat that a clip was just saved.

---

### Button 14 — 🔁 Replay Buffer Toggle
1. Drag **OBS Studio → Start/Stop Replay Buffer** onto button 14
2. Label: `Buffer`

> If your replay buffer ever stops, this restarts it with one button.

---

### Button 15 — ⏹ Stop Bolt
1. Drag **System → Open** onto button 15
2. Set **App/File** →
   `~/Desktop/Bolt/streamdeck_scripts/Bolt_stop.sh`
3. Label: `Stop Bolt`

---

## Important: Allow Scripts to Run

The first time you press any Bolt button, macOS will block the script.
Do this once to allow it:

```
System Settings → Privacy & Security
→ scroll down → click "Allow Anyway" next to the script name
```

Or run this in Terminal once to pre-approve all scripts:

```bash
cd ~/Desktop/Bolt
xattr -cr streamdeck_scripts/
```

---

## Scene Names Cheat Sheet

Open OBS → look at your **Scenes** panel (bottom left).
Write down your exact scene names and match them to buttons 4, 5, 6, 7, 11.
They are case-sensitive.

| Button | What to set |
|--------|-------------|
| 4 | Your main gameplay scene name | Live Scene
| 5 | Your face-cam / just chatting scene name | Chatting Scene
| 6 | Your BRB scene name | Intermission Scene
| 7 | Your starting soon scene name | Starting Scene
| 11 | Your end screen scene name | Ending Scene

---

*Made for BillyandRandyGaming × Bolt ⚡️*
