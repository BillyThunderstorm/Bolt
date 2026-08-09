#!/bin/bash
# Media Rotation Script for Bolt
# Enforces size limits on media/ by removing oldest files first.
#
# Paths follow the post-reorg layout (see scripts/_paths.py):
#   media/Recordings, media/clips, media/vertical_clips
#
# macOS-safe (no GNU-only du -sb / find -printf).
#
# NOTE: Moving files to an archive on the *same* volume does not free disk
# space. Size enforcement therefore *deletes* oldest media files once over
# the limit. Use --dry-run first.

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

# Delete oldest files until dir is under max_size_gb
enforce_size_limit() {
  local dir="$1"
  local max_size_gb="$2"
  local type="$3"

  if [[ ! -d "$dir" ]]; then
    log "${YELLOW}$type: directory missing ($dir) — skip${NC}"
    return 0
  fi

  local current_size
  current_size=$(get_dir_size_gb "$dir")
  log "${GREEN}$type: ${current_size}GB (limit ${max_size_gb}GB) — $dir${NC}"

  if ! command -v bc &>/dev/null; then
    log "${RED}bc not installed; cannot compare sizes. brew install bc${NC}"
    return 1
  fi

  if (( $(echo "$current_size <= $max_size_gb" | bc -l) )); then
    log "${GREEN}$type within limit${NC}"
    return 0
  fi

  log "${YELLOW}$type over limit — removing oldest files…${NC}"

  local freed_gb=0
  local removed=0
  local projected="$current_size"

  while IFS= read -r file; do
    [[ -z "$file" || ! -f "$file" ]] && continue
    if (( $(echo "$projected <= $max_size_gb" | bc -l) )); then
      break
    fi

    local bytes file_gb
    bytes=$(get_file_bytes "$file")
    file_gb=$(awk -v b="$bytes" 'BEGIN { printf "%.4f", b/1024/1024/1024 }')

    if [[ "$DRY_RUN" == true ]]; then
      log "${YELLOW}[DRY RUN] would remove: $file (${file_gb}GB)${NC}"
    else
      rm -f "$file"
      log "${GREEN}removed: $file (${file_gb}GB)${NC}"
    fi

    projected=$(echo "$projected - $file_gb" | bc -l)
    freed_gb=$(echo "$freed_gb + $file_gb" | bc -l)
    removed=$((removed + 1))
  done < <(get_oldest_files "$dir")

  local new_size
  new_size=$(get_dir_size_gb "$dir")
  if [[ "$DRY_RUN" == true ]]; then
    log "${YELLOW}[DRY RUN] $type: would remove $removed files (~${freed_gb}GB); size now ${new_size}GB (unchanged in dry-run)${NC}"
  else
    log "${GREEN}$type: removed $removed files (~${freed_gb}GB); now ${new_size}GB${NC}"
  fi
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
