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

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-$ROOT/.venv/bin/python3}"

# Ensure deps are reachable (same pattern as other scripts in this repo).
export PYTHONPATH="$ROOT/Core:${PYTHONPATH:-}"

exec "$PYTHON" -m modules.Analytics_Tracker "$@"
