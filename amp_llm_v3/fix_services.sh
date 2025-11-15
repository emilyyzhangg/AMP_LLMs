#!/bin/bash
# ============================================================================
# Fix LaunchAgents to Use Virtual Environment
# ============================================================================

set -e

PROJECT_DIR="$HOME/amp_llm_v3"
VENV_PYTHON="$PROJECT_DIR/llm_env/bin/python"

echo "═══════════════════════════════════════════════════════"
echo "Fixing LaunchAgents to Use Virtual Environment"
echo "═══════════════════════════════════════════════════════"

# Check if virtual environment exists
if [ ! -f "$VENV_PYTHON" ]; then
    echo "❌ Virtual environment not found at: $VENV_PYTHON"
    echo ""
    echo "Please create it first:"
    echo "  cd $PROJECT_DIR"
    echo "  python3 -m venv llm_env"
    echo "  source llm_env/bin/activate"
    echo "  pip install -r requirements.txt"
    exit 1
fi

echo "✅ Found virtual environment at: $VENV_PYTHON"
echo ""

# Stop existing services
echo "Stopping existing services..."
launchctl stop com.amplm.webapp 2>/dev/null || true
launchctl stop com.amplm.chat 2>/dev/null || true
launchctl stop com.amplm.nct 2>/dev/null || true
sleep 2

# Unload existing services
echo "Unloading existing services..."
launchctl unload ~/Library/LaunchAgents/com.amplm.webapp.plist 2>/dev/null || true
launchctl unload ~/Library/LaunchAgents/com.amplm.chat.plist 2>/dev/null || true
launchctl unload ~/Library/LaunchAgents/com.amplm.nct.plist 2>/dev/null || true
sleep 2

# Create logs directory
mkdir -p "$PROJECT_DIR/logs"

# --- Webapp LaunchAgent ---
echo "Creating fixed webapp LaunchAgent..."
cat > "$HOME/Library/LaunchAgents/com.amplm.webapp.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.amplm.webapp</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>$VENV_PYTHON</string>
        <string>-m</string>
        <string>uvicorn</string>
        <string>webapp.server:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>9000</string>
    </array>
    
    <key>WorkingDirectory</key>
    <string>$PROJECT_DIR</string>
    
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>$PROJECT_DIR/llm_env/bin:/usr/local/bin:/usr/bin:/bin</string>
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

# --- Chat Service LaunchAgent ---
echo "Creating fixed chat service LaunchAgent..."
cat > "$HOME/Library/LaunchAgents/com.amplm.chat.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.amplm.chat</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>$VENV_PYTHON</string>
        <string>-m</string>
        <string>uvicorn</string>
        <string>chat_service_integrated:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>9001</string>
    </array>
    
    <key>WorkingDirectory</key>
    <string>$PROJECT_DIR/standalone modules/chat_with_llm</string>
    
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>$PROJECT_DIR/llm_env/bin:/usr/local/bin:/usr/bin:/bin</string>
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

# --- NCT Service LaunchAgent ---
echo "Creating fixed NCT service LaunchAgent..."

# Read API keys from .env if it exists
SERPAPI_KEY=""
NCBI_API_KEY=""
if [ -f "$PROJECT_DIR/standalone modules/nct_lookup/.env" ]; then
    export $(grep -v '^#' "$PROJECT_DIR/standalone modules/nct_lookup/.env" | xargs)
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
        <string>$VENV_PYTHON</string>
        <string>-m</string>
        <string>uvicorn</string>
        <string>nct_api:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>9002</string>
    </array>
    
    <key>WorkingDirectory</key>
    <string>$PROJECT_DIR/standalone modules/nct_lookup</string>
    
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>$PROJECT_DIR/llm_env/bin:/usr/local/bin:/usr/bin:/bin</string>
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

# Set permissions
chmod 644 ~/Library/LaunchAgents/com.amplm.*.plist
echo "✅ Set permissions"

# Load and start services
echo ""
echo "Loading services..."
launchctl load ~/Library/LaunchAgents/com.amplm.webapp.plist
echo "✅ Loaded webapp"

launchctl load ~/Library/LaunchAgents/com.amplm.chat.plist
echo "✅ Loaded chat"

launchctl load ~/Library/LaunchAgents/com.amplm.nct.plist
echo "✅ Loaded nct"

echo ""
echo "Starting services..."
launchctl start com.amplm.webapp
launchctl start com.amplm.chat
launchctl start com.amplm.nct

echo ""
echo "Waiting for services to start..."
sleep 10

# Check status
echo ""
echo "═══════════════════════════════════════════════════════"
echo "Service Status"
echo "═══════════════════════════════════════════════════════"

echo ""
echo "LaunchCtl Status:"
launchctl list | grep com.amplm

echo ""
echo "Port Status:"
for port in 9000 9001 9002 9003; do
    if lsof -i :$port | grep -q LISTEN; then
        echo "✅ Port $port - Active"
    else
        echo "❌ Port $port - Not listening"
    fi
done

echo ""
echo "Health Checks:"
for service in "webapp:9000" "chat:9001" "nct:9002"; do
    name=${service%:*}
    port=${service#*:}
    echo ""
    echo "$name (port $port):"
    curl -s http://localhost:$port/health 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "  ❌ Not responding"
done

echo ""
echo "═══════════════════════════════════════════════════════"
echo "If services still aren't starting, check logs:"
echo "  tail -f $PROJECT_DIR/logs/webapp.error.log"
echo "  tail -f $PROJECT_DIR/logs/chat.error.log"
echo "  tail -f $PROJECT_DIR/logs/nct.error.log"
echo "═══════════════════════════════════════════════════════"