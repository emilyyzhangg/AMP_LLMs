#!/bin/bash
# =============================================================================
# AMP Auto-Update Script (MAIN/PROD)
# =============================================================================
# Automatically pulls from main branch, installs dependencies, and restarts services.
# This script is SELF-UPDATING - it copies itself from the repo after each pull.
# =============================================================================

REPO_DIR="/Users/amphoraxe/Developer/AMP_LLMs_main"
LOG_FILE="/tmp/amp_autoupdate.log"
PLIST_DIR="$HOME/Library/LaunchAgents"
SERVICES_DIR="$HOME/AMP_Services"
SELF_SERVICE="com.amplm.autoupdate"
SCRIPT_NAME="amp_autoupdate.sh"

# Timestamp header for each run
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting AMP MAIN auto-update check..." >> "$LOG_FILE"

cd "$REPO_DIR" || {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ❌ Failed to cd into $REPO_DIR" >> "$LOG_FILE"
    exit 1
}

# Make sure we're on main branch
git checkout main >/dev/null 2>&1

# Fetch latest changes from main branch
git fetch origin main >/dev/null 2>&1

LOCAL_HASH=$(git rev-parse HEAD)
REMOTE_HASH=$(git rev-parse origin/main)

if [ "$LOCAL_HASH" != "$REMOTE_HASH" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🔄 New commit detected on MAIN! Pulling changes..." >> "$LOG_FILE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Local: $LOCAL_HASH → Remote: $REMOTE_HASH" >> "$LOG_FILE"

    git reset --hard origin/main >/dev/null 2>&1

    # ==========================================================================
    # UPDATE SERVICE FILES: Copy scripts and plists from repo
    # ==========================================================================
    REPO_SERVICES_DIR="$REPO_DIR/services"

    # Ensure directories exist
    mkdir -p "$SERVICES_DIR"

    # Copy all shell scripts
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🔄 Updating service scripts..." >> "$LOG_FILE"
    for script in "$REPO_SERVICES_DIR"/*.sh; do
        if [ -f "$script" ]; then
            BASENAME=$(basename "$script")
            cp "$script" "$SERVICES_DIR/$BASENAME"
            chmod +x "$SERVICES_DIR/$BASENAME"
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Updated $BASENAME" >> "$LOG_FILE"
        fi
    done

    # Copy all plist files (service definitions)
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🔄 Updating service plists..." >> "$LOG_FILE"
    for plist in "$REPO_SERVICES_DIR"/*.plist; do
        if [ -f "$plist" ]; then
            BASENAME=$(basename "$plist")
            # Check if plist changed
            if ! cmp -s "$plist" "$PLIST_DIR/$BASENAME" 2>/dev/null; then
                cp "$plist" "$PLIST_DIR/$BASENAME"
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
        pip3 install -q -r "$REPO_DIR/amp_llm_v3/requirements.txt" >> "$LOG_FILE" 2>&1
    fi

    # Standalone module requirements (if they exist)
    for req_file in "$REPO_DIR/amp_llm_v3/standalone modules"/**/requirements.txt; do
        if [ -f "$req_file" ]; then
            pip3 install -q -r "$req_file" >> "$LOG_FILE" 2>&1
        fi
    done

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Dependencies installed" >> "$LOG_FILE"

    # ==========================================================================
    # WAIT FOR ACTIVE JOBS TO COMPLETE
    # ==========================================================================
    WEBAPP_URL="http://localhost:8000"
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
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🧹 Restarting MAIN services..." >> "$LOG_FILE"

    # Discover all loaded com.amplm.* services EXCEPT dev services and autoupdate
    SERVICES=$(launchctl list | grep "com\.amplm\." | grep -v "\.dev" | grep -v "$SELF_SERVICE" | awk '{print $3}')

    if [ -z "$SERVICES" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️ No com.amplm.* services found running (excluding dev and autoupdate)" >> "$LOG_FILE"
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Found services to restart: $SERVICES" >> "$LOG_FILE"

        # Unload all services
        for service in $SERVICES; do
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Unloading $service..." >> "$LOG_FILE"
            PLIST_FILE="$PLIST_DIR/${service}.plist"
            if [ -f "$PLIST_FILE" ]; then
                launchctl unload "$PLIST_FILE" 2>/dev/null || true
            else
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️ Plist not found: $PLIST_FILE" >> "$LOG_FILE"
            fi
        done

        sleep 2

        # Load all services
        for service in $SERVICES; do
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Loading $service..." >> "$LOG_FILE"
            PLIST_FILE="$PLIST_DIR/${service}.plist"
            if [ -f "$PLIST_FILE" ]; then
                launchctl load "$PLIST_FILE" 2>/dev/null || true
            fi
        done

        sleep 3

        # Check final status
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 📊 Final service status..." >> "$LOG_FILE"
        for service in $SERVICES; do
            STATUS=$(launchctl list | grep "$service" | awk '{print $1}')
            if [ -z "$STATUS" ] || [ "$STATUS" = "-" ]; then
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🟡 $service loaded (ready to launch)" >> "$LOG_FILE"
            elif [ "$STATUS" = "-15" ]; then
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] ❌ $service failed with status -15" >> "$LOG_FILE"
            else
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ $service running with PID: $STATUS" >> "$LOG_FILE"
            fi
        done
    fi

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ MAIN update and restart complete." >> "$LOG_FILE"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🟢 No updates found on MAIN branch." >> "$LOG_FILE"
fi

echo "" >> "$LOG_FILE"
