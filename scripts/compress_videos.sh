#!/bin/bash
# Video compression for Bolt — HandBrakeCLI on media/clips MP4s
# Soft-fail CLI: bolt compress (Core/modules/Video_Compress.py)
#
# Post-reorg: resolve through symlinks (scripts/media_processing/ → here)
# and use media/clips (not legacy bare clips/).

set -euo pipefail

export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:$PATH"

_SOURCE="${BASH_SOURCE[0]}"
while [ -L "$_SOURCE" ]; do
  _DIR="$(cd -P "$(dirname "$_SOURCE")" && pwd)"
  _LINK="$(readlink "$_SOURCE")"
  [[ $_LINK != /* ]] && _SOURCE="$_DIR/$_LINK" || _SOURCE="$_LINK"
done
SCRIPT_DIR="$(cd -P "$(dirname "$_SOURCE")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

CLIPS_DIR="${CLIPS_DIR:-$REPO_ROOT/media/clips}"
# Legacy fallback if media/clips missing
if [[ ! -d "$CLIPS_DIR" && -d "$REPO_ROOT/clips" ]]; then
  CLIPS_DIR="$REPO_ROOT/clips"
fi
BACKUP_DIR="${BACKUP_DIR:-$CLIPS_DIR/originals_backup}"
LOG_FILE="${LOG_FILE:-$REPO_ROOT/logs/video_compression.log}"
HANDBRAKE_CLI="${HANDBRAKE_CLI:-$(command -v HandBrakeCLI || true)}"
if [[ -z "${HANDBRAKE_CLI}" && -x /opt/homebrew/bin/HandBrakeCLI ]]; then
  HANDBRAKE_CLI="/opt/homebrew/bin/HandBrakeCLI"
fi

mkdir -p "${BACKUP_DIR}" "$(dirname "${LOG_FILE}")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_FILE}"
}

if [[ ! -d "$CLIPS_DIR" ]]; then
    log "ERROR: clips dir missing: $CLIPS_DIR"
    exit 0
fi

if [[ -z "${HANDBRAKE_CLI}" || ! -x "${HANDBRAKE_CLI}" ]]; then
    log "ERROR: HandBrakeCLI not found (brew install handbrake). Skipping."
    exit 0
fi

log "Starting video compression scan (clips=$CLIPS_DIR)"

# MP4s older than 5 minutes, not already backed up
find "${CLIPS_DIR}" -maxdepth 1 -name "*.mp4" -type f -mmin +5 2>/dev/null | while read -r file; do
    filename=$(basename "${file}")

    if [[ -f "${BACKUP_DIR}/${filename}" ]]; then
        log "Skipping ${filename} - already processed"
        continue
    fi

    log "Processing ${filename}"

    original_size=$(du -k "${file}" | cut -f1)
    original_size_mb=$(echo "scale=2; ${original_size}/1024" | bc)

    temp_output="${CLIPS_DIR}/${filename}.tmp.mp4"
    rm -f "${temp_output}"

    "${HANDBRAKE_CLI}" -i "${file}" -o "${temp_output}" --preset="Fast 1080p30" --quality 22 --optimize 2>>"${LOG_FILE}" || true

    if [[ ! -f "${temp_output}" ]]; then
        log "ERROR: Compression failed for ${filename}"
        continue
    fi

    compressed_size=$(du -k "${temp_output}" | cut -f1)
    compressed_size_mb=$(echo "scale=2; ${compressed_size}/1024" | bc)

    if [[ ${original_size} -gt 0 ]]; then
        savings_percent=$(echo "scale=2; (1 - (${compressed_size} * 1.0 / ${original_size})) * 100" | bc)
    else
        savings_percent=0
    fi

    log "Original size: ${original_size_mb} MB"
    log "Compressed size: ${compressed_size_mb} MB"
    log "Space saved: ${savings_percent}%"

    if (( $(echo "${savings_percent} > 10" | bc -l) )); then
        mv "${file}" "${BACKUP_DIR}/${filename}"
        mv "${temp_output}" "${file}"
        log "Successfully compressed and replaced ${filename}"
        log "Moved original to backup: ${BACKUP_DIR}/${filename}"
    else
        log "Compression did not save enough space (${savings_percent}%), keeping original"
        rm -f "${temp_output}"
    fi

    log "---"
done

log "Video compression scan completed"
