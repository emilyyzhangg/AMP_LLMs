#!/bin/bash
# ============================================================================
# Manual Service Restart Script
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
echo "AMP LLM Service Manager"
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
    
    for service in webapp chat nct; do
        label="com.amplm.$service"
        echo ""
        echo -e "${BLUE}$service:${NC}"
        
        if launchctl list | grep -q "$label"; then
            echo -e "  ${GREEN}✅ Running${NC}"
            
            # Show PID
            pid=$(launchctl list | grep "$label" | awk '{print $1}')
            if [ "$pid" != "-" ]; then
                echo "     PID: $pid"
            fi
        else
            echo -e "  ${RED}❌ Not running${NC}"
        fi
    done
    
    echo ""
    echo "Ports:"
    for port in 9000 9001 9002; do
        if lsof -i :$port | grep -q LISTEN; then
            echo -e "  ${GREEN}✅ Port $port - Active${NC}"
        else
            echo -e "  ${RED}❌ Port $port - Not listening${NC}"
        fi
    done
    
    echo ""
}

# Parse command line arguments
if [ $# -eq 0 ]; then
    echo ""
    echo "Usage:"
    echo "  $0 [command]"
    echo ""
    echo "Commands:"
    echo "  restart [service]  - Restart service(s)"
    echo "  start [service]    - Start service(s)"
    echo "  stop [service]     - Stop service(s)"
    echo "  status            - Show status"
    echo "  logs [service]     - Tail logs"
    echo ""
    echo "Services:"
    echo "  webapp, chat, nct, all"
    echo ""
    echo "Examples:"
    echo "  $0 restart all"
    echo "  $0 restart webapp"
    echo "  $0 status"
    echo "  $0 logs chat"
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
            restart_service "Chat Service" "com.amplm.chat"
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
            echo "Starting chat service..."
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
            echo "Stopping chat service..."
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
        ;;
        
    logs)
        if [ "$SERVICE" = "all" ]; then
            echo "Tailing all logs..."
            tail -f "$PROJECT_DIR/logs/"*.log
        else
            echo "Tailing $SERVICE logs..."
            tail -f "$PROJECT_DIR/logs/$SERVICE.log" "$PROJECT_DIR/logs/$SERVICE.error.log"
        fi
        ;;
        
    *)
        echo "Unknown command: $COMMAND"
        echo "Run without arguments for usage help"
        exit 1
        ;;
esac

echo ""