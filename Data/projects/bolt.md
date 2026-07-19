# Project: Bolt

**What it is:** William's AI content manager + business assistant  
**Status:** Active — manager OS live (2026-07-09)  
**Also called:** "the bot", "Bolt", "Good Morning Bolt"

## Label map

| Label | Path | Role |
|-------|------|------|
| 🔴 MANAGER | `Core/modules/Content_Manager.py` | Daily creator OS |
| 🟡 CORE | `Core/` | Bot, modules, config, brain |
| 🔵 DATA | `Data/data/` | Catalog, storefront, sponsors, memory |
| 🟢 DOCS | `Docs/` | Commands, status, briefings |
| 🟠 MEDIA | `media/` | Clips / recordings |
| ⚪ SCRIPTS | `3rd_Party/colabs/scripts/` | Utilities via `bolt` CLI |

## What Bolt Does

- Content manager for game/tech testing (priority), product/skincare expansion
- Review drafts + Amazon storefront (`billycarter-20`)
- Social packaging with approval required
- Sponsor/affiliate prospecting + pitch drafts
- Spoken morning briefing
- Clip pipeline (Twitch → highlights → vertical posts)
- Voice conversation companion

## Key files

| Label | File | Purpose |
|-------|------|---------|
| 🔴 | `Core/modules/Content_Manager.py` | Manager commands |
| 🟡 | `Core/bot.py` | Main bot runtime |
| 🟡 | `Core/bolt_brain.md` | Creator profile |
| 🟡 | `Core/config.json` | Runtime config |
| 🟡 | `bin/bolt` | CLI entry |
| 🟢 | `Docs/BOLT_COMMANDS.md` | Command reference |
| 🟢 | `Docs/PROJECT_STATUS.md` | Progress status |
| 🟢 | `Docs/NEXT_UPGRADE_STEPS.md` | Upgrade tracker |
| 🔵 | `Data/data/content/manager-progress.md` | Manager progress log |

## Daily commands

```bash
bolt morning
bolt manage next
bolt store feature-next
bolt social status
bolt sponsors next
bolt advance next
```
