#!/bin/bash
# =============================================================================
#  migrate_to_shared.sh — Move Bolt to /Users/Shared
# =============================================================================
#
#  Run this from YOUR account (the one Bolt is on now).
#  It copies Bolt to /Users/Shared/ so the other account on this Mac
#  can pick it up and move it into their iCloud Drive.
#
#  Usage:
#      cd ~/Desktop/Bolt
#      bash migrate_to_shared.sh
# =============================================================================

set -euo pipefail

Bolt_SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARED_DEST="/Users/Shared/Bolt"

echo ""
echo "=================================================="
echo "  Bolt — Migrate to /Users/Shared"
echo "=================================================="
echo "  From: ${Bolt_SOURCE}"
echo "  To:   ${SHARED_DEST}"
echo ""

# ── Confirm ───────────────────────────────────────────────────────────────────
read -p "  Copy Bolt to /Users/Shared now? (y/n) [y]: " CONFIRM
CONFIRM="${CONFIRM:-y}"
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "  Cancelled."
    exit 0
fi

# ── Remove old copy if exists ─────────────────────────────────────────────────
if [ -d "$SHARED_DEST" ]; then
    echo "  Removing previous copy in /Users/Shared/Bolt…"
    rm -rf "$SHARED_DEST"
fi

# ── Copy everything except large generated folders ────────────────────────────
echo "  Copying Bolt files…"
mkdir -p "$SHARED_DEST"

rsync -av \
    --exclude='.venv/' \
    --exclude='.venv-1/' \
    --exclude='.venv-6/' \
    --exclude='venv/' \
    --exclude='recordings/' \
    --exclude='clips/' \
    --exclude='vertical_clips/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.DS_Store' \
    "${Bolt_SOURCE}/" "${SHARED_DEST}/"

# ── Make everything readable/writable by all users on this Mac ───────────────
chmod -R 777 "$SHARED_DEST"

echo ""
echo "  ✓ Bolt copied to /Users/Shared/Bolt"
echo ""
echo "=================================================="
echo "  NEXT STEPS:"
echo ""
echo "  1. Log into the other account on this Mac"
echo "     (or use Fast User Switching — Apple menu → your name)"
echo ""
echo "  2. Open Terminal in that account and run:"
echo ""
echo "     bash /Users/Shared/Bolt/setup_icloud.sh"
echo ""
echo "  That will move Bolt into that account's iCloud Drive"
echo "  and set everything up. The other MacBook will sync"
echo "  automatically once iCloud finishes uploading."
echo "=================================================="
echo ""
