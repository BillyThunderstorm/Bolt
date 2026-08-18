# Phase 2 — Researcher Role (shipped Aug 1, 2026)

## Goal

Billy's bottleneck is **direction**, not execution. Phase 2 makes research a
first-class Bolt role so production work is guided by C5/C6/C7 instead of
generic to-do lists.

## Shipped

| ID | Item | Entry point |
|----|------|-------------|
| R1 | User profile + constraints | `Data/memory/user_profile.json` |
| R2 | Gating module | `Core/modules/Researcher.py` |
| R3 | Research log | `Data/memory/research_log.jsonl` |
| R4 | Read CLI | `bolt research status\|questions\|candidates\|log` |
| R5 | Write CLI | `bolt research add\|note\|c5\|pending` |
| R6 | Briefing surface | `bolt briefing` Research Notes + C5 action |
| R7 | Docs/roadmaps | BOLT_COMMANDS, PROJECT_STATUS, NEXT_UPGRADE_STEPS, UPGRADE_STATUS |

## Operator loop (content nights)

```bash
bolt research pending
bolt research c5 keep "Name" --why "Would want to be known for this because…"
bolt research c5 drop "Name" --why "Not my voice"
bolt research add "Name" --platform YouTube --summary "…" --why "…"
bolt briefing --print
```

## Not in this phase

- Apple Reminders delivery (profile channel #1) — wired 2026-08-17 (`bolt briefing --send`)
- Auto web-search for new candidates (M13 sponsors-research is separate)
- External `bolt-creator-command-center` skill (not part of `bin/bolt`)

## Verification

```bash
uv run --directory /Users/carter/developer/Bolt python -m unittest Data.tests.test_researcher
uv run --directory /Users/carter/developer/Bolt bolt research status
```
