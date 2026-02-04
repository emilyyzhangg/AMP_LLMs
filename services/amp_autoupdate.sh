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
    # SELF-UPDATE: Copy this script from repo to AMP_Services
    # ==========================================================================
    REPO_SCRIPT="$REPO_DIR/services/$SCRIPT_NAME"
    if [ -f "$REPO_SCRIPT" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🔄 Self-updating autoupdate script..." >> "$LOG_FILE"
        cp "$REPO_SCRIPT" "$SERVICES_DIR/$SCRIPT_NAME"
        chmod +x "$SERVICES_DIR/$SCRIPT_NAME"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Autoupdate script updated" >> "$LOG_FILE"
    fi

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
