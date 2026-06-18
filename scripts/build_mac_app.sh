#!/bin/bash
# build_mac_app.sh — Assemble Bolt.app for distribution
# ======================================================
# This copies the project into the app bundle so it is self-contained.
# The .app can be dragged to Applications and double-clicked.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="$PROJECT_DIR/dist/Bolt.app"
RESOURCES_DIR="$APP_DIR/Contents/Resources"
MACOS_DIR="$APP_DIR/Contents/MacOS"

echo "Building Bolt.app..."

# Ensure app structure exists
mkdir -p "$RESOURCES_DIR" "$MACOS_DIR"

# Copy project into Resources/Bolt (skip huge/unnecessary dirs)
if [ -d "$RESOURCES_DIR/Bolt" ]; then
    rm -rf "$RESOURCES_DIR/Bolt"
fi

echo "Copying project into app bundle..."
rsync -a \
    --exclude='.git' \
    --exclude='dist' \
    --exclude='build' \
    --exclude='__pycache__' \
    --exclude='.pytest_cache' \
    --exclude='*.pyc' \
    --exclude='archive' \
    --exclude='recordings' \
    --exclude='clips' \
    --exclude='vertical_clips' \
    --exclude='logs' \
    "$PROJECT_DIR/" "$RESOURCES_DIR/Bolt/"

# Make launcher executable
chmod +x "$MACOS_DIR/Bolt"

# Copy icon resources
if [ -f "$PROJECT_DIR/assets/AppIcon.icns" ]; then
    cp "$PROJECT_DIR/assets/AppIcon.icns" "$APP_DIR/Contents/Resources/"
fi
if [ -f "$PROJECT_DIR/assets/menu_bar_icon.png" ]; then
    cp "$PROJECT_DIR/assets/menu_bar_icon.png" "$APP_DIR/Contents/Resources/"
fi

echo "Bolt.app built at: $APP_DIR"
echo "Open with: open '$APP_DIR'"
