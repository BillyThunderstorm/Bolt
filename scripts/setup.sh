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
if [ ! -f "requirements.txt" ]; then
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
pip3 install -r requirements.txt --break-system-packages --quiet 2>/dev/null \
    || pip3 install -r requirements.txt --quiet
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
# macOS voice name — run: say -v ? to see options. Default: Nathan (Enhanced)
Bolt_VOICE=Nathan (Enhanced)
Bolt_VOICE_MUTE=false
ENVEOF
    echo "  ✓ .env created — open it and fill in your API keys!"
else
    echo "  ✓ .env already exists"
fi

# ── Verify config.json ────────────────────────────────────────────────────────
# Canonical config lives at Core/config.json. Never write a second copy
# at the repo root — it drifts (Marvel Rivals vs whatever you're playing).
if [ ! -f "Core/config.json" ] && [ ! -f "config.json" ]; then
    echo "  Creating Core/config.json..."
    mkdir -p Core
    cat > Core/config.json << 'CFGEOF'
{
  "game": "Gaming",
  "recordings_folder": "recordings",
  "clips_folder": "clips",
  "vertical_clips_folder": "vertical_clips",
  "auto_rank": true,
  "auto_format_tiktok": true,
  "highlight_sensitivity": 0.7,
  "use_obs_integration": true,
  "obs_host": "localhost",
  "obs_port": 4455,
  "tiktok_style": "letterbox",
  "min_clip_duration": 15,
  "max_clip_duration": 60,
  "min_clip_score": 65,
  "min_post_score": 65,
  "highlight": {
    "energy_multiplier": 3.5,
    "min_gap_seconds": 30,
    "sensitivity": 0.55,
    "min_confidence": 0.15,
    "pad_before": 8,
    "pad_after": 12
  },
  "quality_tiers": {
    "discard_below": 60,
    "queue_at": 80,
    "use_ai_titles": false
  },
  "peak_notifications": {
    "enabled": true,
    "windows": [
      {"label": "Morning", "start_hour": 7, "end_hour": 9},
      {"label": "Lunch", "start_hour": 12, "end_hour": 14},
      {"label": "Prime Time", "start_hour": 19, "end_hour": 22}
    ],
    "check_interval_minutes": 15,
    "discord_enabled": true
  },
  "use_voice_checklist": false,
  "whisper_model": "base",
  "notes": "TikTok auto-posting is off. Bolt formats clips, saves captions, and pings you at peak hours so you can post manually from the queue.",
  "hashtags": ["gaming", "clips", "viral", "trending"]
}
CFGEOF
    echo "  ✓ Core/config.json created"
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
echo "  Docs: docs/guides/SETUP_GUIDE.md"
echo "=================================================="
echo ""
