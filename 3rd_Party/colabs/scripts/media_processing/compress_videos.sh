#!/bin/bash

# Video compression script for Bolt
# Uses HandBrakeCLI to compress new MP4 files in the clips directory

set -euo pipefail

# Set PATH to include homebrew binaries (needed for cron execution)
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:$PATH"

CLIPS_DIR="/Users/carter/developer/Bolt/clips"
BACKUP_DIR="${CLIPS_DIR}/originals_backup"
LOG_FILE="/Users/carter/developer/Bolt/logs/video_compression.log"
HANDBRAKE_CLI="/opt/homebrew/bin/HandBrakeCLI"

# Create backup directory if it doesn't exist
mkdir -p "${BACKUP_DIR}"

# Log function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_FILE}"
}

log "Starting video compression scan"

# Find MP4 files newer than 5 minutes old (to avoid copying incomplete files)
# and that don't have a backup already (meaning they haven't been processed)
find "${CLIPS_DIR}" -maxdepth 1 -name "*.mp4" -type f -mmin +5 | while read -r file; do
    # Get just the filename
    filename=$(basename "${file}")
    
    # Check if we've already backed up this file (indicating it's been processed)
    if [[ -f "${BACKUP_DIR}/${filename}" ]]; then
        log "Skipping ${filename} - already processed"
        continue
    fi
    
    log "Processing ${filename}"
    
    # Get original size
    original_size=$(du -k "${file}" | cut -f1)
    original_size_mb=$(echo "scale=2; ${original_size}/1024" | bc)
    
    # Create temporary output file
    temp_output="${CLIPS_DIR}/${filename}.tmp.mp4"
    
    # Compress with HandBrakeCLI
    # Using Fast 1080p30 preset with constant quality 22 (good balance)
    # We'll also optimize for web
    "${HANDBRAKE_CLI}" -i "${file}" -o "${temp_output}" --preset="Fast 1080p30" --quality 22 --optimize 2>>"${LOG_FILE}"
    
    # Check if compression succeeded
    if [[ ! -f "${temp_output}" ]]; then
        log "ERROR: Compression failed for ${filename}"
        continue
    fi
    
    # Get compressed size
    compressed_size=$(du -k "${temp_output}" | cut -f1)
    compressed_size_mb=$(echo "scale=2; ${compressed_size}/1024" | bc)
    
    # Calculate savings
    if [[ ${original_size} -gt 0 ]]; then
        savings_percent=$(echo "scale=2; (1 - (${compressed_size} * 1.0 / ${original_size})) * 100" | bc)
    else
        savings_percent=0
    fi
    
    log "Original size: ${original_size_mb} MB"
    log "Compressed size: ${compressed_size_mb} MB"
    log "Space saved: ${savings_percent}%"
    
    # Only replace if we saved at least 10% space (to avoid making files larger)
    if (( $(echo "${savings_percent} > 10" | bc -l) )); then
        # Move original to backup
        mv "${file}" "${BACKUP_DIR}/${filename}"
        
        # Move compressed file to original location
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
