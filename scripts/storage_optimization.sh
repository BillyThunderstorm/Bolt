#!/bin/bash
# Comprehensive Storage Optimization Script for Bolt
# Combines age-based cleanup, size-based limits, and deduplication
#
# Post-reorg paths (macOS-safe). Since 2026-10-20 every removal goes through
# Core/modules/Media_Retention.py: queued clips are skipped, age = Bolt creation
# time, and files are moved to the macOS Trash (never rm). This nightly job is
# Bolt's only age-based clip cleaner (launch.py no longer deletes on startup).

set -uo pipefail

# Resolve repo root even when invoked via scripts/maintenance/ symlink
_SOURCE="${BASH_SOURCE[0]}"
while [ -L "$_SOURCE" ]; do
  _DIR="$(cd -P "$(dirname "$_SOURCE")" && pwd)"
  _LINK="$(readlink "$_SOURCE")"
  [[ $_LINK != /* ]] && _SOURCE="$_DIR/$_LINK" || _SOURCE="$_LINK"
done
SCRIPT_DIR="$(cd -P "$(dirname "$_SOURCE")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# Configuration — canonical media layout
MEDIA_DIR="${MEDIA_DIR:-$REPO_ROOT/media}"
RECORDINGS_DIR="${RECORDINGS_DIR:-$MEDIA_DIR/Recordings}"
CLIPS_DIR="${CLIPS_DIR:-$MEDIA_DIR/clips}"
VERTICAL_CLIPS_DIR="${VERTICAL_CLIPS_DIR:-$MEDIA_DIR/vertical_clips}"
OUTPUT_DIR="${OUTPUT_DIR:-$MEDIA_DIR/output}"
MAX_RECORDINGS_GB="${MAX_RECORDINGS_GB:-50}"
MAX_CLIPS_GB="${MAX_CLIPS_GB:-5}"
MAX_RECORDINGS_DAYS="${MAX_RECORDINGS_DAYS:-30}"
MAX_CLIPS_DAYS="${MAX_CLIPS_DAYS:-14}"
# Optional archive of age-deleted copies is disabled by default; age cleanup deletes.
ARCHIVE_DIR="${ARCHIVE_DIR:-$MEDIA_DIR/archive}"
DRY_RUN=false
SKIP_DEDUP=false
SKIP_COMPRESS=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Media retention helper (2026-10-20): protects clips still in the post queue,
# ages files by Bolt's creation time (not a carried-over VOD mtime), and moves
# files to the macOS Trash instead of rm. Log: logs/media_retention.log
RETENTION_PY="${RETENTION_PY:-$REPO_ROOT/.venv/bin/python}"
[[ -x "$RETENTION_PY" ]] || RETENTION_PY="$(command -v python3)"
RETENTION="$REPO_ROOT/Core/modules/Media_Retention.py"
retention() {
    if [[ ! -f "$RETENTION" || -z "$RETENTION_PY" ]]; then
        echo -e "${RED}Media_Retention.py or python missing — skipping cleanup (nothing removed)${NC}"
        return 1
    fi
    "$RETENTION_PY" "$RETENTION" "$@"
}

# Function to get directory size in GB (cross-platform)
get_dir_size_gb() {
    local dir="$1"
    if [[ -d "$dir" ]]; then
        # Get size in kilobytes first, then convert to GB
        local size_kb
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS
            size_kb=$(du -sk "$dir" 2>/dev/null | cut -f1)
        else
            # Linux
            size_kb=$(du -sk "$dir" 2>/dev/null | cut -f1)
        fi
        
        # Convert KB to GB: KB / 1024 / 1024
        if [[ -n "$size_kb" && "$size_kb" -gt 0 ]]; then
            echo "$size_kb" | awk '{printf "%.1f", $1/1024/1024}'
        else
            echo "0"
        fi
    else
        echo "0"
    fi
}

# Function to get directory size in MB (for smaller items)
get_dir_size_mb() {
    local dir="$1"
    if [[ -d "$dir" ]]; then
        # Get size in kilobytes
        local size_kb
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS
            size_kb=$(du -sk "$dir" 2>/dev/null | cut -f1)
        else
            # Linux
            size_kb=$(du -sk "$dir" 2>/dev/null | cut -f1)
        fi
        
        # Convert KB to MB: KB / 1024
        if [[ -n "$size_kb" && "$size_kb" -gt 0 ]]; then
            echo "$size_kb" | awk '{printf "%.1f", $1/1024}'
        else
            echo "0"
        fi
    else
        echo "0"
    fi
}

# Function to get file size in bytes (cross-platform)
get_file_size_bytes() {
    local file="$1"
    if [[ -f "$file" ]]; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS: stat command
            stat -f%z "$file" 2>/dev/null || echo "0"
        else
            # Linux: stat command
            stat -c%s "$file" 2>/dev/null || echo "0"
        fi
    else
        echo "0"
    fi
}

# Function to get file size in MB
get_file_size_mb() {
    local file="$1"
    local bytes=$(get_file_size_bytes "$file")
    if [[ -n "$bytes" && "$bytes" -gt 0 ]]; then
        echo "$bytes" | awk '{printf "%.1f", $1/1024/1024}'
    else
        echo "0"
    fi
}

# Function to get file size in KB
get_file_size_kb() {
    local file="$1"
    local bytes=$(get_file_size_bytes "$file")
    if [[ -n "$bytes" && "$bytes" -gt 0 ]]; then
        echo "$bytes" | awk '{printf "%.1f", $1/1024}'
    else
        echo "0"
    fi
}

# Function to get oldest files in a directory (by modification time)
# macOS-safe (BSD stat); falls back to GNU find -printf on Linux.
get_oldest_files() {
    local dir="$1"
    if [[ ! -d "$dir" ]]; then
        return 0
    fi
    if stat -f '%m' "$dir" &>/dev/null; then
        find "$dir" -type f \( \
            -name "*.mp4" -o -name "*.mov" -o -name "*.mkv" -o -name "*.avi" -o \
            -name "*.m4v" -o -name "*.jpg" -o -name "*.png" -o -name "*.jpeg" \
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
            -name "*.m4v" -o -name "*.jpg" -o -name "*.png" -o -name "*.jpeg" \
        \) -printf '%T@\t%p\n' 2>/dev/null \
            | sort -n \
            | cut -f2-
    fi
}

# Function to get files older than X days
get_old_files() {
    local dir="$1"
    local days="$2"
    if [[ -d "$dir" ]]; then
        find "$dir" -type f \( -name "*.mp4" -o -name "*.mov" -o -name "*.mkv" -o -name "*.jpg" -o -name "*.png" -o -name "*.jpeg" \) -mtime +"$days" -print 2>/dev/null
    fi
}

# Function to calculate file hash
get_file_hash() {
    local file="$1"
    if [[ -f "$file" ]]; then
        if command -v gsha256sum &> /dev/null; then
            # macOS with coreutils
            gsha256sum "$file" 2>/dev/null | cut -d' ' -f1
        elif command -v shasum &> /dev/null; then
            # macOS default
            shasum -a 256 "$file" 2>/dev/null | cut -d' ' -f1
        else
            # Linux
            sha256sum "$file" 2>/dev/null | cut -d' ' -f1
        fi
    else
        echo ""
    fi
}

# Function to find and handle duplicates
find_and_handle_duplicates() {
    local dir="$1"
    local type="$2"
    
    if [[ ! -d "$dir" ]]; then
        echo -e "${YELLOW}Directory $dir does not exist, skipping deduplication...${NC}"
        return 0
    fi
    
    echo -e "${BLUE}Checking for duplicates in $type...${NC}"
    
    # Create temporary file to store hash -> file mappings
    local temp_file=$(mktemp)
    local duplicates_found=0
    local space_saved=0
    
    # Find all media files and calculate their hashes
    while IFS= read -r file; do
        if [[ -z "$file" ]]; then
            continue
        fi
        
        local file_hash=$(get_file_hash "$file")
        if [[ -n "$file_hash" ]]; then
            if grep -q "^$file_hash:" "$temp_file"; then
                # Duplicate found
                local original_file=$(grep "^$file_hash:" "$temp_file" | cut -d':' -f2-)
                local file_size=$(get_file_size_bytes "$file")
                local file_size_mb=$(get_file_size_mb "$file")
                
                echo -e "${YELLOW}Duplicate found: $file (original: $original_file)${NC}"
                
                if [[ "$DRY_RUN" = true ]]; then
                    retention trash-file "$file" --reason "duplicate of $original_file" --dry-run
                else
                    retention trash-file "$file" --reason "duplicate of $original_file"
                fi
                
                duplicates_found=$((duplicates_found + 1))
                space_saved=$((space_saved + file_size))
            else
                # First occurrence of this hash
                echo "$file_hash:$file" >> "$temp_file"
            fi
        fi
    done < <(find "$dir" -type f \( -name "*.mp4" -o -name "*.mov" -o -name "*.mkv" -o -name "*.jpg" -o -name "*.png" -o -name "*.jpeg" \) 2>/dev/null)
    
    # Clean up
    rm -f "$temp_file"
    
    if [[ $duplicates_found -gt 0 ]]; then
        local space_saved_mb=$(echo "$space_saved" | awk '{printf "%.1f", $1/1024/1024}')
        echo -e "${GREEN}Found $duplicates_found duplicates, saved ${space_saved_mb}MB${NC}"
    else
        echo -e "${GREEN}No duplicates found in $type${NC}"
    fi
    
    return $duplicates_found
}

# Function to enforce size limit — trashes oldest unqueued files via Media_Retention.
# (Files sit in the Trash until it is emptied; that is when disk space is freed.)
archive_files_by_size() {
    local dir="$1"
    local max_size_gb="$2"
    local type="$3"

    if [[ ! -d "$dir" ]]; then
        echo -e "${YELLOW}Directory $dir does not exist, skipping...${NC}"
        return 0
    fi
    local dry=""
    [[ "$DRY_RUN" = true ]] && dry="--dry-run"
    retention size --dir "$dir" --max-gb "$max_size_gb" --label "$type" $dry
    return 0
}

# Function to cleanup files by age — via Media_Retention (queue-protected, Trash)
cleanup_by_age() {
    local dir="$1"
    local max_days="$2"
    local type="$3"

    if [[ ! -d "$dir" ]]; then
        echo -e "${YELLOW}Directory $dir does not exist, skipping age-based cleanup...${NC}"
        return 0
    fi
    local dry=""
    [[ "$DRY_RUN" = true ]] && dry="--dry-run"
    retention age --dir "$dir" --days "$max_days" --label "$type" $dry
    return 0
}

# Function to compress media files (requires HandBrakeCLI or FFmpeg)
compress_media() {
    local dir="$1"
    local type="$2"
    
    if [[ -d "$dir" ]]; then
        # Check if compression tools are available
        if ! command -v HandBrakeCLI &> /dev/null && ! command -v ffmpeg &> /dev/null; then
            echo -e "${YELLOW}Neither HandBrakeCLI nor ffmpeg found. Skipping compression.${NC}"
            echo -e "${YELLOW}Install with: brew install handbrake  # or  brew install ffmpeg${NC}"
            return 0
        fi
        
        echo -e "${BLUE}Checking for compression opportunities in $type...${NC}"
        
        # Find uncompressed or potentially compressible files (limit to avoid overload)
        local compressible_files=$(find "$dir" -type f \( -name "*.mp4" -o -name "*.mov" -o -name "*.mkv" \) ! -name "*_compressed*" | head -20)  # Limit to first 20 for safety
        
        if [[ -z "$compressible_files" ]]; then
            echo -e "${GREEN}No compressible files found in $type${NC}"
            return 0
        fi
        
        local compressed_count=0
        local space_saved=0
        
        while IFS= read -r file; do
            if [[ -z "$file" ]]; then
                continue
            fi
            
            local original_size=$(get_file_size_bytes "$file")
            local original_size_mb=$(get_file_size_mb "$file")
            
            # Skip if too small (less than 1MB)
            local is_too_small=$(echo "$original_size < 1048576" | bc -l)
            if [[ "$is_too_small" -eq 1 ]]; then
                continue
            fi
            
            local output_file="${file%.mp4}_compressed.mp4"
            output_file="${output_file%.mov}_compressed.mp4"
            output_file="${output_file%.mkv}_compressed.mp4"
            
            echo -e "${BLUE}Compressing: $file (${original_size_mb}MB)${NC}"
            
            if [[ "$DRY_RUN" = true ]]; then
                echo -e "${YELLOW}[DRY RUN] Would compress: $file -> $output_file${NC}"
            else
                # Try HandBrakeCLI first, then ffmpeg
                if command -v HandBrakeCLI &> /dev/null; then
                    HandBrakeCLI -i "$file" -o "$output_file" --preset="Fast 1080p30" --encoder="x265" 2>/dev/null
                    local result=$?
                else
                    ffmpeg -i "$file" -c:v libx265 -crf 28 -preset medium -c:a aac -b:a 128k "$output_file" 2>/dev/null
                    local result=$?
                fi
                
                if [[ $result -eq 0 && -f "$output_file" ]]; then
                    local compressed_size=$(get_file_size_bytes "$output_file")
                    local compressed_size_mb=$(get_file_size_mb "$output_file")
                    local saved=$((original_size - compressed_size))
                    local saved_mb=$(echo "$saved" | awk '{printf "%.1f", $1/1024/1024}')
                    
                    space_saved=$((space_saved + saved))
                    
                    # Replace original with compressed version
                    mv "$output_file" "$file"
                    
                    echo -e "${GREEN}Compressed: $file (${original_size_mb}MB -> ${compressed_size_mb}MB, saved ${saved_mb}MB)${NC}"
                    ((compressed_count++))
                else
                    echo -e "${RED}Compression failed for: $file${NC}"
                    # Clean up failed output
                    rm -f "$output_file"
                fi
            fi
            
            # Progress update every 5 files
            if (( compressed_count % 5 == 0 )); then
                echo -e "${YELLOW}Progress: Compressed $compressed_count files, saved $(echo "$space_saved" | awk '{printf "%.1f", $1/1024/1024}')MB${NC}"
            fi
        done <<< "$compressible_files"
        
        if [[ "$DRY_RUN" = true ]]; then
            echo -e "${YELLOW}[DRY RUN] Would compress $compressed_count files, saving $(echo "$space_saved" | awk '{printf "%.1f", $1/1024/1024}')MB${NC}"
        else
            echo -e "${GREEN}Compressed $compressed_count files, saved $(echo "$space_saved" | awk '{printf "%.1f", $1/1024/1024}')MB${NC}"
        fi
        
        return $compressed_count
    else
        echo -e "${YELLOW}Directory $dir does not exist, skipping compression...${NC}"
        return 0
    fi
}

# Main execution
main() {
    echo -e "${GREEN}Starting Comprehensive Storage Optimization for Bolt${NC}"
    echo "========================================================"
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --skip-dedup)
                SKIP_DEDUP=true
                shift
                ;;
            --skip-compress)
                SKIP_COMPRESS=true
                shift
                ;;
            --recordings-gb)
                MAX_RECORDINGS_GB="$2"
                shift 2
                ;;
            --clips-gb)
                MAX_CLIPS_GB="$2"
                shift 2
                ;;
            --recordings-days)
                MAX_RECORDINGS_DAYS="$2"
                shift 2
                ;;
            --clips-days)
                MAX_CLIPS_DAYS="$2"
                shift 2
                ;;
            --archive-dir)
                ARCHIVE_DIR="$2"
                shift 2
                ;;
            *)
                echo "Unknown option: $1"
                echo "Usage: $0 [--dry-run] [--skip-dedup] [--skip-compress] [--recordings-gb GB] [--clips-gb GB] [--recordings-days DAYS] [--clips-days DAYS]"
                exit 1
                ;;
        esac
    done
    
    echo "Configuration:"
    echo "  Repo root: $REPO_ROOT"
    echo "  Recordings: $RECORDINGS_DIR  (limit ${MAX_RECORDINGS_GB}GB / ${MAX_RECORDINGS_DAYS}d)"
    echo "  Clips:      $CLIPS_DIR  (limit ${MAX_CLIPS_GB}GB / ${MAX_CLIPS_DAYS}d)"
    echo "  Dry run: $DRY_RUN"
    echo "  Skip deduplication: $SKIP_DEDUP"
    echo "  Skip compression: $SKIP_COMPRESS"
    echo ""
    
    # Track overall statistics
    local start_time=$(date +%s)
    
    # Step 1: Age-based cleanup (deletes old files → frees space)
    echo -e "${BLUE}=== STEP 1: Age-based cleanup ===${NC}"
    cleanup_by_age "$RECORDINGS_DIR" "$MAX_RECORDINGS_DAYS" "Recordings"
    cleanup_by_age "$CLIPS_DIR" "$MAX_CLIPS_DAYS" "Clips"
    cleanup_by_age "$VERTICAL_CLIPS_DIR" "$MAX_CLIPS_DAYS" "Vertical clips"
    echo ""
    
    # Step 2: Size-based enforcement (deletes oldest until under limit)
    echo -e "${BLUE}=== STEP 2: Size-based enforcement ===${NC}"
    archive_files_by_size "$RECORDINGS_DIR" "$MAX_RECORDINGS_GB" "Recordings"
    archive_files_by_size "$CLIPS_DIR" "$MAX_CLIPS_GB" "Clips"
    archive_files_by_size "$VERTICAL_CLIPS_DIR" "$MAX_CLIPS_GB" "Vertical clips"
    echo ""
    
    # Step 3: Deduplication (unless skipped)
    if [[ "$SKIP_DEDUP" = false ]]; then
        echo -e "${BLUE}=== STEP 3: Deduplication ===${NC}"
        find_and_handle_duplicates "$RECORDINGS_DIR" "Recordings"
        find_and_handle_duplicates "$CLIPS_DIR" "Clips"
        echo ""
    else
        echo -e "${YELLOW}=== SKIPPING DEDUPLICATION ===${NC}"
        echo ""
    fi
    
    # Step 4: Media compression (optional; expensive)
    if [[ "$SKIP_COMPRESS" = false ]]; then
        echo -e "${BLUE}=== STEP 4: Media compression ===${NC}"
        compress_media "$CLIPS_DIR" "Clips"
        # Skip compressing full recordings by default — huge and slow.
        echo -e "${YELLOW}Skipping recordings compression (use without --skip-compress only on clips).${NC}"
        echo ""
    else
        echo -e "${YELLOW}=== SKIPPING COMPRESSION ===${NC}"
        echo ""
    fi
    
    # Final summary
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    echo -e "${GREEN}Storage optimization completed!${NC}"
    echo "Duration: ${duration}s"
    echo ""
    echo -e "${BLUE}Final directory sizes:${NC}"
    echo "  Recordings: $(get_dir_size_gb "$RECORDINGS_DIR")GB  ($RECORDINGS_DIR)"
    echo "  Clips:      $(get_dir_size_gb "$CLIPS_DIR")GB  ($CLIPS_DIR)"
    echo "  Vertical:   $(get_dir_size_gb "$VERTICAL_CLIPS_DIR")GB  ($VERTICAL_CLIPS_DIR)"
    echo "  Free disk:  $(df -h / | awk 'NR==2 {print $4}')"
}

# Run main function with all arguments
main "$@"