# chat_with_llm.py
"""
Modular LLM Chat Service
========================

Self-contained FastAPI service for interactive chat with Ollama models.
Provides REST API and WebSocket endpoints for model selection and conversation.

Features:
- List available Ollama models
- Interactive chat sessions with conversation history
- WebSocket support for real-time streaming
- Clean API following NCT lookup patterns
- No external dependencies except Ollama

Installation:
    pip install fastapi uvicorn aiohttp

Usage:
    uvicorn chat_with_llm:app --host 0.0.0.0 --port 8001 --reload

API Endpoints:
    GET  /health              - Health check
    GET  /models              - List available models
    POST /chat/init           - Initialize chat session
    POST /chat/message        - Send message (non-streaming)
    WS   /ws/chat             - WebSocket chat (streaming)
    GET  /conversations       - List conversations
    GET  /conversations/{id}  - Get conversation history
    DELETE /conversations/{id} - Delete conversation
"""

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import aiohttp
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
import uuid

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# Configuration
# ============================================================================

OLLAMA_BASE_URL = "http://localhost:11434"
API_VERSION = "1.0.0"

# ============================================================================
# Pydantic Models
# ============================================================================

class ModelInfo(BaseModel):
    """Information about an available model"""
    name: str
    size: int
    modified_at: str
    digest: Optional[str] = None


class ChatMessage(BaseModel):
    """Single chat message"""
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: str


class InitChatRequest(BaseModel):
    """Request to initialize a chat session"""
    model: str = Field(..., description="Model name to use")
    conversation_id: Optional[str] = Field(None, description="Resume existing conversation")


class InitChatResponse(BaseModel):
    """Response for chat initialization"""
    conversation_id: str
    model: str
    status: str
    message: str


class SendMessageRequest(BaseModel):
    """Request to send a message"""
    conversation_id: str
    message: str
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class SendMessageResponse(BaseModel):
    """Response with AI message"""
    conversation_id: str
    message: ChatMessage
    model: str


class ConversationInfo(BaseModel):
    """Conversation metadata"""
    conversation_id: str
    model: str
    created_at: str
    updated_at: str
    message_count: int


class ConversationHistory(BaseModel):
    """Full conversation history"""
    conversation_id: str
    model: str
    created_at: str
    updated_at: str
    messages: List[ChatMessage]


class HealthResponse(BaseModel):
    """Service health check response"""
    status: str
    ollama_connected: bool
    version: str
    active_conversations: int


# ============================================================================
# Conversation Manager
# ============================================================================

class ConversationManager:
    """Manages conversation histories and state"""
    
    def __init__(self):
        self.conversations: Dict[str, Dict[str, Any]] = {}
        self.conversation_dir = Path("conversations")
        self.conversation_dir.mkdir(exist_ok=True)
    
    def create_conversation(self, model: str, conversation_id: Optional[str] = None) -> str:
        """Create a new conversation or resume existing"""
        if conversation_id and conversation_id in self.conversations:
            logger.info(f"Resuming conversation: {conversation_id}")
            return conversation_id
        
        conv_id = conversation_id or str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        
        self.conversations[conv_id] = {
            "model": model,
            "created_at": now,
            "updated_at": now,
            "messages": []
        }
        
        logger.info(f"Created conversation: {conv_id} with model: {model}")
        return conv_id
    
    def add_message(self, conversation_id: str, role: str, content: str):
        """Add a message to conversation"""
        if conversation_id not in self.conversations:
            raise ValueError(f"Conversation {conversation_id} not found")
        
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.conversations[conversation_id]["messages"].append(message)
        self.conversations[conversation_id]["updated_at"] = message["timestamp"]
        
        logger.debug(f"Added {role} message to {conversation_id}")
    
    def get_messages(self, conversation_id: str) -> List[Dict[str, str]]:
        """Get all messages in conversation"""
        if conversation_id not in self.conversations:
            raise ValueError(f"Conversation {conversation_id} not found")
        
        return self.conversations[conversation_id]["messages"]
    
    def get_model(self, conversation_id: str) -> str:
        """Get model for conversation"""
        if conversation_id not in self.conversations:
            raise ValueError(f"Conversation {conversation_id} not found")
        
        return self.conversations[conversation_id]["model"]
    
    def list_conversations(self) -> List[Dict[str, Any]]:
        """List all conversations"""
        result = []
        for conv_id, conv_data in self.conversations.items():
            result.append({
                "conversation_id": conv_id,
                "model": conv_data["model"],
                "created_at": conv_data["created_at"],
                "updated_at": conv_data["updated_at"],
                "message_count": len(conv_data["messages"])
            })
        return result
    
    def get_conversation(self, conversation_id: str) -> Dict[str, Any]:
        """Get full conversation data"""
        if conversation_id not in self.conversations:
            raise ValueError(f"Conversation {conversation_id} not found")
        
        return {
            "conversation_id": conversation_id,
            **self.conversations[conversation_id]
        }
    
    def delete_conversation(self, conversation_id: str):
        """Delete a conversation"""
        if conversation_id in self.conversations:
            del self.conversations[conversation_id]
            logger.info(f"Deleted conversation: {conversation_id}")
    
    def save_conversation(self, conversation_id: str):
        """Save conversation to disk"""
        if conversation_id not in self.conversations:
            return
        
        file_path = self.conversation_dir / f"{conversation_id}.json"
        with open(file_path, 'w') as f:
            json.dump(
                self.get_conversation(conversation_id),
                f,
                indent=2,
                ensure_ascii=False
            )
        logger.info(f"Saved conversation to {file_path}")


# ============================================================================
# Ollama Client
# ============================================================================

class OllamaClient:
    """Client for interacting with Ollama API"""
    
    def __init__(self, base_url: str = OLLAMA_BASE_URL):
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def initialize(self):
        """Initialize HTTP session"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=300)
            self.session = aiohttp.ClientSession(timeout=timeout)
            logger.info("Ollama client session initialized")
    
    async def close(self):
        """Close HTTP session"""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("Ollama client session closed")
    
    async def check_health(self) -> bool:
        """Check if Ollama is running"""
        try:
            async with self.session.get(f"{self.base_url}/api/tags") as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
    async def list_models(self) -> List[ModelInfo]:
        """Get list of available models"""
        try:
            async with self.session.get(f"{self.base_url}/api/tags") as resp:
                if resp.status != 200:
                    raise HTTPException(
                        status_code=503,
                        detail=f"Ollama returned status {resp.status}"
                    )
                
                data = await resp.json()
                models = []
                
                for model_data in data.get("models", []):
                    models.append(ModelInfo(
                        name=model_data["name"],
                        size=model_data.get("size", 0),
                        modified_at=model_data.get("modified_at", ""),
                        digest=model_data.get("digest")
                    ))
                
                logger.info(f"Found {len(models)} models")
                return models
                
        except Exception as e:
            logger.error(f"Failed to list models: {e}")
            raise HTTPException(status_code=503, detail=str(e))
    
    async def generate_response(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        stream: bool = False
    ):
        """
        Generate response from model
        
        Args:
            model: Model name
            messages: Conversation history in OpenAI format
            temperature: Sampling temperature
            stream: Whether to stream response
            
        Yields:
            Response chunks if streaming, else yields complete response
        """
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": temperature
            }
        }
        
        try:
            async with self.session.post(
                f"{self.base_url}/api/chat",
                json=payload
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise HTTPException(
                        status_code=503,
                        detail=f"Ollama error: {error_text}"
                    )
                
                if stream:
                    # Stream response
                    async for line in resp.content:
                        if line:
                            try:
                                chunk = json.loads(line)
                                yield chunk
                            except json.JSONDecodeError:
                                continue
                else:
                    # Non-streaming response
                    data = await resp.json()
                    yield data
                    
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="LLM Chat Service",
    description="Modular service for interactive chat with Ollama models",
    version=API_VERSION
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure based on your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances
ollama_client = OllamaClient()
conversation_manager = ConversationManager()


# ============================================================================
# Lifecycle Events
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize service on startup"""
    logger.info(f"LLM Chat Service v{API_VERSION} starting...")
    await ollama_client.initialize()
    
    is_healthy = await ollama_client.check_health()
    if is_healthy:
        logger.info("✅ Connected to Ollama")
        models = await ollama_client.list_models()
        logger.info(f"✅ Found {len(models)} models")
    else:
        logger.warning("⚠️ Warning: Ollama not available")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    await ollama_client.close()
    logger.info("LLM Chat Service stopped")


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "LLM Chat Service",
        "version": API_VERSION,
        "status": "running",
        "endpoints": {
            "health": "GET /health",
            "models": "GET /models",
            "init_chat": "POST /chat/init",
            "send_message": "POST /chat/message",
            "websocket": "WS /ws/chat",
            "conversations": "GET /conversations",
            "conversation_detail": "GET /conversations/{id}",
            "delete_conversation": "DELETE /conversations/{id}"
        }
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    ollama_connected = await ollama_client.check_health()
    
    return HealthResponse(
        status="healthy" if ollama_connected else "degraded",
        ollama_connected=ollama_connected,
        version=API_VERSION,
        active_conversations=len(conversation_manager.conversations)
    )


@app.get("/models", response_model=List[ModelInfo])
async def list_models():
    """List available Ollama models"""
    return await ollama_client.list_models()


@app.post("/chat/init", response_model=InitChatResponse)
async def initialize_chat(request: InitChatRequest):
    """
    Initialize a new chat session or resume existing one.
    
    Returns conversation_id to use for subsequent messages.
    """
    try:
        # Verify model exists
        models = await ollama_client.list_models()
        model_names = [m.name for m in models]
        
        if request.model not in model_names:
            raise HTTPException(
                status_code=400,
                detail=f"Model '{request.model}' not found. Available: {model_names}"
            )
        
        # Create or resume conversation
        conv_id = conversation_manager.create_conversation(
            model=request.model,
            conversation_id=request.conversation_id
        )
        
        return InitChatResponse(
            conversation_id=conv_id,
            model=request.model,
            status="ready",
            message=f"Chat session initialized with {request.model}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to initialize chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/message", response_model=SendMessageResponse)
async def send_message(request: SendMessageRequest):
    """
    Send a message and get AI response (non-streaming).
    
    Conversation history is maintained automatically.
    """
    try:
        # Get conversation data
        model = conversation_manager.get_model(request.conversation_id)
        messages = conversation_manager.get_messages(request.conversation_id)
        
        # Add user message
        conversation_manager.add_message(
            request.conversation_id,
            "user",
            request.message
        )
        
        # Prepare messages for Ollama (convert to OpenAI format)
        ollama_messages = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in conversation_manager.get_messages(request.conversation_id)
        ]
        
        # Generate response
        response_text = ""
        async for chunk in ollama_client.generate_response(
            model=model,
            messages=ollama_messages,
            temperature=request.temperature,
            stream=False
        ):
            response_text = chunk.get("message", {}).get("content", "")
        
        if not response_text:
            raise HTTPException(status_code=500, detail="Empty response from model")
        
        # Add assistant message
        conversation_manager.add_message(
            request.conversation_id,
            "assistant",
            response_text
        )
        
        # Save conversation
        conversation_manager.save_conversation(request.conversation_id)
        
        return SendMessageResponse(
            conversation_id=request.conversation_id,
            message=ChatMessage(
                role="assistant",
                content=response_text,
                timestamp=datetime.utcnow().isoformat()
            ),
            model=model
        )
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Message sending failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket endpoint for streaming chat.
    
    Protocol:
        Client sends: {"action": "init", "model": "...", "conversation_id": "..."}
        Client sends: {"action": "message", "message": "..."}
        Client sends: {"action": "exit"}
        
        Server sends: {"type": "init", "conversation_id": "...", "model": "..."}
        Server sends: {"type": "chunk", "content": "...", "done": false}
        Server sends: {"type": "done", "message": "..."}
        Server sends: {"type": "error", "message": "..."}
    """
    await websocket.accept()
    conversation_id = None
    current_model = None
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            action = data.get("action")
            
            if action == "init":
                # Initialize conversation
                model = data.get("model")
                conv_id = data.get("conversation_id")
                
                if not model:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Model name required"
                    })
                    continue
                
                # Verify model exists
                models = await ollama_client.list_models()
                model_names = [m.name for m in models]
                
                if model not in model_names:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Model '{model}' not found"
                    })
                    continue
                
                # Create conversation
                conversation_id = conversation_manager.create_conversation(
                    model=model,
                    conversation_id=conv_id
                )
                current_model = model
                
                await websocket.send_json({
                    "type": "init",
                    "conversation_id": conversation_id,
                    "model": model,
                    "status": "ready"
                })
            
            elif action == "message":
                if not conversation_id or not current_model:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Conversation not initialized. Send 'init' first."
                    })
                    continue
                
                message = data.get("message")
                temperature = data.get("temperature", 0.7)
                
                if not message:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Message content required"
                    })
                    continue
                
                # Add user message
                conversation_manager.add_message(
                    conversation_id,
                    "user",
                    message
                )
                
                # Prepare messages for Ollama
                messages = conversation_manager.get_messages(conversation_id)
                ollama_messages = [
                    {"role": msg["role"], "content": msg["content"]}
                    for msg in messages
                ]
                
                # Stream response
                full_response = ""
                async for chunk in ollama_client.generate_response(
                    model=current_model,
                    messages=ollama_messages,
                    temperature=temperature,
                    stream=True
                ):
                    content = chunk.get("message", {}).get("content", "")
                    done = chunk.get("done", False)
                    
                    if content:
                        full_response += content
                        await websocket.send_json({
                            "type": "chunk",
                            "content": content,
                            "done": done
                        })
                
                # Add assistant response
                conversation_manager.add_message(
                    conversation_id,
                    "assistant",
                    full_response
                )
                
                # Save conversation
                conversation_manager.save_conversation(conversation_id)
                
                # Send completion
                await websocket.send_json({
                    "type": "done",
                    "message": "Response complete"
                })
            
            elif action == "exit":
                await websocket.send_json({
                    "type": "exit",
                    "message": "Conversation ended"
                })
                break
            
            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown action: {action}"
                })
    
    except WebSocketDisconnect:
        logger.info(f"Client disconnected from conversation: {conversation_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except:
            pass


@app.get("/conversations", response_model=List[ConversationInfo])
async def list_conversations():
    """List all conversations"""
    conversations = conversation_manager.list_conversations()
    return [ConversationInfo(**conv) for conv in conversations]


@app.get("/conversations/{conversation_id}", response_model=ConversationHistory)
async def get_conversation(conversation_id: str):
    """Get full conversation history"""
    try:
        conv_data = conversation_manager.get_conversation(conversation_id)
        return ConversationHistory(
            conversation_id=conv_data["conversation_id"],
            model=conv_data["model"],
            created_at=conv_data["created_at"],
            updated_at=conv_data["updated_at"],
            messages=[ChatMessage(**msg) for msg in conv_data["messages"]]
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation"""
    try:
        conversation_manager.delete_conversation(conversation_id)
        return {
            "status": "deleted",
            "conversation_id": conversation_id
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "chat_with_llm:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info"
    )