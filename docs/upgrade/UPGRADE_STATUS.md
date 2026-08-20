# Bolt Upgrade Status

Source of truth: `/Users/carter/developer/Bolt`

*Last updated: August 2, 2026*

## Grok / LLM layer (L1–L4) — complete (Aug 2, 2026)

- [x] L1 — `LLM_Handler` multi-provider (OpenAI + xAI/Grok), env switch + fallback
- [x] L2 — Voice conversation (`Bolt_Conversation`) routes replies through `ask_llm`
- [x] L3 — Twitch chat (`Bolt_Chat` / `!Bolt`) routes replies through `ask_llm`
- [x] L4 — `Intent_Router` maps plain phrases → real actions (morning, next, status, queue, research, mission)
- [x] Merged to `main` via PR #3 (`feature/llm-handler-xai`)

**Env (local `.env`, never commit keys):**
```bash
BOLT_LLM_PROVIDER=xai
BOLT_LLM_FALLBACK=none
XAI_API_KEY=...
# Optional model overrides:
# BOLT_XAI_MODEL=grok-4.5
# BOLT_OPENAI_MODEL=gpt-4o-mini
```

**Natural phrases (conversation mode):**
- "Good morning Bolt" / morning briefing → `morning()`
- "What should I do next?" → `next_actions()`
- "How are things?" / status → manager status summary
- "Show the queue" → posting/social queue
- research / mission status phrases → those modules

## Researcher tier (R1–R7) — complete (Aug 1, 2026)

- [x] R1 — User profile + hard constraints C1–C7 (`Data/memory/user_profile.json`)
- [x] R2 — Researcher module with C5/C6/C7 gating
- [x] R3 — Append-only research log + unit tests
- [x] R4 — `bolt research` read CLI (status / questions / candidates / log)
- [x] R5 — `bolt research` write CLI (add / note / c5 keep|drop / pending)
- [x] R6 — Daily briefing Research Notes + pending-C5 action items
- [x] R7 — Commands + roadmaps updated

**Nightly content loop:** research first → C5 keep/drop → then produce.


## Creator Command Center — in bin/bolt (Aug 1, 2026)

- [x] CC1 — Skill playbook at `Core/skills/creator-command-center/SKILL.md`
- [x] CC2 — `Core/modules/Command_Center.py` mission scaffold (profile + research + catalog)
- [x] CC3 — CLI: `bolt mission` / `bolt command-center` / `bolt ccc`
- [x] CC4 — Tests in `Data/tests/test_command_center.py`
- [x] Missions store: `Data/memory/missions/*.md`

## Manager tier (M1–M13) — all complete

- [x] M1 — Content catalog + journals
- [x] M2 — Review draft builder + Amazon tag `billycarter-20`
- [x] M3 — Good Morning Bolt spoken briefing
- [x] M4 — Amazon storefront tracker
- [x] M5 — Social package queue (approval required)
- [x] M6 — Sponsor/affiliate prospector + pitches
- [x] M7 — Business playbook + Bolt advancement docs
- [x] M8 — `bin/bolt` manager subcommands + tests
- [x] M9 — Real ASINs on owned gear (code complete; operator adds the ASINs)
- [x] M10 — First shipped game + tech review posts (`mark_ready` + `mark_posted` reachable)
- [x] M11 — TikTok API end-to-end publish (gated on TikTok `video.publish` scope approval)
- [x] M12 — YouTube/X OAuth upload (manual-assist bridge; real API publishers pending platform app review)
- [x] M13 — Live sponsor research enrichment (web search results attached to prospects)

## ML ranking — recency-weighted learned model (Jul 19, 2026)

- [x] 4-component score: audio + trigger bonus + hand-coded history + learned boost
- [x] `learned_boost()`: 14-day half-life recency decay, like_rate-aware, 3-sample minimum, capped at 20 points
- [x] `update_historical_performance()` now appends to an `observations` array (capped at 200 per (game, trigger))
- [x] `inspect_learned_model(game=None)` and `learning_loop_status()` for visibility
- [x] 15 new tests in `Data/tests/test_clip_ranker.py` (module had zero coverage before this)
- [x] Back-compat with legacy `total_clips` / `avg_views` / `total_likes` aggregate fields

## Week 1: LLM Titles

- [x] Copy code from `UPGRADE_CODE_EXAMPLES.md`
- [x] Update `modules/Title_Generator.py`
- [x] Test with 10 clips
- [x] Enable in production
- [x] Monitor results

## What Changed

- `modules/Title_Generator.py` supports AI title generation when enabled, caches responses, cleans hashtags, and falls back to templates.
- `config.json` has `quality_tiers.use_ai_titles` enabled.
- Title review is `bolt queue title`. Connectivity is `bolt doctor`.
- Title generator behavior is covered by `Data/tests/test_title_generator.py`.

## Commands

```bash
python3 -m unittest tests.test_title_generator tests.test_multi_publisher tests.test_log_clip_performance
python3 bin/bolt doctor
python3 scripts/log_clip_performance.py --list
```

## Production Note

Chat / conversation replies default through `LLM_Handler`. Set `BOLT_LLM_PROVIDER=xai` and `XAI_API_KEY` for Grok. OpenAI remains available as fallback or for Whisper transcription only.

AI titles may still call OpenAI when enabled; if that key has no credits, title generation falls back to local templates.

## Next: Auto-Posting With Safeguards

- [x] Add 30-minute pre-peak review window
- [x] Auto-post when approved or when the review deadline is missed
- [x] Hold rejected clips and record the rejection reason
- [x] Add Twitch chat overrides: `!postnow`, `!dontpost`, `!stopclip`
- [x] Keep failed publish attempts in the queue for manual posting or retry

Real publishing uses `modules/TikTok_Publisher.py` and requires
`TIKTOK_ACCESS_TOKEN`. Without that token, the queue/review/override flow still
works, and failed publish attempts stay visible instead of disappearing.

## Producer Commands From Twitch Chat

- [x] `!postnow [clip_id]` publishes the next ready clip immediately
- [x] `!dontpost [clip_id] <reason>` holds a clip and records why
- [x] `!stopclip [clip_id] <reason>` emergency-holds a clip
- [x] `!skip [clip_id] <reason>` alias for holding a clip
- [x] `!rank <score>` or `!rank <clip_id> <score>` overrides queue score/tier
- [x] `!config <safe_key> <value>` allows guarded live tuning for selected config keys

## TikTok Token Setup

- [x] Add `scripts/get_tiktok_token.py` guided OAuth helper
- [x] Save TikTok client credentials, access token, refresh token, scope, and expiry values to `.env`
- [x] Add `modules/TikTok_Auth.py` for refreshable token management
- [x] Teach `modules/TikTok_Publisher.py` to refresh the access token before publishing

Direct auto-posting still depends on TikTok approving the app for `video.publish`.
The helper can request the scope, but TikTok decides whether it is granted.
