"""
Enhanced AMP LLM Web API Server with Chat Service Integration
FIXED: Static file serving for proper CSS loading
"""
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import logging
from pathlib import Path
import json
import os
from datetime import datetime
import httpx
import mimetypes

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from amp_llm.llm.utils.session import OllamaSessionManager
from amp_llm.data.workflows.core_fetch import fetch_clinical_trial_and_pubmed_pmc
from amp_llm.data.clinical_trials.rag import ClinicalTrialRAG
from webapp.config import settings
from webapp.auth import verify_api_key

# ============================================================================
# CRITICAL FIX: Configure MIME types
# ============================================================================
mimetypes.init()
mimetypes.add_type('text/css', '.css')
mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('text/html', '.html')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WEBAPP_DIR = Path(__file__).parent

app = FastAPI(title="AMP LLM Enhanced API", version="3.0.0")

# ============================================================================
# CORS
# ============================================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins + ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Directory setup
# ============================================================================
OUTPUT_DIR = Path("output")
DATABASE_DIR = Path("ct_database")
OUTPUT_DIR.mkdir(exist_ok=True)
DATABASE_DIR.mkdir(exist_ok=True)

static_dir = WEBAPP_DIR / "static"
templates_dir = WEBAPP_DIR / "templates"

logger.info(f"Static directory: {static_dir.absolute()}")
logger.info(f"Templates directory: {templates_dir.absolute()}")

if static_dir.exists():
    css_files = list(static_dir.glob("*.css"))
    logger.info(f"CSS files found: {[f.name for f in css_files]}")

# ============================================================================
# FIXED: Explicit static file serving
# ============================================================================

@app.get("/static/{filename:path}")
async def serve_static_file(filename: str):
    """Serve static files with explicit content types."""
    file_path = static_dir / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    
    # Determine content type
    content_type = "application/octet-stream"
    if filename.endswith('.css'):
        content_type = "text/css; charset=utf-8"
    elif filename.endswith('.js'):
        content_type = "application/javascript; charset=utf-8"
    elif filename.endswith('.html'):
        content_type = "text/html; charset=utf-8"
    
    content = file_path.read_bytes()
    
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=3600",
            "Content-Type": content_type
        }
    )

# ============================================================================
# Initialize RAG system
# ============================================================================
try:
    rag_system = ClinicalTrialRAG(DATABASE_DIR)
    logger.info(f"✅ RAG system initialized with {len(rag_system.db.trials)} trials")
except Exception as e:
    logger.warning(f"RAG system not available: {e}")
    rag_system = None

# Chat service configuration
CHAT_SERVICE_URL = "http://localhost:8001"


# ============================================================================
# Request/Response Models
# ============================================================================

class ChatRequest(BaseModel):
    query: str
    model: str = "llama3.2"
    temperature: float = 0.7
    context_file: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    model: str
    query: str


class NCTLookupRequest(BaseModel):
    nct_ids: List[str] = Field(..., description="List of NCT numbers")
    use_extended_apis: bool = Field(default=False, description="Use extended APIs")


class NCTLookupResponse(BaseModel):
    success: bool
    results: List[Dict[str, Any]]
    summary: Dict[str, Any]


class ResearchQueryRequest(BaseModel):
    query: str
    model: str = "llama3.2"
    max_trials: int = 10


class ResearchQueryResponse(BaseModel):
    answer: str
    trials_used: int
    model: str


class ExtractRequest(BaseModel):
    nct_id: str
    model: str = "ct-research-assistant:latest"


class ExtractResponse(BaseModel):
    nct_id: str
    extraction: Dict[str, Any]


class FileSaveRequest(BaseModel):
    filename: str
    content: str


class FileListResponse(BaseModel):
    files: List[Dict[str, Any]]


class FileContentResponse(BaseModel):
    filename: str
    content: str


class InitChatRequest(BaseModel):
    model: str
    conversation_id: Optional[str] = None

class ChatMessageRequest(BaseModel):
    conversation_id: str
    message: str
    temperature: float = 0.7


# ============================================================================
# MAIN ROUTES
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint - serve the app."""
    index_file = templates_dir / "index.html"
    
    if index_file.exists():
        return FileResponse(index_file)
    
    static_index = WEBAPP_DIR / "static" / "index.html"
    if static_index.exists():
        return FileResponse(static_index)
    
    return HTMLResponse("""
    <html>
        <head>
            <title>AMP LLM</title>
            <style>
                body { font-family: sans-serif; text-align: center; padding: 50px; }
                h1 { color: #667eea; }
            </style>
        </head>
        <body>
            <h1>🔬 AMP LLM</h1>
            <p>Static files not found. Please check file locations.</p>
            <ul style="text-align: left; max-width: 500px; margin: 20px auto;">
                <li>Expected: webapp/templates/index.html</li>
                <li>Or: webapp/static/index.html</li>
                <li>Static files mount: /static/</li>
            </ul>
        </body>
    </html>
    """)


@app.get("/app")
async def app_page():
    """Serve main app page at /app endpoint."""
    return await root()


# ============================================================================
# Debug Endpoint
# ============================================================================

@app.get("/debug/files")
async def debug_files():
    """Debug endpoint to check file structure."""
    return {
        "webapp_dir": str(WEBAPP_DIR.absolute()),
        "static_dir": {
            "path": str(static_dir.absolute()),
            "exists": static_dir.exists(),
            "files": [f.name for f in static_dir.glob("*")] if static_dir.exists() else []
        },
        "templates_dir": {
            "path": str(templates_dir.absolute()),
            "exists": templates_dir.exists(),
            "files": [f.name for f in templates_dir.glob("*")] if templates_dir.exists() else []
        },
        "css_files": [f.name for f in static_dir.glob("*.css")] if static_dir.exists() else [],
        "js_files": [f.name for f in static_dir.glob("*.js")] if static_dir.exists() else []
    }


# ============================================================================
# Health & Models
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check - includes chat service status."""
    try:
        async with OllamaSessionManager(settings.ollama_host, settings.ollama_port) as session:
            ollama_alive = await session.is_alive()
    except Exception as e:
        logger.error(f"Ollama health check failed: {e}")
        ollama_alive = False
    
    chat_service_alive = False
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{CHAT_SERVICE_URL}/health", timeout=5.0)
            chat_service_alive = response.status_code == 200
    except Exception as e:
        logger.error(f"Chat service health check failed: {e}")
    
    return {
        "status": "healthy" if (ollama_alive and chat_service_alive) else "degraded",
        "ollama_connected": ollama_alive,
        "chat_service_connected": chat_service_alive,
        "chat_service_url": CHAT_SERVICE_URL,
        "rag_available": rag_system is not None,
        "trials_indexed": len(rag_system.db.trials) if rag_system else 0,
        "output_dir": str(OUTPUT_DIR.absolute()),
        "files_count": len(list(OUTPUT_DIR.glob("*.json"))),
        "static_dir": str((WEBAPP_DIR / "static").absolute()),
        "templates_dir": str((WEBAPP_DIR / "templates").absolute())
    }


@app.get("/models")
async def list_models(api_key: str = Depends(verify_api_key)):
    """List available models from chat service."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{CHAT_SERVICE_URL}/models", timeout=10.0)
            
            if response.status_code == 200:
                data = response.json()
                return {"models": [{"name": m["name"]} for m in data], "count": len(data)}
            else:
                raise HTTPException(status_code=503, detail="Chat service unavailable")
    except Exception as e:
        logger.error(f"Failed to list models: {e}")
        raise HTTPException(status_code=503, detail=str(e))


# ============================================================================
# Chat Endpoints - Proxy to Chat Service
# ============================================================================

@app.post("/chat/init")
async def init_chat(
    request: InitChatRequest,
    api_key: str = Depends(verify_api_key)
):
    """Initialize chat session (proxy to chat service)."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{CHAT_SERVICE_URL}/chat/init",
                json={
                    "model": request.model,
                    "conversation_id": request.conversation_id
                },
                timeout=10.0
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                error_data = response.json()
                raise HTTPException(
                    status_code=response.status_code,
                    detail=error_data.get("detail", "Chat init failed")
                )
    except httpx.RequestError as e:
        logger.error(f"Failed to connect to chat service: {e}")
        raise HTTPException(status_code=503, detail="Chat service unavailable")

@app.post("/chat/message")
async def send_chat_message(
    request: ChatMessageRequest,
    api_key: str = Depends(verify_api_key)
):
    """Send message to chat (proxy to chat service)."""
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{CHAT_SERVICE_URL}/chat/message",
                json={
                    "conversation_id": request.conversation_id,
                    "message": request.message,
                    "temperature": request.temperature
                }
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                error_data = response.json()
                raise HTTPException(
                    status_code=response.status_code,
                    detail=error_data.get("detail", "Chat failed")
                )
    except httpx.RequestError as e:
        logger.error(f"Failed to connect to chat service: {e}")
        raise HTTPException(status_code=503, detail="Chat service unavailable")

@app.get("/chat/conversations")
async def list_conversations(api_key: str = Depends(verify_api_key)):
    """List all conversations (proxy to chat service)."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{CHAT_SERVICE_URL}/conversations", timeout=10.0)
            
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=503, detail="Chat service unavailable")
    except httpx.RequestError as e:
        logger.error(f"Failed to connect to chat service: {e}")
        raise HTTPException(status_code=503, detail="Chat service unavailable")


@app.delete("/chat/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, api_key: str = Depends(verify_api_key)):
    """Delete conversation (proxy to chat service)."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{CHAT_SERVICE_URL}/conversations/{conversation_id}",
                timeout=10.0
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=404, detail="Conversation not found")
    except httpx.RequestError as e:
        logger.error(f"Failed to connect to chat service: {e}")
        raise HTTPException(status_code=503, detail="Chat service unavailable")


# ============================================================================
# Original Chat Endpoint (Legacy - for backward compatibility)
# ============================================================================

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, api_key: str = Depends(verify_api_key)):
    """Legacy chat endpoint with direct Ollama connection."""
    logger.info(f"Chat: model={request.model}, query_length={len(request.query)}")
    
    try:
        prompt = request.query
        
        if request.context_file:
            file_path = OUTPUT_DIR / request.context_file
            if file_path.exists():
                file_content = file_path.read_text()
                prompt = f"{request.query}\n\n[File: {request.context_file}]\n{file_content}"
                logger.info(f"Added file context: {request.context_file}")
        
        async with OllamaSessionManager(settings.ollama_host, settings.ollama_port) as session:
            response_text = await session.send_prompt(
                model=request.model,
                prompt=prompt,
                temperature=request.temperature,
                max_retries=3
            )
            
            if response_text.startswith("Error:"):
                raise HTTPException(status_code=503, detail=response_text)
            
            return ChatResponse(
                response=response_text,
                model=request.model,
                query=request.query
            )
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# NCT Lookup Endpoint
# ============================================================================

@app.post("/nct-lookup", response_model=NCTLookupResponse)
async def nct_lookup(request: NCTLookupRequest, api_key: str = Depends(verify_api_key)):
    """Fetch clinical trial data for NCT numbers."""
    logger.info(f"NCT Lookup: {len(request.nct_ids)} trials")
    
    results = []
    errors = []
    
    for nct_id in request.nct_ids:
        try:
            result = await fetch_clinical_trial_and_pubmed_pmc(nct_id)
            
            if "error" in result:
                errors.append({"nct_id": nct_id, "error": result["error"]})
            else:
                results.append(result)
        except Exception as e:
            logger.error(f"Error fetching {nct_id}: {e}")
            errors.append({"nct_id": nct_id, "error": str(e)})
    
    return NCTLookupResponse(
        success=len(results) > 0,
        results=results,
        summary={
            "total_requested": len(request.nct_ids),
            "successful": len(results),
            "failed": len(errors),
            "errors": errors
        }
    )


# ============================================================================
# Research Assistant Query
# ============================================================================

@app.post("/research", response_model=ResearchQueryResponse)
async def research_query(request: ResearchQueryRequest, api_key: str = Depends(verify_api_key)):
    """Query the Research Assistant with RAG."""
    if not rag_system:
        raise HTTPException(
            status_code=503,
            detail="Research Assistant not available. No trials indexed."
        )
    
    logger.info(f"Research query: {request.query[:50]}...")
    
    try:
        context = rag_system.get_context_for_llm(request.query, max_trials=request.max_trials)
        
        prompt = f"""You are a clinical trial research assistant. Use the trial data below to answer the question.

Question: {request.query}

{context}

Provide a clear, well-structured answer based on the trial data above."""
        
        async with OllamaSessionManager(settings.ollama_host, settings.ollama_port) as session:
            response = await session.send_prompt(
                model=request.model,
                prompt=prompt,
                temperature=0.7,
                max_retries=3
            )
        
        extractions = rag_system.retrieve(request.query)
        
        return ResearchQueryResponse(
            answer=response,
            trials_used=len(extractions),
            model=request.model
        )
    except Exception as e:
        logger.error(f"Research query error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Extract Structured Data
# ============================================================================

@app.post("/extract", response_model=ExtractResponse)
async def extract_trial(request: ExtractRequest, api_key: str = Depends(verify_api_key)):
    """Extract structured data from a clinical trial."""
    if not rag_system:
        raise HTTPException(status_code=503, detail="RAG system not available")
    
    logger.info(f"Extract: {request.nct_id}")
    
    try:
        extraction = rag_system.db.extract_structured_data(request.nct_id)
        
        if not extraction:
            raise HTTPException(status_code=404, detail=f"Trial {request.nct_id} not found")
        
        from dataclasses import asdict
        extraction_dict = asdict(extraction)
        
        return ExtractResponse(
            nct_id=request.nct_id,
            extraction=extraction_dict
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Extraction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Database Stats
# ============================================================================

@app.get("/stats")
async def database_stats(api_key: str = Depends(verify_api_key)):
    """Get database statistics."""
    if not rag_system:
        return {"error": "RAG system not available"}
    
    total = len(rag_system.db.trials)
    status_counts = {}
    peptide_count = 0
    
    for nct, trial in rag_system.db.trials.items():
        try:
            extraction = rag_system.db.extract_structured_data(nct)
            if extraction:
                status = extraction.study_status
                status_counts[status] = status_counts.get(status, 0) + 1
                if hasattr(extraction, 'is_peptide') and extraction.is_peptide:
                    peptide_count += 1
        except:
            pass
    
    return {
        "total_trials": total,
        "peptide_trials": peptide_count,
        "by_status": status_counts
    }


# ============================================================================
# FILE MANAGEMENT ENDPOINTS
# ============================================================================

@app.get("/files/list", response_model=FileListResponse)
async def list_files(api_key: str = Depends(verify_api_key)):
    """List all files in output directory."""
    try:
        files = []
        
        for filepath in OUTPUT_DIR.glob("*.json"):
            stat = filepath.stat()
            files.append({
                "name": filepath.name,
                "size": f"{stat.st_size / 1024:.1f} KB",
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "path": str(filepath.relative_to(OUTPUT_DIR))
            })
        
        files.sort(key=lambda x: x["modified"], reverse=True)
        
        return FileListResponse(files=files)
    
    except Exception as e:
        logger.error(f"Error listing files: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/files/content/{filename}")
async def get_file_content(filename: str, api_key: str = Depends(verify_api_key)):
    """Get content of a specific file."""
    try:
        file_path = OUTPUT_DIR / filename
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        content = file_path.read_text()
        
        return FileContentResponse(
            filename=filename,
            content=content
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/files/save")
async def save_file(request: FileSaveRequest, api_key: str = Depends(verify_api_key)):
    """Save content to a file."""
    try:
        file_path = OUTPUT_DIR / request.filename
        file_path.write_text(request.content)
        
        logger.info(f"Saved file: {request.filename}")
        
        return {"success": True, "filename": request.filename, "path": str(file_path)}
    
    except Exception as e:
        logger.error(f"Error saving file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/files/upload")
async def upload_file(file: UploadFile = File(...), api_key: str = Depends(verify_api_key)):
    """Upload a file to output directory."""
    try:
        if not file.filename.endswith(('.json', '.txt')):
            raise HTTPException(status_code=400, detail="Only .json and .txt files are allowed")
        
        file_path = OUTPUT_DIR / file.filename
        content = await file.read()
        file_path.write_bytes(content)
        
        logger.info(f"Uploaded file: {file.filename}")
        
        return {
            "success": True,
            "filename": file.filename,
            "size": len(content),
            "path": str(file_path)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/files/download/{filename}")
async def download_file(filename: str, api_key: str = Depends(verify_api_key)):
    """Download a file."""
    try:
        file_path = OUTPUT_DIR / filename
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        return FileResponse(
            path=str(file_path),
            filename=filename,
            media_type='application/octet-stream'
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/files/delete/{filename}")
async def delete_file(filename: str, api_key: str = Depends(verify_api_key)):
    """Delete a file."""
    try:
        file_path = OUTPUT_DIR / filename
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        file_path.unlink()
        logger.info(f"Deleted file: {filename}")
        
        return {"success": True, "filename": filename}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Startup
# ============================================================================

@app.on_event("startup")
async def startup_event():
    logger.info("=" * 60)
    logger.info("AMP LLM Enhanced API Server Starting")
    logger.info("=" * 60)
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Ollama: {settings.ollama_host}:{settings.ollama_port}")
    logger.info(f"Chat Service: {CHAT_SERVICE_URL}")
    logger.info(f"RAG Available: {rag_system is not None}")
    if rag_system:
        logger.info(f"Trials Indexed: {len(rag_system.db.trials)}")
    logger.info(f"Output Directory: {OUTPUT_DIR.absolute()}")
    logger.info(f"Static Directory: {(WEBAPP_DIR / 'static').absolute()}")
    logger.info(f"Templates Directory: {(WEBAPP_DIR / 'templates').absolute()}")
    logger.info("=" * 60)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("webapp.server:app", host="0.0.0.0", port=8000, reload=True)