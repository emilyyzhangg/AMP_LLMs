#!/bin/bash
# ============================================================================
# Setup Automatic Service Restart on Git Pull (Updated for Integrated Architecture)
# ============================================================================

set -e

PROJECT_DIR="$HOME/amp_llm_v3"
USER_HOME="$HOME"

echo "═══════════════════════════════════════════════════════"
echo "Setting Up Auto-Restart on Git Pull"
echo "Updated for Integrated Chat + Research Architecture"
echo "═══════════════════════════════════════════════════════"

# Get current username
CURRENT_USER=$(whoami)
echo "Current User: $CURRENT_USER"
echo "Project Directory: $PROJECT_DIR"
echo ""

# ============================================================================
# Step 1: Create LaunchAgents for all services
# ============================================================================

echo "Step 1: Creating LaunchAgents for all services..."
echo ""

# Create logs directory
mkdir -p "$PROJECT_DIR/logs"
echo "✅ Created logs directory"

# --- Webapp LaunchAgent ---
echo "Creating webapp LaunchAgent..."
cat > "$HOME/Library/LaunchAgents/com.amplm.webapp.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.amplm.webapp</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>-m</string>
        <string>uvicorn</string>
        <string>webapp.server:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>9000</string>
        <string>--reload</string>
    </array>
    
    <key>WorkingDirectory</key>
    <string>$PROJECT_DIR</string>
    
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
        <key>PYTHONPATH</key>
        <string>$PROJECT_DIR</string>
    </dict>
    
    <key>RunAtLoad</key>
    <true/>
    
    <key>KeepAlive</key>
    <true/>
    
    <key>StandardOutPath</key>
    <string>$PROJECT_DIR/logs/webapp.log</string>
    
    <key>StandardErrorPath</key>
    <string>$PROJECT_DIR/logs/webapp.error.log</string>
</dict>
</plist>
EOF
echo "✅ Created webapp LaunchAgent (port 9000)"

# --- Integrated Chat + Research Service LaunchAgent ---
echo "Creating integrated chat + research service LaunchAgent..."

# Check which service file exists

cat > "$HOME/Library/LaunchAgents/com.amplm.chat.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.amplm.chat</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>-m</string>
        <string>uvicorn</string>
        <string>chat_service_integrated:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>9001</string>
        <string>--reload</string>
    </array>
    
    <key>WorkingDirectory</key>
    <string>$PROJECT_DIR/standalone modules/chat_with_llm</string>
    
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
        <key>PYTHONPATH</key>
        <string>$PROJECT_DIR</string>
    </dict>
    
    <key>RunAtLoad</key>
    <true/>
    
    <key>KeepAlive</key>
    <true/>
    
    <key>StandardOutPath</key>
    <string>$PROJECT_DIR/logs/chat.log</string>
    
    <key>StandardErrorPath</key>
    <string>$PROJECT_DIR/logs/chat.error.log</string>
</dict>
</plist>
EOF
echo "✅ Created chat service LaunchAgent (port 9001)"
echo "   Service: Integrated Chat + Research Service"

# --- NCT Service LaunchAgent ---
echo "Creating NCT service LaunchAgent..."

# Read API keys from .env if it exists
SERPAPI_KEY=""
NCBI_API_KEY=""
if [ -f "$PROJECT_DIR/standalone modules/nct_lookup/.env" ]; then
    source "$PROJECT_DIR/standalone modules/nct_lookup/.env"
fi

cat > "$HOME/Library/LaunchAgents/com.amplm.nct.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.amplm.nct</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>-m</string>
        <string>uvicorn</string>
        <string>nct_api:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>9002</string>
        <string>--reload</string>
    </array>
    
    <key>WorkingDirectory</key>
    <string>$PROJECT_DIR/standalone modules/nct_lookup</string>
    
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
        <key>PYTHONPATH</key>
        <string>$PROJECT_DIR</string>
        <key>SERPAPI_KEY</key>
        <string>$SERPAPI_KEY</string>
        <key>NCBI_API_KEY</key>
        <string>$NCBI_API_KEY</string>
    </dict>
    
    <key>RunAtLoad</key>
    <true/>
    
    <key>KeepAlive</key>
    <true/>
    
    <key>StandardOutPath</key>
    <string>$PROJECT_DIR/logs/nct.log</string>
    
    <key>StandardErrorPath</key>
    <string>$PROJECT_DIR/logs/nct.error.log</string>
</dict>
</plist>
EOF
echo "✅ Created NCT service LaunchAgent (port 9002)"

# Set permissions
chmod 644 "$HOME/Library/LaunchAgents/com.amplm."*.plist
echo "✅ Set LaunchAgent permissions"

# ============================================================================
# Step 2: Install Git Hook
# ============================================================================

echo ""
echo "Step 2: Installing Git post-merge hook..."

GIT_HOOKS_DIR="$PROJECT_DIR/.git/hooks"
HOOK_FILE="$GIT_HOOKS_DIR/post-merge"

# Create hooks directory if it doesn't exist
mkdir -p "$GIT_HOOKS_DIR"

# Create the post-merge hook
cat > "$HOOK_FILE" <<'EOF'
#!/bin/bash
# ============================================================================
# Git Post-Merge Hook - Auto-restart services after git pull
# Updated for Integrated Chat + Research Architecture
# ============================================================================

set -e

PROJECT_DIR="$(git rev-parse --show-toplevel)"
cd "$PROJECT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo "═══════════════════════════════════════════════════════"
echo "Git Pull Detected - Checking for Service Restarts"
echo "═══════════════════════════════════════════════════════"

# Function to check if files changed in a directory
files_changed_in_dir() {
    local dir=$1
    git diff-tree -r --name-only --no-commit-id ORIG_HEAD HEAD | grep -q "^$dir/"
}

# Function to restart a service
restart_service() {
    local service_name=$1
    local service_label=$2
    
    echo ""
    echo -e "${YELLOW}Restarting $service_name...${NC}"
    
    if launchctl list | grep -q "$service_label"; then
        launchctl stop "$service_label"
        sleep 2
        launchctl start "$service_label"
        
        sleep 3
        if launchctl list | grep -q "$service_label"; then
            echo -e "${GREEN}✅ $service_name restarted${NC}"
        else
            echo -e "${RED}❌ $service_name failed to restart${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️  $service_name not running${NC}"
    fi
}

RESTART_NEEDED=false

# Check webapp changes
if files_changed_in_dir "webapp"; then
    echo "📝 Changes detected in webapp/"
    restart_service "Webapp" "com.amplm.webapp"
    RESTART_NEEDED=true
fi

# Check chat service changes (now includes research)
if files_changed_in_dir "standalone modules/chat_with_llm"; then
    echo "📝 Changes detected in chat_with_llm/"
    echo -e "${BLUE}   Note: This includes both chat AND research functionality${NC}"
    restart_service "Integrated Chat + Research Service" "com.amplm.chat"
    RESTART_NEEDED=true
fi

# Check NCT service changes
if files_changed_in_dir "standalone modules/nct_lookup"; then
    echo "📝 Changes detected in nct_lookup/"
    restart_service "NCT Service" "com.amplm.nct"
    RESTART_NEEDED=true
fi

# Check for specific file changes that require restart
if git diff-tree -r --name-only --no-commit-id ORIG_HEAD HEAD | grep -qE '\.(py|json|env)$'; then
    if [ "$RESTART_NEEDED" = false ]; then
        echo "📝 Python/config changes detected"
        
        # Check if it's in a service directory
        if git diff-tree -r --name-only --no-commit-id ORIG_HEAD HEAD | grep -qE 'chat_service_integrated|research_routes|chat_api'; then
            echo "   Restarting chat service (integrated chat + research)"
            restart_service "Integrated Chat + Research Service" "com.amplm.chat"
            RESTART_NEEDED=true
        else
            echo "   Restarting all services as precaution..."
            restart_service "Webapp" "com.amplm.webapp"
            restart_service "Integrated Chat + Research Service" "com.amplm.chat"
            restart_service "NCT Service" "com.amplm.nct"
            RESTART_NEEDED=true
        fi
    fi
fi

if [ "$RESTART_NEEDED" = false ]; then
    echo "✅ No service restarts needed"
fi

echo ""
echo "═══════════════════════════════════════════════════════"
echo "Service Status:"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "LaunchCtl Services:"
launchctl list | grep -E "com.amplm.(webapp|chat|nct)" || echo "No services running"
echo ""
echo "Port Status:"
echo "  Port 9000 (Webapp):                $(lsof -i :9000 | grep -q LISTEN && echo '✅ Active' || echo '❌ Inactive')"
echo "  Port 9001 (Chat + Research):       $(lsof -i :9001 | grep -q LISTEN && echo '✅ Active' || echo '❌ Inactive')"
echo "  Port 9002 (NCT Lookup):            $(lsof -i :9002 | grep -q LISTEN && echo '✅ Active' || echo '❌ Inactive')"
echo ""
echo "═══════════════════════════════════════════════════════"
echo ""
EOF

# Make hook executable
chmod +x "$HOOK_FILE"
echo "✅ Installed git post-merge hook"

# ============================================================================
# Step 3: Load and Start Services
# ============================================================================

echo ""
echo "Step 3: Loading and starting services..."

# Unload existing services (ignore errors)
launchctl unload "$HOME/Library/LaunchAgents/com.amplm.webapp.plist" 2>/dev/null || true
launchctl unload "$HOME/Library/LaunchAgents/com.amplm.chat.plist" 2>/dev/null || true
launchctl unload "$HOME/Library/LaunchAgents/com.amplm.nct.plist" 2>/dev/null || true

sleep 2

# Load services
echo "Loading webapp..."
launchctl load "$HOME/Library/LaunchAgents/com.amplm.webapp.plist"
echo "✅ Webapp loaded"

echo "Loading integrated chat + research service..."
launchctl load "$HOME/Library/LaunchAgents/com.amplm.chat.plist"
echo "✅ Integrated chat + research service loaded"

echo "Loading NCT service..."
launchctl load "$HOME/Library/LaunchAgents/com.amplm.nct.plist"
echo "✅ NCT service loaded"

sleep 3

# Start services
echo ""
echo "Starting services..."
launchctl start com.amplm.webapp
launchctl start com.amplm.chat
launchctl start com.amplm.nct

sleep 5

# ============================================================================
# Step 4: Verify Services
# ============================================================================

echo ""
echo "═══════════════════════════════════════════════════════"
echo "Service Status Check"
echo "═══════════════════════════════════════════════════════"

echo ""
echo "LaunchCtl Status:"
launchctl list | grep -E "com.amplm.(webapp|chat|nct)" || echo "❌ No services found"

echo ""
echo "Port Status:"
echo "Port 9000 (Webapp):"
lsof -i :9000 | grep LISTEN || echo "  ❌ Not listening"

echo ""
echo "Port 9001 (Integrated Chat + Research):"
lsof -i :9001 | grep LISTEN || echo "  ❌ Not listening"

echo ""
echo "Port 9002 (NCT Lookup):"
lsof -i :9002 | grep LISTEN || echo "  ❌ Not listening"

echo ""
echo "Health Checks:"
echo "Webapp:"
curl -s http://localhost:9000/health | python3 -m json.tool 2>/dev/null || echo "  ❌ Not responding"

echo ""
echo "Integrated Chat + Research Service:"
curl -s http://localhost:9001/health | python3 -m json.tool 2>/dev/null || echo "  ❌ Not responding"

echo ""
echo "Research Endpoints:"
curl -s http://localhost:9001/research/health | python3 -m json.tool 2>/dev/null || echo "  ❌ Not responding"

echo ""
echo "NCT Service:"
curl -s http://localhost:9002/health | python3 -m json.tool 2>/dev/null || echo "  ❌ Not responding"

# ============================================================================
# Summary
# ============================================================================

echo ""
echo "═══════════════════════════════════════════════════════"
echo "Setup Complete!"
echo "═══════════════════════════════════════════════════════"

cat <<EOF

✅ All services configured for auto-restart on git pull!

Architecture:
─────────────
• Port 9001 now runs INTEGRATED service with:
  - Chat endpoints:     /chat/*
  - Research endpoints: /research/*
• Port 9002 - NCT Lookup (data fetching)
• Port 9000 - Web Interface

What This Does:
───────────────
When you run 'git pull', the post-merge hook will:
1. Detect which files changed
2. Automatically restart affected services
3. Handle integrated chat + research as one service
4. Show you the status

Services:
─────────
• Webapp                      - http://localhost:9000
• Integrated Chat + Research  - http://localhost:9001
  - API Docs                  - http://localhost:9001/docs
  - Chat API                  - http://localhost:9001/chat/*
  - Research API              - http://localhost:9001/research/*
• NCT Lookup                  - http://localhost:9002

Test It:
────────
1. Make a change to any service file
2. Commit and push from another machine (or create a test branch)
3. Run: git pull
4. Watch services auto-restart!

Test Research Integration:
─────────────────────────
curl http://localhost:9001/research/health

View Logs:
──────────
tail -f $PROJECT_DIR/logs/webapp.log
tail -f $PROJECT_DIR/logs/chat.log       # Includes research logs
tail -f $PROJECT_DIR/logs/nct.log

Manage Services:
────────────────
# Stop all
launchctl stop com.amplm.webapp
launchctl stop com.amplm.chat     # Stops both chat AND research
launchctl stop com.amplm.nct

# Start all
launchctl start com.amplm.webapp
launchctl start com.amplm.chat    # Starts both chat AND research
launchctl start com.amplm.nct

# Restart all
launchctl stop com.amplm.webapp && launchctl start com.amplm.webapp
launchctl stop com.amplm.chat && launchctl start com.amplm.chat
launchctl stop com.amplm.nct && launchctl start com.amplm.nct

# Check status
launchctl list | grep com.amplm

# View realtime logs
tail -f $PROJECT_DIR/logs/*.log

Important Notes:
────────────────
• Research assistant is now INTEGRATED with chat service
• Both chat and research share same Ollama connection
• Restarting com.amplm.chat restarts BOTH functionalities

Disable Auto-Restart:
─────────────────────
rm $PROJECT_DIR/.git/hooks/post-merge

Re-enable:
──────────
Run this script again

═══════════════════════════════════════════════════════════
EOF