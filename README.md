# Bolt

Bolt is Billy Carter’s local-first creator operations system: a Python CLI and companion local interfaces for product testing, media processing, research, planning, and review.

It is a personal project, not a hosted SaaS product. It keeps creator data and generated media on the local machine, while treating paid model calls and publishing as explicit, reviewable actions.

## What works today

- Product-testing workflow: catalog items, daily notes, drafts, assessments, and manual posting plans.
- Media workflow: recordings/VODs → highlight candidates → clips, vertical renders, captions where available, and review queues.
- Creator operations: daily/weekly briefings, missions, research, local memory, and cost-aware LLM routing.
- Local integrations: optional OBS, Twitch, Google services, voice, macOS notifications, Apple Reminders, and a Monday phone board for vault tasks.

- Post-stream helpers: game freshness, motion detection, wrap packages, release packages, and per-game clip settings.

The live command reference is [Core/modules/BOLT_COMMANDS.md](Core/modules/BOLT_COMMANDS.md). Capability maturity and prerequisites are tracked in [Docs/READINESS.md](Docs/READINESS.md).

## Quick start

Requirements: Python 3.11 or 3.12 and [uv](https://docs.astral.sh/uv/). macOS is recommended for the optional voice, OBS, and Apple integrations.

```bash
git clone https://github.com/BillyThunderstorm/Bolt.git
cd Bolt
uv sync

# Optional feature groups
uv sync --extra subtitles
uv sync --extra ocr
uv sync --extra menubar

cp .env.example .env
# Add only the credentials you plan to use; never commit .env.

uv run bolt verify
uv run bolt doctor
uv run bolt help
```

If you use pip instead, install the dependencies declared in `pyproject.toml`; this repository does not maintain a separate `requirements.txt`.

## Everyday commands

```bash
uv run bolt day --decide      # daily briefing and queue review
uv run bolt manage next       # next product-testing actions
uv run bolt game status       # current game freshness and drift check
uv run bolt wrap --dry-run    # preview a post-stream package
uv run bolt memory recall "what should I do next?"
uv run bolt doctor            # installation/integration diagnostics
```

## Monday board on your phone

Bolt's notes stay in the Obsidian vault. When you add a Monday API token, the same tasks, events, and pages also show up on your Monday board so you can glance at them and make small edits from your phone.

1. On monday.com, click your avatar (top right), then **Developers**, and copy the API token.
2. Put it in `.env` as `MONDAY_API_TOKEN`. Leave `MONDAY_BOARD_ID` as `18436882096` unless you made a new board.
3. Run `bolt monday sync` once. After that, Bolt updates Monday whenever it saves a task, and `bolt monday watch` (or a live `bolt launch`) pulls phone edits back into the vault.

The vault wins if both sides change at the same moment. Bolt will not delete a note just because a Monday card disappeared. Details: [Docs/MONDAY.md](Docs/MONDAY.md).

## Safety and publishing

- William approves purchases and publishing.
- TikTok API auto-publishing is paused; use the manual review and logging flow.
- Secrets, credentials, tokens, generated media, and runtime state stay out of Git.
- Optional integrations soft-fail with a clear status rather than blocking local work.

## Project map

- [Docs/INDEX.md](Docs/INDEX.md) — documentation map
- [Docs/BOLT_NOW.md](Docs/BOLT_NOW.md) — living status and next steps
- [Docs/READINESS.md](Docs/READINESS.md) — ready vs. partial capabilities
- [Core/bolt_brain.md](Core/bolt_brain.md) — creator context
- [Data/MEMORY.md](Data/MEMORY.md) — current operating memory
- [AGENTS.md](AGENTS.md) — repository operating rules

## Status

Actively developed. The current focus is product testing: complete three detailed assessments of products already owned, with a short-form deliverable for each. See [Docs/BOLT_NOW.md](Docs/BOLT_NOW.md) for the current plan.

## License

No license has been selected yet. Do not reuse or redistribute this repository until a license is added.

## Author

Built by Billy Carter (@SimplyBilly_).

Navy veteran · independent developer · content creator
