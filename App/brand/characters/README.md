# Bolt character references

Working design lock for the companion avatar track (not the channel logo).

## Decision (2026-08-10)

| Role | Primary | Notes |
|------|---------|--------|
| **Bolt** | Bearded, glasses, navy + gold lightning suit | Canon still: `bolt/bolt_canon_app_icon.png` (same art as `App/assets/app_icon.png`) |
| **Puppy (pet)** | **White robotic puppy** (lane A) | Primary companion form — cute, rounded, cyan eyes, gold bolt mark |
| Soft puppy / hybrid | Kept as **reference only** | Adorable; may inform future “rest day” or plush variants |

Brand wings / storm mark stay separate: see `../BRAND_VISION_DESCRIPTION.md` (studio mark ≠ Bolt the teammate).

## Files

### Bolt
- `bolt/bolt_canon_app_icon.png` — locked face/body for the teammate
- `bolt/bolt_with_puppy_robo.jpg` — Bolt + robotic puppy together

### Puppy
- `puppy/puppy_robo_expression_sheet.jpg` — **primary** form (sitting, curious, bounce, sleep)
- `puppy/puppy_soft_tech_reference.jpg` — soft living puppy + light tech (collar/LED) — **reference, not primary**

## Relationship

- **Bolt** = words, advice, queue help, personality voice
- **Puppy** = presence, reactions, random desktop “someone walked in”
- Scale: puppy roughly knee-high to standing Bolt
- Colors: white / soft cream + gold bolt + cyan glow (don’t steal full rainbow wings for the pet)

## Names (locked + optional)

| Name | Status | Who |
|------|--------|-----|
| **Thunder & Lightning** | **LOCKED** — the duo | Bolt + Lightning when they appear together |
| **Bolt** | Locked | Teammate (product name stays `bolt`) |
| **Lightning** | **LOCKED** — the puppy | White robotic pet; solo call-name |
| **Billy / Thunderstorm** | Locked | Creator + channel |

### Duo

When both show up (desktop pop, overlay, briefing art):

> **Thunder & Lightning**

### Solo

- **Bolt** — words, advice, voice, CLI  
- **Lightning** — reactions, presence, random desktop pops  

Mapping: Lightning = small + sharp; Bolt = warmer thunder that follows. Duo name still **Thunder & Lightning**.

### UI poses (Lightning) — ready

All under `puppy/poses/` (`.png` + `.jpg` of each):

| File | Mood | Use when |
|------|------|----------|
| `lightning_idle` | Sitting, friendly default | Waiting / default bubble |
| `lightning_alert` | Ears up, bright eyes | Peak window, needs attention |
| `lightning_happy` | Mid-bounce, spark tail | Post succeeded, win, celebration |
| `lightning_sleep` | Curled up, eyes closed | Off-peak / quiet / “come back later” |

Primary form: white robotic pup, cyan eyes, gold bolt collar tag, lightning-tip tail.  
Sheet + soft refs still in `puppy/` for redesign.

## Next (when ready)

1. Optional: short loop for “random appear”
2. Presence surface (menu bar / overlay / decide-mode decoration)
3. Wire pose → event map in companion UI
