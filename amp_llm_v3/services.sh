#!/bin/bash
# ============================================================================
# Manual Service Restart Script (Updated for Integrated Architecture)
# ============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo "═══════════════════════════════════════════════════════"
echo "AMP LLM Service Manager (Integrated Architecture)"
echo "═══════════════════════════════════════════════════════"

# Function to restart a service
restart_service() {
    local service_name=$1
    local service_label=$2
    
    echo ""
    echo -e "${BLUE}Restarting $service_name...${NC}"
    
    if launchctl list | grep -q "$service_label"; then
        launchctl stop "$service_label"
        sleep 2
        launchctl start "$service_label"
        sleep 2
        
        if launchctl list | grep -q "$service_label"; then
            echo -e "${GREEN}✅ $service_name restarted successfully${NC}"
        else
            echo -e "${RED}❌ $service_name failed to restart${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️  $service_name not running - starting...${NC}"
        launchctl start "$service_label"
        sleep 2
        
        if launchctl list | grep -q "$service_label"; then
            echo -e "${GREEN}✅ $service_name started${NC}"
        else
            echo -e "${RED}❌ Failed to start $service_name${NC}"
        fi
    fi
}

# Function to show service status
show_status() {
    echo ""
    echo "═══════════════════════════════════════════════════════"
    echo "Service Status"
    echo "═══════════════════════════════════════════════════════"
    
    # Webapp
    echo ""
    echo -e "${BLUE}webapp (Web Interface):${NC}"
    if launchctl list | grep -q "com.amplm.webapp"; then
        echo -e "  ${GREEN}✅ Running${NC}"
        pid=$(launchctl list | grep "com.amplm.webapp" | awk '{print $1}')
        if [ "$pid" != "-" ]; then
            echo "     PID: $pid"
        fi
        echo "     Port: 8000"
    else
        echo -e "  ${RED}❌ Not running${NC}"
    fi
    
    # Chat + Research (Integrated)
    echo ""
    echo -e "${BLUE}chat (Integrated Chat + Research Service):${NC}"
    if launchctl list | grep -q "com.amplm.chat"; then
        echo -e "  ${GREEN}✅ Running${NC}"
        pid=$(launchctl list | grep "com.amplm.chat" | awk '{print $1}')
        if [ "$pid" != "-" ]; then
            echo "     PID: $pid"
        fi
        echo "     Port: 9001"
        echo "     Endpoints: /chat/* and /research/*"
    else
        echo -e "  ${RED}❌ Not running${NC}"
    fi
    
    # NCT
    echo ""
    echo -e "${BLUE}nct (NCT Lookup Service):${NC}"
    if launchctl list | grep -q "com.amplm.nct"; then
        echo -e "  ${GREEN}✅ Running${NC}"
        pid=$(launchctl list | grep "com.amplm.nct" | awk '{print $1}')
        if [ "$pid" != "-" ]; then
            echo "     PID: $pid"
        fi
        echo "     Port: 9002"
    else
        echo -e "  ${RED}❌ Not running${NC}"
    fi
    
    echo ""
    echo "Port Status:"
    if lsof -i :8000 | grep -q LISTEN; then
        echo -e "  ${GREEN}✅ Port 8000 (Webapp)${NC}"
    else
        echo -e "  ${RED}❌ Port 8000 (Webapp)${NC}"
    fi
    
    if lsof -i :9001 | grep -q LISTEN; then
        echo -e "  ${GREEN}✅ Port 9001 (Chat + Research)${NC}"
    else
        echo -e "  ${RED}❌ Port 9001 (Chat + Research)${NC}"
    fi
    
    if lsof -i :9002 | grep -q LISTEN; then
        echo -e "  ${GREEN}✅ Port 9002 (NCT Lookup)${NC}"
    else
        echo -e "  ${RED}❌ Port 9002 (NCT Lookup)${NC}"
    fi
    
    # Check if old research service is running (shouldn't be)
    if lsof -i :9003 | grep -q LISTEN; then
        echo -e "  ${YELLOW}⚠️  Port 9003 - Old research service still running!${NC}"
        echo -e "     ${YELLOW}This should be stopped (research is now integrated on 9001)${NC}"
    fi
    
    echo ""
}

# Parse command line arguments
if [ $# -eq 0 ]; then
    echo ""
    echo "Usage:"
    echo "  $0 [command] [service]"
    echo ""
    echo "Commands:"
    echo "  restart [service]  - Restart service(s)"
    echo "  start [service]    - Start service(s)"
    echo "  stop [service]     - Stop service(s)"
    echo "  status            - Show status"
    echo "  logs [service]     - Tail logs"
    echo ""
    echo "Services:"
    echo "  webapp  - Web interface (port 8000)"
    echo "  chat    - Integrated chat + research service (port 9001)"
    echo "  nct     - NCT lookup service (port 9002)"
    echo "  all     - All services"
    echo ""
    echo "Note: The 'chat' service now includes BOTH chat and research functionality."
    echo ""
    echo "Examples:"
    echo "  $0 restart all       # Restart all services"
    echo "  $0 restart chat      # Restart chat + research (both on port 9001)"
    echo "  $0 restart webapp    # Restart just the web interface"
    echo "  $0 status            # Show service status"
    echo "  $0 logs chat         # View chat + research logs"
    exit 0
fi

COMMAND=$1
SERVICE=${2:-all}

PROJECT_DIR="$HOME/amp_llm_v3"

case $COMMAND in
    restart)
        if [ "$SERVICE" = "all" ] || [ "$SERVICE" = "webapp" ]; then
            restart_service "Webapp" "com.amplm.webapp"
        fi
        
        if [ "$SERVICE" = "all" ] || [ "$SERVICE" = "chat" ]; then
            restart_service "Integrated Chat + Research Service" "com.amplm.chat"
            echo -e "${BLUE}   Note: This restarts BOTH chat and research functionality${NC}"
        fi
        
        if [ "$SERVICE" = "all" ] || [ "$SERVICE" = "nct" ]; then
            restart_service "NCT Service" "com.amplm.nct"
        fi
        
        show_status
        ;;
        
    start)
        if [ "$SERVICE" = "all" ] || [ "$SERVICE" = "webapp" ]; then
            echo "Starting webapp..."
            launchctl start com.amplm.webapp
        fi
        
        if [ "$SERVICE" = "all" ] || [ "$SERVICE" = "chat" ]; then
            echo "Starting integrated chat + research service..."
            launchctl start com.amplm.chat
        fi
        
        if [ "$SERVICE" = "all" ] || [ "$SERVICE" = "nct" ]; then
            echo "Starting NCT service..."
            launchctl start com.amplm.nct
        fi
        
        sleep 3
        show_status
        ;;
        
    stop)
        if [ "$SERVICE" = "all" ] || [ "$SERVICE" = "webapp" ]; then
            echo "Stopping webapp..."
            launchctl stop com.amplm.webapp
        fi
        
        if [ "$SERVICE" = "all" ] || [ "$SERVICE" = "chat" ]; then
            echo "Stopping integrated chat + research service..."
            echo "  (This stops BOTH chat and research functionality)"
            launchctl stop com.amplm.chat
        fi
        
        if [ "$SERVICE" = "all" ] || [ "$SERVICE" = "nct" ]; then
            echo "Stopping NCT service..."
            launchctl stop com.amplm.nct
        fi
        
        sleep 2
        show_status
        ;;
        
    status)
        show_status
        
        # Additional health checks
        echo "Health Checks:"
        
        # Webapp
        if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
            echo -e "  ${GREEN}✅ Webapp responding${NC}"
        else
            echo -e "  ${RED}❌ Webapp not responding${NC}"
        fi
        
        # Chat + Research
        if curl -sf http://localhost:9001/health > /dev/null 2>&1; then
            echo -e "  ${GREEN}✅ Chat service responding${NC}"
        else
            echo -e "  ${RED}❌ Chat service not responding${NC}"
        fi
        
        if curl -sf http://localhost:9001/research/health > /dev/null 2>&1; then
            echo -e "  ${GREEN}✅ Research endpoints responding${NC}"
        else
            echo -e "  ${RED}❌ Research endpoints not responding${NC}"
        fi
        
        # NCT
        if curl -sf http://localhost:9002/health > /dev/null 2>&1; then
            echo -e "  ${GREEN}✅ NCT service responding${NC}"
        else
            echo -e "  ${RED}❌ NCT service not responding${NC}"
        fi
        
        echo ""
        ;;
        
    logs)
        if [ "$SERVICE" = "all" ]; then
            echo "Tailing all logs..."
            tail -f "$PROJECT_DIR/logs/"*.log
        else
            echo "Tailing $SERVICE logs..."
            if [ -f "$PROJECT_DIR/logs/$SERVICE.log" ]; then
                tail -f "$PROJECT_DIR/logs/$SERVICE.log" "$PROJECT_DIR/logs/$SERVICE.error.log" 2>/dev/null
            else
                echo -e "${RED}Error: Log file not found for $SERVICE${NC}"
                echo "Available logs:"
                ls -1 "$PROJECT_DIR/logs/"*.log 2>/dev/null | sed 's/.*\//  /'
            fi
        fi
        ;;
        
    *)
        echo "Unknown command: $COMMAND"
        echo "Run without arguments for usage help"
        exit 1
        ;;
esac

echo ""