#!/bin/bash
# ============================================================================
# Fix Cloudflare Tunnel Setup
# ============================================================================

set -e

PROJECT_DIR="$HOME/Developer/AMP_LLMs/amp_llm_v3"

echo "═══════════════════════════════════════════════════════"
echo "Cloudflare Tunnel Setup & Fix"
echo "═══════════════════════════════════════════════════════"

# ----------------------------------------------------------------------------
# Step 1: Check if cloudflared is installed
# ----------------------------------------------------------------------------
echo ""
echo "Step 1: Checking cloudflared installation..."

if ! command -v cloudflared &> /dev/null; then
    echo "❌ cloudflared not installed"
    echo ""
    echo "Install with:"
    echo "  brew install cloudflared"
    exit 1
fi

echo "✅ cloudflared is installed"
cloudflared --version

# ----------------------------------------------------------------------------
# Step 2: List existing tunnels
# ----------------------------------------------------------------------------
echo ""
echo "Step 2: Checking for existing tunnels..."

TUNNEL_LIST=$(cloudflared tunnel list 2>&1)

echo "$TUNNEL_LIST"

if echo "$TUNNEL_LIST" | grep -q "amp-llm"; then
    echo "✅ Found amp-llm tunnel"
    TUNNEL_ID=$(echo "$TUNNEL_LIST" | grep "amp-llm" | awk '{print $1}')
    echo "   Tunnel ID: $TUNNEL_ID"
else
    echo ""
    echo "❌ No amp-llm tunnel found!"
    echo ""
    echo "You need to create one:"
    echo "  1. Login: cloudflared tunnel login"
    echo "  2. Create: cloudflared tunnel create amp-llm"
    echo "  3. Route DNS: cloudflared tunnel route dns amp-llm llm.amphoraxe.ca"
    echo ""
    read -p "Do you want to create it now? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo ""
        echo "Creating tunnel..."
        cloudflared tunnel create amp-llm
        
        TUNNEL_ID=$(cloudflared tunnel list | grep "amp-llm" | awk '{print $1}')
        echo "✅ Created tunnel with ID: $TUNNEL_ID"
        
        echo ""
        echo "Routing DNS..."
        cloudflared tunnel route dns amp-llm llm.amphoraxe.ca
        echo "✅ DNS routed"
    else
        echo "Exiting. Please create tunnel manually."
        exit 1
    fi
fi

# ----------------------------------------------------------------------------
# Step 3: Create/Update config file
# ----------------------------------------------------------------------------
echo ""
echo "Step 3: Setting up configuration..."

CONFIG_DIR="$HOME/.cloudflared"
CONFIG_FILE="$CONFIG_DIR/config.yml"

mkdir -p "$CONFIG_DIR"

# Find credentials file
CREDS_FILE=$(find "$CONFIG_DIR" -name "${TUNNEL_ID}.json" 2>/dev/null | head -1)

if [ -z "$CREDS_FILE" ]; then
    echo "⚠️  Credentials file not found for tunnel $TUNNEL_ID"
    echo "Looking for any .json files..."
    CREDS_FILE=$(find "$CONFIG_DIR" -name "*.json" 2>/dev/null | head -1)
fi

if [ -z "$CREDS_FILE" ]; then
    echo "❌ No credentials file found!"
    echo ""
    echo "Run: cloudflared tunnel login"
    exit 1
fi

echo "✅ Found credentials: $(basename $CREDS_FILE)"

# Create config file
cat > "$CONFIG_FILE" <<EOF
tunnel: $TUNNEL_ID
credentials-file: $CREDS_FILE

ingress:
  - hostname: llm.amphoraxe.ca
    service: http://localhost:8000
  - service: http_status:404
EOF

echo "✅ Created config file: $CONFIG_FILE"
echo ""
echo "Configuration:"
cat "$CONFIG_FILE"

# ----------------------------------------------------------------------------
# Step 4: Create LaunchAgent
# ----------------------------------------------------------------------------
echo ""
echo "Step 4: Creating LaunchAgent..."

PLIST_FILE="$HOME/Library/LaunchAgents/com.cloudflare.cloudflared.plist"

cat > "$PLIST_FILE" <<EOF
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
        <string>$TUNNEL_ID</string>
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

chmod 644 "$PLIST_FILE"
echo "✅ Created LaunchAgent: $PLIST_FILE"

# ----------------------------------------------------------------------------
# Step 5: Load and start service
# ----------------------------------------------------------------------------
echo ""
echo "Step 5: Starting tunnel service..."

# Unload if already loaded
launchctl unload "$PLIST_FILE" 2>/dev/null || true

# Load the service
launchctl load "$PLIST_FILE"

# Start it
launchctl start com.cloudflare.cloudflared

sleep 3

# ----------------------------------------------------------------------------
# Step 6: Check status
# ----------------------------------------------------------------------------
echo ""
echo "═══════════════════════════════════════════════════════"
echo "Status Check"
echo "═══════════════════════════════════════════════════════"

echo ""
echo "Service status:"
if launchctl list | grep -q "com.cloudflare.cloudflared"; then
    echo "✅ Tunnel service is running"
    launchctl list | grep cloudflared
else
    echo "❌ Tunnel service failed to start"
    echo ""
    echo "Check logs:"
    echo "  tail -f $PROJECT_DIR/logs/cloudflared.error.log"
    exit 1
fi

echo ""
echo "Recent logs:"
tail -10 "$PROJECT_DIR/logs/cloudflared.log" 2>/dev/null || echo "No logs yet"

# ----------------------------------------------------------------------------
# Step 7: Test connectivity
# ----------------------------------------------------------------------------
echo ""
echo "═══════════════════════════════════════════════════════"
echo "Testing Connectivity"
echo "═══════════════════════════════════════════════════════"

echo ""
echo "Waiting for tunnel to establish..."
sleep 5

echo ""
echo "1. Local server:"
if curl -s http://localhost:8000/health > /dev/null; then
    echo "✅ localhost:8000 is responding"
else
    echo "❌ localhost:8000 is NOT responding"
    echo "   Start webapp service first:"
    echo "   launchctl start com.amplm.webapp"
fi

echo ""
echo "2. External URL:"
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://llm.amphoraxe.ca/health 2>/dev/null || echo "000")

if [ "$HTTP_STATUS" = "200" ]; then
    echo "✅ https://llm.amphoraxe.ca is accessible!"
    curl -s https://llm.amphoraxe.ca/health | python3 -m json.tool
elif [ "$HTTP_STATUS" = "403" ]; then
    echo "⚠️  Got 403 - Cloudflare Access may be enabled"
    echo "   Try accessing in browser: https://llm.amphoraxe.ca"
elif [ "$HTTP_STATUS" = "502" ]; then
    echo "❌ Got 502 Bad Gateway"
    echo "   Tunnel is running but can't reach local server"
    echo "   Check: launchctl list | grep amplm"
elif [ "$HTTP_STATUS" = "000" ]; then
    echo "❌ Cannot connect to https://llm.amphoraxe.ca"
    echo ""
    echo "Possible issues:"
    echo "  1. DNS not propagated yet (wait 5-10 minutes)"
    echo "  2. Tunnel not properly connected"
    echo "  3. Check tunnel logs for errors"
else
    echo "⚠️  Got HTTP $HTTP_STATUS"
    echo "   Try: curl -I https://llm.amphoraxe.ca"
fi

# ----------------------------------------------------------------------------
# Summary
# ----------------------------------------------------------------------------
echo ""
echo "═══════════════════════════════════════════════════════"
echo "Setup Complete!"
echo "═══════════════════════════════════════════════════════"

cat <<EOF

Next Steps:
-----------

1. View tunnel logs:
   tail -f $PROJECT_DIR/logs/cloudflared.log

2. Access your app:
   https://llm.amphoraxe.ca

3. If you get 403 Forbidden:
   - This means Cloudflare Access is blocking
   - Go to Cloudflare Dashboard -> Zero Trust -> Access
   - Add your email to the allow list

4. If page doesn't load:
   - Wait 5-10 minutes for DNS propagation
   - Check tunnel is connected: tail -f logs/cloudflared.log
   - Look for "Connection registered" message

Useful Commands:
----------------

Check tunnel status:
  cloudflared tunnel info $TUNNEL_ID

Restart tunnel:
  launchctl stop com.cloudflare.cloudflared
  launchctl start com.cloudflare.cloudflared

View logs:
  tail -f $PROJECT_DIR/logs/cloudflared.log

Manual test:
  cloudflared tunnel run $TUNNEL_ID

═══════════════════════════════════════════════════════════
EOF