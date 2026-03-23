#!/bin/bash
# =============================================================================
# AMP Auto-Update Script (MAIN/PROD)
# =============================================================================
# Automatically pulls from main branch, installs dependencies, and restarts services.
# This script is SELF-UPDATING - it copies itself from the repo after each pull.
# Tracks last-deployed hash so local changes also trigger restarts.
# =============================================================================

REPO_DIR="/Users/amphoraxe/Developer/amphoraxe/llm.amphoraxe.ca"
LOG_FILE="/tmp/amp_autoupdate.log"
LAST_DEPLOYED_FILE="/tmp/amp_last_deployed_hash"
PLIST_DIR="/Library/LaunchDaemons"
SERVICES_DIR="/Users/amphoraxe/AMP_Services"
SELF_SERVICE="com.amplm.autoupdate"
SCRIPT_NAME="amp_autoupdate.sh"
RUN_USER="amphoraxe"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting AMP MAIN auto-update check..." >> "$LOG_FILE"

cd "$REPO_DIR" || {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ❌ Failed to cd into $REPO_DIR" >> "$LOG_FILE"
    exit 1
}

sudo -u "$RUN_USER" git checkout main >/dev/null 2>&1
sudo -u "$RUN_USER" git fetch origin main >/dev/null 2>&1

LOCAL_HASH=$(sudo -u "$RUN_USER" git rev-parse HEAD)
REMOTE_HASH=$(sudo -u "$RUN_USER" git rev-parse origin/main)
LAST_DEPLOYED_HASH=$(cat "$LAST_DEPLOYED_FILE" 2>/dev/null || echo "")

# Pull remote changes if ahead
if [ "$LOCAL_HASH" != "$REMOTE_HASH" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🔄 New commit detected on MAIN! Pulling changes..." >> "$LOG_FILE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Local: $LOCAL_HASH → Remote: $REMOTE_HASH" >> "$LOG_FILE"
    sudo -u "$RUN_USER" git reset --hard origin/main >/dev/null 2>&1
    LOCAL_HASH=$(sudo -u "$RUN_USER" git rev-parse HEAD)
fi

# Deploy if HEAD differs from last deployed (covers both remote pulls and local changes)
if [ "$LOCAL_HASH" != "$LAST_DEPLOYED_HASH" ]; then
    if [ "$LOCAL_HASH" = "$REMOTE_HASH" ] && [ -n "$LAST_DEPLOYED_HASH" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🔧 Local changes detected (HEAD moved since last deploy)" >> "$LOG_FILE"
    fi
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🚀 Deploying $LOCAL_HASH..." >> "$LOG_FILE"

    REPO_SERVICES_DIR="$REPO_DIR/services"
    sudo -u "$RUN_USER" mkdir -p "$SERVICES_DIR"

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

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🔄 Updating service plists..." >> "$LOG_FILE"
    for plist in "$REPO_SERVICES_DIR"/*.plist; do
        if [ -f "$plist" ]; then
            BASENAME=$(basename "$plist")
            if ! cmp -s "$plist" "$PLIST_DIR/$BASENAME" 2>/dev/null; then
                cp "$plist" "$PLIST_DIR/$BASENAME"
                chown root:wheel "$PLIST_DIR/$BASENAME"
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Updated $BASENAME" >> "$LOG_FILE"
            fi
        fi
    done

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 📦 Installing Python dependencies..." >> "$LOG_FILE"
    if [ -f "$REPO_DIR/amp_llm_v3/requirements.txt" ]; then
        sudo -u "$RUN_USER" pip3 install -q -r "$REPO_DIR/amp_llm_v3/requirements.txt" >> "$LOG_FILE" 2>&1
    fi
    for req_file in "$REPO_DIR/amp_llm_v3/standalone modules"/**/requirements.txt; do
        if [ -f "$req_file" ]; then
            sudo -u "$RUN_USER" pip3 install -q -r "$req_file" >> "$LOG_FILE" 2>&1
        fi
    done
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Dependencies installed" >> "$LOG_FILE"

    # Wait for chat LLM jobs only (short-lived, usually < 60s)
    # Agent-annotate jobs are long-running and auto-resume after restart,
    # so we don't wait for them — just restart and the orchestrator picks up.
    WEBAPP_URL="http://localhost:8000"
    MAX_WAIT=120
    POLL_INTERVAL=5
    WAITED=0
    JOBS_RESPONSE=$(curl -s --max-time 5 "$WEBAPP_URL/api/chat/jobs" 2>/dev/null)
    if [ -n "$JOBS_RESPONSE" ]; then
        CHAT_ACTIVE=$(echo "$JOBS_RESPONSE" | python3 -c "import sys, json; data = json.load(sys.stdin); print(data.get('active', 0))" 2>/dev/null)
        CHAT_ACTIVE=${CHAT_ACTIVE:-0}
        if [ "$CHAT_ACTIVE" != "0" ]; then
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⏳ $CHAT_ACTIVE chat job(s) running, waiting up to ${MAX_WAIT}s..." >> "$LOG_FILE"
            while [ "$CHAT_ACTIVE" != "0" ] && [ $WAITED -lt $MAX_WAIT ]; do
                sleep $POLL_INTERVAL
                WAITED=$((WAITED + POLL_INTERVAL))
                JOBS_RESPONSE=$(curl -s --max-time 5 "$WEBAPP_URL/api/chat/jobs" 2>/dev/null)
                CHAT_ACTIVE=$(echo "$JOBS_RESPONSE" | python3 -c "import sys, json; data = json.load(sys.stdin); print(data.get('active', 0))" 2>/dev/null)
                CHAT_ACTIVE=${CHAT_ACTIVE:-0}
            done
        fi
    fi
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Proceeding with restart..." >> "$LOG_FILE"

    # Check if agent-annotate has an active job — if so, skip restarting it.
    # Restarting mid-job interrupts the current trial and wastes the Ollama
    # inference time. The code changes will take effect after the job completes
    # and the service is restarted on the next update cycle.
    ANNOTATE_URL="http://localhost:8005"
    ANNOTATE_ACTIVE=0
    ANNOTATE_RESPONSE=$(curl -s --max-time 3 "$ANNOTATE_URL/api/jobs/active" 2>/dev/null)
    if [ -n "$ANNOTATE_RESPONSE" ]; then
        ANNOTATE_ACTIVE=$(echo "$ANNOTATE_RESPONSE" | python3 -c "import sys, json; data = json.load(sys.stdin); print(data.get('active', 0))" 2>/dev/null)
        ANNOTATE_ACTIVE=${ANNOTATE_ACTIVE:-0}
    fi
    SKIP_ANNOTATE=""
    if [ "$ANNOTATE_ACTIVE" != "0" ]; then
        SKIP_ANNOTATE="com.amplm.annotate"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⏭️ Skipping annotate restart — $ANNOTATE_ACTIVE active job(s). Code changes apply after job completes." >> "$LOG_FILE"
    fi

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🧹 Restarting MAIN services..." >> "$LOG_FILE"
    SERVICES=""
    for plist_file in "$PLIST_DIR"/com.amplm.*.plist; do
        if [ -f "$plist_file" ]; then
            LABEL=$(basename "$plist_file" .plist)
            case "$LABEL" in
                *.dev) continue ;;
                "$SELF_SERVICE") continue ;;
            esac
            # Skip annotate service if it has an active job
            if [ "$LABEL" = "$SKIP_ANNOTATE" ]; then
                continue
            fi
            SERVICES="$SERVICES $LABEL"
        fi
    done
    SERVICES=$(echo "$SERVICES" | xargs)

    if [ -z "$SERVICES" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️ No com.amplm.* prod plists found (or all skipped)" >> "$LOG_FILE"
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Found services to restart: $SERVICES" >> "$LOG_FILE"
        for service in $SERVICES; do
            launchctl bootout "system/$service" 2>/dev/null || true
        done
        sleep 2
        for service in $SERVICES; do
            PLIST_FILE="$PLIST_DIR/${service}.plist"
            if [ -f "$PLIST_FILE" ]; then
                launchctl bootstrap system "$PLIST_FILE" 2>/dev/null || launchctl load "$PLIST_FILE" 2>/dev/null || true
            fi
        done
        sleep 3
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 📊 Final service status..." >> "$LOG_FILE"
        for service in $SERVICES; do
            STATUS=$(launchctl print "system/$service" 2>/dev/null | grep "pid =" | awk '{print $3}')
            if [ -n "$STATUS" ]; then
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ $service running with PID: $STATUS" >> "$LOG_FILE"
            else
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] ❌ $service not running" >> "$LOG_FILE"
            fi
        done
    fi

    # Run site verification (background, non-blocking)
    /Users/amphoraxe/Developer/amphoraxe/auth.amphoraxe.ca/verify/run.sh amp_llm
    /Users/amphoraxe/Developer/amphoraxe/auth.amphoraxe.ca/verify/run.sh agent_annotate

    echo "$LOCAL_HASH" > "$LAST_DEPLOYED_FILE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ MAIN update and restart complete." >> "$LOG_FILE"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🟢 No updates found on MAIN branch." >> "$LOG_FILE"
fi

echo "" >> "$LOG_FILE"
