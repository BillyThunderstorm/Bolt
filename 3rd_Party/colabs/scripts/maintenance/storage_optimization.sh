#!/bin/bash
# Comprehensive Storage Optimization Script for Bolt
# Combines age-based cleanup, size-based limits, and deduplication

# Configuration
RECORDINGS_DIR="recordings"
CLIPS_DIR="clips"
MAX_RECORDINGS_GB=50
MAX_CLIPS_GB=1
MAX_RECORDINGS_DAYS=30
MAX_CLIPS_DAYS=7
ARCHIVE_DIR="archive"
DRY_RUN=false
SKIP_DEDUP=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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
get_oldest_files() {
    local dir="$1"
    if [[ -d "$dir" ]]; then
        find "$dir" -type f \( -name "*.mp4" -o -name "*.mov" -o -name "*.mkv" -o -name "*.jpg" -o -name "*.png" -o -name "*.jpeg" \) -printf '%T@ %p\n' 2>/dev/null | sort -n | cut -d' ' -f2-
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
                    echo -e "${YELLOW}[DRY RUN] Would remove duplicate: $file (${file_size_mb}MB)${NC}"
                else
                    rm "$file"
                    echo -e "${GREEN}Removed duplicate: $file (${file_size_mb}MB)${NC}"
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

# Function to archive files (size-based)
archive_files_by_size() {
    local dir="$1"
    local max_size_gb="$2"
    local type="$3"
    
    if [[ -d "$dir" ]]; then
        local current_size=$(get_dir_size_gb "$dir")
        
        # Check if current_size is a valid number
        if ! [[ "$current_size" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
            echo -e "${YELLOW}Could not determine size for $dir, skipping...${NC}"
            return 0
        fi
        
        # Compare using bc for floating point
        local within_limit=$(echo "$current_size <= $max_size_gb" | bc -l)
        
        if [[ "$within_limit" -eq 1 ]]; then
            echo -e "${GREEN}$type directory is within size limit: ${current_size}GB <= ${max_size_gb}GB${NC}"
            return 0
        fi
        
        echo -e "${YELLOW}$type directory exceeds size limit: ${current_size}GB > ${max_size_gb}GB${NC}"
        echo -e "${YELLOW}Starting size-based archival process for $type...${NC}"
        
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
            
            local file_size=$(get_file_size_bytes "$file")
            local file_size_gb=$(echo "$file_size" | awk '{printf "%.1f", $1/1024/1024}')
            
            # Check if we need to archive more files
            local projected_size=$(echo "$current_size - $to_archive_size" | bc -l)
            local should_stop=$(echo "$projected_size <= $max_size_gb" | bc -l)
            
            if [[ "$should_stop" -eq 1 ]]; then
                break
            fi
            
            # Archive the file
            if [[ "$DRY_RUN" = true ]]; then
                echo -e "${YELLOW}[DRY RUN] Would archive: $file (${file_size_gb}GB)${NC}"
            else
                mkdir -p "$(dirname "$ARCHIVE_DIR/$file")"
                mv "$file" "$ARCHIVE_DIR/$file"
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
    else
        echo -e "${YELLOW}Directory $dir does not exist, skipping...${NC}"
    fi
}

# Function to cleanup files by age
cleanup_by_age() {
    local dir="$1"
    local max_days="$2"
    local type="$3"
    
    if [[ -d "$dir" ]]; then
        local old_files=$(get_old_files "$dir" "$max_days")
        local file_count=0
        local space_freed=0
        
        if [[ -z "$old_files" ]]; then
            echo -e "${GREEN}No files older than $max_days days found in $type${NC}"
            return 0
        fi
        
        echo -e "${YELLOW}Finding files older than $max_days days in $type...${NC}"
        
        while IFS= read -r file; do
            if [[ -z "$file" ]]; then
                continue
            fi
            
            local file_size=$(get_file_size_bytes "$file")
            local file_size_mb=$(get_file_size_mb "$file")
            
            if [[ "$DRY_RUN" = true ]]; then
                echo -e "${YELLOW}[DRY RUN] Would remove old file: $file (${file_size_mb}MB)${NC}"
            else
                rm "$file"
                echo -e "${GREEN}Removed old file: $file (${file_size_mb}MB)${NC}"
            fi
            
            space_freed=$((space_freed + file_size))
            ((file_count++))
            
            # Progress update every 10 files
            if (( file_count % 10 == 0 )); then
                echo -e "${YELLOW}Progress: Removed $file_count files, freed $(echo "$space_freed" | awk '{printf "%.1f", $1/1024/1024}')MB${NC}"
            fi
        done <<< "$old_files"
        
        if [[ "$DRY_RUN" = true ]]; then
            echo -e "${YELLOW}[DRY RUN] Would remove $file_count files older than $max_days days, freeing $(echo "$space_freed" | awk '{printf "%.1f", $1/1024/1024}')MB${NC}"
        else
            echo -e "${GREEN}Removed $file_count files older than $max_days days, freed $(echo "$space_freed" | awk '{printf "%.1f", $1/1024/1024}')MB${NC}"
        fi
        
        return $file_count
    else
        echo -e "${YELLOW}Directory $dir does not exist, skipping age-based cleanup...${NC}"
        return 0
    fi
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
                echo "Usage: $0 [--dry-run] [--skip-dedup] [--recordings-gb GB] [--clips-gb GB] [--recordings-days DAYS] [--clips-days DAYS] [--archive-dir PATH]"
                exit 1
                ;;
        esac
    done
    
    echo "Configuration:"
    echo "  Recordings limit: ${MAX_RECORDINGS_GB}GB (max ${MAX_RECORDINGS_DAYS} days)"
    echo "  Clips limit: ${MAX_CLIPS_GB}GB (max ${MAX_CLIPS_DAYS} days)"
    echo "  Archive directory: $ARCHIVE_DIR"
    echo "  Dry run: $DRY_RUN"
    echo "  Skip deduplication: $SKIP_DEDUP"
    echo ""
    
    # Track overall statistics
    local start_time=$(date +%s)
    
    # Step 1: Age-based cleanup
    echo -e "${BLUE}=== STEP 1: Age-based cleanup ===${NC}"
    cleanup_by_age "$RECORDINGS_DIR" "$MAX_RECORDINGS_DAYS" "Recordings"
    cleanup_by_age "$CLIPS_DIR" "$MAX_CLIPS_DAYS" "Clips"
    echo ""
    
    # Step 2: Size-based archival
    echo -e "${BLUE}=== STEP 2: Size-based archival ===${NC}"
    archive_files_by_size "$RECORDINGS_DIR" "$MAX_RECORDINGS_GB" "Recordings"
    archive_files_by_size "$CLIPS_DIR" "$MAX_CLIPS_GB" "Clips"
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
    
    # Step 4: Media compression
    echo -e "${BLUE}=== STEP 4: Media compression ===${NC}"
    compress_media "$RECORDINGS_DIR" "Recordings"
    compress_media "$CLIPS_DIR" "Clips"
    echo ""
    
    # Final summary
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    echo -e "${GREEN}Storage optimization completed!${NC}"
    echo "Duration: ${duration}s"
    echo ""
    echo -e "${BLUE}Final directory sizes:${NC}"
    echo "  Recordings: $(get_dir_size_gb "$RECORDINGS_DIR")GB"
    echo "  Clips: $(get_dir_size_gb "$CLIPS_DIR")GB"
    echo "  Archive: $(get_dir_size_gb "$ARCHIVE_DIR")GB"
}

# Run main function with all arguments
main "$@"