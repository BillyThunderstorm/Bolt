# Bolt Commands To Remember

This file keeps the important Bolt commands in one place.

## Local Paths

Go to the real Bolt project:

```bash
cd "/Users/carter/developer/Bolt"
```

Go to the helper scripts folder:

```bash
cd "/Users/carter/Documents/Codex/2026-05-13/im-trying-to-create-my-own"
```

## Run The Repair/Patch Scripts

Run these from the helper scripts folder. They patch the Bolt project.

```bash
python3 bolt_repair.py
```

```bash
python3 bolt_patch_ai_title.py
```

```bash
python3 bolt_patch_lazy_clip_factory.py
```

```bash
python3 bolt_patch_lazy_highlight.py
```

```bash
python3 bolt_patch_lazy_tiktok.py
```

Note: the helper scripts currently point at an older iCloud Bolt path. Update their `ROOT` value to this before running them:

```python
ROOT = Path("/Users/carter/developer/Bolt")
```

## Bolt Setup Commands

Run these from the Bolt project folder:

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

Back up `.env` before changing keys:

```bash
cp .env .env.backup
```

Note: this repo currently has `.env`, but does not have `.env.example`.

## Verify Bolt

Run the project verifier:

```bash
python3 scripts/verify.py
```

Note: `scripts/verify.py` may warn about older file names that are no longer in this repo.

Run Python compile checks:

```bash
python3 -m compileall .
```

Run tests:

```bash
python3 -m pytest
```

## Launch Bolt

Run the full launch flow:

```bash
python3 launch.py
```

Skip the checklist:

```bash
python3 launch.py --no-checklist
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

## Twitch Token

Generate or refresh the Twitch bot token:

```bash
python3 scripts/get_twitch_token.py
```

## Clip Performance Logging

Log TikTok performance after posting so Bolt can learn:

```bash
python3 scripts/log_clip_performance.py
```

## Cleanup

Run Bolt cleanup:

```bash
bash scripts/cleanup_bolt.sh
```

## Git LFS Commands

Use these if Bolt needs Git LFS for large video/model files:

```bash
git lfs install
```

```bash
cp "/Users/carter/Documents/Codex/2026-05-13/im-trying-to-create-my-own/bolt_gitattributes_fixed" .gitattributes
```

```bash
git add .gitattributes
```

## Helpful Checks

```bash
git status
```

```bash
git diff --stat
```

```bash
find . -maxdepth 3 -name "*.py"
```
