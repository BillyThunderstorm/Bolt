#!/bin/bash
# =============================================================================
#  setup_icloud.sh — Move Bolt into iCloud Drive (run from the OTHER account)
# =============================================================================
#
#  Run this from the SECOND user account on this Mac, after
#  migrate_to_shared.sh has been run from the first account.
#
#  Usage (from the second account's Terminal):
#      bash /Users/Shared/Bolt/setup_icloud.sh
# =============================================================================

set -euo pipefail

SOURCE="/Users/Shared/Bolt"
ICLOUD="${HOME}/Library/Mobile Documents/com~apple~CloudDocs"
DEST="${ICLOUD}/Bolt"

echo ""
echo "=================================================="
echo "  Bolt — iCloud Drive Setup"
echo "=================================================="
echo "  Moving Bolt into your iCloud Drive so it syncs"
echo "  automatically to your other MacBook."
echo ""

# ── Check iCloud Drive is accessible ─────────────────────────────────────────
if [ ! -d "$ICLOUD" ]; then
    echo "  ⚠  iCloud Drive folder not found at:"
    echo "     ${ICLOUD}"
    echo ""
    echo "  Make sure you are:"
    echo "  1. Signed into iCloud on this account"
    echo "     (System Settings → Apple ID → iCloud → iCloud Drive ON)"
    echo "  2. Running this script from the correct account"
    echo ""
    exit 1
fi

echo "  ✓ iCloud Drive found"

# ── Check source exists ───────────────────────────────────────────────────────
if [ ! -d "$SOURCE" ]; then
    echo "  ⚠  /Users/Shared/Bolt not found."
    echo "     Run migrate_to_shared.sh from the other account first."
    exit 1
fi

# ── Confirm ───────────────────────────────────────────────────────────────────
echo "  From: ${SOURCE}"
echo "  To:   ${DEST}"
echo ""
read -p "  Move Bolt into iCloud Drive? (y/n) [y]: " CONFIRM
CONFIRM="${CONFIRM:-y}"
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "  Cancelled."
    exit 0
fi

# ── Move to iCloud Drive ──────────────────────────────────────────────────────
if [ -d "$DEST" ]; then
    echo "  Removing previous Bolt in iCloud Drive…"
    rm -rf "$DEST"
fi

echo "  Moving to iCloud Drive…"
cp -r "$SOURCE" "$DEST"
chmod -R 755 "$DEST"

# ── Install venv in the new location ─────────────────────────────────────────
echo ""
echo "  Setting up Python environment…"
cd "$DEST"

if [ ! -f "requirement.txt" ]; then
    echo "  ⚠  requirement.txt not found — skipping package install"
else
    pip3 install -r requirement.txt --break-system-packages --quiet 2>/dev/null \
        || pip3 install -r requirement.txt --quiet
    echo "  ✓ Python packages installed"
fi

# ── Clean up Shared folder ────────────────────────────────────────────────────
echo ""
read -p "  Remove the copy from /Users/Shared now? (y/n) [y]: " CLEANUP
CLEANUP="${CLEANUP:-y}"
if [[ "$CLEANUP" =~ ^[Yy]$ ]]; then
    rm -rf "$SOURCE"
    echo "  ✓ /Users/Shared/Bolt removed"
fi

echo ""
echo "=================================================="
echo "  ✓ Bolt is now in iCloud Drive!"
echo ""
echo "  Location: ${DEST}"
echo ""
echo "  iCloud will upload everything to Apple's servers."
echo "  Once it finishes (watch for the sync icon in Finder),"
echo "  Bolt will appear automatically in iCloud Drive on"
echo "  your other MacBook — no manual copying ever again."
echo ""
echo "  On the other MacBook:"
echo "  1. Open Finder → iCloud Drive → Bolt"
echo "  2. Open Terminal, drag the Bolt folder in, press Enter"
echo "  3. Run: bash scripts/setup.sh   (installs packages + creates .env)"
echo "  4. Edit .env with your API keys (copy from this Mac)"
echo "  5. Run: python3 launch.py"
echo "=================================================="
echo ""
