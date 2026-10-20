#!/bin/bash
# Media Rotation Script for Bolt
# Enforces size limits on media/ by removing oldest files first.
#
# Paths follow the post-reorg layout (see scripts/_paths.py):
#   media/Recordings, media/clips, media/vertical_clips
#
# macOS-safe (no GNU-only du -sb / find -printf).
#
# Since 2026-10-20 over-limit files are moved to the macOS Trash (oldest first
# by Bolt creation time, queued clips skipped) via Core/modules/Media_Retention.py.
# Disk space is freed when the Trash is emptied. Use --dry-run first.

set -euo pipefail

# ── Resolve repo root (works when invoked via scripts/maintenance/ symlink) ──
_SOURCE="${BASH_SOURCE[0]}"
while [ -L "$_SOURCE" ]; do
  _DIR="$(cd -P "$(dirname "$_SOURCE")" && pwd)"
  _LINK="$(readlink "$_SOURCE")"
  [[ $_LINK != /* ]] && _SOURCE="$_DIR/$_LINK" || _SOURCE="$_LINK"
done
SCRIPT_DIR="$(cd -P "$(dirname "$_SOURCE")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# ── Paths (canonical media layout) ───────────────────────────────────────────
MEDIA_DIR="${MEDIA_DIR:-$REPO_ROOT/media}"
RECORDINGS_DIR="${RECORDINGS_DIR:-$MEDIA_DIR/Recordings}"
CLIPS_DIR="${CLIPS_DIR:-$MEDIA_DIR/clips}"
VERTICAL_CLIPS_DIR="${VERTICAL_CLIPS_DIR:-$MEDIA_DIR/vertical_clips}"
OUTPUT_DIR="${OUTPUT_DIR:-$MEDIA_DIR/output}"
LOG_DIR="${LOG_DIR:-$REPO_ROOT/logs}"
LOG_FILE="$LOG_DIR/media_rotation.log"

MAX_RECORDINGS_GB="${MAX_RECORDINGS_GB:-50}"
MAX_CLIPS_GB="${MAX_CLIPS_GB:-5}"
MAX_VERTICAL_GB="${MAX_VERTICAL_GB:-5}"
MAX_OUTPUT_GB="${MAX_OUTPUT_GB:-5}"
DRY_RUN=false

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

mkdir -p "$LOG_DIR"

log() {
  local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
  echo -e "$msg" | tee -a "$LOG_FILE"
}

# Directory size in GB (macOS + Linux via du -sk)
get_dir_size_gb() {
  local dir="$1"
  if [[ -d "$dir" ]]; then
    local size_kb
    size_kb=$(du -sk "$dir" 2>/dev/null | cut -f1)
    size_kb=${size_kb:-0}
    awk -v kb="$size_kb" 'BEGIN { printf "%.2f", kb/1024/1024 }'
  else
    echo "0"
  fi
}

# Oldest media files first (macOS-safe; no find -printf)
get_oldest_files() {
  local dir="$1"
  [[ -d "$dir" ]] || return 0
  # stat -f is macOS; fall back to GNU stat -c
  if stat -f '%m' "$dir" &>/dev/null; then
    find "$dir" -type f \( \
      -name "*.mp4" -o -name "*.mov" -o -name "*.mkv" -o -name "*.avi" -o \
      -name "*.m4v" -o -name "*.jpg" -o -name "*.jpeg" -o -name "*.png" \
    \) -print0 2>/dev/null \
      | while IFS= read -r -d '' f; do
          mod=$(stat -f '%m' "$f" 2>/dev/null || echo 0)
          printf '%s\t%s\n' "$mod" "$f"
        done \
      | sort -n \
      | cut -f2-
  else
    find "$dir" -type f \( \
      -name "*.mp4" -o -name "*.mov" -o -name "*.mkv" -o -name "*.avi" -o \
      -name "*.m4v" -o -name "*.jpg" -o -name "*.jpeg" -o -name "*.png" \
    \) -printf '%T@\t%p\n' 2>/dev/null \
      | sort -n \
      | cut -f2-
  fi
}

get_file_bytes() {
  local file="$1"
  if [[ ! -f "$file" ]]; then
    echo 0
    return
  fi
  if stat -f%z "$file" &>/dev/null; then
    stat -f%z "$file"
  else
    stat -c%s "$file" 2>/dev/null || echo 0
  fi
}

# Trash oldest unqueued files until dir is under max_size_gb.
# Goes through Core/modules/Media_Retention.py (2026-10-20): clips still in the
# post queue are kept, age = Bolt creation time, files go to the macOS Trash.
RETENTION_PY="${RETENTION_PY:-$REPO_ROOT/.venv/bin/python}"
[[ -x "$RETENTION_PY" ]] || RETENTION_PY="$(command -v python3 || true)"
RETENTION="$REPO_ROOT/Core/modules/Media_Retention.py"

enforce_size_limit() {
  local dir="$1"
  local max_size_gb="$2"
  local type="$3"

  if [[ ! -d "$dir" ]]; then
    log "${YELLOW}$type: directory missing ($dir) — skip${NC}"
    return 0
  fi
  if [[ ! -f "$RETENTION" || -z "$RETENTION_PY" ]]; then
    log "${RED}$type: Media_Retention.py or python missing — nothing removed${NC}"
    return 0
  fi
  local dry=""
  [[ "$DRY_RUN" == true ]] && dry="--dry-run"
  local line
  while IFS= read -r line; do
    log "$type: $line"
  done < <("$RETENTION_PY" "$RETENTION" size --dir "$dir" --max-gb "$max_size_gb" --label "$type" $dry 2>&1 || true)
}

main() {
  while [[ $# -gt 0 ]]; do
    case $1 in
      --dry-run) DRY_RUN=true; shift ;;
      --recordings-gb) MAX_RECORDINGS_GB="$2"; shift 2 ;;
      --clips-gb) MAX_CLIPS_GB="$2"; shift 2 ;;
      --vertical-gb) MAX_VERTICAL_GB="$2"; shift 2 ;;
      --output-gb) MAX_OUTPUT_GB="$2"; shift 2 ;;
      -h|--help)
        echo "Usage: $0 [--dry-run] [--recordings-gb N] [--clips-gb N] [--vertical-gb N] [--output-gb N]"
        exit 0
        ;;
      *)
        echo "Unknown option: $1"
        exit 1
        ;;
    esac
  done

  log "Starting media rotation (repo=$REPO_ROOT dry_run=$DRY_RUN)"
  log "Recordings limit=${MAX_RECORDINGS_GB}GB clips=${MAX_CLIPS_GB}GB vertical=${MAX_VERTICAL_GB}GB output=${MAX_OUTPUT_GB}GB"

  enforce_size_limit "$RECORDINGS_DIR" "$MAX_RECORDINGS_GB" "Recordings"
  enforce_size_limit "$CLIPS_DIR" "$MAX_CLIPS_GB" "Clips"
  enforce_size_limit "$VERTICAL_CLIPS_DIR" "$MAX_VERTICAL_GB" "Vertical clips"
  enforce_size_limit "$OUTPUT_DIR" "$MAX_OUTPUT_GB" "Output"

  log "${GREEN}Media rotation finished${NC}"
}

main "$@"
