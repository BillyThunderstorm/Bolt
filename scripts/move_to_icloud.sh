#!/bin/bash
# =============================================================================
#  move_to_icloud.sh — Move Bolt into iCloud Drive (run ONCE on your main Mac)
# =============================================================================
#
#  This moves the entire Bolt folder into your iCloud Drive.
#  After that, iCloud syncs it automatically to your other MacBook.
#
#  Usage (run from inside your Bolt folder):
#      bash scripts/move_to_icloud.sh
#
#  What this does:
#    1. Copies Bolt into ~/iCloud Drive/Bolt
#    2. Skips recordings/ (too large for iCloud — keep locally)
#    3. Leaves your current folder in place (safe — doesn't delete anything)
#    4. Tells you exactly what to do next on the other Mac
# =============================================================================

set -euo pipefail

Bolt_SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ICLOUD="${HOME}/Library/Mobile Documents/com~apple~CloudDocs"
DEST="${ICLOUD}/Bolt"

echo ""
echo "=================================================="
echo "  Bolt — Move to iCloud Drive"
echo "=================================================="
echo ""

# ── Check iCloud Drive is accessible ─────────────────────────────────────────
if [ ! -d "$ICLOUD" ]; then
    echo "  ERROR: iCloud Drive not found."
    echo ""
    echo "  To fix this:"
    echo "  1. Go to System Settings → Apple ID"
    echo "  2. Click iCloud → iCloud Drive → turn it ON"
    echo "  3. Run this script again"
    echo ""
    exit 1
fi

echo "  iCloud Drive: found"
echo "  Moving from:  ${Bolt_SOURCE}"
echo "  Moving to:    ${DEST}"
echo ""
echo "  NOTE: recordings/ will be SKIPPED (they're too large for iCloud)."
echo "  Your video files stay on this Mac. Clips go to iCloud just fine."
echo ""

read -p "  Ready? Move Bolt to iCloud Drive? (y/n) [y]: " CONFIRM
CONFIRM="${CONFIRM:-y}"
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "  Cancelled — nothing was changed."
    exit 0
fi

# ── Copy to iCloud (skip recordings, pycache, .DS_Store) ─────────────────────
echo ""
echo "  Copying files to iCloud Drive..."
echo "  (This may take a moment — skipping recordings and junk files)"
echo ""

rsync -av \
    --exclude='recordings/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.DS_Store' \
    --exclude='.venv/' \
    --exclude='venv/' \
    --exclude='Bolt 2/' \
    --exclude='logs/*.log' \
    "${Bolt_SOURCE}/" "${DEST}/"

chmod -R 755 "${DEST}"

# ── Preserve the .env (make sure it copied) ──────────────────────────────────
if [ -f "${Bolt_SOURCE}/.env" ] && [ ! -f "${DEST}/.env" ]; then
    cp "${Bolt_SOURCE}/.env" "${DEST}/.env"
    echo "  .env copied"
fi

echo ""
echo "=================================================="
echo "  Bolt is now in iCloud Drive!"
echo ""
echo "  Location: ${DEST}"
echo ""
echo "  iCloud will start uploading now. Watch for the"
echo "  cloud icon next to Bolt in Finder. Once it shows"
echo "  a checkmark, it's fully synced."
echo ""
echo "  ─────────────────────────────────────────────────"
echo "  On your OTHER MacBook:"
echo "  ─────────────────────────────────────────────────"
echo "  1. Open Finder → iCloud Drive → Bolt"
echo "     (wait for sync to finish — checkmark icon)"
echo ""
echo "  2. Open Terminal and run:"
echo "     cd ~/Library/Mobile\ Documents/com~apple~CloudDocs/Bolt"
echo "     bash scripts/setup.sh"
echo ""
echo "  3. Your .env is already synced — just check it:"
echo "     nano .env"
echo "     (update OBS_PASSWORD if it's different on that Mac)"
echo ""
echo "  4. Run Bolt:"
echo "     python3 launch.py"
echo ""
echo "  IMPORTANT: On the other Mac, recordings/ will be empty."
echo "  That Mac can still process clips you manually copy there,"
echo "  or you can use it for editing, reviewing, and posting."
echo "=================================================="
echo ""
