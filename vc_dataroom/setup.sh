#!/bin/bash
# VC Data Room - Complete Setup Script
# Run this script to set up the entire VC data room infrastructure

set -e

echo "================================================"
echo "  VC Data Room - Setup Script"
echo "================================================"
echo ""

# Configuration
INSTALL_DIR="/Users/amphoraxe/Developer/vc_dataroom"
SERVICES_DIR="/Users/amphoraxe/AMP_Services"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
CLOUDFLARED_CONFIG="$HOME/.cloudflared/config.yml"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_step() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# Step 1: Create directory structure
echo "Step 1: Creating directory structure..."
mkdir -p "$INSTALL_DIR"/{app,data/uploads,logs,static}
print_step "Created directories"

# Step 2: Create virtual environment
echo ""
echo "Step 2: Setting up Python virtual environment..."
if [ ! -d "$INSTALL_DIR/venv" ]; then
    python3 -m venv "$INSTALL_DIR/venv"
    print_step "Created virtual environment"
else
    print_warning "Virtual environment already exists"
fi

# Step 3: Install dependencies
echo ""
echo "Step 3: Installing Python dependencies..."
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
print_step "Installed dependencies"

# Step 4: Generate secure keys
echo ""
echo "Step 4: Generating secure keys..."
SECRET_KEY=$(openssl rand -hex 32)
ADMIN_PASSWORD=$(openssl rand -base64 12)
echo "Generated SECRET_KEY and ADMIN_PASSWORD"
print_warning "Save these securely!"
echo "  SECRET_KEY: $SECRET_KEY"
echo "  ADMIN_PASSWORD: $ADMIN_PASSWORD"
echo ""

# Step 5: Update plist with secure keys
echo "Step 5: Setting up LaunchAgent plist..."
PLIST_FILE="$INSTALL_DIR/infrastructure/plists/com.amphoraxe.vc.webapp.plist"
if [ -f "$PLIST_FILE" ]; then
    # Update the secret key and admin password in the plist
    sed -i '' "s/CHANGE_THIS_TO_A_SECURE_RANDOM_KEY/$SECRET_KEY/g" "$PLIST_FILE"
    sed -i '' "s/CHANGE_THIS_ADMIN_PASSWORD/$ADMIN_PASSWORD/g" "$PLIST_FILE"
    print_step "Updated plist with secure keys"
fi

# Step 6: Copy scripts to services directory
echo ""
echo "Step 6: Installing scripts..."
mkdir -p "$SERVICES_DIR"
cp "$INSTALL_DIR/infrastructure/scripts/vc_autoupdate.sh" "$SERVICES_DIR/"
chmod +x "$SERVICES_DIR/vc_autoupdate.sh"
print_step "Installed vc_autoupdate.sh to $SERVICES_DIR"

# Step 7: Install LaunchAgent plists
echo ""
echo "Step 7: Installing LaunchAgent plists..."
cp "$INSTALL_DIR/infrastructure/plists/com.amphoraxe.vc.webapp.plist" "$LAUNCH_AGENTS_DIR/"
cp "$INSTALL_DIR/infrastructure/plists/com.amphoraxe.vc.autoupdate.plist" "$LAUNCH_AGENTS_DIR/"
print_step "Installed plists to $LAUNCH_AGENTS_DIR"

# Step 8: Update Cloudflare config
echo ""
echo "Step 8: Updating Cloudflare tunnel config..."
if [ -f "$CLOUDFLARED_CONFIG" ]; then
    # Backup existing config
    cp "$CLOUDFLARED_CONFIG" "$CLOUDFLARED_CONFIG.backup.$(date +%Y%m%d_%H%M%S)"
    print_step "Backed up existing Cloudflare config"
fi
cp "$INSTALL_DIR/infrastructure/cloudflare/config.yml" "$CLOUDFLARED_CONFIG"
print_step "Updated Cloudflare config"

# Step 9: Add DNS route for vc.amphoraxe.ca
echo ""
echo "Step 9: Setting up DNS route..."
echo "Run this command to add the DNS route (if not already done):"
echo "  cloudflared tunnel route dns 82fa7b4f-2f7b-4afc-99d7-57ea2e6ac39e vc.amphoraxe.ca"
echo ""

# Step 10: Load services
echo "Step 10: Loading services..."
launchctl load "$LAUNCH_AGENTS_DIR/com.amphoraxe.vc.webapp.plist" 2>/dev/null || true
launchctl load "$LAUNCH_AGENTS_DIR/com.amphoraxe.vc.autoupdate.plist" 2>/dev/null || true
print_step "Loaded LaunchAgent services"

# Step 11: Restart Cloudflare tunnel
echo ""
echo "Step 11: Restarting Cloudflare tunnel..."
launchctl unload "$LAUNCH_AGENTS_DIR/com.cloudflare.cloudflared.plist" 2>/dev/null || true
sleep 2
launchctl load "$LAUNCH_AGENTS_DIR/com.cloudflare.cloudflared.plist" 2>/dev/null || true
print_step "Restarted Cloudflare tunnel"

echo ""
echo "================================================"
echo "  Setup Complete!"
echo "================================================"
echo ""
echo "Your VC Data Room should now be accessible at:"
echo "  https://vc.amphoraxe.ca"
echo ""
echo "Default admin login:"
echo "  Email: admin@amphoraxe.ca"
echo "  Password: $ADMIN_PASSWORD"
echo ""
echo "Important files:"
echo "  App:      $INSTALL_DIR/app/main.py"
echo "  Database: $INSTALL_DIR/data/dataroom.db"
echo "  Uploads:  $INSTALL_DIR/data/uploads/"
echo "  Logs:     $INSTALL_DIR/logs/"
echo ""
echo "To check service status:"
echo "  launchctl list | grep amphoraxe.vc"
echo ""
echo "To view logs:"
echo "  tail -f $INSTALL_DIR/logs/webapp.log"
echo "  tail -f $INSTALL_DIR/logs/webapp.error.log"
echo ""
print_warning "IMPORTANT: Please change the admin password after first login!"
echo ""
