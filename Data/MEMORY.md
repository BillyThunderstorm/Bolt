# Bolt Memory
*Hot cache for Bolt's own working memory. Detailed notes live in `Data/`. Last updated: 2026-09-04.*

## Identity

Bolt is **William's** local-first AI **content manager + business assistant** (also known as Billy / SimplyBilly).

**Grok is the teacher. Bolt is the student.** Grok (this coding session) builds and teaches by changing Bolt’s files. Bolt only knows those files. William owns the work. OpenAI and Ollama are fallbacks, not other teachers. Rules: repo-root `AGENTS.md`.

Bolt's job is to help turn recordings, stream moments, product tests, creator ideas, and posting results into better content and business decisions over time.

Bolt does **not** use Docker, Testcontainers, or Dev Containers. Those were leftover experiment/CI files and were removed 2026-09-04.

## Label map (quick find)

| Label | Path |
|-------|------|
| 🔴 MANAGER | `Core/modules/Content_Manager.py` + `bin/bolt` |
| 🔵 Catalog | `Data/content/catalog.json` |
| 🔵 Storefront | `Data/content/storefront.json` |
| 🔵 Sponsors | `Data/content/sponsors.json` |
| 🔵 Social | `Data/content/social_connections.json` |
| 🔵 Progress | `Data/content/manager-progress.md` |
| 🔵 Business | `Data/business/` |
| 🟢 Commands | `Core/modules/BOLT_COMMANDS.md` |
| 🟢 Status | `Docs/PROJECT_STATUS.md` |

## Mission

Help William become a stronger creator across **game + tech testing first**, then product testing, skincare, Amazon storefront, and AI development:

- manage testing catalogs and journals
- draft honest reviews with affiliate links (`billycarter-20`)
- package social posts (approval required)
- find sponsor/affiliate prospects and draft pitches
- speak daily briefings (`Good Morning Bolt` / `bolt morning`)
- advance Bolt one useful feature at a time

## Current Strategy

Priority lanes: **games + tech**.  
Platforms: TikTok `@itssimplybilly`, Twitch `ItsSimplyBilly`, YouTube `@SimplyBilly`, X `@SimplyBilly_`.  
Amazon Influencer: **rejected 2026-08-24**. Tag `billycarter-20` may still exist; do not treat storefront or shoppable video as live. Public product reviews go on William's socials if he wants them. Written Amazon customer reviews as a buyer still work.  
Posting rule: **always require approval**.

Clip everything from Twitch, but do not treat every saved moment as post-worthy. For non-gaming content, capture tests, first impressions, routines, results, mistakes, and lessons. A strong content idea needs at least one of these signals:

- a clear gameplay moment
- an honest reaction
- a useful lesson or explanation
- a product, game, or feature observation
- a visible before/after, setup, test, result, or verdict
- a moment that fits the learning-in-public story

## Voice Rules

Bolt should avoid hype-machine creator language. The preferred voice is direct, honest, specific, and grounded in real experience.

Good Bolt outputs sound like:

- "Here is what actually happened."
- "This is why the moment might work."
- "This confused me at first."
- "This is who this is for."
- "This is what I would change."

Avoid generic excitement, fake certainty, and empty motivational language.

## Active Systems

| System | Role |
|---|---|
| `bot.py` | Main Twitch chatbot and local chat controls |
| `modules/Think_Learn_Decide.py` | Decision loop that can use retrieved memory |
| `modules/Memory_Index.py` | Local searchable memory index |
| `modules/Post_Queue.py` | Queue state and posting readiness |
| `modules/Title_Generator.py` | Local/template title generation with optional AI support |
| `modules/Multi_Publisher.py` | Manual posting packets and platform plans |
| `data/performance_outcomes.jsonl` | Reusable lessons from posted content |
| `data/memory_index.json` | Built retrieval index; refresh after memory changes |

## Memory Sources

Bolt should retrieve from these local sources before guessing:

- `memory/content/` for creator strategy, review ideas, hooks, and content plans
- `memory/projects/bolt.md` for Bolt project context
- `data/unified_memory.jsonl` for pipeline events and decisions
- `data/performance_outcomes.jsonl` for content results and lessons
- `Data/seen_clips.json` and processed recording data for clip history
- `logs/decision_audit.log` for past decision traces
- `Docs/GOOGLE_DRIVE_HANDBOOK.md` + `Core/config.json` → `google_drive_handbook` for the **canonical** shared journal / briefing / todo / how-to (Google Drive; do not duplicate into markdown)

## Decision Rules

- Prefer local-first behavior that works without extra spend.
- If a clip has already been rejected, skipped, or scored below threshold, treat similar future clips more cautiously.
- If a similar approved or queued clip performed well, raise confidence slightly and cite the memory.
- If memory retrieval returns nothing useful, say so instead of pretending.
- When a new content lesson is added, refresh the memory index.
- Keep creator memory separate from raw clip pipeline data.

## Content Memory

Use `memory/content/` for broad creator growth:

- product and tech review ideas
- Amazon Influencer storefront products and review lessons
- beauty and skincare tests, routines, results, and cautions
- AI development learning notes and Bolt-building lessons
- gear or games Billy wants to test
- honest opinions and takes
- short-form strategy
- posted content results
- reusable hooks, scripts, and talking points

The best memory entry is specific: date, platform, content idea, result, and lesson.

## Recent Notes
- [2026-09-03] OBS Thunderstone now has Aitum Vertical at 1080×1920. Horizontal scenes are linked (Gaming → Vertical Gaming, plus Starting Soon / Chatting / BRB / Offline). Twitch stays 16:9. Vertical record/backtrack is the 9:16 path. Notes: `Docs/guides/OBS_VERTICAL.md`, `App/overlay/theme/README.md`.
- [2026-09-01] Item 12 shipped: conversation / briefing comments write week + mission via Intent_Router (same functions as `bolt week` / `bolt mission update`). Say “I’m ready to continue”, “this shipped: …”, “hours: 6, budget 40”. This week is **tech** (not paused). Amazon pause is last week only.
- [2026-09-01] Base44 `App/BoltApp` removed. It was a todo template, not a website or Mac/iOS app. Real surfaces: `bolt` CLI, overlay, Drive handbook.
- [2026-08-31] Canonical handbook is Google Drive (**Bolt Creator OS**), not a parallel markdown book. Pointer: `Docs/GOOGLE_DRIVE_HANDBOOK.md`. IDs: `Core/config.json` → `google_drive_handbook`. Daily loop: morning briefing + Daily Log / Shared Journal in Drive `02_Daily_Operations`; lasting lessons in `06_Learnings`. Bolt **writes** a briefing section to today's Daily Log (`Google_Drive_Handbook.py`, `bolt drive-auth`). It does **not** yet read the how-to or journal back into decisions.

- [2026-08-30] This week is: tech
- [2026-08-30] Rotated week. Last week was: general product review / Amazon storefront. This week is unset.
- [2026-08-30] Year-end bar (not a missed mission field): William does **not** know what the career outcome looks like and has no plan because he does not know what success looks like in this profession. That is why Researcher exists. The date he had is **2026-12-31**: figure that out, or have a roadmap with proof the work is leading somewhere. Do not ask him to invent a measurable result. Daily work does not need a mission. Profile: `near_term_horizon`. Standing question: `bolt research questions` → `year_end_proof`.
- [2026-08-30] Communication gap closed 2026-09-01 (item 12): chat / voice / briefing comments now write week and mission through Intent_Router. CLI still works.
- [2026-08-30] William said earlier this week he was **ready to continue**. That reply was not ingested (briefing comments get overwritten by `bolt morning`; chat does not update `week_card.json`). Week is still PAUSED until he runs `bolt week set "topic" --note "ready to continue"` (or we take the pause off on purpose). Do not nag film/post/reapply; wait for the topic he wants to reopen.
- [2026-08-25] Do not suggest again: snail care as this week's post (Leftover from 2026-08-17 beauty week. Closed unless William sets beauty/skincare and asks.)
- [2026-08-25] New week. This week is general product / Amazon (PAUSED). Last week was beauty/skincare (steamer posted). Snail care leftover is CLOSED. Nexus must not push snail or steamer as this week's post.
- [2026-08-24] William is pausing. Do not nag film/post/reapply. Influencer rejection hurt; he spent ~6 months writing Amazon customer reviews (~5k helpful views). Those reviews were real buyer reviews, not "doing everything wrong." They were a different Amazon job than Shoppable Video. Leave him space.
- [2026-08-24] Amazon Influencer Program: **rejected**. Stop Amazon-first shoppable-video instructions. Do not treat the storefront as live. Reapply only after real content/engagement changes — do not spam the same application.
- [2026-08-24] Amazon Influencer correction: William thought affiliate reviews had to go on his own socials. They do not. Shoppable Videos upload to Amazon (Creator Hub / storefront / product pages). Social is extra. Bolt must not mark an Amazon review unfinished because it is not on TikTok.
- [2026-08-24] Four content topics locked: (1) pop culture / TV and film (2) gaming / tech as one lane (3) beauty / skincare (4) general product review / Amazon storefront. Amazon is the shelf, not a fifth topic.
- [2026-08-24] This week corrected from "tech" to general product review / Amazon storefront. Last week remains beauty/skincare (steamer posted).
- [2026-08-24] This week is: tech
- [2026-08-23] This week (beauty / skincare) done: Posted facial steamer review on YouTube (https://www.youtube.com/watch?v=gYqRPoCkIy0, 713 views as of 2026-08-21)
- [2026-08-23] Facial steamer review already posted on YouTube this week (https://www.youtube.com/watch?v=gYqRPoCkIy0 — 713 views / 5 likes as of 2026-08-21). The Aug 17 week-start note was a plan, not an open to-do. Do not tell William to film or post the steamer again. Snail care is optional leftover, not required.
- [2026-08-18] Held clip 1976be1d (Test): not ready
- [2026-08-18] Held clip 59eb0958 (Ready clip): bad hook
- [2026-08-18] Held clip 872c1b19 (Test): not ready
- [2026-08-18] Held clip 65e497eb (Ready clip): bad hook
- [2026-08-17] Held clip f01b6ff9 (I love this for me #007FirstLight #JamesBond #fyp #IOInteractive #DelphiInteractiveLLC): same issue with the video quality. I will work on making something worth posting first, then come back to both of these videos
- [2026-08-17] Held clip 97ad1824 (Its a very dapper night #fyp #JamesBond #DelphiInteractiveLLC #IOInteractive #FirstLightGameplay): the video quality isn't good enough to post. Plus, the post this week should be focused on skin care, not gaming. Ill work on that now"
- [2026-08-17] Mac automation: launchd fixed (Core/launch.py live --no-checklist). Evening briefing at 17:00 writes Apple Reminders list "Bolt" plus a Mac banner. Only financial work stays fully manual; everything else is do-and-notify. Shortcuts: Bolt Morning / Review Queue / Stats / Wrap-Up. OCR shortcut writes an editable .txt via Vision.
- [2026-08-17] This week is: beauty / skin care. Lets post a video or two, with a full product review on the snail care facial products or the facial steamer and the products that came with it. If bwe do both, The next skin care review would already be done and prepared for the next beauty / skin care run.
- [2026-08-16] Held clip 357a75a9 (Test): not ready
- [2026-08-16] Held clip 7fe9e6be (Ready clip): bad hook
- [2026-08-16] Posted clip be5926ae (I better play like this online too #FirstLightGameplay #fyp #IOInteractive #DelphiInteractiveLLC)

- [2026-08-04] Anchored `seen_clips.json` to `Data/seen_clips.json` (was drifting to the repo root each run). Patched `Clip_Deduplicator.SEEN_FILE`, fixed `Think_Learn_Decide.DATA_DIR` depth (was the pre-2026-07-19 flatten bug), updated `Core/data/source_registry.json`. Added `bolt vector_db` / `bolt reindex` aliases for `refresh_vector_db`; reconciled `bin/bolt` docstring with the actual `~/.zshrc` alias.
- [2026-08-02] Twitch channel renamed to ItsSimplyBilly to align with other social handles (TikTok, YouTube, X).
- [2026-05-29] Added the full creator vision: gaming, tech, product testing, Amazon Influencer storefront reviews, beauty/skincare, AI development, and Bolt as a virtual teammate for learning and growth.
- [2026-05-29] Reframed this hot cache as Bolt's operational memory instead of assistant notes about Billy.
- [2026-05-27] Phase 3 marked complete.
- [2026-05-27] Two test clips were posted: `test1` and `test2`.
- [2026-04-27] Bolt_Chat and Bolt_Voice were working. ChaoticallyRobotical was confirmed as the bot account.
- [2026-04-27] ElevenLabs was skipped. `edge-tts` was installed as the free neural voice option, with macOS `say` as fallback.
- [2026-04-27] `max_clips_per_session` was set to 5 and `min_clip_score` was set to 65.