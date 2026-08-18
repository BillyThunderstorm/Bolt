# Bolt: System Architecture & Operation Manual

**Version 2.0 · August 15, 2026**

This is the purpose-and-shape document for Bolt. It is not the command list.

**Commands live in one place:** `Core/modules/BOLT_COMMANDS.md`

---

## Purpose

Bolt is William’s (Billy / SimplyBilly) **local-first AI teammate**: a content manager and business assistant for a real creator business.

It is **not** a Twitch clip bot with extra features bolted on. The clip pipeline is one subsystem. The job is bigger: help William create, learn, test, post, and grow a sustainable creative life.

Every feature, decision, and warning is filtered through that goal.

If uncertain, Bolt asks:

> Will this help William grow, create, learn, or succeed?

**Decision priority:** Safety → Truth → Long-Term Benefit → Helpfulness → Efficiency → Entertainment.

**Posting always requires William’s approval.** Nothing publishes because a file landed in a folder.

---

## Why Bolt exists

William is building a creator business while learning to code. The blockers are friction, decision paralysis, and overwhelm — not a lack of ideas.

Bolt’s job is to:

- Turn recordings, tests, and ideas into work that can actually ship
- Make the next step obvious (one step, not five)
- Remember what worked, what was held, and why
- Protect creative health (Safety first)
- Keep the full creator picture intact when one lane gets loud

Gaming is one strong lane. It is not the whole mission.

---

## Creator lanes

**Priority now:** games + tech testing / reviews.

**Expansion:** general product testing, Amazon Influencer storefront (`billycarter-20`), beauty / skincare, AI development learned in public, and building Bolt itself.

| Platform | Handle | Role |
|---|---|---|
| TikTok | @itssimplybilly | Primary short-form |
| Twitch | ItsSimplyBilly | Live source material |
| YouTube | @SimplyBilly | Shorts now, long-form later |
| X | @SimplyBilly_ | Presence / takes |
| Amazon Influencer | tag `billycarter-20` | Storefront + affiliate |

A strong idea needs at least one of: a real gameplay moment, an honest reaction, a useful lesson, a product/game observation, a visible test result, or a learning-in-public beat.

---

## What Bolt is — and is not

**Bolt is:**

- A local CLI (`bolt`) plus voice, Twitch chat, and a checkup dashboard
- A daily production OS: brief → decide the queue → post
- A clip factory with a hard candidate cap and a ranked ready-queue
- A catalog / storefront / sponsor / research / mission planner
- A memory system that learns from what actually posted

**Bolt is not:**

- An auto-poster that skips review
- A Discord-first bot
- A gaming-only clip factory
- Calendar theater or fake productivity
- A system that treats every saved moment as post-worthy

---

## Personality

**Sources:** `Data/context/bolt-personality.md` (persona) · `Core/bolt_brain.md` (creator profile)

Bolt is cheerful, useful, and honestly blunt. He is allowed to challenge William when safety, burnout, waste, or long-term goals are at risk.

Day-to-day operational voice is **direct, specific, and grounded** in real footage or tests. No fake hype. No “this is insane.” Explain *what* and *why*. Give one next step.

---

## How the system is organized

| Root | Role |
|---|---|
| `Core/` | Runtime, modules, config, brain |
| `Data/` | Queue state, memory, catalogs |
| `media/` | Recordings, intermediate clips, vertical exports |
| `Docs/` | Status, guides, briefings |
| `bin/bolt` + `bolt_cli/` | CLI entry (`uv run bolt`) |
| `App/` | UI, brand, sites |

**Two stores stay separate:**

| Path | Role |
|---|---|
| `media/Recordings/` | Source VODs |
| `media/clips/` | Intermediate / horizontal cuts |
| `media/vertical_clips/` | 9:16 files only — **not** the approval surface |
| `Data/ready_to_post.json` | Ready-queue **state** (title, score, status, schedule, approval) |

Editing or renaming a file under `media/vertical_clips/` does **not** enqueue or approve it. Hand-edited finals must be registered with `bolt queue add`.

---

## Day-to-day operating loop

Preferred production path:

1. `bolt day --decide`
2. Review the next postable clips
3. Approve for peak, hold with a reason, or post now
4. If you posted outside Bolt, `bolt queue mark-posted`

| Command | Meaning |
|---|---|
| `bolt setup` | Finite readiness check (config / keys). Prints “Setup complete” and **exits**. Does not start live watch. |
| `bolt launch` | Long-running live watcher |
| `bolt day` | Morning brief + next clip. `--decide` runs queue review. `--quiet` for non-interactive use. |
| `bolt queue decide` | Interactive review: open / approve / post now / hold / retitle / skip |

Commands: `Core/modules/BOLT_COMMANDS.md`

---

## Clip pipeline

Trigger: new or processed files in `media/Recordings/`.

1. **Detect** — `Highlight_Detector` (energy + prominence, min-gap, hard candidate cap)
2. **Cap** — `max_highlight_candidates` (default 12) **before** any cutting
3. **Cut** — `Clip_Generator` → `media/clips/`
4. **Dedup** — against seen-clips / hash db
5. **Rank** — `Clip_Ranker` (quality tiers + recency-weighted learned boost)
6. **Enrich** — titles, subtitles, vertical 9:16 → `media/vertical_clips/`
7. **Queue** — rows in `Data/ready_to_post.json`
8. **Review** — `bolt queue decide` (approve / hold / post now / skip)
9. **Learn** — performance outcomes feed the ranker

Caps matter. Uncapped long VODs explode into hundreds of spikes and hang the machine.

**Quality tiers** (`Core/config.json`):

- Below 60: discard
- 60–64: keep on disk, no queue
- 65–79: format and queue
- 80+: queue and alert at peak hours

**Peak windows** (America/New_York): 7–9 AM, 12–2 PM, 7–10 PM. About 30 minutes of review before peak.

Twitch chat: `!queue`, `!qstatus`, `!postnow [id]`, `!dontpost [id] <reason>`, `!skip`.

---

## Decision, memory, and planning

- **`Think_Learn_Decide`** is the canonical reasoning path. `Brain_Controller` is a compatibility wrapper.
- **`Memory_Index`** builds a local searchable index from markdown memory, queue/history, decisions, and posted performance.
- Vector enrichment uses local Ollama (`nomic-embed-text`). If Ollama is down, skip fast — do not hang.
- **Researcher** (`bolt research`) helps answer “what should I be known for?” C5 keep/drop is always William’s call.
- **Content Manager** (`bolt manage` / `store` / `social` / `sponsors`) is the creator OS for tests, drafts, storefront, and pitches.
- **Creator Command Center** (`bolt mission`) turns a goal into a printable plan. Planning only — nothing posts or purchases without approval.

---

## Interfaces

| Interface | How |
|---|---|
| CLI | `bolt …` (`uv run bolt` or the `.venv` alias) |
| Voice | `bolt voice` / `bolt talk` / `bolt say` — Siri Voice 3 (`say -v "Voice 3"`). Mac alerts use the same voice. |
| Reminders | List **Bolt** — `bolt briefing --send` at 17:00 writes action items + a link to the briefing file |
| Shortcuts | Bolt Morning, Review Queue, Stats, Wrap-Up; Extract Text from Photos (editable `.txt`) |
| Twitch chat | Queue and post controls on the live bot |
| Dashboard | `Checkup_Writer` → `Data/Bolt_data.js` |
| Sites | bolt.billythunderstorm.us · billythunderstorm.us · billythunderstorm.live |

Voice **does** run: day kickoff, queue status, approve/hold/post next, budget, storage one-liner, research/mission status.

Voice **does not** run: recordings processing, TikTok OAuth, queue add/retitle, setup, site deploy. Full queue review stays in the terminal (`bolt queue decide` / `bolt day --decide`).

---

## LLM and cost

Light mode by default (`BOLT_LLM_MODE=light`).

- **Ollama** for chat, titles, everyday status
- **Grok API** only for high-value strategy / research / decisions
- SuperGrok subscription is app/web chat only — it does **not** cover the API
- Soft cap **$35/month** → force local when hit
- Alerts via Mac banner + Voice 3 + iMessage + email. **No Discord.**
- Only financial work is fully manual. Everything else is do-and-notify (alert or file link to review/revise).

---

## How to run

```bash
alias bolt='/Users/carter/developer/Bolt/.venv/bin/bolt'

bolt setup              # one-shot readiness; exits
bolt day --decide       # daily production path
bolt launch             # live folder-watch
bolt queue              # what you can post
bolt help               # command summary
bolt verify             # files, folders, config, env
bolt test               # test suite
```

From the repo without the alias: `uv run bolt <command>`.

---

## Owner note

Update this document when the **purpose**, the **daily operating loop**, or `process_recording` changes.

Do not grow this file into a second command sheet. Keep commands in `Core/modules/BOLT_COMMANDS.md`.
