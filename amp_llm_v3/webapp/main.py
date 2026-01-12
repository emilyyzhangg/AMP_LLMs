"""
AMP_LLM Web Application - FastAPI Server
Serves web interface and handles LLM interactions
"""
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
from pathlib import Path
from typing import Optional

# Import existing LLM utilities
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from amp_llm.llm.utils.session import OllamaSessionManager
from amp_llm.config import get_logger, get_config

logger = get_logger(__name__)
config = get_config()

app = FastAPI(title="AMP LLM Web Interface")

# CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (HTML, CSS, JS)
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Global session manager (reuses connection)
session_manager: Optional[OllamaSessionManager] = None


@app.on_event("startup")
async def startup():
    """Initialize Ollama connection on startup"""
    global session_manager
    try:
        # Connect to local Ollama (no SSH needed)
        session_manager = OllamaSessionManager(
            host="localhost",
            port=11434,
            ssh_connection=None  # No SSH in web mode
        )
        await session_manager.start_session()
        logger.info("✅ Connected to Ollama")
    except Exception as e:
        logger.error(f"Failed to connect to Ollama: {e}")
        # Continue anyway - will retry on requests


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown"""
    global session_manager
    if session_manager:
        await session_manager.close_session()
        logger.info("Closed Ollama session")


@app.get("/")
async def home():
    """Serve main page"""
    index_file = Path(__file__).parent / "templates" / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse("<h1>AMP LLM Web Interface</h1><p>Coming soon...</p>")


@app.get("/api/models")
async def list_models():
    """List available Ollama models"""
    if not session_manager:
        raise HTTPException(status_code=503, detail="LLM service not available")
    
    try:
        models = await session_manager.list_models()
        return {"models": models}
    except Exception as e:
        logger.error(f"Error listing models: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/generate")
async def generate(request: dict):
    """Generate LLM response (non-streaming)"""
    if not session_manager:
        raise HTTPException(status_code=503, detail="LLM service not available")
    
    model = request.get("model")
    prompt = request.get("prompt")
    temperature = request.get("temperature", 0.7)
    
    if not model or not prompt:
        raise HTTPException(status_code=400, detail="model and prompt required")
    
    try:
        response = await session_manager.send_prompt(
            model=model,
            prompt=prompt,
            temperature=temperature
        )
        return {"response": response}
    except Exception as e:
        logger.error(f"Generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket endpoint for streaming chat"""
    await websocket.accept()
    
    if not session_manager:
        await websocket.send_json({
            "type": "error",
            "message": "LLM service not available"
        })
        await websocket.close()
        return
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            
            message_type = data.get("type")
            
            if message_type == "chat":
                model = data.get("model")
                prompt = data.get("prompt")
                
                # Send response (can be extended for streaming)
                response = await session_manager.send_prompt(
                    model=model,
                    prompt=prompt
                )
                
                await websocket.send_json({
                    "type": "response",
                    "content": response
                })
            
            elif message_type == "ping":
                await websocket.send_json({"type": "pong"})
    
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.close()


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    ollama_status = "connected" if session_manager and await session_manager.is_alive() else "disconnected"
    
    return {
        "status": "healthy",
        "ollama": ollama_status
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=9000,
        reload=True,
        log_level="info"
    )