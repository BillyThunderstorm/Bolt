#!/bin/bash
# =============================================================================
#  cleanup_Bolt.sh — Remove junk files from Bolt folder
# =============================================================================
#
#  Run this from your Bolt folder to clean up:
#    - "Bolt 2/"         (old Xcode iOS project — 592MB, not needed)
#    - __pycache__/      (auto-regenerated Python junk)
#    - .DS_Store files   (macOS folder thumbnails, not needed)
#    - Empty log files
#
#  Usage:
#      cd /path/to/Bolt
#      bash scripts/cleanup_Bolt.sh
# =============================================================================

set -euo pipefail

Bolt_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo ""
echo "=================================================="
echo "  Bolt — Cleanup"
echo "=================================================="
echo "  Working in: ${Bolt_ROOT}"
echo ""

FREED=0

# ── Remove Bolt 2/ (old Xcode project + GitHub clones) ───────────────────────
Bolt2="${Bolt_ROOT}/Bolt 2"
if [ -d "${Bolt2}" ]; then
    SIZE=$(du -sh "${Bolt2}" 2>/dev/null | cut -f1)
    echo "  Removing 'Bolt 2/' (${SIZE} — old Xcode project, not needed)..."
    rm -rf "${Bolt2}"
    echo "  Freed ${SIZE}"
else
    echo "  'Bolt 2/' not found — already clean"
fi

# ── Remove __pycache__ ────────────────────────────────────────────────────────
echo ""
echo "  Removing __pycache__ folders (auto-regenerated Python junk)..."
find "${Bolt_ROOT}" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find "${Bolt_ROOT}" -name "*.pyc" -delete 2>/dev/null || true
echo "  Done"

# ── Remove .DS_Store files ────────────────────────────────────────────────────
echo ""
echo "  Removing .DS_Store files (macOS junk)..."
find "${Bolt_ROOT}" -name ".DS_Store" -delete 2>/dev/null || true
echo "  Done"

# ── Remove empty log files ────────────────────────────────────────────────────
echo ""
echo "  Removing empty log files..."
find "${Bolt_ROOT}/logs" -name "*.log" -empty -delete 2>/dev/null || true
echo "  Done"

# ── Final size check ──────────────────────────────────────────────────────────
echo ""
TOTAL=$(du -sh "${Bolt_ROOT}" 2>/dev/null | cut -f1)
echo "=================================================="
echo "  Cleanup complete!"
echo "  Bolt folder is now: ${TOTAL}"
echo ""
echo "  NOTE: recordings/ still contains your video files."
echo "  Delete those manually if you want to free more space."
echo "  (recordings/ is never synced to iCloud — only on this Mac)"
echo "=================================================="
echo ""
