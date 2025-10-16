"""
AMP LLM Web API Server
Secure FastAPI backend with double authentication.
"""
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List
import logging
from pathlib import Path

# Import from amp_llm package
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from amp_llm.llm.utils.session import OllamaSessionManager
from webapp.config import settings
from webapp.auth import verify_api_key

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(
    title="AMP LLM API",
    description="Secure Clinical Trial Research LLM API",
    version="1.0.0",
    docs_url="/docs" if settings.environment == "development" else None,
    redoc_url="/redoc" if settings.environment == "development" else None,
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Request/Response Models
class ChatRequest(BaseModel):
    """Chat request model."""
    query: str = Field(..., min_length=1, max_length=10000, description="User query")
    model: str = Field(default="llama3.2", description="LLM model to use")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Temperature")


class ChatResponse(BaseModel):
    """Chat response model."""
    response: str = Field(..., description="LLM response")
    model: str = Field(..., description="Model used")
    query: str = Field(..., description="Original query")


class ModelInfo(BaseModel):
    """Model information."""
    name: str
    available: bool = True


class ModelsResponse(BaseModel):
    """Models list response."""
    models: List[ModelInfo]
    count: int


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    ollama_connected: bool
    environment: str


# Exception Handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler."""
    logger.error(f"HTTP Exception: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "status_code": exc.status_code}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """General exception handler."""
    logger.error(f"Unexpected error: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "status_code": 500}
    )


# Routes
@app.get("/", response_model=HealthResponse, tags=["Health"])
async def root():
    """
    Root endpoint - health check.
    No authentication required.
    """
    try:
        async with OllamaSessionManager(
            settings.ollama_host, 
            settings.ollama_port
        ) as session:
            is_alive = await session.is_alive()
            
        return HealthResponse(
            status="healthy" if is_alive else "degraded",
            ollama_connected=is_alive,
            environment=settings.environment
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            ollama_connected=False,
            environment=settings.environment
        )


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Detailed health check.
    No authentication required.
    """
    return await root()


@app.get("/models", response_model=ModelsResponse, tags=["Models"])
async def list_models(api_key: str = Depends(verify_api_key)):
    """
    List available Ollama models.
    Requires valid API key.
    """
    try:
        async with OllamaSessionManager(
            settings.ollama_host,
            settings.ollama_port
        ) as session:
            models = await session.list_models()
            
        model_list = [ModelInfo(name=model) for model in models]
        
        logger.info(f"Listed {len(model_list)} models")
        return ModelsResponse(models=model_list, count=len(model_list))
        
    except Exception as e:
        logger.error(f"Error listing models: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to list models: {str(e)}"
        )


@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(
    request: ChatRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Send a chat message to the LLM.
    Requires valid API key.
    
    - **query**: Your question or prompt
    - **model**: Ollama model name (default: llama3.2)
    - **temperature**: Creativity level 0.0-2.0 (default: 0.7)
    """
    logger.info(f"Chat request: model={request.model}, query_length={len(request.query)}")
    
    try:
        async with OllamaSessionManager(
            settings.ollama_host,
            settings.ollama_port
        ) as session:
            # Verify model exists
            models = await session.list_models()
            if request.model not in models:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Model '{request.model}' not found. Available: {models}"
                )
            
            # Send prompt
            response_text = await session.send_prompt(
                model=request.model,
                prompt=request.query,
                temperature=request.temperature,
                max_retries=3
            )
            
            if response_text.startswith("Error:"):
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=response_text
                )
            
            logger.info(f"Chat response generated: {len(response_text)} chars")
            
            return ChatResponse(
                response=response_text,
                model=request.model,
                query=request.query
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat failed: {str(e)}"
        )


# Mount static files (web interface)
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount(
        "/app",
        StaticFiles(directory=str(static_dir), html=True),
        name="static"
    )
    logger.info(f"Mounted static files from {static_dir}")


# Startup Event
@app.on_event("startup")
async def startup_event():
    """Log startup information."""
    logger.info("=" * 60)
    logger.info("AMP LLM API Server Starting")
    logger.info("=" * 60)
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Ollama: {settings.ollama_host}:{settings.ollama_port}")
    logger.info(f"CORS Origins: {settings.allowed_origins}")
    logger.info(f"API Keys configured: {len(settings.api_keys)}")
    logger.info("=" * 60)
    
    # Test Ollama connection
    try:
        async with OllamaSessionManager(
            settings.ollama_host,
            settings.ollama_port
        ) as session:
            is_alive = await session.is_alive()
            if is_alive:
                models = await session.list_models()
                logger.info(f"✅ Ollama connected - {len(models)} models available")
            else:
                logger.warning("⚠️  Ollama connection failed")
    except Exception as e:
        logger.error(f"❌ Ollama connection error: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Log shutdown information."""
    logger.info("AMP LLM API Server Shutting Down")


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "webapp.server:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.environment == "development",
        log_level="info"
    )