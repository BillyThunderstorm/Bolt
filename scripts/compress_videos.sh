#!/bin/bash
# Clip compression for Bolt — cron entry point (every 30 min).
# Thin wrapper: the real work is Core/modules/Video_Compress.py (`bolt compress`).
#   * ffmpeg-full (libx264 CRF 22, keeps frame rate) first; HandBrakeCLI only
#     if no ffmpeg works.
#   * keeps a smaller copy only when it is >=10% smaller and the same length;
#     originals go to media/clips/originals_backup/ (`bolt compress clean-backups`).
#   * quiet when nothing is new; writes its own lines to logs/video_compression.log
#     (so the cron `>> log` redirect doesn't double every line).

set -uo pipefail
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:$PATH"

_SOURCE="${BASH_SOURCE[0]}"
while [ -L "$_SOURCE" ]; do
  _DIR="$(cd -P "$(dirname "$_SOURCE")" && pwd)"
  _LINK="$(readlink "$_SOURCE")"
  [[ $_LINK != /* ]] && _SOURCE="$_DIR/$_LINK" || _SOURCE="$_LINK"
done
SCRIPT_DIR="$(cd -P "$(dirname "$_SOURCE")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PY="$REPO_ROOT/.venv/bin/python"
[[ -x "$PY" ]] || PY="$(command -v python3)"

cd "$REPO_ROOT" || exit 0
# Heartbeat: the run is quiet when nothing is new, so the log alone can't show
# cron is still firing. `bolt mac-auto status` reads this file.
mkdir -p "$REPO_ROOT/logs/heartbeats" 2>/dev/null && date '+%Y-%m-%d %H:%M:%S' > "$REPO_ROOT/logs/heartbeats/compress_videos.last" 2>/dev/null || true
PYTHONPATH="$REPO_ROOT/Core${PYTHONPATH:+:$PYTHONPATH}" \
  exec "$PY" -m modules.Video_Compress run --cron "$@"
