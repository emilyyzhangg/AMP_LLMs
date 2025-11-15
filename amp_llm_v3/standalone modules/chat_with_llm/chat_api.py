"""
Chat Service API
================

FastAPI application for LLM chat service.

Usage:
    uvicorn chat_api:app --host 0.0.0.0 --port 8001 --reload
"""
import logging
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import List

from chat_config import config
from chat_models import (
    ModelInfo,
    InitChatRequest,
    InitChatResponse,
    SendMessageRequest,
    SendMessageResponse,
    ConversationInfo,
    ConversationHistory,
    HealthResponse,
    ChatMessage
)
from chat_client import OllamaClient
from chat_manager import ConversationManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title=config.SERVICE_NAME,
    description="Modular service for interactive chat with Ollama models",
    version=config.API_VERSION
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
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
    logger.info(f"{config.SERVICE_NAME} v{config.API_VERSION} starting...")
    logger.info(f"Ollama endpoint: {config.OLLAMA_BASE_URL}")
    
    await ollama_client.initialize()
    
    is_healthy = await ollama_client.check_health()
    if is_healthy:
        logger.info("✅ Connected to Ollama")
        try:
            models = await ollama_client.list_models()
            logger.info(f"✅ Found {len(models)} models")
        except Exception as e:
            logger.warning(f"⚠️ Could not list models: {e}")
    else:
        logger.warning("⚠️ Warning: Ollama not available")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    await ollama_client.close()
    logger.info(f"{config.SERVICE_NAME} stopped")


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": config.SERVICE_NAME,
        "version": config.API_VERSION,
        "status": "running",
        "endpoints": {
            "health": "GET /health",
            "models": "GET /models",
            "init_chat": "POST /chat/init",
            "send_message": "POST /chat/message",
            "websocket": "WS /ws/chat",
            "conversations": "GET /conversations",
            "conversation_detail": "GET /conversations/{id}",
            "delete_conversation": "DELETE /conversations/{id}",
            "statistics": "GET /stats"
        }
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    ollama_connected = await ollama_client.check_health()
    
    return HealthResponse(
        status="healthy" if ollama_connected else "degraded",
        ollama_connected=ollama_connected,
        version=config.API_VERSION,
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
        model_exists = await ollama_client.verify_model(request.model)
        if not model_exists:
            models = await ollama_client.list_models()
            model_names = [m.name for m in models]
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
        
        # Add user message
        conversation_manager.add_message(
            request.conversation_id,
            "user",
            request.message
        )
        
        # Prepare messages for Ollama (convert to OpenAI format)
        messages = conversation_manager.get_messages(request.conversation_id)
        ollama_messages = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in messages
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
        from datetime import datetime
        timestamp = datetime.utcnow().isoformat()
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
                timestamp=timestamp
            ),
            model=model
        )
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Message sending failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket endpoint for streaming chat.
    
    Protocol:
        Client -> {"action": "init", "model": "...", "conversation_id": "..."}
        Client -> {"action": "message", "message": "...", "temperature": 0.7}
        Client -> {"action": "exit"}
        
        Server -> {"type": "init", "conversation_id": "...", "model": "..."}
        Server -> {"type": "chunk", "content": "...", "done": false}
        Server -> {"type": "done"}
        Server -> {"type": "error", "message": "..."}
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
                model_exists = await ollama_client.verify_model(model)
                if not model_exists:
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
                    "type": "done"
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
    """List all active conversations"""
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
    conversation_manager.delete_conversation(conversation_id)
    return {
        "status": "deleted",
        "conversation_id": conversation_id
    }


@app.get("/stats")
async def get_statistics():
    """Get service statistics"""
    stats = conversation_manager.get_statistics()
    stats["ollama_connected"] = await ollama_client.check_health()
    return stats


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "chat_api:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info"
    )