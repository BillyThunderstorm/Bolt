#!/bin/bash
# activate_bolt_venv.sh — Source Bolt's virtualenv and exec Python
# Usage: ./scripts/activate_bolt_venv.sh <python_script> [args...]

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [ -f "$PROJECT_DIR/.venv/bin/activate" ]; then
    source "$PROJECT_DIR/.venv/bin/activate"
fi

exec python3 "$@"
