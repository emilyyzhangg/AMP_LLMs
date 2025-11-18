"""
LLM Chat Service with Research Assistant Integration (Port 9001)
================================================================

Main chat service that now includes research assistant functionality.
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from assistant_config import config

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
# Import and include routers
# ============================================================================

# Import chat routes (your existing chat functionality)
try:
    from chat_routes import router as chat_router
    app.include_router(chat_router)
    logger.info("✅ Chat routes loaded")
except ImportError as e:
    logger.warning(f"⚠️  Chat routes not found: {e}")
    logger.info("💡 Using inline chat routes")
    
    # Inline basic chat routes if separate file doesn't exist
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel
    from typing import Optional, List, Dict, Any
    import httpx
    import uuid
    
    chat_router = APIRouter(prefix="/chat", tags=["chat"])
    
    # Store conversations in memory (you might want to use Redis/DB)
    conversations: Dict[str, List[Dict]] = {}
    
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
    
    @chat_router.post("/init")
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
    
    @chat_router.post("/message", response_model=ChatResponse)
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
    
    @chat_router.get("/conversations/{conversation_id}")
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
    
    app.include_router(chat_router)

# Import research routes (NEW - integrated research assistant)
import os
import sys

print("=" * 60)
print("DEBUG: Attempting to load research routes")
print(f"Current working directory: {os.getcwd()}")
print(f"Python path: {sys.path[:3]}")
print(f"Files in current directory:")
for f in sorted(os.listdir('.')):
    if f.endswith('.py'):
        print(f"  - {f}")
print(f"research_routes.py exists: {os.path.exists('research_routes.py')}")
print("=" * 60)

try:
    from research_routes import router as research_router
    print("✅ Successfully imported research_router")
    app.include_router(research_router)
    print("✅ Successfully included research_router in app")
    logger.info("✅ Research assistant routes loaded")
except ImportError as e:
    print(f"❌ ImportError: {e}")
    logger.error(f"❌ Failed to load research routes: {e}")
    import traceback
    traceback.print_exc()
except Exception as e:
    print(f"❌ Other error: {e}")
    logger.error(f"❌ Error loading research routes: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# Root endpoints
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
            "research_assistant": "enabled",
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
    return {
        "status": "healthy",
        "service": config.SERVICE_NAME,
        "version": config.API_VERSION,
        "ollama": config.OLLAMA_BASE_URL
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