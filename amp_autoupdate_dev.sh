#!/bin/bash
# Auto-update AMP_LLMs DEV branch and restart dev services on macOS
# Automatically discovers all com.amplm.dev.* services (except autoupdate)
REPO_DIR="/Users/amphoraxe/Developer/AMP_LLMs"
LOG_FILE="/tmp/amp_autoupdate_dev.log"
PLIST_DIR="$HOME/Library/LaunchAgents"
SELF_SERVICE="com.amplm.autoupdate.dev"

# Timestamp header for each run
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting AMP DEV auto-update check..." >> "$LOG_FILE"

cd "$REPO_DIR" || {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ❌ Failed to cd into $REPO_DIR" >> "$LOG_FILE"
    exit 1
}

# Make sure we're on dev branch
git checkout dev >/dev/null 2>&1

# Fetch latest changes from dev branch
git fetch origin dev >/dev/null 2>&1

LOCAL_HASH=$(git rev-parse HEAD)
REMOTE_HASH=$(git rev-parse origin/dev)

if [ "$LOCAL_HASH" != "$REMOTE_HASH" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🔄 New commit detected on DEV! Pulling changes..." >> "$LOG_FILE"
    
    git reset --hard origin/dev >/dev/null 2>&1
    
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🧹 Restarting dev services..." >> "$LOG_FILE"
    
    # Discover all loaded com.amplm.dev.* services EXCEPT autoupdate.dev
    SERVICES=$(launchctl list | grep "com\.amplm\.dev\." | grep -v "$SELF_SERVICE" | awk '{print $3}')
    
    if [ -z "$SERVICES" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️ No com.amplm.dev services found running (excluding autoupdate)" >> "$LOG_FILE"
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Found dev services to restart: $SERVICES" >> "$LOG_FILE"
        
        # Unload all dev services (except autoupdate)
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
        
        # Load all dev services
        for service in $SERVICES; do
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Loading $service..." >> "$LOG_FILE"
            PLIST_FILE="$PLIST_DIR/${service}.plist"
            if [ -f "$PLIST_FILE" ]; then
                launchctl load "$PLIST_FILE" 2>/dev/null || true
            fi
        done
        
        sleep 3
        
        # Check final status
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 📊 Final dev service status..." >> "$LOG_FILE"
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
    
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ DEV update and restart complete." >> "$LOG_FILE"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🟢 No updates found on DEV branch." >> "$LOG_FILE"
fi

echo "" >> "$LOG_FILE"