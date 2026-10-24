# Bolt documentation index

This is the entry point for human-facing project documentation. Keep current-state material here or linked from here; do not duplicate daily logs.

## Start here

| Document | Purpose |
|---|---|
| [../README.md](../README.md) | Installation, safety posture, and project overview |
| [BOLT_NOW.md](BOLT_NOW.md) | Current focus, next steps, and longer-term direction |
| [READINESS.md](READINESS.md) | Capability maturity, prerequisites, and known limits |
| [../Core/modules/BOLT_COMMANDS.md](../Core/modules/BOLT_COMMANDS.md) | Canonical CLI command reference |
| [../AGENTS.md](../AGENTS.md) | Rules for maintaining Bolt |

## Operations and architecture

| Document | Purpose |
|---|---|
| [GOOGLE_DRIVE_HANDBOOK.md](GOOGLE_DRIVE_HANDBOOK.md) | Daily operations and shared Drive handbook |
| [MONDAY.md](MONDAY.md) | Phone board: Obsidian vault synced with Monday |
| [architecture/SYSTEM_README.md](architecture/SYSTEM_README.md) | System purpose and architecture |
| [guides/OBS_VERTICAL.md](guides/OBS_VERTICAL.md) | Vertical OBS workflow |
| [reports/DEBUG_REPORT.md](reports/DEBUG_REPORT.md) | Debugging reference, when present |

## Current source-of-truth files

- `Data/MEMORY.md`: current operating memory and recent decisions.
- `Data/memory/week_card.json`: the active week and explicit do-not-suggest choices.
- `Data/business/product-tester-plan.md`: product-testing plan and assessment template.
- `Core/config.json`: runtime defaults. Secrets belong only in `.env`.
- `pyproject.toml`: Python dependencies and optional feature groups.

## Maintenance rule

When a capability changes, update its command reference and readiness status first. Update `BOLT_NOW.md` only for a material change in current focus, plan, or operating policy.

*Last reviewed: 2026-10-19*
