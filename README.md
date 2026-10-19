# Bolt

Bolt is Billy Carter’s local-first creator operations system: a Python CLI and companion local interfaces for product testing, media processing, research, planning, and review.

It is a personal project, not a hosted SaaS product. It keeps creator data and generated media on the local machine, while treating paid model calls and publishing as explicit, reviewable actions.

## What works today

- Product-testing workflow: catalog items, daily notes, drafts, assessments, and manual posting plans.
- Media workflow: recordings/VODs → highlight candidates → clips, vertical renders, captions where available, and review queues.
- Creator operations: daily/weekly briefings, missions, research, local memory, and cost-aware LLM routing.
- Local integrations: optional OBS, Twitch, Google services, voice, macOS notifications, and Apple Reminders.
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
