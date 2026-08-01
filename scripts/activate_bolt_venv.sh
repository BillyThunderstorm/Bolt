#!/bin/bash
# activate_bolt_venv.sh — Source Bolt's virtualenv and exec Python
#
# Two ways to invoke Bolt's Python:
#
#   1. PREFERRED — `uv run python <script>` or `uv run bolt <subcommand>`
#      Always uses the uv-managed Python pinned in .python-version and the
#      fully-resolved deps in uv.lock. This is the canonical path.
#
#   2. FALLBACK — Source this script, then call python normally:
#         source ./scripts/activate_bolt_venv.sh
#         python scripts/daily_briefing.py --print
#      Works without `uv` on the PATH, but you must have manually run
#      `uv sync` (or created .venv/ some other way) before this works.
#
# Usage:
#   ./scripts/activate_bolt_venv.sh <python-script-or-module> [args...]
#   uv run python <python-script-or-module> [args...]
#
# Set BOLT_USE_UV=0 to force this script to ignore `uv` even if it's installed.

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Prefer `uv run` when available so contributors always see the same Python
# interpreter and lock step. BOLT_USE_UV lets you opt out for debugging.
if [ "${BOLT_USE_UV:-1}" = "1" ] && command -v uv >/dev/null 2>&1; then
    exec uv --directory "$PROJECT_DIR" run python "$@"
fi

# Fallback: source the venv if it exists, then exec python3.
if [ -f "$PROJECT_DIR/.venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$PROJECT_DIR/.venv/bin/activate"
fi

exec python3 "$@"
