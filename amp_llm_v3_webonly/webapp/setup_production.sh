#!/bin/bash
# ============================================================================
# Phase 4: Production Deployment - macOS LaunchDaemon Setup
# ============================================================================

echo "═══════════════════════════════════════════════════════"
echo "AMP LLM Production Deployment for macOS"
echo "═══════════════════════════════════════════════════════"

# Get current user
CURRENT_USER=$(whoami)
USER_HOME="/Users/$CURRENT_USER"
PROJECT_DIR="$USER_HOME/amp_llm_v3"
PYTHON_PATH="$PROJECT_DIR/llm_env/bin/python"

echo "Current User: $CURRENT_USER"
echo "Project Directory: $PROJECT_DIR"
echo ""

# ----------------------------------------------------------------------------
# STEP 1: Create LaunchAgent for Web Server
# ----------------------------------------------------------------------------

echo "Creating LaunchAgent for AMP LLM Web Server..."

cat > ~/Library/LaunchAgents/com.amplm.webapp.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.amplm.webapp</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_PATH</string>
        <string>-m</string>
        <string>uvicorn</string>
        <string>webapp.server:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>8000</string>
    </array>
    
    <key>WorkingDirectory</key>
    <string>$PROJECT_DIR</string>
    
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>$PROJECT_DIR/llm_env/bin:/usr/local/bin:/usr/bin:/bin</string>
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

echo "✅ Created: ~/Library/LaunchAgents/com.amplm.webapp.plist"

# ----------------------------------------------------------------------------
# STEP 2: Create LaunchAgent for Cloudflare Tunnel
# ----------------------------------------------------------------------------

echo "Creating LaunchAgent for Cloudflare Tunnel..."

cat > ~/Library/LaunchAgents/com.cloudflare.cloudflared.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.cloudflare.cloudflared</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/cloudflared</string>
        <string>tunnel</string>
        <string>run</string>
        <string>amp-llm-tunnel</string>
    </array>
    
    <key>RunAtLoad</key>
    <true/>
    
    <key>KeepAlive</key>
    <true/>
    
    <key>StandardOutPath</key>
    <string>$PROJECT_DIR/logs/cloudflared.log</string>
    
    <key>StandardErrorPath</key>
    <string>$PROJECT_DIR/logs/cloudflared.error.log</string>
</dict>
</plist>
EOF

echo "✅ Created: ~/Library/LaunchAgents/com.cloudflare.cloudflared.plist"

# ----------------------------------------------------------------------------
# STEP 3: Create logs directory
# ----------------------------------------------------------------------------

echo "Creating logs directory..."
mkdir -p "$PROJECT_DIR/logs"
echo "✅ Created: $PROJECT_DIR/logs"

# ----------------------------------------------------------------------------
# STEP 4: Set correct permissions
# ----------------------------------------------------------------------------

echo "Setting permissions..."
chmod 644 ~/Library/LaunchAgents/com.amplm.webapp.plist
chmod 644 ~/Library/LaunchAgents/com.cloudflare.cloudflared.plist
echo "✅ Permissions set"

# ----------------------------------------------------------------------------
# STEP 5: Load LaunchAgents
# ----------------------------------------------------------------------------

echo ""
echo "Loading LaunchAgents..."

# Unload if already loaded (ignore errors)
launchctl unload ~/Library/LaunchAgents/com.amplm.webapp.plist 2>/dev/null
launchctl unload ~/Library/LaunchAgents/com.cloudflare.cloudflared.plist 2>/dev/null

# Load the agents
launchctl load ~/Library/LaunchAgents/com.amplm.webapp.plist
launchctl load ~/Library/LaunchAgents/com.cloudflare.cloudflared.plist

echo "✅ LaunchAgents loaded"

# ----------------------------------------------------------------------------
# STEP 6: Start services
# ----------------------------------------------------------------------------

echo ""
echo "Starting services..."

launchctl start com.amplm.webapp
launchctl start com.cloudflare.cloudflared

sleep 3
echo "✅ Services started"

# ----------------------------------------------------------------------------
# STEP 7: Check status
# ----------------------------------------------------------------------------

echo ""
echo "═══════════════════════════════════════════════════════"
echo "Service Status Check"
echo "═══════════════════════════════════════════════════════"

echo ""
echo "Web Server Status:"
if launchctl list | grep -q "com.amplm.webapp"; then
    echo "✅ com.amplm.webapp is running"
    launchctl list | grep com.amplm.webapp
else
    echo "❌ com.amplm.webapp is not running"
fi

echo ""
echo "Cloudflare Tunnel Status:"
if launchctl list | grep -q "com.cloudflare.cloudflared"; then
    echo "✅ com.cloudflare.cloudflared is running"
    launchctl list | grep com.cloudflare.cloudflared
else
    echo "❌ com.cloudflare.cloudflared is not running"
fi

echo ""
echo "═══════════════════════════════════════════════════════"

# ----------------------------------------------------------------------------
# STEP 8: Test connectivity
# ----------------------------------------------------------------------------

echo ""
echo "Testing local web server..."
sleep 5  # Give services time to start
curl -s http://localhost:8000/health | python3 -m json.tool || echo "⚠️  Web server not responding yet (may need a moment to start)"

echo ""
echo "Testing external access..."
echo "Visit: https://llm.amphoraxe.ca/health"

echo ""
echo "═══════════════════════════════════════════════════════"
echo "Setup Complete!"
echo "═══════════════════════════════════════════════════════"

# ----------------------------------------------------------------------------
# USEFUL COMMANDS
# ----------------------------------------------------------------------------

cat <<EOF

═══════════════════════════════════════════════════════════════════
Useful Commands for Managing Services (macOS)
═══════════════════════════════════════════════════════════════════

View logs (web server):
  tail -f $PROJECT_DIR/logs/webapp.log
  tail -f $PROJECT_DIR/logs/webapp.error.log

View logs (tunnel):
  tail -f $PROJECT_DIR/logs/cloudflared.log
  tail -f $PROJECT_DIR/logs/cloudflared.error.log

Check service status:
  launchctl list | grep com.amplm.webapp
  launchctl list | grep com.cloudflare.cloudflared

Stop services:
  launchctl stop com.amplm.webapp
  launchctl stop com.cloudflare.cloudflared

Start services:
  launchctl start com.amplm.webapp
  launchctl start com.cloudflare.cloudflared

Restart services:
  launchctl stop com.amplm.webapp && launchctl start com.amplm.webapp
  launchctl stop com.cloudflare.cloudflared && launchctl start com.cloudflare.cloudflared

Unload services (disable):
  launchctl unload ~/Library/LaunchAgents/com.amplm.webapp.plist
  launchctl unload ~/Library/LaunchAgents/com.cloudflare.cloudflared.plist

Load services (enable):
  launchctl load ~/Library/LaunchAgents/com.amplm.webapp.plist
  launchctl load ~/Library/LaunchAgents/com.cloudflare.cloudflared.plist

Test local endpoint:
  curl http://localhost:8000/health

Test external endpoint:
  curl https://llm.amphoraxe.ca/health

View all running LaunchAgents:
  launchctl list

═══════════════════════════════════════════════════════════════════

TROUBLESHOOTING:

If services don't start, check logs:
  tail -n 50 $PROJECT_DIR/logs/webapp.error.log
  tail -n 50 $PROJECT_DIR/logs/cloudflared.error.log

If port 8000 is in use:
  lsof -i :8000
  kill <PID>

Test Python environment:
  $PYTHON_PATH --version
  $PYTHON_PATH -m pip list

Manually test web server:
  cd $PROJECT_DIR
  source llm_env/bin/activate
  python -m uvicorn webapp.server:app --host 0.0.0.0 --port 8000

Manually test tunnel:
  cloudflared tunnel run amp-llm-tunnel

═══════════════════════════════════════════════════════════════════
EOF