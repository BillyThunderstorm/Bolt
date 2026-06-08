#!/bin/bash
# Media Rotation Script for Bolt
# Automatically rotates and archives old media files to maintain storage limits

# Configuration
RECORDINGS_DIR="recordings"
CLIPS_DIR="clips"
MAX_RECORDINGS_GB=50
MAX_CLIPS_GB=1
ARCHIVE_DIR="archive"
DRY_RUN=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to get directory size in GB
get_dir_size_gb() {
    local dir="$1"
    if [[ -d "$dir" ]]; then
        du -sb "$dir" | awk '{print $1/1024/1024/1024}'
    else
        echo "0"
    fi
}

# Function to get oldest files in a directory
get_oldest_files() {
    local dir="$1"
    if [[ -d "$dir" ]]; then
        find "$dir" -type f \( -name "*.mp4" -o -name "*.mov" -o -name "*.mkv" -o -name "*.jpg" -o -name "*.png" \) -printf '%T@ %p\n' | sort -n | cut -d' ' -f2-
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
    
    local current_size=$(get_dir_size_gb "$dir")
    
    if (( $(echo "$current_size <= $max_size_gb" | bc -l) )); then
        echo -e "${GREEN}$type directory is within limit: ${current_size}GB <= ${max_size_gb}GB${NC}"
        return 0
    fi
    
    echo -e "${YELLOW}$type directory exceeds limit: ${current_size}GB > ${max_size_gb}GB${NC}"
    echo -e "${YELLOW}Starting archival process for $type...${NC}"
    
    # Create archive directory if it doesn't exist
    mkdir -p "$ARCHIVE_DIR/$dir"
    
    # Get list of files sorted by oldest first
    local files=$(get_oldest_files "$dir")
    local to_archive_size=0
    local archived_count=0
    
    while IFS= read -r file; do
        if [[ -z "$file" ]]; then
            continue
        fi
        
        local file_size=$(du -b "$file" | awk '{print $1}')
        local file_size_gb=$(echo "$file_size/1024/1024/1024" | bc -l)
        
        # Check if we need to archive more files
        local projected_size=$(echo "$current_size - $to_archive_size" | bc -l)
        if (( $(echo "$projected_size <= $max_size_gb" | bc -l) )); then
            break
        fi
        
        # Archive the file
        if [[ "$DRY_RUN" = true ]]; then
            echo -e "${YELLOW}[DRY RUN] Would archive: $file (${file_size_gb}GB)${NC}"
        else
            mkdir -p "$(dirname "$ARCHIVE_DIR/$file")"
            mv "$file" "$ARCHIVE_DIR/$file/"
            echo -e "${GREEN}Archived: $file (${file_size_gb}GB)${NC}"
        fi
        
        to_archive_size=$(echo "$to_archive_size + $file_size_gb" | bc -l)
        ((archived_count++))
        
        # Progress update every 10 files
        if (( archived_count % 10 == 0 )); then
            echo -e "${YELLOW}Progress: Archived $archived_count files, freed $(echo "$to_archive_size" | bc -l)GB${NC}"
        fi
    done <<< "$files"
    
    if [[ "$DRY_RUN" = true ]]; then
        echo -e "${YELLOW}[DRY RUN] Would archive $archived_count files, freeing $(echo "$to_archive_size" | bc -l)GB${NC}"
    else
        echo -e "${GREEN}Archived $archived_count files, freed $(echo "$to_archive_size" | bc -l)GB${NC}"
    fi
    
    # Verify new size
    local new_size=$(get_dir_size_gb "$dir")
    echo -e "${GREEN}New $type directory size: ${new_size}GB${NC}"
}

# Main execution
main() {
    echo -e "${GREEN}Starting Bolt Media Rotation Script${NC}"
    echo "========================================"
    
    # Parse arguments
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
    echo "  Recordings limit: ${MAX_RECORDINGS_GB}GB"
    echo "  Clips limit: ${MAX_CLIPS_GB}GB"
    echo "  Archive directory: $ARCHIVE_DIR"
    echo "  Dry run: $DRY_RUN"
    echo ""
    
    # Process recordings
    archive_files "$RECORDINGS_DIR" "$MAX_RECORDINGS_GB" "Recordings"
    echo ""
    
    # Process clips
    archive_files "$CLIPS_DIR" "$MAX_CLIPS_GB" "Clips"
    echo ""
    
    echo -e "${GREEN}Media rotation completed!${NC}"
}

# Run main function with all arguments
main "$@"