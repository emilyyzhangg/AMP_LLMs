#!/bin/bash

# ============================================================================
# AMP LLM - Start All Services (5-Service Architecture)
# ============================================================================
# This script starts all five required services:
# 1. Chat Service with Annotation (port 9001)
# 2. NCT Lookup Service (port 9002)
# 3. Runner Service - File Manager (port 9003)
# 4. LLM Assistant Service (port 9004) - NEW
# 5. Web Interface (port 9000)
# ============================================================================

echo "═══════════════════════════════════════════════════════"
echo "Starting AMP LLM Services (5-Service Architecture)"
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
    echo "⚠️  Virtual environment not found at llm_env/"
    echo "Looking for alternative Python..."
    PYTHON_CMD="python3"
else
    # Activate virtual environment
    source llm_env/bin/activate
    echo "✅ Virtual environment activated"
    PYTHON_CMD="python"
fi

echo ""

# Create logs directory
mkdir -p logs

# Function to check if port is in use
check_port() {
    lsof -i :$1 > /dev/null 2>&1
    return $?
}

# ============================================================================
# Start NCT Lookup Service (Port 9002) - Start first as dependency
# ============================================================================

echo ""
echo "─────────────────────────────────────────────────────"
echo "Starting NCT Lookup Service on port 9002..."
echo "─────────────────────────────────────────────────────"

if check_port 9002; then
    echo "⚠️  Port 9002 already in use"
    read -p "Kill existing process? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        lsof -ti:9002 | xargs kill -9
        echo "✅ Killed existing process on port 9002"
        sleep 2
    else
        echo "Skipping NCT service..."
        SKIP_NCT=true
    fi
fi

if [ "$SKIP_NCT" != "true" ]; then
    cd "standalone modules/nct_lookup"
    
    # Check if requirements are installed
    if [ ! -f ".installed" ]; then
        echo "📦 Installing NCT service dependencies..."
        $PYTHON_CMD -m pip install -r requirements.txt
        touch .installed
    fi
    
    # Create results directory
    mkdir -p results
    
    # Start service in background
    nohup $PYTHON_CMD -m uvicorn nct_api:app --port 9002 > "$PROJECT_DIR/logs/nct_service.log" 2>&1 &
    NCT_PID=$!
    
    echo "✅ NCT service starting (PID: $NCT_PID)"
    echo "   Log: $PROJECT_DIR/logs/nct_service.log"
    
    cd "$PROJECT_DIR"
fi

sleep 2

# ============================================================================
# Start LLM Assistant Service (Port 9004) - NEW
# ============================================================================

echo ""
echo "─────────────────────────────────────────────────────"
echo "Starting LLM Assistant Service on port 9004..."
echo "─────────────────────────────────────────────────────"

if check_port 9004; then
    echo "⚠️  Port 9004 already in use"
    read -p "Kill existing process? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        lsof -ti:9004 | xargs kill -9
        echo "✅ Killed existing process on port 9004"
        sleep 2
    else
        echo "Skipping LLM Assistant service..."
        SKIP_LLM_ASSISTANT=true
    fi
fi

if [ "$SKIP_LLM_ASSISTANT" != "true" ]; then
    cd "standalone modules/llm_assistant"
    
    # Check if llm_assistant_api.py exists
    if [ ! -f "llm_assistant_api.py" ]; then
        echo "❌ llm_assistant_api.py not found!"
        echo "   Please ensure the file is in standalone modules/llm_assistant/"
        cd "$PROJECT_DIR"
        SKIP_LLM_ASSISTANT=true
    else
        # Check if requirements are installed
        if [ ! -f ".installed" ]; then
            echo "📦 Installing LLM Assistant dependencies..."
            $PYTHON_CMD -m pip install fastapi uvicorn httpx pydantic
            touch .installed
        fi
        
        # Start service in background
        nohup $PYTHON_CMD -m uvicorn llm_assistant_api:app --port 9004 > "$PROJECT_DIR/logs/llm_assistant.log" 2>&1 &
        LLM_ASSISTANT_PID=$!
        
        echo "✅ LLM Assistant service starting (PID: $LLM_ASSISTANT_PID)"
        echo "   Function: JSON parsing, prompt generation, LLM annotation"
        echo "   Endpoints: /annotate, /batch-annotate, /parse, /generate-prompt"
        echo "   Log: $PROJECT_DIR/logs/llm_assistant.log"
        
        cd "$PROJECT_DIR"
    fi
fi

sleep 2

# ============================================================================
# Start Runner Service - File Manager (Port 9003)
# ============================================================================

echo ""
echo "─────────────────────────────────────────────────────"
echo "Starting Runner Service on port 9003..."
echo "─────────────────────────────────────────────────────"

if check_port 9003; then
    echo "⚠️  Port 9003 already in use"
    read -p "Kill existing process? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        lsof -ti:9003 | xargs kill -9
        echo "✅ Killed existing process on port 9003"
        sleep 2
    else
        echo "Skipping runner service..."
        SKIP_RUNNER=true
    fi
fi

if [ "$SKIP_RUNNER" != "true" ]; then
    cd "standalone modules/runner"
    
    # Check if runner_service.py exists
    if [ ! -f "runner_service.py" ]; then
        echo "❌ runner_service.py not found!"
        echo "   Please ensure the file is in standalone modules/runner/"
        cd "$PROJECT_DIR"
        SKIP_RUNNER=true
    else
        # Check if requirements are installed
        if [ ! -f ".installed" ]; then
            echo "📦 Installing runner service dependencies..."
            $PYTHON_CMD -m pip install -r requirements.txt 2>/dev/null || \
            $PYTHON_CMD -m pip install fastapi uvicorn httpx pydantic
            touch .installed
        fi
        
        # Create results directory
        mkdir -p results
        
        # Start service in background
        nohup $PYTHON_CMD -m uvicorn runner_service:app --port 9003 > "$PROJECT_DIR/logs/runner_service.log" 2>&1 &
        RUNNER_PID=$!
        
        echo "✅ Runner service starting (PID: $RUNNER_PID)"
        echo "   Function: File manager, NCT data fetcher, annotation orchestrator"
        echo "   Endpoints: /get-data, /batch-get-data, /annotate, /batch-annotate"
        echo "   Log: $PROJECT_DIR/logs/runner_service.log"
        
        cd "$PROJECT_DIR"
    fi
fi

sleep 2

# ============================================================================
# Start Chat Service with Annotation (Port 9001)
# ============================================================================

echo ""
echo "─────────────────────────────────────────────────────"
echo "Starting Chat Service with Annotation on port 9001..."
echo "─────────────────────────────────────────────────────"

if check_port 9001; then
    echo "⚠️  Port 9001 already in use"
    read -p "Kill existing process? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        lsof -ti:9001 | xargs kill -9
        echo "✅ Killed existing process on port 9001"
        sleep 2
    else
        echo "Skipping chat service..."
        SKIP_CHAT=true
    fi
fi

if [ "$SKIP_CHAT" != "true" ]; then
    cd "standalone modules/chat_with_llm"
    
    # Check for chat service file (prefer chat_api.py which now has annotation)
    if [ -f "chat_api.py" ]; then
        SERVICE_FILE="chat_api"
        echo "✅ Using chat_api.py with annotation support"
    elif [ -f "chat_api_with_annotation.py" ]; then
        SERVICE_FILE="chat_api_with_annotation"
        echo "✅ Using chat_api_with_annotation.py"
    else
        echo "❌ No chat service file found!"
        exit 1
    fi
    
    # Check if requirements are installed
    if [ ! -f ".installed" ]; then
        echo "📦 Installing chat service dependencies..."
        $PYTHON_CMD -m pip install -r requirements.txt 2>/dev/null || \
        $PYTHON_CMD -m pip install fastapi uvicorn httpx pydantic
        touch .installed
    fi
    
    # Start service in background
    nohup $PYTHON_CMD -m uvicorn ${SERVICE_FILE}:app --port 9001 > "$PROJECT_DIR/logs/chat_service.log" 2>&1 &
    CHAT_PID=$!
    
    echo "✅ Chat service starting (PID: $CHAT_PID)"
    echo "   Service: ${SERVICE_FILE}"
    echo "   Endpoints: /chat/* (with annotation support)"
    echo "   Log: $PROJECT_DIR/logs/chat_service.log"
    
    cd "$PROJECT_DIR"
fi

sleep 2

# ============================================================================
# Start Web Interface (Port 9000)
# ============================================================================

echo ""
echo "─────────────────────────────────────────────────────"
echo "Starting Web Interface on port 9000..."
echo "─────────────────────────────────────────────────────"

if check_port 9000; then
    echo "⚠️  Port 9000 already in use"
    read -p "Kill existing process? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        lsof -ti:9000 | xargs kill -9
        echo "✅ Killed existing process on port 9000"
        sleep 2
    else
        echo "Skipping web interface..."
        SKIP_WEB=true
    fi
fi

if [ "$SKIP_WEB" != "true" ]; then
    # Check if requirements are installed
    if [ ! -f "webapp/.installed" ]; then
        echo "📦 Installing webapp dependencies..."
        $PYTHON_CMD -m pip install fastapi uvicorn aiohttp httpx python-dotenv pydantic-settings
        touch webapp/.installed
    fi
    
    # Start service in background
    nohup $PYTHON_CMD -m uvicorn webapp.server:app --host 0.0.0.0 --port 9000 > "$PROJECT_DIR/logs/webapp.log" 2>&1 &
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

# Web Interface
if check_port 9000; then
    echo "✅ Web Interface:        Running on port 9000"
else
    echo "❌ Web Interface:        Not running"
fi

# Chat Service
if check_port 9001; then
    echo "✅ Chat Service:         Running on port 9001"
else
    echo "❌ Chat Service:         Not running"
fi

# NCT Service
if check_port 9002; then
    echo "✅ NCT Lookup Service:   Running on port 9002"
else
    echo "❌ NCT Lookup Service:   Not running"
fi

# Runner Service
if check_port 9003; then
    echo "✅ Runner Service:       Running on port 9003"
else
    echo "❌ Runner Service:       Not running"
fi

# LLM Assistant Service
if check_port 9004; then
    echo "✅ LLM Assistant:        Running on port 9004"
else
    echo "❌ LLM Assistant:        Not running"
fi

# Check Ollama
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "✅ Ollama:               Running on port 11434"
else
    echo "⚠️  Ollama:               Not running (needed for LLM inference)"
fi

echo ""
echo "═══════════════════════════════════════════════════════"
echo "Access Your Application"
echo "═══════════════════════════════════════════════════════"

echo ""
echo "🌐 Web Interface:"
echo "   http://localhost:9000"
echo ""
echo "📚 API Documentation:"
echo "   Web API:             http://localhost:9000/docs"
echo "   Chat Service:        http://localhost:9001/docs"
echo "   NCT Lookup:          http://localhost:9002/docs"
echo "   Runner Service:      http://localhost:9003/docs"
echo "   LLM Assistant:       http://localhost:9004/docs"
echo ""
echo "🔬 Architecture (5-Service):"
echo ""
echo "   ┌─────────────────────────────────────────────────────┐"
echo "   │              Web Interface (9000)                   │"
echo "   └─────────────────────────┬───────────────────────────┘"
echo "                             │"
echo "                             ▼"
echo "   ┌─────────────────────────────────────────────────────┐"
echo "   │              Chat Service (9001)                    │"
echo "   │         Entry point for chat & annotation           │"
echo "   └─────────────────────────┬───────────────────────────┘"
echo "                             │"
echo "                             ▼"
echo "   ┌─────────────────────────────────────────────────────┐"
echo "   │              Runner Service (9003)                  │"
echo "   │      Data fetching & annotation orchestration       │"
echo "   └───────────┬─────────────────────────┬───────────────┘"
echo "               │                         │"
echo "               ▼                         ▼"
echo "   ┌───────────────────────┐   ┌─────────────────────────┐"
echo "   │  NCT Lookup (9002)    │   │   LLM Assistant (9004)  │"
echo "   │  ClinicalTrials.gov   │   │  JSON parsing, prompts  │"
echo "   │  PubMed, PMC, BioC    │   │  & LLM annotation       │"
echo "   └───────────────────────┘   └───────────┬─────────────┘"
echo "                                           │"
echo "                                           ▼"
echo "                               ┌───────────────────────┐"
echo "                               │    Ollama (11434)     │"
echo "                               │    LLM Inference      │"
echo "                               └───────────────────────┘"
echo ""
echo "📋 Logs:"
echo "   Chat Service:      tail -f logs/chat_service.log"
echo "   NCT Lookup:        tail -f logs/nct_service.log"
echo "   Runner Service:    tail -f logs/runner_service.log"
echo "   LLM Assistant:     tail -f logs/llm_assistant.log"
echo "   Web Interface:     tail -f logs/webapp.log"
echo "   All Services:      tail -f logs/*.log"
echo ""
echo "🔍 Health Check:"
echo "   curl http://localhost:9001/health"
echo ""
echo "🧪 Test Annotation:"
echo "   curl -X POST http://localhost:9003/annotate \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"nct_id\": \"NCT06566833\", \"model\": \"llama3.2\"}'"
echo ""
echo "🛑 Stop All Services:"
echo "   lsof -ti:9000,9001,9002,9003,9004 | xargs kill"
echo ""
echo "═══════════════════════════════════════════════════════"