#!/bin/bash

# ============================================================================
# Setup Auto-Restart for AMP LLM Services (4-Service Architecture)
# ============================================================================

echo "═══════════════════════════════════════════════════════"
echo "AMP LLM Auto-Restart Setup (4-Service Architecture)"
echo "═══════════════════════════════════════════════════════"
echo ""

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$SCRIPT_DIR"

echo "Project Directory: $PROJECT_DIR"
echo ""

# Check if virtual environment exists
if [ ! -d "$PROJECT_DIR/llm_env" ]; then
    echo "❌ Virtual environment not found at $PROJECT_DIR/llm_env"
    echo "Please create it first with: python3 -m venv llm_env"
    exit 1
fi

# Create logs directory
mkdir -p "$PROJECT_DIR/logs"
echo "✅ Created logs directory"

# Update username in plist files
USERNAME=$(whoami)
echo "👤 Username: $USERNAME"

# Service definitions
declare -A services=(
    ["webapp"]="8000:webapp.server:app"
    ["chat"]="9001:chat_api_with_annotation:app"
    ["nct"]="9002:nct_api:app"
    ["runner"]="9003:runner_service:app"
)

declare -A working_dirs=(
    ["webapp"]="$PROJECT_DIR/webapp"
    ["chat"]="$PROJECT_DIR/standalone modules/chat_with_llm"
    ["nct"]="$PROJECT_DIR/standalone modules/nct_lookup"
    ["runner"]="$PROJECT_DIR/standalone modules/runner"
)

# LaunchAgents directory
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$LAUNCH_AGENTS_DIR"

echo ""
echo "Creating LaunchAgent plists..."
echo ""

for service in "${!services[@]}"; do
    IFS=':' read -r port module app <<< "${services[$service]}"
    working_dir="${working_dirs[$service]}"
    
    PLIST_FILE="$LAUNCH_AGENTS_DIR/com.amplm.$service.plist"
    
    echo "Creating plist for $service service (port $port)..."
    
    cat > "$PLIST_FILE" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.amplm.$service</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>$PROJECT_DIR/llm_env/bin/python</string>
        <string>-m</string>
        <string>uvicorn</string>
        <string>$module:$app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>$port</string>
    </array>
    
    <key>WorkingDirectory</key>
    <string>$working_dir</string>
    
    <key>StandardOutPath</key>
    <string>$PROJECT_DIR/logs/${service}_service.log</string>
    
    <key>StandardErrorPath</key>
    <string>$PROJECT_DIR/logs/${service}_service.error.log</string>
    
    <key>RunAtLoad</key>
    <true/>
    
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
        <key>Crashed</key>
        <true/>
    </dict>
    
    <key>ProcessType</key>
    <string>Interactive</string>
    
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
        <key>PATH</key>
        <string>$PROJECT_DIR/llm_env/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    
    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>
EOF
    
    echo "  ✅ Created $PLIST_FILE"
done

echo ""
echo "Loading services..."
echo ""

for service in "${!services[@]}"; do
    echo "Loading $service service..."
    
    # Unload if already loaded
    launchctl unload "$LAUNCH_AGENTS_DIR/com.amplm.$service.plist" 2>/dev/null
    
    # Load the service
    if launchctl load "$LAUNCH_AGENTS_DIR/com.amplm.$service.plist"; then
        echo "  ✅ $service service loaded"
    else
        echo "  ❌ Failed to load $service service"
    fi
done

echo ""
echo "Waiting for services to start..."
sleep 5

echo ""
echo "═══════════════════════════════════════════════════════"
echo "Service Status"
echo "═══════════════════════════════════════════════════════"
echo ""

# Check service status
for service in "${!services[@]}"; do
    IFS=':' read -r port module app <<< "${services[$service]}"
    
    if launchctl list | grep -q "com.amplm.$service"; then
        echo "✅ $service: Running (port $port)"
    else
        echo "❌ $service: Not running"
    fi
done

echo ""
echo "Checking ports..."
echo ""

for service in "${!services[@]}"; do
    IFS=':' read -r port module app <<< "${services[$service]}"
    
    if lsof -i :$port | grep -q LISTEN; then
        echo "✅ Port $port ($service): Active"
    else
        echo "❌ Port $port ($service): Not listening"
    fi
done

echo ""
echo "═══════════════════════════════════════════════════════"
echo "Setup Complete!"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "Services are now configured to:"
echo "  • Start automatically on login"
echo "  • Restart automatically if they crash"
echo "  • Run in the background"
echo ""
echo "Service Architecture:"
echo "  Port 8000 - Webapp (Web Interface)"
echo "  Port 9001 - Chat Service with Annotation"
echo "  Port 9002 - NCT Lookup Service"
echo "  Port 9003 - Runner Service (File Manager)"
echo ""
echo "Management commands:"
echo "  Start service:   launchctl start com.amplm.[service]"
echo "  Stop service:    launchctl stop com.amplm.[service]"
echo "  Restart service: launchctl stop com.amplm.[service] && launchctl start com.amplm.[service]"
echo "  View status:     launchctl list | grep amplm"
echo "  Remove service:  launchctl unload ~/Library/LaunchAgents/com.amplm.[service].plist"
echo ""
echo "Service names: webapp, chat, nct, runner"
echo ""
echo "Logs are stored in: $PROJECT_DIR/logs/"
echo "  View logs: tail -f $PROJECT_DIR/logs/[service]_service.log"
echo ""
echo "Access the web interface at: http://localhost:8000"
echo ""