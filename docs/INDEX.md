# Bolt Documentation Index

Use this page as the central map for Bolt.

## Color / Label Map

| Label | Path root | Use for |
|-------|-----------|---------|
| 🟡 CORE | `Core/` | Code, modules, brain, config |
| 🔵 DATA | `Data/data/` | Catalog, storefront, sponsors, memory |
| 🟢 DOCS | `Docs/` | Commands, status, briefings, reviews |
| 🟣 APP | `App/` | UI / brand |
| 🟠 MEDIA | `media/` | Clips / recordings |
| 🔴 MANAGER | `Content_Manager` + `bin/bolt` | Daily creator OS |

## Start Here

| Label | File | Description |
|-------|------|-------------|
| 🔴 | `Core/modules/BOLT_COMMANDS.md` | **All commands** (manager + researcher + Grok conversation) |
| 🟢 | `docs/PROJECT_STATUS.md` | Current build status + progress |
| 🟢 | `docs/upgrade/NEXT_UPGRADE_STEPS.md` | Upgrade tracker (L1–L4 Grok, M1–M13, R1–R7, CC) |
| 🟢 | `docs/upgrade/UPGRADE_STATUS.md` | Per-upgrade checklist |
| 🟢 | `docs/upgrade/SHIP_LOG_2026-08-02.md` | **Grok layer ship log** |
| 🟢 | `docs/INDEX.md` | This map |
| 🟡 | `Core/modules/LLM_Handler.py` | Multi-provider LLM (OpenAI + xAI/Grok) |
| 🟡 | `Core/modules/Intent_Router.py` | Natural-language → real Bolt actions |
| 🟡 | `Core/Bolt_Conversation.py` | Voice/text conversation (Grok + intents) |
| 🟡 | `Core/modules/Content_Manager.py` | Creator manager implementation |
| 🟡 | `Core/modules/Researcher.py` | Direction-finding research role (C5/C6/C7) |
| 🟡 | `Core/modules/Command_Center.py` | Creator Command Center (`bolt mission` / `ccc`) |
| 🟡 | `Core/skills/creator-command-center/` | Mission playbook skill (SKILL.md) |
| 🟡 | `Core/modules/Clip_Ranker.py` | Recency-weighted learned clip-rank model |
| 🟡 | `Core/bolt_brain.md` | William creator profile |
| 🔵 | `Data/memory/user_profile.json` | Hard constraints + vision for Researcher |
| 🟡 | `bin/bolt` | Single CLI entry |

## LLM / conversation (Aug 2, 2026)

| Piece | Path | Notes |
|-------|------|-------|
| Provider switch | `Core/modules/LLM_Handler.py` | `BOLT_LLM_PROVIDER=xai` |
| Intent router | `Core/modules/Intent_Router.py` | morning / next / status / queue |
| Voice + text chat | `Core/Bolt_Conversation.py` | Grok replies + intents |
| Twitch personality | `Core/modules/Bolt_Chat.py` | `!Bolt` via same handler |
| Commands | `Core/modules/BOLT_COMMANDS.md` | LLM + conversation section |

```bash
PYTHONPATH=Core python3 -m modules.LLM_Handler
PYTHONPATH=Core python3 -m Bolt_Conversation --text
```

## Canonical Runtime Docs

| File | Description |
|------|-------------|
| `docs/PROJECT_STATUS.md` | Current build status and next steps |
| `docs/upgrade/SHIP_LOG_2026-08-02.md` | Latest engineering ship |
| `modules/Think_Learn_Decide.py` | Ingestion, reasoning, decisions, feedback loop |
| `memory/content/full-creator-vision.md` | North star across all creator lanes |
| `docs/requirements/creator-domains-requirements.md` | System requirements for 7 creator domains |
| `.github/instructions/creator-domains.instructions.md` | Behavioral instructions with full personality |

## Setup and Integration

| File | Description |
|------|-------------|
| `docs/guides/SETUP_GUIDE.md` | Setup, prerequisites, and troubleshooting |
| `docs/guides/STREAM_DECK_SETUP.md` | Stream Deck setup notes |
| `scripts/setup.sh` | First-time setup and dependency install |
| `scripts/verify.py` | Project verification checks |

## Runtime Modules (high-signal)

| Module | Description |
|--------|-------------|
| `modules/LLM_Handler.py` | Shared LLM entry (Grok / OpenAI) |
| `modules/Intent_Router.py` | Natural language action routing |
| `Bolt_Conversation.py` | Voice/text conversation |
| `modules/Bolt_Chat.py` | Twitch personality layer |
| `modules/Content_Manager.py` | Creator manager OS |
| `modules/Researcher.py` | Direction-finding research |
| `modules/Command_Center.py` | Missions / CCC |
| `modules/Think_Learn_Decide.py` | Decision engine |
| `modules/Clip_Ranker.py` | Ranking and tiering |
| `modules/Memory_Index.py` | Local searchable memory index |

## User Interfaces Summary

| Interface | Command | Description |
|-----------|---------|-------------|
| CLI | `bolt <cmd>` / `bin/bolt` | Primary entry |
| Conversation (text) | `PYTHONPATH=Core python3 -m Bolt_Conversation --text` | Grok + intents |
| Conversation (voice) | `PYTHONPATH=Core python3 -m Bolt_Conversation` | Mic + TTS |
| LLM health | `PYTHONPATH=Core python3 -m modules.LLM_Handler` | Provider status |
| Twitch chat | `PYTHONPATH=Core python3 -m modules.Bolt_Chat` | Live chat bot |
| Morning | `bolt morning` | Spoken briefing |
| Research | `bolt research …` | C5 direction loop |
| Mission | `bolt mission …` | Command Center |

---

*Last updated: August 2, 2026 — Grok LLM layer + Intent_Router documented.*
