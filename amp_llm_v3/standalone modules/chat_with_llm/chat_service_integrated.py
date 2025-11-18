"""
LLM Chat Service with Research Assistant Integration (Port 9001)
================================================================

Complete standalone version with all chat routes inline.
No dependencies on chat_api.py or chat_routes.py needed.
"""
import logging
import uuid
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

try:
    from assistant_config import config
except ImportError:
    # Fallback config if assistant_config doesn't exist
    class ChatConfig:
        OLLAMA_HOST = "localhost"
        OLLAMA_PORT = 11434
        @property
        def OLLAMA_BASE_URL(self):
            return f"http://{self.OLLAMA_HOST}:{self.OLLAMA_PORT}"
        API_VERSION = "3.0.0"
        SERVICE_NAME = "LLM Chat Service with Research Assistant"
        CORS_ORIGINS = ["*"]
    config = ChatConfig()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# Initialize FastAPI app
# ============================================================================

app = FastAPI(
    title="LLM Chat Service with Research Assistant",
    description="Unified service for chat and clinical trial research",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# In-memory conversation storage
# ============================================================================

conversations: Dict[str, Dict] = {}

# ============================================================================
# Chat Models
# ============================================================================

class ChatInitRequest(BaseModel):
    model: str

class ChatMessageRequest(BaseModel):
    conversation_id: str
    message: str
    temperature: float = 0.7

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatResponse(BaseModel):
    conversation_id: str
    message: ChatMessage
    model: str

# ============================================================================
# Chat Endpoints
# ============================================================================

@app.post("/chat/init")
async def init_conversation(request: ChatInitRequest):
    """Initialize a new conversation"""
    conversation_id = str(uuid.uuid4())
    conversations[conversation_id] = {
        "model": request.model,
        "messages": []
    }
    logger.info(f"✅ Created conversation {conversation_id} with {request.model}")
    return {
        "conversation_id": conversation_id,
        "model": request.model
    }

@app.post("/chat/message", response_model=ChatResponse)
async def send_message(request: ChatMessageRequest):
    """Send a message in an existing conversation"""
    if request.conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    conv = conversations[request.conversation_id]
    
    # Add user message
    conv["messages"].append({
        "role": "user",
        "content": request.message
    })
    
    # Call Ollama
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{config.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": conv["model"],
                    "messages": conv["messages"],
                    "temperature": request.temperature,
                    "stream": False
                }
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=503,
                    detail=f"Ollama error: {response.text}"
                )
            
            data = response.json()
            assistant_message = data["message"]["content"]
            
            # Add assistant message
            conv["messages"].append({
                "role": "assistant",
                "content": assistant_message
            })
            
            return ChatResponse(
                conversation_id=request.conversation_id,
                message=ChatMessage(role="assistant", content=assistant_message),
                model=conv["model"]
            )
            
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to Ollama at {config.OLLAMA_BASE_URL}"
        )
    except Exception as e:
        logger.error(f"❌ Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/chat/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Get conversation history"""
    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversations[conversation_id]

@app.get("/models")
async def get_models():
    """Get available Ollama models"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{config.OLLAMA_BASE_URL}/api/tags")
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=503, detail="Cannot fetch models")
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
    

# ============================================================================
# Research Routes
# ============================================================================

try:
    from research_routes import router as research_router
    app.include_router(research_router)
    logger.info("✅ Research assistant routes loaded")
except ImportError as e:
    logger.warning(f"⚠️  Research routes not available: {e}")
    logger.info("💡 Chat-only mode - research functionality disabled")

# ============================================================================
# Root Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "LLM Chat Service with Research Assistant",
        "version": "3.0.0",
        "status": "running",
        "features": {
            "chat": "enabled",
            "research_assistant": "enabled" if "research_routes" in locals() else "disabled",
            "auto_fetch": "enabled"
        },
        "endpoints": {
            "chat": "/chat/*",
            "research": "/research/*",
            "docs": "/docs"
        }
    }

@app.get("/health")
async def health():
    """Health check"""
    
    # Check Ollama connection
    ollama_connected = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{config.OLLAMA_BASE_URL}/api/tags")
            ollama_connected = response.status_code == 200
    except:
        pass
    
    return {
        "status": "healthy",
        "service": config.SERVICE_NAME,
        "version": config.API_VERSION,
        "ollama": config.OLLAMA_BASE_URL,
        "ollama_connected": ollama_connected,
        "active_conversations": len(conversations)
    }

# ============================================================================
# Run standalone
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting LLM Chat Service with Research Assistant on port 9001...")
    print(f"🤖 Ollama: {config.OLLAMA_BASE_URL}")
    print("🔬 Research Assistant: Integrated")
    print("📡 NCT Lookup: Expected on port 9002")
    print("📚 Docs: http://localhost:9001/docs")
    uvicorn.run(app, host="0.0.0.0", port=9001, reload=True)