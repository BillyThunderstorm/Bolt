#!/bin/bash
# Media Rotation Script for Bolt
# Automatically rotates and archives old media files to maintain storage limits
# Paths aligned with scripts/_paths.py (post-reorg layout)

# Configuration — matches _paths.py
RECORDINGS_DIR="media/Recordings"
CLIPS_DIR="media/clips"
MAX_RECORDINGS_GB=50
MAX_CLIPS_GB=1
ARCHIVE_DIR="Data/archive"
DRY_RUN=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Ensure we run from repo root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$REPO_ROOT" || exit 1

# Function to get directory size in GB (cross-platform)
get_dir_size_gb() {
    local dir="$1"
    if [[ -d "$dir" ]]; then
        local size_kb
        size_kb=$(du -sk "$dir" 2>/dev/null | cut -f1)
        if [[ -n "$size_kb" && "$size_kb" -gt 0 ]]; then
            echo "$size_kb" | awk '{printf "%.2f", $1/1024/1024}'
        else
            echo "0"
        fi
    else
        echo "0"
    fi
}

# Function to get oldest files (macOS + Linux compatible)
get_oldest_files() {
    local dir="$1"
    if [[ ! -d "$dir" ]]; then
        return
    fi
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        find "$dir" -type f \( -name "*.mp4" -o -name "*.mov" -o -name "*.mkv" -o -name "*.jpg" -o -name "*.png" -o -name "*.jpeg" \) -exec stat -f '%m %N' {} \; 2>/dev/null | sort -n | cut -d' ' -f2-
    else
        # Linux
        find "$dir" -type f \( -name "*.mp4" -o -name "*.mov" -o -name "*.mkv" -o -name "*.jpg" -o -name "*.png" -o -name "*.jpeg" \) -printf '%T@ %p\n' 2>/dev/null | sort -n | cut -d' ' -f2-
    fi
}

# Function to archive files
archive_files() {
    local dir="$1"
    local max_size_gb="$2"
    local type="$3"

    if [[ ! -d "$dir" ]]; then
        echo -e "${YELLOW}Directory $dir does not exist, skipping...${NC}"
        return 0
    fi

    local current_size
    current_size=$(get_dir_size_gb "$dir")

    if (( $(echo "$current_size <= $max_size_gb" | bc -l) )); then
        echo -e "${GREEN}$type directory is within limit: ${current_size}GB <= ${max_size_gb}GB${NC}"
        return 0
    fi

    echo -e "${YELLOW}$type directory exceeds limit: ${current_size}GB > ${max_size_gb}GB${NC}"
    echo -e "${YELLOW}Starting archival process for $type...${NC}"

    mkdir -p "$ARCHIVE_DIR/$dir"

    local files
    files=$(get_oldest_files "$dir")
    local to_archive_size=0
    local archived_count=0

    while IFS= read -r file; do
        if [[ -z "$file" ]]; then
            continue
        fi

        local file_size_bytes
        if [[ "$OSTYPE" == "darwin"* ]]; then
            file_size_bytes=$(stat -f%z "$file" 2>/dev/null || echo 0)
        else
            file_size_bytes=$(stat -c%s "$file" 2>/dev/null || echo 0)
        fi
        local file_size_gb
        file_size_gb=$(echo "$file_size_bytes" | awk '{printf "%.4f", $1/1024/1024/1024}')

        local projected_size
        projected_size=$(echo "$current_size - $to_archive_size" | bc -l)
        if (( $(echo "$projected_size <= $max_size_gb" | bc -l) )); then
            break
        fi

        if [[ "$DRY_RUN" = true ]]; then
            echo -e "${YELLOW}[DRY RUN] Would archive: $file (${file_size_gb}GB)${NC}"
        else
            mkdir -p "$(dirname "$ARCHIVE_DIR/$file")"
            mv "$file" "$ARCHIVE_DIR/$file"
            echo -e "${GREEN}Archived: $file (${file_size_gb}GB)${NC}"
        fi

        to_archive_size=$(echo "$to_archive_size + $file_size_gb" | bc -l)
        ((archived_count++))

        if (( archived_count % 10 == 0 )); then
            echo -e "${YELLOW}Progress: Archived $archived_count files, freed ${to_archive_size}GB${NC}"
        fi
    done <<< "$files"

    if [[ "$DRY_RUN" = true ]]; then
        echo -e "${YELLOW}[DRY RUN] Would archive $archived_count files, freeing ${to_archive_size}GB${NC}"
    else
        echo -e "${GREEN}Archived $archived_count files, freed ${to_archive_size}GB${NC}"
    fi

    local new_size
    new_size=$(get_dir_size_gb "$dir")
    echo -e "${GREEN}New $type directory size: ${new_size}GB${NC}"
}

# Main execution
main() {
    echo -e "${GREEN}Starting Bolt Media Rotation Script${NC}"
    echo "========================================"
    echo "Repo root: $REPO_ROOT"

    while [[ $# -gt 0 ]]; do
        case $1 in
            --dry-run)
                DRY_RUN=true
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
            --archive-dir)
                ARCHIVE_DIR="$2"
                shift 2
                ;;
            *)
                echo "Unknown option: $1"
                echo "Usage: $0 [--dry-run] [--recordings-gb GB] [--clips-gb GB] [--archive-dir PATH]"
                exit 1
                ;;
        esac
    done

    echo "Configuration:"
    echo "  Recordings: $RECORDINGS_DIR (limit ${MAX_RECORDINGS_GB}GB)"
    echo "  Clips:      $CLIPS_DIR (limit ${MAX_CLIPS_GB}GB)"
    echo "  Archive:    $ARCHIVE_DIR"
    echo "  Dry run:    $DRY_RUN"
    echo ""

    archive_files "$RECORDINGS_DIR" "$MAX_RECORDINGS_GB" "Recordings"
    echo ""
    archive_files "$CLIPS_DIR" "$MAX_CLIPS_GB" "Clips"
    echo ""

    echo -e "${GREEN}Media rotation completed!${NC}"
}

main "$@"
