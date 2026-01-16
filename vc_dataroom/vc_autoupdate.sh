#!/bin/bash
# VC Data Room Auto-Update Script
# Checks for new commits and restarts services

REPO_DIR="/Users/amphoraxe/Developer/vc_dataroom"
LOG_FILE="/tmp/vc_autoupdate.log"
PLIST_DIR="$HOME/Library/LaunchAgents"
SELF_SERVICE="com.amphoraxe.vc.autoupdate"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting VC auto-update check..." >> "$LOG_FILE"

cd "$REPO_DIR" || { 
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Failed to cd into $REPO_DIR" >> "$LOG_FILE"
    exit 1
}

# Fetch latest changes
git checkout main >/dev/null 2>&1
git fetch origin main >/dev/null 2>&1

LOCAL_HASH=$(git rev-parse HEAD)
REMOTE_HASH=$(git rev-parse origin/main)

if [ "$LOCAL_HASH" != "$REMOTE_HASH" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] New commit detected! Pulling changes..." >> "$LOG_FILE"
    
    # Pull the changes
    git reset --hard origin/main >/dev/null 2>&1
    
    # Find all VC services (excluding the autoupdate service itself)
    SERVICES=$(launchctl list | grep "com\.amphoraxe\.vc\." | grep -v "$SELF_SERVICE" | awk '{print $3}')
    
    if [ ! -z "$SERVICES" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Restarting services: $SERVICES" >> "$LOG_FILE"
        
        # Unload all VC services
        for service in $SERVICES; do
            PLIST_FILE="$PLIST_DIR/${service}.plist"
            if [ -f "$PLIST_FILE" ]; then
                launchctl unload "$PLIST_FILE" 2>/dev/null || true
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] Unloaded $service" >> "$LOG_FILE"
            fi
        done
        
        sleep 2
        
        # Reload all VC services
        for service in $SERVICES; do
            PLIST_FILE="$PLIST_DIR/${service}.plist"
            if [ -f "$PLIST_FILE" ]; then
                launchctl load "$PLIST_FILE" 2>/dev/null || true
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] Loaded $service" >> "$LOG_FILE"
            fi
        done
    fi
    
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Update complete!" >> "$LOG_FILE"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] No updates found." >> "$LOG_FILE"
fi

echo "" >> "$LOG_FILE"
