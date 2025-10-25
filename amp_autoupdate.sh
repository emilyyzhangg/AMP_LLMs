#!/bin/bash
# Auto-update AMP_LLMs repo and restart PROD services on macOS
# Automatically discovers all com.amplm.* services EXCLUDING dev and autoupdate
REPO_DIR="/Users/amphoraxe/Developer/AMP_LLMs"
LOG_FILE="/tmp/amp_autoupdate.log"
PLIST_DIR="$HOME/Library/LaunchAgents"
SELF_SERVICE="com.amplm.autoupdate"

# Timestamp header for each run
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting AMP auto-update check..." >> "$LOG_FILE"

cd "$REPO_DIR" || {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ❌ Failed to cd into $REPO_DIR" >> "$LOG_FILE"
    exit 1
}

# Make sure we're on main
git checkout main >/dev/null 2>&1

# Fetch latest changes
git fetch origin main >/dev/null 2>&1

LOCAL_HASH=$(git rev-parse HEAD)
REMOTE_HASH=$(git rev-parse origin/main)

if [ "$LOCAL_HASH" != "$REMOTE_HASH" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🔄 New commit detected! Pulling changes..." >> "$LOG_FILE"
    
    git reset --hard origin/main >/dev/null 2>&1
    
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🧹 Restarting PROD services..." >> "$LOG_FILE"
    
    # Discover all loaded com.amplm.* services EXCLUDING:
    # - autoupdate (self)
    # - anything with .dev (dev services)
    SERVICES=$(launchctl list | grep "com\.amplm\." | grep -v "\.dev" | grep -v "$SELF_SERVICE" | awk '{print $3}')
    
    if [ -z "$SERVICES" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️ No com.amplm PROD services found running" >> "$LOG_FILE"
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Found PROD services to restart: $SERVICES" >> "$LOG_FILE"
        
        # Unload all PROD services
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
        
        # Load all PROD services
        for service in $SERVICES; do
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Loading $service..." >> "$LOG_FILE"
            PLIST_FILE="$PLIST_DIR/${service}.plist"
            if [ -f "$PLIST_FILE" ]; then
                launchctl load "$PLIST_FILE" 2>/dev/null || true
            fi
        done
        
        sleep 3
        
        # Check final status
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 📊 Final PROD service status..." >> "$LOG_FILE"
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
    
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ PROD update and restart complete." >> "$LOG_FILE"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🟢 No updates found." >> "$LOG_FILE"
fi

echo "" >> "$LOG_FILE"