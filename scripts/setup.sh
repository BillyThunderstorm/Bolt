#!/bin/bash
# =============================================================================
#  setup.sh — Bolt first-time setup (works on any Mac, including from iCloud)
# =============================================================================
#
#  Run this once after cloning or downloading Bolt:
#      cd ~/Library/"Mobile Documents"/com~apple~CloudDocs/Bolt
#      bash scripts/setup.sh
# =============================================================================

set -euo pipefail

echo ""
echo "=================================================="
echo "  Bolt — Setup"
echo "=================================================="

# ── Check we're in the right place ───────────────────────────────────────────
if [ ! -f "requirement.txt" ]; then
    echo "  ⚠  Run this script from the Bolt root folder."
    echo "     cd path/to/Bolt && bash scripts/setup.sh"
    exit 1
fi

# ── Check Python ──────────────────────────────────────────────────────────────
if ! command -v python3 &> /dev/null; then
    echo "  ⚠  Python 3 not found."
    echo "     Install it from: https://www.python.org/downloads/"
    exit 1
fi
echo "  ✓ Python: $(python3 --version)"

# ── Create output directories ─────────────────────────────────────────────────
echo "  Creating folders..."
mkdir -p recordings clips vertical_clips assets logs data
echo "  ✓ Folders ready"

# ── Install Python dependencies ───────────────────────────────────────────────
echo "  Installing Python packages..."
pip3 install -r requirement.txt --break-system-packages --quiet 2>/dev/null \
    || pip3 install -r requirement.txt --quiet
echo "  ✓ Packages installed"

# ── Set up .env if missing ────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    echo "  Creating .env from template..."
    cat > .env << 'ENVEOF'
# ── Anthropic (Claude AI) ─────────────────────────────────────────────────────
ANTHROPIC_API_KEY=your_key_here

# ── Twitch ────────────────────────────────────────────────────────────────────
TWITCH_CLIENT_ID=your_client_id_here
TWITCH_CLIENT_SECRET=your_client_secret_here
TWITCH_CHANNEL=BillyandRandy

# ── OBS WebSocket ─────────────────────────────────────────────────────────────
OBS_PASSWORD=your_obs_password_here

# ── Streamlabs ────────────────────────────────────────────────────────────────
STREAMLABS_SOCKET_TOKEN=your_streamlabs_token_here

# ── Discord (peak-hour clip alerts) ──────────────────────────────────────────
DISCORD_WEBHOOK_URL=your_discord_webhook_here

# ── Bolt Chat Bot (Phase 3) ───────────────────────────────────────────────────
# Run: python3 scripts/get_twitch_token.py  to generate these
TWITCH_BOT_TOKEN=
TWITCH_BOT_NAME=

# ── Bolt Voice (optional) ─────────────────────────────────────────────────────
# macOS voice name — run: say -v ? to see options. Default: Samantha
Bolt_VOICE=Samantha
Bolt_VOICE_MUTE=false
ENVEOF
    echo "  ✓ .env created — open it and fill in your API keys!"
else
    echo "  ✓ .env already exists"
fi

# ── Verify config.json ────────────────────────────────────────────────────────
if [ ! -f "config.json" ]; then
    echo "  Creating config.json..."
    cat > config.json << 'CFGEOF'
{
  "game": "Marvel Rivals",
  "auto_rank": true,
  "auto_format_tiktok": true,
  "highlight_sensitivity": 0.7,
  "use_obs_integration": true,
  "peak_hour_windows": [
    {"start": "07:00", "end": "09:00"},
    {"start": "12:00", "end": "14:00"},
    {"start": "19:00", "end": "22:00"}
  ],
  "hashtags": ["#gaming", "#clips", "#viral", "#trending"]
}
CFGEOF
    echo "  ✓ config.json created"
else
    echo "  ✓ config.json already exists"
fi

echo ""
echo "=================================================="
echo "  ✓ Setup complete!"
echo ""
echo "  Next steps:"
echo "  1. Edit .env with your API keys"
echo "     (copy them from your other Mac's .env)"
echo "  2. Run Bolt: python3 launch.py"
echo ""
echo "  Docs: docs/SETUP_GUIDE.md"
echo "=================================================="
echo ""
