#!/bin/bash

# ============================================================================
# AMP LLM - Start All Services
# ============================================================================
# This script starts all three required services:
# 1. Chat Service (port 8001)
# 2. NCT Lookup Service (port 8002)
# 3. Web Interface (port 8000)
# ============================================================================

echo "═══════════════════════════════════════════════════════"
echo "Starting AMP LLM Services"
echo "═══════════════════════════════════════════════════════"

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Check if project directory exists
if [ ! -d "$PROJECT_DIR" ]; then
    echo "❌ Project directory not found: $PROJECT_DIR"
    echo "Please update PROJECT_DIR in this script"
    exit 1
fi

cd "$PROJECT_DIR"

# Check if virtual environment exists
if [ ! -d "llm_env" ]; then
    echo "❌ Virtual environment not found"
    echo "Please create it first: python3 -m venv llm_env"
    exit 1
fi

# Activate virtual environment
source llm_env/bin/activate

echo ""
echo "✅ Virtual environment activated"

# Create logs directory
mkdir -p logs

# Function to check if port is in use
check_port() {
    lsof -i :$1 > /dev/null 2>&1
    return $?
}

# ============================================================================
# Start Chat Service (Port 8001)
# ============================================================================

echo ""
echo "─────────────────────────────────────────────────────"
echo "Starting Chat Service on port 8001..."
echo "─────────────────────────────────────────────────────"

if check_port 8001; then
    echo "⚠️  Port 8001 already in use"
    read -p "Kill existing process? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        lsof -ti:8001 | xargs kill -9
        echo "✅ Killed existing process on port 8001"
    else
        echo "Skipping chat service..."
    fi
else
    cd "standalone modules/chat_with_llm"
    
    # Check if requirements are installed
    if [ ! -f ".installed" ]; then
        echo "📦 Installing chat service dependencies..."
        pip install -r requirements.txt
        touch .installed
    fi
    
    # Start service in background
    nohup uvicorn chat_api:app --port 8001 > "$PROJECT_DIR/logs/chat_service.log" 2>&1 &
    CHAT_PID=$!
    
    echo "✅ Chat service starting (PID: $CHAT_PID)"
    echo "   Log: $PROJECT_DIR/logs/chat_service.log"
    
    cd "$PROJECT_DIR"
fi

sleep 2

# ============================================================================
# Start NCT Lookup Service (Port 8002)
# ============================================================================

echo ""
echo "─────────────────────────────────────────────────────"
echo "Starting NCT Lookup Service on port 8002..."
echo "─────────────────────────────────────────────────────"

if check_port 8002; then
    echo "⚠️  Port 8002 already in use"
    read -p "Kill existing process? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        lsof -ti:8002 | xargs kill -9
        echo "✅ Killed existing process on port 8002"
    else
        echo "Skipping NCT service..."
    fi
else
    cd "standalone modules/nct_lookup"
    
    # Check if requirements are installed
    if [ ! -f ".installed" ]; then
        echo "📦 Installing NCT service dependencies..."
        pip install -r requirements.txt
        touch .installed
    fi
    
    # Create results directory
    mkdir -p results
    
    # Start service in background
    nohup uvicorn nct_api:app --port 8002 > "$PROJECT_DIR/logs/nct_service.log" 2>&1 &
    NCT_PID=$!
    
    echo "✅ NCT service starting (PID: $NCT_PID)"
    echo "   Log: $PROJECT_DIR/logs/nct_service.log"
    
    cd "$PROJECT_DIR"
fi

sleep 2

# ============================================================================
# Start Web Interface (Port 8000)
# ============================================================================

echo ""
echo "─────────────────────────────────────────────────────"
echo "Starting Web Interface on port 8000..."
echo "─────────────────────────────────────────────────────"

if check_port 8000; then
    echo "⚠️  Port 8000 already in use"
    read -p "Kill existing process? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        lsof -ti:8000 | xargs kill -9
        echo "✅ Killed existing process on port 8000"
    else
        echo "Skipping web interface..."
    fi
else
    # Check if requirements are installed
    if [ ! -f "webapp/.installed" ]; then
        echo "📦 Installing webapp dependencies..."
        pip install fastapi uvicorn aiohttp httpx python-dotenv pydantic-settings
        touch webapp/.installed
    fi
    
    # Start service in background
    nohup uvicorn webapp.server:app --host 0.0.0.0 --port 8000 > "$PROJECT_DIR/logs/webapp.log" 2>&1 &
    WEBAPP_PID=$!
    
    echo "✅ Web interface starting (PID: $WEBAPP_PID)"
    echo "   Log: $PROJECT_DIR/logs/webapp.log"
fi

sleep 3

# ============================================================================
# Service Status Check
# ============================================================================

echo ""
echo "═══════════════════════════════════════════════════════"
echo "Service Status"
echo "═══════════════════════════════════════════════════════"

echo ""
echo "Checking services..."

# Chat Service
if check_port 8001; then
    echo "✅ Chat Service: Running on port 8001"
else
    echo "❌ Chat Service: Not running"
fi

# NCT Service
if check_port 8002; then
    echo "✅ NCT Lookup Service: Running on port 8002"
else
    echo "❌ NCT Lookup Service: Not running"
fi

# Web Interface
if check_port 8000; then
    echo "✅ Web Interface: Running on port 8000"
else
    echo "❌ Web Interface: Not running"
fi

echo ""
echo "═══════════════════════════════════════════════════════"
echo "Access Your Application"
echo "═══════════════════════════════════════════════════════"

echo ""
echo "🌐 Web Interface:"
echo "   http://localhost:8000"
echo ""
echo "📚 API Documentation:"
echo "   Chat Service:      http://localhost:8001/docs"
echo "   NCT Lookup:        http://localhost:8002/docs"
echo "   Web API:           http://localhost:8000/docs"
echo ""
echo "📋 Logs:"
echo "   Chat:              tail -f logs/chat_service.log"
echo "   NCT Lookup:        tail -f logs/nct_service.log"
echo "   Web Interface:     tail -f logs/webapp.log"
echo ""
echo "🛑 Stop All Services:"
echo "   lsof -ti:8000,8001,8002 | xargs kill"
echo ""
echo "═══════════════════════════════════════════════════════"
