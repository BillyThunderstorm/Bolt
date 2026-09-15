# My Diamond — Overlay Brief

Agent playbook for building and teaching the **My Diamond** overlay pack.
Separate from Storm Cast (Storm Cast stays the storm sting / cam experiments).

- **Owner taste:** William (Billy / SimplyBilly)
- **Teacher lane:** Edit Coach (Motion, Final Cut, Compressor, Pixelmator)
- **Last updated:** 2026-09-14 (America/Chicago)
- **Working folder (suggested):** `App/overlay/my-diamond/` (create when build starts)
- **Reference art:** `Desktop/Thunder_Diamonds/`, `App/overlay/theme/logo-diamond.png`

---

## 1. Vision

Looking from **inside a diamond**. Light hits the crystal and it shines different colors — alexandrite-like: shimmering pink, dazzling emerald, sparkling purple. Move “into” the diamond; scene moods can ride those colors.

- **Gameplay stays in the center** (main focus, always readable).
- **Border** of the scene carries the moving/shimmering color.
- Optional **backdrop** behind the crystal: starry space.
- Animated, loop-friendly overlays for **OBS**, viewed on **YouTube, Twitch, and Kick** live.
- Reactive flavor targets (later): Marvel Rivals, Wolverine, Halloween games — only after base loops exist.

---

## 2. Hard rules (non-negotiable)

1. **Gameplay center always readable.** Opening stings may be full-frame and bold; live/game overlays frame the edge/camera only — never wash out the main focus (lesson from Storm Cast).
2. **Dual output.** Every finished piece should land as:
   - **OBS-ready** local loop (and/or still) for scenes
   - **Final Cut Title / Motion template** (or reusable Motion project) when it’s an animated overlay
3. **Local-first reuse.** Prefer **looped scenes and animations** saved on disk under Bolt so they can be reused in other projects (clips, VODs, thumbnails). No one-off exports that only live inside a random library.
4. **Never post** without William’s approval. TikTok-first for clip pipeline.
5. **Product-review / Amazon week is paused** — do not assign product-review overlay work.
6. **Pull William for taste** on color intensity, “inside the diamond” feel, corner roundness, and HUD placement.
7. Teach **one skill at a time** on real Bolt media — no syllabus dumps.

---

## 3. Deliverables

### Pack name

**My Diamond**

### OBS scenes (color → use)

| Scene key | Color name | Use |
|-----------|------------|-----|
| Game | **White** | Live gameplay — center clear, diamond border only |
| BRB | **Blue** | Be right back |
| Starting | **Pink** | Starting soon |
| Chatting | **Yellow** | Just chatting |
| Offline / Ending | **Black** | Offline / end screen |

### Layout requirements

Each UI piece uses a **different diamond cut** so the pack reads as a crystal set, not one repeated frame:

| Piece | Shape language |
|-------|----------------|
| **Scene border** | Large faceted **kite / brilliant** diamond frame around gameplay |
| **Webcam** | Soft-rounded **square cushion** cut (curved corners, not hard 90°) |
| **Social + Username** | Small **baguette / emerald-cut** plaques |
| **Death tracker** | Twin **emerald-cut** gems — left = times defeated, right = times defeated others |
| **Game name** | Elongated **marquise / baguette** bar |
| **Alerts** | Compact **brilliant-cut** spark (short sting, not a full wash) |

- Reserve safe zones; don’t cover typical game HUD.
- Labels / HUD slots: social media, username, interactive death tracker (in + out), game name, alert placement.

### Outputs per scene (minimum)

- Looped animation and/or still, local under `App/overlay/my-diamond/` (or `theme/` when promoted)
- OBS-ready at **1920×1080** ( Motions may be authored 1280×720 then stretch / export to canvas — match existing Thunder Diamonds theme pack practice)
- Where animated: Motion source + published FCP Title (or clear note why still-only)

### Related but separate

- **Storm Cast** (`Storm_Cast_Ring.motn`, FCP Title `Bolt/Storm Caast Ring`) — storm sting / experiments. Do **not** merge into My Diamond; may steal art lessons only.

---

## 4. Acceptance tests

A deliverable is done when:

1. At **100% opacity**, gameplay (or webcam) in the **center remains fully readable** — no heavy wash.
2. Border/shimmer reads as diamond/crystal, not a full-frame takeover (except intentional stings/starting cards).
3. Webcam frame is **rounded soft square**, not sharp 90° corners.
4. Label slots exist for social, username, death tracker (in + out), game name, alerts — and don’t collide with typical Marvel Rivals / shooter HUDs (taste check with William).
5. Loops **cleanly in OBS** on YouTube/Twitch/Kick canvas (1920×1080).
6. Files are **saved locally** in Bolt and reusable in FCP / other projects.
7. Dual output present (OBS asset + Motion/FCP where animation applies).

---

## 5. Palette (working — from Thunder Diamonds + counter accents)

You do **not** need to invent hex. Start here; William can nudge after first Motion pass.

| Role | Name | Hex | Source note |
|------|------|-----|-------------|
| Game border / crystal light | Ice white | `#D8E4F0` | Sampled light facets |
| BRB | Deep diamond blue | `#182454` | Dominant Thunder Diamonds blue |
| Starting | Alexandrite pink | `#B4909C` | Sampled pink facet |
| Chatting | Soft gold / yellow | `#F0C75E` | Match existing wins accent in counter |
| Offline / Ending | Void black | `#070B16` | Counter dark bg family |
| Accent emerald | Soft emerald | `#B4D8C0` | Sparse in art — boost in Motion |
| Accent purple | Facet purple | `#6C5484` | Sampled purple |
| Tracker “defeated others” | Cyan spark | `#5EE7FF` | Existing `--kills` in thunder-diamond-counter |
| Tracker “times defeated” | Gold spark | `#F0C75E` | Existing `--wins` (remap labels in My Diamond) |

Eyedrop later in Pixelmator if a specific Thunder Diamonds still should override a row.

---

## 6. “Reacts” (define before building)

Do **not** invent game hooks. Default build order is **manual OBS scenes + loops** first.

| Trigger idea | Meaning | Status |
|--------------|---------|--------|
| OBS scene switch | Pink / Blue / White / Black by scene | **Primary** |
| Stream Deck | Manual color / sting | Optional |
| Bolt / game detect | Marvel Rivals, Wolverine, Halloween | **Later** — needs explicit trigger design |
| Death tracker | Increment defeated / defeated-others | **Reuse existing local counter** (see §10) — Stream Deck + browser source |

---

## 7. Build order (agents)

1. Still diamond plate + **transparent center** (prove gameplay shows through).
2. Soft-square webcam frame (curved corners).
3. Color-shift **border loop** for White / Pink / Blue / Black scene variants.
4. Label / HUD placeholder layout (social, username, death tracker, game name, alerts).
5. Publish: OBS loops + Motion/FCP templates; save under Bolt.
6. Reactive variants last (Rivals / Wolverine / Halloween).

---

## 8. Taste gates (stop and ask William)

- How “inside the diamond” should feel (depth vs flat frame)
- Pink / emerald / purple intensity
- Yellow chatting intensity vs BRB blue
- Death tracker look (minimal vs flashy)
- Whether starry backdrop is on for Game or only Starting/BRB/Offline

---

## 9. Open questions

- Fine-tune hex after first Motion pass (William taste)

---

## 10. Death tracker data source (decided default)

William does not need a new invention. Bolt already has a local counter:

| Piece | Path |
|-------|------|
| Browser UI | `App/overlay/theme/thunder-diamond-counter.html` |
| Local URL | `http://127.0.0.1:8766/thunder-diamond-counter.html` |
| Stream Deck | `scripts/streamdeck/overlay_kill.sh`, `overlay_win.sh`, minus/reset variants |
| State | Browser localStorage key `thunder-diamond-counter-state` |

**My Diamond mapping (labels only at first):**

- Existing **kills** (`#5EE7FF`) → **defeated others**
- Existing **wins** (`#F0C75E`) → **times defeated** *(or swap if William prefers the opposite — taste gate)*

**How it works in OBS:** Browser Source pointing at that URL; Stream Deck bumps counts; optional flash on `thunder-diamond-cam.html` ring.

**Later (optional):** auto-read from Marvel Rivals / other games — only after manual Stream Deck loop feels right.

**Not default:** inventing a game API or OCR pipeline on day one.
