# Thunder Diamonds — OBS theme pack

Clear names for the chosen art in `Desktop/Thunder_Diamonds`.
Videos are local-only (git ignores `.mp4`).

Path: `/Users/carter/developer/Bolt/App/overlay/theme/`

## Scenes (Image or Media Source, stretch to 1920×1080)

| OBS scene | File | Notes |
|---|---|---|
| Starting Soon | `starting-soon.mp4` | Media Source, **Loop** on, mute. Fallback: `starting-soon.jpg` |
| Be Right Back | `brb.jpg` | |
| Offline / End | `offline.jpg` | |
| Just Chatting | `chatting.jpg` | Webcam on top |
| Gaming | `live-frame.jpg` **on top of** game capture | Color Key the dark center so gameplay shows through |
| Optional live sting | `live-intro.jpg` | Full-screen LIVE card, not over gameplay |

## On the gaming scene (layer order, bottom → top)

1. Game capture
2. Webcam
3. `cam-ring.png` (or `cam-ring-wide.png`) — same size/position as the webcam. Already transparent.
4. `live-frame.jpg` — Color Key the hole
5. Kill/win badges from `bolt overlay` (optional)

`cam-ring.mp4` is the looping ring if you want motion on the cam later (needs a color key on the black hole; `cam-ring.png` is easier today).

## Alerts (Streamlabs / StreamElements image, or a hidden OBS source)

- `alert-follower.jpg`
- `alert-subscriber.jpg`
- `alert-donation.jpg`

`logo-diamond.png` is the isolated lightning diamond (transparent). `background-storm.jpg` is an unlabeled storm plate if you need a spare background.

Spline / Rive / Motion interactivity can replace these stills later without changing the scene names.

## Vertical (Aitum, 1080×1920)

Thunderstone collection. Plugin: Aitum Vertical (`vertical-canvas`). Canvas is **1080×1920**. Horizontal scene switches also switch the matching vertical scene.

| Horizontal | Vertical | Layout |
|---|---|---|
| Gaming | Vertical Gaming | Game 16:9 on top, Camo + `cam-ring.png` below, storm plate behind |
| Starting Soon | Vertical Starting Soon | Full 16:9 card centered on storm (no side-crop of the title) |
| Chatting | Vertical Chatting | 16:9 chatting card on top, cam + ring below |
| BRB | Vertical BRB | Full 16:9 card centered on storm |
| Offline | Vertical Offline | Full 16:9 card centered on storm |

Kill/win `Counter` is in Vertical Gaming but **hidden**. Camo must be running or the ring hole is empty. Unlock a source in the **Vertical Sources** dock to nudge it.

Backtrack (vertical replay) writes to `recordings/`. Twitch stays 16:9 on the main canvas. Use the Vertical dock’s record / backtrack for TikTok-ready 9:16.
