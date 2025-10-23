"""
Enhanced AMP LLM Web API Server with Standalone NCT API Integration
UPDATED: Now uses standalone NCT lookup service instead of amp_llm package
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
# Note: NCT lookup now uses standalone API service
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
# Dynamic Theme Discovery API Endpoint for AMP LLM WebApp
# ============================================================================

@app.get("/api/themes")
async def list_available_themes():
    """
    Scan static directory for theme-*.css files and return metadata.
    
    Returns:
        List of theme objects with id, name, and preview colors
    """
    static_dir = WEBAPP_DIR / "static"
    themes = []
    
    # Theme metadata - maps filename to display info
    # You can also parse this from CSS comments if you want
    # theme_metadata = {
    #     "theme-green.css": {
    #         "id": "green",
    #         "name": "Green Primary",
    #         "colors": ["#1BEB49", "#0E1F81"]
    #     },
    #     "theme-blue.css": {
    #         "id": "blue", 
    #         "name": "Blue Primary",
    #         "colors": ["#0E1F81", "#1BEB49"]
    #     },
    #     "theme-balanced.css": {
    #         "id": "balanced",
    #         "name": "Tri-Color",
    #         "colors": ["#0E1F81", "#1BEB49", "#FFA400"]
    #     },
    #     "theme-professional.css": {
    #         "id": "professional",
    #         "name": "Professional",
    #         "colors": ["#2C3E50", "#16A085", "#E67E22"]
    #     }
    # }
    
    try:
        # Scan for theme files
        for theme_file in static_dir.glob("theme-*.css"):
            filename = theme_file.name
            
            if filename in theme_metadata:
                themes.append(theme_metadata[filename])
            else:
                # Auto-generate metadata for unknown themes
                theme_id = filename.replace("theme-", "").replace(".css", "")
                themes.append({
                    "id": theme_id,
                    "name": theme_id.title(),
                    "colors": ["#667eea", "#764ba2"]  # Default colors
                })
        
        return {
            "themes": themes,
            "count": len(themes)
        }
    
    except Exception as e:
        logger.error(f"Error listing themes: {e}")
        return {
            "themes": [],
            "count": 0,
            "error": str(e)
        }

# ============================================================================
# Service URLs
# ============================================================================
CHAT_SERVICE_URL = "http://localhost:8001"
NCT_SERVICE_URL = "http://localhost:8002"  # Standalone NCT API


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
    databases: Optional[List[str]] = Field(default=None, description="Specific databases to query")


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
    """Health check - includes all service statuses."""
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
    
    nct_service_alive = False
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{NCT_SERVICE_URL}/health", timeout=5.0)
            nct_service_alive = response.status_code == 200
    except Exception as e:
        logger.error(f"NCT service health check failed: {e}")
    
    return {
        "status": "healthy" if (ollama_alive and chat_service_alive and nct_service_alive) else "degraded",
        "ollama_connected": ollama_alive,
        "chat_service_connected": chat_service_alive,
        "chat_service_url": CHAT_SERVICE_URL,
        "nct_service_connected": nct_service_alive,
        "nct_service_url": NCT_SERVICE_URL,
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
# NCT Lookup Endpoint - NOW USING STANDALONE API
# ============================================================================

@app.post("/nct-lookup", response_model=NCTLookupResponse)
async def nct_lookup(
    request: NCTLookupRequest, 
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key)
):
    """
    Fetch clinical trial data using standalone NCT API service.
    
    This proxies requests to the standalone NCT lookup service running
    on port 8002, which provides comprehensive trial data from multiple sources.
    """
    logger.info(f"NCT Lookup: {len(request.nct_ids)} trials")
    
    results = []
    errors = []
    search_jobs = {}
    
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            # Initiate searches for each NCT number
            for nct_id in request.nct_ids:
                try:
                    # Build search request
                    search_request = {
                        "include_extended": request.use_extended_apis
                    }
                    
                    if request.databases:
                        search_request["databases"] = request.databases
                    
                    # Initiate search on NCT service
                    response = await client.post(
                        f"{NCT_SERVICE_URL}/api/search/{nct_id}",
                        json=search_request
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        search_jobs[nct_id] = data["job_id"]
                        logger.info(f"Initiated search for {nct_id}: {data['status']}")
                    else:
                        error_data = response.json()
                        errors.append({
                            "nct_id": nct_id,
                            "error": error_data.get("detail", f"HTTP {response.status_code}")
                        })
                        logger.error(f"Failed to initiate search for {nct_id}: {error_data}")
                
                except Exception as e:
                    logger.error(f"Error initiating search for {nct_id}: {e}")
                    errors.append({"nct_id": nct_id, "error": str(e)})
            
            # Poll for results
            import asyncio
            max_wait = 300  # 5 minutes max
            poll_interval = 2  # Check every 2 seconds
            start_time = asyncio.get_event_loop().time()
            
            while search_jobs and (asyncio.get_event_loop().time() - start_time) < max_wait:
                completed_jobs = []
                
                for nct_id, job_id in list(search_jobs.items()):
                    try:
                        # Check status
                        status_response = await client.get(
                            f"{NCT_SERVICE_URL}/api/search/{job_id}/status"
                        )
                        
                        if status_response.status_code == 200:
                            status_data = status_response.json()
                            
                            if status_data["status"] == "completed":
                                # Fetch results
                                results_response = await client.get(
                                    f"{NCT_SERVICE_URL}/api/results/{job_id}"
                                )
                                
                                if results_response.status_code == 200:
                                    result_data = results_response.json()
                                    results.append(result_data)
                                    completed_jobs.append(nct_id)
                                    logger.info(f"Retrieved results for {nct_id}")
                                else:
                                    errors.append({
                                        "nct_id": nct_id,
                                        "error": "Failed to retrieve results"
                                    })
                                    completed_jobs.append(nct_id)
                            
                            elif status_data["status"] == "failed":
                                errors.append({
                                    "nct_id": nct_id,
                                    "error": status_data.get("error", "Search failed")
                                })
                                completed_jobs.append(nct_id)
                        
                    except Exception as e:
                        logger.error(f"Error checking status for {nct_id}: {e}")
                        errors.append({"nct_id": nct_id, "error": str(e)})
                        completed_jobs.append(nct_id)
                
                # Remove completed jobs
                for nct_id in completed_jobs:
                    del search_jobs[nct_id]
                
                # Wait before next poll
                if search_jobs:
                    await asyncio.sleep(poll_interval)
            
            # Handle any remaining jobs that timed out
            for nct_id in search_jobs.keys():
                errors.append({"nct_id": nct_id, "error": "Search timeout"})
    
    except Exception as e:
        logger.error(f"NCT lookup error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
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
    logger.info(f"NCT Service: {NCT_SERVICE_URL}")
    logger.info(f"Output Directory: {OUTPUT_DIR.absolute()}")
    logger.info(f"Static Directory: {(WEBAPP_DIR / 'static').absolute()}")
    logger.info(f"Templates Directory: {(WEBAPP_DIR / 'templates').absolute()}")
    logger.info("=" * 60)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("webapp.server:app", host="0.0.0.0", port=8000, reload=True)