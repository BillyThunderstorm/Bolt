#!/bin/bash
# Storage Monitoring Script for Bolt
# Monitors disk usage and sends alerts when thresholds are exceeded
# Supports email, SMS (via email-to-SMS), and webhook notifications

# =============================================================================
# CONFIGURATION - Edit these values or set via environment variables
# =============================================================================
THRESHOLD_WARN=${STORAGE_THRESHOLD_WARN:-80}    # Warning at 80% usage
THRESHOLD_CRIT=${STORAGE_THRESHOLD_CRIT:-95}    # Critical at 95% usage
LOG_FILE="logs/storage_monitor.log"
LOG_DIR="logs"

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

# Check disk usage
check_disk_usage() {
    local usage_percent
    usage_percent=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')

    log_message "INFO" "Current disk usage: ${usage_percent}%"

    if [ "$usage_percent" -ge "$THRESHOLD_CRIT" ]; then
        log_message "CRITICAL" "Disk usage critical: ${usage_percent}%"
        send_notifications "CRITICAL" \
            "🔴 Bolt Storage CRITICAL" \
            "Disk usage is ${usage_percent}% on $(hostname). Immediate action required!"
        return 2
    elif [ "$usage_percent" -ge "$THRESHOLD_WARN" ]; then
        log_message "WARNING" "Disk usage warning: ${usage_percent}%"
        send_notifications "WARNING" \
            "🟡 Bolt Storage WARNING" \
            "Disk usage is ${usage_percent}% on $(hostname). Consider cleanup."
        return 1
    else
        log_message "INFO" "Disk usage normal: ${usage_percent}%"
        return 0
    fi
}

# Check specific directory sizes
check_directory_sizes() {
    local dirs=("recordings" "clips" "logs" "data")
    local limits=(50 1 2 5) # GB limits for each directory

    for i in "${!dirs[@]}"; do
        local dir="${dirs[$i]}"
        local limit=${limits[$i]}

        if [ -d "$dir" ]; then
            local size_gb
            size_gb=$(du -sb "$dir" 2>/dev/null | awk '{print $1/1024/1024/1024}' | cut -d. -f1)
            size_gb=${size_gb:-0}

            log_message "INFO" "Directory $dir: ${size_gb}GB (limit: ${limit}GB)"

            if [ "$size_gb" -gt "$limit" ]; then
                log_message "WARNING" "Directory $dir exceeds limit: ${size_gb}GB > ${limit}GB"

                # Trigger cleanup if significantly over limit
                if [ "$size_gb" -gt $((limit * 2)) ]; then
                    log_message "INFO" "Triggering cleanup for $dir"
                    ./scripts/maintenance/media_rotation.sh --${dir}-gb "$limit"
                    send_notifications "WARNING" \
                        "Bolt Cleanup Triggered" \
                        "Directory $dir was at ${size_gb}GB (limit: ${limit}GB). Auto-cleanup initiated."
                fi
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
    log_message "INFO" "  Webhook: ${WEBHOOK_URL:-disabled}"
    log_message "INFO" "  Discord: ${DISCORD_WEBHOOK:-disabled}"
}

# =============================================================================
# Load Configuration
# =============================================================================
CONFIG_FILE="/Users/carter/developer/Bolt/configs/storage_alerts.env"
if [[ -f "$CONFIG_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$CONFIG_FILE"
fi

# =============================================================================
# Main Execution
# =============================================================================

main() {
    # Ensure log directory exists
    mkdir -p "$LOG_DIR"

    log_message "INFO" "Storage monitor started"
    log_message "INFO" "Loaded configuration from: $CONFIG_FILE"

    # Print configuration
    print_config

    # Check disk usage
    check_disk_usage
    local disk_status=$?

    # Check directory sizes
    check_directory_sizes

    # Log completion
    log_message "INFO" "Storage monitor completed"

    # Exit with worst status
    exit $disk_status
}

# Run main function
main "$@"
