#!/bin/bash
# Storage Monitoring Script for Bolt
# Monitors disk usage and sends alerts when thresholds are exceeded
# Supports email, SMS (via email-to-SMS), and webhook notifications

# =============================================================================
# CONFIGURATION - Edit these values or set via environment variables
# =============================================================================
THRESHOLD_WARN=${STORAGE_THRESHOLD_WARN:-80}    # Warning at 80% usage
THRESHOLD_CRIT=${STORAGE_THRESHOLD_CRIT:-95}    # Critical at 95% usage
# LOG paths set after REPO_ROOT is resolved below

# Email notifications (set ALERT_EMAIL to enable)
ALERT_EMAIL="${ALERT_EMAIL:-}"

# SMS notifications via email-to-SMS gateways (set ALERT_PHONE and CARRIER)
# Supported carriers: verizon, att, tmobile, sprint, virgin, boost
ALERT_PHONE="${ALERT_PHONE:-}"
CARRIER="${CARRIER:-}"

# Webhook notifications (set WEBHOOK_URL to enable)
WEBHOOK_URL="${WEBHOOK_URL:-}"

# Discord webhook (set DISCORD_WEBHOOK to enable)
DISCORD_WEBHOOK="${DISCORD_WEBHOOK:-}"

# =============================================================================
# Carrier SMS Gateway Mappings (function for bash 3.2 compatibility)
# =============================================================================
get_sms_gateway() {
    local carrier="$1"
    case "$carrier" in
        verizon) echo "@vtext.com" ;;
        att) echo "@txt.att.net" ;;
        tmobile) echo "@tmomail.net" ;;
        sprint) echo "@mms.sprintpcs.com" ;;
        virgin) echo "@vmobl.com" ;;
        boost) echo "@myboostmobile.com" ;;
        *) echo "" ;;
    esac
}

# =============================================================================
# Functions
# =============================================================================

log_message() {
    local level="$1"
    local message="$2"
    mkdir -p "$LOG_DIR"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$level] $message" >> "$LOG_FILE"
}

# Send email notification
send_email() {
    local subject="$1"
    local body="$2"
    local recipient="$3"

    if [[ -z "$recipient" ]]; then
        return 0
    fi

    log_message "INFO" "Sending email to $recipient: $subject"

    # Try different mail commands
    if command -v mail &> /dev/null; then
        echo "$body" | mail -s "$subject" "$recipient"
    elif command -v sendmail &> /dev/null; then
        {
            echo "To: $recipient"
            echo "Subject: $subject"
            echo ""
            echo "$body"
        } | sendmail -t
    elif command -v python3 &> /dev/null; then
        # Fallback to Python if mail utilities not available
        python3 -c "
import subprocess
import sys
try:
    # Try using macOS mail app if available
    subprocess.run(['osascript', '-e', '''
        tell application \"Mail\"
            set newMessage to make new outgoing message with properties {subject:\"$subject\", content:\"$body\", visible:true}
            tell newMessage
                make new to recipient at end of to recipients with properties {address:\"$recipient\"}
            end tell
        end tell
    '''])
except Exception as e:
    print(f'Mail failed: {e}', file=sys.stderr)
    sys.exit(1)
" 2>/dev/null || true
    else
        log_message "WARNING" "No mail utility available for email notification"
        return 1
    fi
}

# Send SMS via email-to-SMS gateway
send_sms() {
    local message="$1"
    local phone="$2"
    local carrier="$3"

    if [[ -z "$phone" ]] || [[ -z "$carrier" ]]; then
        return 0
    fi

    local gateway
    gateway=$(get_sms_gateway "$carrier")
    if [[ -z "$gateway" ]]; then
        log_message "WARNING" "Unknown carrier: $carrier"
        return 1
    fi

    local sms_email="${phone}${gateway}"
    log_message "INFO" "Sending SMS to $phone via $carrier ($sms_email)"
    send_email "Bolt Storage Alert" "$message" "$sms_email"
}

# Send webhook notification (generic JSON webhook)
send_webhook() {
    local title="$1"
    local message="$2"
    local level="$3"
    local url="$4"

    if [[ -z "$url" ]]; then
        return 0
    fi

    log_message "INFO" "Sending webhook to $url"

    curl -s -X POST "$url" \
        -H "Content-Type: application/json" \
        -d "{
            \"title\": \"$title\",
            \"message\": \"$message\",
            \"level\": \"$level\",
            \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",
            \"hostname\": \"$(hostname)\"
        }" 2>/dev/null || log_message "WARNING" "Webhook failed"
}

# Send Discord webhook notification
send_discord() {
    local title="$1"
    local message="$2"
    local level="$3"
    local webhook_url="$4"

    if [[ -z "$webhook_url" ]]; then
        return 0
    fi

    log_message "INFO" "Sending Discord notification"

    # Set color based on level
    local color="3447003"  # Blue for info
    case "$level" in
        WARNING) color="15158332" ;;  # Yellow
        CRITICAL) color="15105570" ;;  # Red
    esac

    curl -s -X POST "$webhook_url" \
        -H "Content-Type: application/json" \
        -d "{
            \"embeds\": [{
                \"title\": \"$title\",
                \"description\": \"$message\",
                \"color\": $color,
                \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",
                \"footer\": {
                    \"text\": \"Bolt Storage Monitor on $(hostname)\"
                }
            }]
        }" 2>/dev/null || log_message "WARNING" "Discord webhook failed"
}

# Send all configured notifications
send_notifications() {
    local level="$1"
    local subject="$2"
    local body="$3"

    # Email
    if [[ -n "$ALERT_EMAIL" ]]; then
        send_email "$subject" "$body" "$ALERT_EMAIL"
    fi

    # SMS
    if [[ -n "$ALERT_PHONE" ]] && [[ -n "$CARRIER" ]]; then
        # Truncate message for SMS (160 char limit)
        local sms_message="${subject}: ${body:0:100}"
        send_sms "$sms_message" "$ALERT_PHONE" "$CARRIER"
    fi

    # Generic webhook
    if [[ -n "$WEBHOOK_URL" ]]; then
        send_webhook "$subject" "$body" "$level" "$WEBHOOK_URL"
    fi

    # Discord webhook
    if [[ -n "$DISCORD_WEBHOOK" ]]; then
        send_discord "$subject" "$body" "$level" "$DISCORD_WEBHOOK"
    fi
}

# Check disk usage on the volume that holds the repo (not the read-only system slice)
check_disk_usage() {
    local target="${REPO_ROOT:-.}"
    local usage_percent avail
    usage_percent=$(df -P "$target" | tail -1 | awk '{print $5}' | sed 's/%//')
    avail=$(df -hP "$target" | tail -1 | awk '{print $4}')

    log_message "INFO" "Disk usage on volume for $target: ${usage_percent}% (${avail} free)"

    if [ "$usage_percent" -ge "$THRESHOLD_CRIT" ]; then
        log_message "CRITICAL" "Disk usage critical: ${usage_percent}% (${avail} free)"
        send_notifications "CRITICAL" \
            "Bolt Storage CRITICAL" \
            "Disk usage is ${usage_percent}% (${avail} free) on $(hostname). Immediate action required!"
        return 2
    elif [ "$usage_percent" -ge "$THRESHOLD_WARN" ]; then
        log_message "WARNING" "Disk usage warning: ${usage_percent}% (${avail} free)"
        send_notifications "WARNING" \
            "Bolt Storage WARNING" \
            "Disk usage is ${usage_percent}% (${avail} free) on $(hostname). Consider cleanup."
        return 1
    else
        log_message "INFO" "Disk usage normal: ${usage_percent}% (${avail} free)"
        return 0
    fi
}

# Directory size in whole GB (macOS-safe: du -sk)
_dir_size_gb_int() {
    local dir="$1"
    if [[ ! -d "$dir" ]]; then
        echo 0
        return
    fi
    local size_kb
    size_kb=$(du -sk "$dir" 2>/dev/null | cut -f1)
    size_kb=${size_kb:-0}
    awk -v kb="$size_kb" 'BEGIN { printf "%d", int(kb/1024/1024) }'
}

# Check specific directory sizes (canonical post-reorg media paths)
check_directory_sizes() {
    # name|relative_or_absolute_path|limit_gb|rotation_flag
    local entries=(
        "Recordings|${REPO_ROOT}/media/Recordings|50|recordings-gb"
        "Clips|${REPO_ROOT}/media/clips|5|clips-gb"
        "Vertical|${REPO_ROOT}/media/vertical_clips|5|vertical-gb"
        "Output|${REPO_ROOT}/media/output|5|output-gb"
        "Logs|${REPO_ROOT}/logs|5|"
    )

    local entry name dir limit flag size_gb
    for entry in "${entries[@]}"; do
        IFS='|' read -r name dir limit flag <<< "$entry"

        if [[ ! -d "$dir" ]]; then
            log_message "INFO" "Directory $name missing: $dir"
            continue
        fi

        size_gb=$(_dir_size_gb_int "$dir")
        log_message "INFO" "Directory $name: ${size_gb}GB (limit: ${limit}GB) path=$dir"

        if [ "$size_gb" -gt "$limit" ]; then
            log_message "WARNING" "Directory $name exceeds limit: ${size_gb}GB > ${limit}GB"

            # Auto-clean only when STORAGE_AUTO_CLEAN=1 (default on when critically over 2x limit)
            # Set STORAGE_AUTO_CLEAN=0 to monitor-only.
            local auto="${STORAGE_AUTO_CLEAN:-1}"
            if [ -n "$flag" ] && [ "$size_gb" -gt $((limit * 2)) ] && [ "$auto" != "0" ]; then
                log_message "INFO" "Triggering media rotation for $name (limit ${limit}GB)"
                if [[ -x "${REPO_ROOT}/scripts/media_rotation.sh" ]]; then
                    bash "${REPO_ROOT}/scripts/media_rotation.sh" "--${flag}" "$limit" \
                        >> "${LOG_FILE}" 2>&1 || true
                    send_notifications "WARNING" \
                        "Bolt Cleanup Triggered" \
                        "Directory $name was at ${size_gb}GB (limit: ${limit}GB). Auto-cleanup initiated."
                else
                    log_message "ERROR" "media_rotation.sh not found at ${REPO_ROOT}/scripts/media_rotation.sh"
                fi
            elif [ -n "$flag" ] && [ "$size_gb" -gt "$limit" ]; then
                log_message "INFO" "Over limit but under 2x — not auto-cleaning $name (run media_rotation.sh manually)"
            fi
        fi
    done
}

# Print current configuration
print_config() {
    log_message "INFO" "Configuration:"
    log_message "INFO" "  Warning threshold: ${THRESHOLD_WARN}%"
    log_message "INFO" "  Critical threshold: ${THRESHOLD_CRIT}%"
    log_message "INFO" "  Email alerts: ${ALERT_EMAIL:-disabled}"
    log_message "INFO" "  SMS alerts: ${ALERT_PHONE:-disabled} (${CARRIER:-unknown})"
    log_message "INFO" "  Webhook: $([[ -n "$WEBHOOK_URL" ]] && echo set || echo disabled)"
    log_message "INFO" "  Discord: $([[ -n "$DISCORD_WEBHOOK" ]] && echo set || echo disabled)"
}

# =============================================================================
# Resolve repo + load configuration
# =============================================================================
_SOURCE="${BASH_SOURCE[0]}"
while [ -L "$_SOURCE" ]; do
  _DIR="$(cd -P "$(dirname "$_SOURCE")" && pwd)"
  _LINK="$(readlink "$_SOURCE")"
  [[ $_LINK != /* ]] && _SOURCE="$_DIR/$_LINK" || _SOURCE="$_LINK"
done
SCRIPT_DIR="$(cd -P "$(dirname "$_SOURCE")" && pwd)"
# scripts/storage_monitor.sh → repo root is parent
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

LOG_DIR="${REPO_ROOT}/logs"
LOG_FILE="${LOG_DIR}/storage_monitor.log"

# Prefer Data/configs (post-reorg); fall back to legacy configs/
CONFIG_FILE=""
for candidate in \
    "${REPO_ROOT}/Data/configs/storage_alerts.env" \
    "${REPO_ROOT}/configs/storage_alerts.env" \
    "${REPO_ROOT}/Data/data/configs/storage_alerts.env"
do
    if [[ -f "$candidate" ]]; then
        CONFIG_FILE="$candidate"
        break
    fi
done
if [[ -n "$CONFIG_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$CONFIG_FILE"
fi

# =============================================================================
# Main Execution
# =============================================================================

main() {
    mkdir -p "$LOG_DIR"

    log_message "INFO" "Storage monitor started (repo=$REPO_ROOT)"
    if [[ -n "$CONFIG_FILE" ]]; then
        log_message "INFO" "Loaded configuration from: $CONFIG_FILE"
    else
        log_message "WARNING" "No storage_alerts.env found under Data/configs/ or configs/"
    fi

    print_config

    check_disk_usage
    local disk_status=$?

    check_directory_sizes

    log_message "INFO" "Storage monitor completed"
    exit $disk_status
}

main "$@"
