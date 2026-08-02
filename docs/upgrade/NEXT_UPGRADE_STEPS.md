# NEXT_UPGRADE_STEPS.md

## 🚀 Upgrade Status

### 🟢 GROK / LLM LAYER — complete (Aug 2, 2026)

| # | Upgrade | Status | Date | Notes |
|---|---------|--------|------|-------|
| L1 | `LLM_Handler` multi-provider (OpenAI + xAI/Grok) | ✅ COMPLETE | Aug 2 | `BOLT_LLM_PROVIDER`, fallback, model overrides |
| L2 | Voice conversation → `ask_llm` | ✅ COMPLETE | Aug 2 | `Core/Bolt_Conversation.py` |
| L3 | Twitch `!Bolt` → `ask_llm` | ✅ COMPLETE | Aug 2 | `Core/modules/Bolt_Chat.py` |
| L4 | `Intent_Router` natural-language actions | ✅ COMPLETE | Aug 2 | morning / next / status / queue / research / mission |
| L5 | Merge to main | ✅ COMPLETE | Aug 2 | PR #3 squash-merged |

**Operator env:**
```bash
BOLT_LLM_PROVIDER=xai
BOLT_LLM_FALLBACK=none
XAI_API_KEY=...
```

**Test:**
```bash
PYTHONPATH=Core python3 -m modules.LLM_Handler
PYTHONPATH=Core python3 -m Bolt_Conversation --text
```

### 🟠 COMMAND CENTER — Missions in bin/bolt ✅ COMPLETE (Aug 1, 2026)

| # | Upgrade | Status | Date | Notes |
|---|---------|--------|------|-------|
| CC1 | Skill playbook under `Core/skills/creator-command-center/` | ✅ COMPLETE | Aug 1 | Was root `bolt-creator-command-center/` |
| CC2 | `Command_Center` module + mission scaffold | ✅ COMPLETE | Aug 1 | Profile + research + catalog context |
| CC3 | `bolt mission` / `command-center` / `ccc` | ✅ COMPLETE | Aug 1 | start, list, show, next, checkin, playbook |
| CC4 | Unit tests | ✅ COMPLETE | Aug 1 | `Data/tests/test_command_center.py` |

**Operator loop:**
```bash
bolt mission checkin
bolt mission start "your goal" --hours 6 --budget 40 --assets "…"
bolt mission show latest
bolt mission next
```

### 🟣 RESEARCHER — Direction-finding role ✅ COMPLETE (Aug 1, 2026)

| # | Upgrade | Status | Date | Notes |
|---|---------|--------|------|-------|
| R1 | User profile (`Data/memory/user_profile.json`) + C1–C7 | ✅ COMPLETE | Jul 29 | Interview complete; night-shift + authenticity gates |
| R2 | Researcher module + C5/C6/C7 gating | ✅ COMPLETE | Jul 30 | `Core/modules/Researcher.py` |
| R3 | Research log + unit tests (37→46+) | ✅ COMPLETE | Jul 30–Aug 1 | `Data/memory/research_log.jsonl` |
| R4 | `bolt research` read CLI | ✅ COMPLETE | Aug 1 | status / questions / candidates / log |
| R5 | `bolt research` write CLI | ✅ COMPLETE | Aug 1 | add / note / c5 keep\|drop / pending |
| R6 | Briefing integration | ✅ COMPLETE | Aug 1 | Research Notes + pending C5 action item |
| R7 | Command docs + roadmaps | ✅ COMPLETE | Aug 1 | BOLT_COMMANDS + PROJECT_STATUS + this file |

**Operator loop (not engineering):**
```bash
bolt research pending
bolt research c5 keep "Name" --why "…"
bolt research c5 drop "Name" --why "…"
bolt research add "Name" --platform YouTube --summary "…" --why "…"
```

**Where to look:** 🟡 `Core/modules/Researcher.py` · 🔵 `Data/memory/` · 🔴 `bin/bolt research`

### 🔴 MANAGER — Content Manager OS ✅ COMPLETE (Jul 9–19, 2026)

M1–M13 + ML ranking complete. See `docs/upgrade/UPGRADE_STATUS.md` for the full checklist.

**Where to look:** 🔴 `Core/modules/Content_Manager.py` · 🟡 `Core/modules/Clip_Ranker.py` · 🟢 `Core/modules/BOLT_COMMANDS.md`

### Operator follow-ups (not engineering work)

- **Research:** clear C5 queue with `bolt research pending` + `c5 keep|drop`
- **Catalog:** add real owned products (`bolt manage add … --asin …`)
- **Ship:** first real post → `bolt manage mark-posted "Name" --platforms tiktok --where <url>`
- Fill in real TikTok OAuth when ready to auto-publish
- Optional Google OAuth for live calendar/gmail in briefings
- Expand `Intent_Router` phrases as you discover what you actually say to Bolt

### Earlier infrastructure upgrades ✅ (June 6, 2026)

Cron, compression, storage alerts, duplicate detection, performance baseline — complete.

---

*Last updated: August 2, 2026 — Grok LLM layer + Intent_Router shipped and documented.*
