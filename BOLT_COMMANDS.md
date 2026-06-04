# Bolt Commands To Remember

This file keeps the current Bolt commands in one place.

## Local Paths

Real Bolt repo:

```bash
cd "/Users/carter/developer/Bolt"
```

Helper workspace for side scaffolds and sibling tooling:

```bash
cd "/Users/carter/Documents/Codex/2026-05-13/im-trying-to-create-my-own"
```

Keep those workspaces separate unless you are intentionally copying a specific artifact.

## Setup

Run from `/Users/carter/developer/Bolt`:

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

```bash
python3 -m pip install --upgrade pip
```

```bash
python3 -m pip install -r requirements.txt
```

Create a local `.env` from the safe template:

```bash
cp .env.example .env
```

Back up `.env` before changing keys:

```bash
cp .env .env.backup
```

## Verify Bolt

Run the project verifier:

```bash
python3 scripts/verify.py
```

Run the unit tests:

```bash
python3 -m unittest
```

Run focused tests:

```bash
python3 -m unittest tests.test_memory_index
```

```bash
python3 -m unittest tests.test_think_learn_decide
```

Run Python compile checks:

```bash
python3 -m compileall launch.py bot.py modules scripts tests
```

## Launch Bolt

Run the full launch flow:

```bash
python3 launch.py
```

Process the latest recording:

```bash
python3 launch.py process
```

Run the bot directly:

```bash
python3 bot.py
```

## Process Recordings

Drop recordings into `recordings/`, then run:

```bash
python3 scripts/process_recordings.py
```

## Chat, Voice, And Local Controls

Run Bolt chat locally:

```bash
python3 -m modules.Bolt_Chat
```

Test voice:

```bash
python3 -m modules.Bolt_Voice "say this out loud"
```

Useful chat commands when Bolt chat is running:

```text
!queue
!recall honest product reviews
!recall beauty skincare routine product test
!recall AI development virtual teammate
```

## Memory

Refresh the local searchable memory index after editing memory files:

```bash
python3 scripts/refresh_memory_index.py
```

Search memory through the index module:

```bash
python3 -m modules.Memory_Index --refresh "Amazon Influencer storefront product testing"
```

Search memory through Bolt memory:

```bash
python3 -m modules.Bolt_Memory --search "beauty skincare routine product test results"
```

## Content Results And Learning

List logged performance outcomes:

```bash
python3 scripts/log_clip_performance.py --list
```

Log a posted clip result:

```bash
python3 scripts/log_clip_performance.py --clip clips/example.mp4 --platform TikTok --note "Strong opening hook"
```

## Multi-Platform Posting Plans

Build a no-cost posting packet:

```bash
python3 -m modules.Multi_Publisher clips/example.mp4 "Working title" --hashtags gaming ai
```

## Title Generation

Monitor title generation results:

```bash
python3 scripts/monitor_title_results.py
```

Run the local title upgrade test helper:

```bash
python3 scripts/test_title_upgrade_10_clips.py
```

## Tokens And Auth

Generate or refresh the Twitch bot token:

```bash
python3 scripts/get_twitch_token.py
```

Generate or refresh TikTok auth:

```bash
python3 scripts/get_tiktok_token.py
```

## AI Learning

Run the cleaned neural-network learning example:

```bash
python3 llm/neural_model.py
```

## Docs To Check Before Upgrades

```bash
open README.md
```

```bash
open docs/INDEX.md
```

```bash
open docs/PROJECT_STATUS.md
```

```bash
open memory/content/full-creator-vision.md
```

## Git Checks

```bash
git status --short
```

```bash
git diff --stat
```

```bash
git diff -- README.md BOLT_COMMANDS.md docs memory brand llm
```
