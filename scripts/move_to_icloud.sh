#!/bin/bash
# =============================================================================
#  move_to_icloud.sh — copy Bolt into iCloud Drive/Bolt (for the second Mac)
# =============================================================================
#  Thin wrapper around `bolt icloud run` (Core/modules/ICloud_Sync.py).
#  No prompts. Copy-only: never deletes, never overwrites a changed iCloud file,
#  never moves this checkout. Skips .env/.env.local + tokens, recordings/media,
#  video/audio, .git, .venv, node_modules, caches, logs, Data/backups.
#
#  Usage:
#      bash scripts/move_to_icloud.sh            # dry-run report (nothing copied)
#      bash scripts/move_to_icloud.sh --apply    # real copy, logged to logs/icloud_sync.jsonl
# =============================================================================
set -euo pipefail
Bolt_SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${Bolt_SOURCE}/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"
cd "$Bolt_SOURCE"
PYTHONPATH="${Bolt_SOURCE}/Core${PYTHONPATH:+:$PYTHONPATH}" exec "$PY" -m modules.ICloud_Sync run "$@" </dev/null
