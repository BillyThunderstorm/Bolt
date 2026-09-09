# OBS vertical canvas (Aitum)

Aitum Vertical is installed. Thunderstone already has a **1080×1920** canvas next to the 16:9 Twitch canvas. Do not create a second OBS profile or a second OBS window.

## What is live

| Horizontal scene | Linked vertical scene |
|---|---|
| Gaming | Vertical Gaming |
| Starting Soon | Vertical Starting Soon |
| Chatting | Vertical Chatting |
| BRB | Vertical BRB |
| Offline | Vertical Offline |

Stream Deck scene buttons still switch the **main** 16:9 scene. Aitum follows that switch on the 9:16 canvas.

- Main canvas: 1920×1080 → Twitch
- Aitum canvas: 1080×1920 → TikTok / Shorts / vertical record
- Vertical backtrack folder: `recordings/`
- Overlay HTML: `bolt overlay` → `http://127.0.0.1:8766/` (same Counter source; hidden on vertical until you show it)

## Why vertical clips looked like VHS

Bolt was not "bad at clipping." Three OBS + encode settings stacked:

1. **Twitch output is 1280×720.** Canvas is 1080p, but `OutputCX/CY` is 720p. Center-cropping that to 9:16 is a ~405px-wide strip, then upscaled to 1080×1920. Motion looks analog.
2. **Aitum vertical recordings are ~160 kbps.** `recording_match_main` is on and `record_encoder` is empty, so the native 1080×1920 file is unusable. A good 9:16 clip is 20–40 Mbps (see `media/vertical_clips/Wow.mp4`).
3. **Game Sound and Elgato Game are both in the mix.** `Game` (capture card) is at full volume on every track. `Game Sound` is at ~25%. Same audio twice = hollow / late game audio.

Bolt-side fix (2026-09-08): no unsharp, 720p sources use blur-fill instead of crop, already-9:16 files are not recropped, clip cuts use a working ffmpeg.

OBS still needs a one-time change before the next recording:

- **Vertical Gaming is missing the Game source.** Native `*-vertical*` files are black. In OBS, Vertical Scenes → Vertical Gaming → add **Game**, scale/crop it to fill 1080×1920, lock it. Turn **Game Sound** back on for that scene (it is currently hidden).
- Aitum Vertical → Recording: **uncheck Match main**, set encoder (Apple VT H.264), quality/bitrate around 12–16 Mbps
- OBS Settings → Video: keep canvas 1920×1080; if you want crop-style TikToks later, record at 1080p not 720p (stream can stay 720p)
- Mixer (horizontal): mute **Game** audio (keep the picture) **or** mute **Game Sound** — not both live

## If OBS will not stay open

On macOS 27, OBS 32.2.2 crashes in Chromium (`CreateBrowserSync`) if the Twitch Chat / Info / Stats / Feed **docks** restore at launch. Safe Mode does not help — those docks are first-party.

Fix already applied (2026-09-04):

- Browser hardware acceleration off (`BrowserHWAccel=false` in OBS `global.ini`)
- Saved dock layout cleared so those CEF docks do not auto-open
- Config backups: `~/Library/Application Support/obs-studio/backups/`

OBS itself, Thunderstone, Counter (browser **source**), Aitum, and Elgato/Camo are fine. Do not re-pin the Twitch browser docks until OBS ships a CEF build for this OS. Chat in a browser tab instead.

If it starts crashing on launch again: quit OBS, delete `DockState=` lines from `user.ini` and `basic/profiles/Bolt/basic.ini`, then reopen.

## If Start Streaming hangs

Twitch OAuth in OBS expires. Enhanced Broadcasting then sits on `GetClientConfiguration` and never connects. The stream key still works.

Fix already applied (2026-09-04): Enhanced Broadcasting off, OBS using the stream key (Twitch account disconnected in OBS). There is a **20 second stream delay** — Twitch dashboard lags that long after OBS says live.

To reconnect later: OBS **Settings → Stream → Connect Account (Twitch)**. Leave Enhanced Broadcasting off until that login works. Vertical still records locally.

## If the Vertical docks are missing

OBS menu **Docks** → enable **Vertical**, **Vertical Scenes**, **Vertical Sources**. A dock-layout reset also clears these — turn them back on.

## Tweak layout

1. Select the scene in **Vertical Scenes**.
2. Unlock the source in **Vertical Sources**.
3. Drag on the vertical preview (not the 16:9 preview).
4. Lock it again.

Cam hole empty = Camo is off. Game empty = Elgato is off. Same devices as the horizontal scene — do not add a second capture of the Elgato.

Art files: `App/overlay/theme/README.md`.
