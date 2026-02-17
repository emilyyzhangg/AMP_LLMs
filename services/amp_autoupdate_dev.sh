#!/bin/bash
# =============================================================================
# AMP Auto-Update Script (DEV)
# =============================================================================
# Automatically pulls from dev branch, installs dependencies, and restarts services.
# This script is SELF-UPDATING - it copies itself from the repo after each pull.
# =============================================================================

REPO_DIR="/Users/amphoraxe/Developer/AMP_LLMs_dev"
LOG_FILE="/tmp/amp_autoupdate_dev.log"
PLIST_DIR="/Library/LaunchDaemons"
SERVICES_DIR="/Users/amphoraxe/AMP_Services"
SELF_SERVICE="com.amplm.autoupdate.dev"
SCRIPT_NAME="amp_autoupdate_dev.sh"
RUN_USER="amphoraxe"

# Timestamp header for each run
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting AMP DEV auto-update check..." >> "$LOG_FILE"

cd "$REPO_DIR" || {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ❌ Failed to cd into $REPO_DIR" >> "$LOG_FILE"
    exit 1
}

# Make sure we're on dev branch (run as amphoraxe to avoid ownership issues)
sudo -u "$RUN_USER" git checkout dev >/dev/null 2>&1

# Fetch latest changes from dev branch
sudo -u "$RUN_USER" git fetch origin dev >/dev/null 2>&1

LOCAL_HASH=$(sudo -u "$RUN_USER" git rev-parse HEAD)
REMOTE_HASH=$(sudo -u "$RUN_USER" git rev-parse origin/dev)

if [ "$LOCAL_HASH" != "$REMOTE_HASH" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🔄 New commit detected on DEV! Pulling changes..." >> "$LOG_FILE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Local: $LOCAL_HASH → Remote: $REMOTE_HASH" >> "$LOG_FILE"

    sudo -u "$RUN_USER" git reset --hard origin/dev >/dev/null 2>&1

    # ==========================================================================
    # UPDATE SERVICE FILES: Copy scripts and plists from repo
    # ==========================================================================
    REPO_SERVICES_DIR="$REPO_DIR/services"

    # Ensure directories exist
    sudo -u "$RUN_USER" mkdir -p "$SERVICES_DIR"

    # Copy all shell scripts (owned by amphoraxe)
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🔄 Updating service scripts..." >> "$LOG_FILE"
    for script in "$REPO_SERVICES_DIR"/*.sh; do
        if [ -f "$script" ]; then
            BASENAME=$(basename "$script")
            cp "$script" "$SERVICES_DIR/$BASENAME"
            chown "$RUN_USER":staff "$SERVICES_DIR/$BASENAME"
            chmod +x "$SERVICES_DIR/$BASENAME"
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Updated $BASENAME" >> "$LOG_FILE"
        fi
    done

    # Copy all plist files to /Library/LaunchDaemons (owned by root)
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🔄 Updating service plists..." >> "$LOG_FILE"
    for plist in "$REPO_SERVICES_DIR"/*.plist; do
        if [ -f "$plist" ]; then
            BASENAME=$(basename "$plist")
            # Check if plist changed
            if ! cmp -s "$plist" "$PLIST_DIR/$BASENAME" 2>/dev/null; then
                cp "$plist" "$PLIST_DIR/$BASENAME"
                chown root:wheel "$PLIST_DIR/$BASENAME"
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Updated $BASENAME" >> "$LOG_FILE"
            fi
        fi
    done

    # ==========================================================================
    # INSTALL PYTHON DEPENDENCIES
    # ==========================================================================
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 📦 Installing Python dependencies..." >> "$LOG_FILE"

    # Main requirements
    if [ -f "$REPO_DIR/amp_llm_v3/requirements.txt" ]; then
        sudo -u "$RUN_USER" pip3 install -q -r "$REPO_DIR/amp_llm_v3/requirements.txt" >> "$LOG_FILE" 2>&1
    fi

    # Standalone module requirements (if they exist)
    for req_file in "$REPO_DIR/amp_llm_v3/standalone modules"/**/requirements.txt; do
        if [ -f "$req_file" ]; then
            sudo -u "$RUN_USER" pip3 install -q -r "$req_file" >> "$LOG_FILE" 2>&1
        fi
    done

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Dependencies installed" >> "$LOG_FILE"

    # ==========================================================================
    # WAIT FOR ACTIVE JOBS TO COMPLETE
    # ==========================================================================
    WEBAPP_URL="http://localhost:9000"
    MAX_WAIT=64800  # Maximum wait time in seconds (18 hours)
    POLL_INTERVAL=10  # Check every 10 seconds
    WAITED=0

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🔍 Checking for active annotation jobs..." >> "$LOG_FILE"

    while true; do
        # Try to get job status from the webapp API
        JOBS_RESPONSE=$(curl -s --max-time 5 "$WEBAPP_URL/api/chat/jobs" 2>/dev/null)

        if [ -z "$JOBS_RESPONSE" ]; then
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️ Could not reach jobs API, proceeding with restart" >> "$LOG_FILE"
            break
        fi

        # Extract active job count using python (more reliable JSON parsing)
        ACTIVE_JOBS=$(echo "$JOBS_RESPONSE" | python3 -c "import sys, json; data = json.load(sys.stdin); print(data.get('active', 0))" 2>/dev/null)

        if [ -z "$ACTIVE_JOBS" ] || [ "$ACTIVE_JOBS" = "0" ]; then
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ No active jobs, proceeding with restart" >> "$LOG_FILE"
            break
        fi

        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⏳ $ACTIVE_JOBS active job(s) running, waiting... (${WAITED}s elapsed)" >> "$LOG_FILE"

        sleep $POLL_INTERVAL
        WAITED=$((WAITED + POLL_INTERVAL))

        if [ $WAITED -ge $MAX_WAIT ]; then
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️ Max wait time reached ($MAX_WAIT seconds), proceeding with restart anyway" >> "$LOG_FILE"
            break
        fi
    done

    # ==========================================================================
    # RESTART SERVICES
    # ==========================================================================
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🧹 Restarting DEV services..." >> "$LOG_FILE"

    # Discover all dev service plists in /Library/LaunchDaemons EXCEPT autoupdate
    SERVICES=""
    for plist_file in "$PLIST_DIR"/com.amplm.*.dev.plist; do
        if [ -f "$plist_file" ]; then
            LABEL=$(basename "$plist_file" .plist)
            if [ "$LABEL" != "$SELF_SERVICE" ]; then
                SERVICES="$SERVICES $LABEL"
            fi
        fi
    done
    SERVICES=$(echo "$SERVICES" | xargs)  # trim whitespace

    if [ -z "$SERVICES" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️ No com.amplm.*.dev plists found (excluding autoupdate)" >> "$LOG_FILE"
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Found dev services to restart: $SERVICES" >> "$LOG_FILE"

        # Unload all dev services (except autoupdate)
        for service in $SERVICES; do
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Unloading $service..." >> "$LOG_FILE"
            launchctl bootout "system/$service" 2>/dev/null || true
        done

        sleep 2

        # Load all dev services
        for service in $SERVICES; do
            PLIST_FILE="$PLIST_DIR/${service}.plist"
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Loading $service..." >> "$LOG_FILE"
            if [ -f "$PLIST_FILE" ]; then
                launchctl bootstrap system "$PLIST_FILE" 2>/dev/null || launchctl load "$PLIST_FILE" 2>/dev/null || true
            fi
        done

        sleep 3

        # Check final status
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 📊 Final dev service status..." >> "$LOG_FILE"
        for service in $SERVICES; do
            STATUS=$(launchctl print "system/$service" 2>/dev/null | grep "pid =" | awk '{print $3}')
            if [ -n "$STATUS" ]; then
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ $service running with PID: $STATUS" >> "$LOG_FILE"
            else
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] ❌ $service not running" >> "$LOG_FILE"
            fi
        done
    fi

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ DEV update and restart complete." >> "$LOG_FILE"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🟢 No updates found on DEV branch." >> "$LOG_FILE"
fi

echo "" >> "$LOG_FILE"
