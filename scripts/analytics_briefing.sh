#!/usr/bin/env bash
# scripts/analytics_briefing.sh
#
# Print Bolt's performance summary. Designed to be cron-able so Billy
# can see "what's working" without running the command manually.
#
# Usage:
#   bash scripts/analytics_briefing.sh
#   bash scripts/analytics_briefing.sh --days 7 --top 3
#   bash scripts/analytics_briefing.sh --json > /tmp/briefing.json
#
# Cron suggestion (weekly digest, Mondays at 9am):
#   0 9 * * 1 cd /Users/carter/developer/Bolt && bash scripts/analytics_briefing.sh --days 7 >> logs/analytics_weekly.log 2>&1

set -euo pipefail

# scripts/ → repo root is one level up (not ../../../).
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-$ROOT/.venv/bin/python3}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

# Ensure deps are reachable (same pattern as other scripts in this repo).
export PYTHONPATH="$ROOT/Core:${PYTHONPATH:-}"

# Optional: pull fresh platform stats before summarizing.
# Set SYNC_TIKTOK=0 / SYNC_YOUTUBE=0 to skip (e.g. offline runs).
if [[ "${SYNC_TIKTOK:-1}" == "1" ]]; then
  "$PYTHON" "$ROOT/scripts/sync_tiktok_stats.py" --min-age-hours 24 --no-learning 2>/dev/null \
    || echo "[analytics_briefing] TikTok sync skipped (token/scope missing or network error)" >&2
fi
if [[ "${SYNC_YOUTUBE:-1}" == "1" ]]; then
  "$PYTHON" "$ROOT/scripts/sync_youtube_stats.py" --min-age-hours 24 --no-learning 2>/dev/null \
    || echo "[analytics_briefing] YouTube sync skipped (token missing or network error)" >&2
fi

exec "$PYTHON" -m modules.Analytics_Tracker "$@"
