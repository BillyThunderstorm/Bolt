#!/bin/bash
# build_mac_app.sh — thin wrapper → bolt mac-app build (PARTIAL)
# Prefer: bolt mac-app status | build
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"
export PYTHONPATH="$PROJECT_DIR/Core${PYTHONPATH:+:$PYTHONPATH}"
PY="$PROJECT_DIR/.venv/bin/python3"
if [ ! -x "$PY" ]; then
  PY="$(command -v python3)"
fi
exec "$PY" -m modules.Bolt_Mac_App build "$@"
