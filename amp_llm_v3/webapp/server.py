"""
Enhanced AMP LLM Web API Server with Automatic Theme Discovery
COMPLETE VERSION - All endpoints included
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
import re
import asyncio

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
# Annotation CSVs from chat service (relative to amp_llm_v3/)
ANNOTATIONS_DIR = Path("standalone modules/chat_with_llm/output/annotations")

OUTPUT_DIR.mkdir(exist_ok=True)
DATABASE_DIR.mkdir(exist_ok=True)
ANNOTATIONS_DIR.mkdir(parents=True, exist_ok=True)

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
    elif filename.endswith('.png'):
        content_type = "image/png"
    elif filename.endswith('.jpg') or filename.endswith('.jpeg'):
        content_type = "image/jpeg"
    elif filename.endswith('.svg'):
        content_type = "image/svg+xml"
    
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
# Automatic Theme Discovery with CSS Comment Parsing
# ============================================================================

def parse_theme_metadata_from_css(css_file: Path) -> Optional[dict]:
    """
    Parse theme metadata from CSS file comments.
    
    Expected format at the top of CSS file:
    /* THEME_NAME: My Theme Name
       THEME_COLORS: #1BEB49, #0E1F81, #FFA400
    */
    
    Returns:
        dict with 'name' and 'colors' keys, or None if not found
    """
    try:
        with open(css_file, 'r', encoding='utf-8') as f:
            # Read first 20 lines to find metadata
            content = ''.join([f.readline() for _ in range(20)])
            
            metadata = {}
            
            # Look for THEME_NAME
            name_match = re.search(r'THEME_NAME:\s*(.+)', content)
            if name_match:
                metadata['name'] = name_match.group(1).strip()
            
            # Look for THEME_COLORS
            colors_match = re.search(r'THEME_COLORS:\s*(.+)', content)
            if colors_match:
                colors_str = colors_match.group(1).strip()
                # Extract hex colors
                colors = re.findall(r'#[0-9A-Fa-f]{6}', colors_str)
                if colors:
                    metadata['colors'] = colors
            
            return metadata if metadata else None
            
    except Exception as e:
        logger.warning(f"Could not parse metadata from {css_file.name}: {e}")
        return None


@app.get("/api/themes")
async def list_available_themes():
    """
    Automatically discover and list all theme-*.css files in static directory.
    """
    static_dir = WEBAPP_DIR / "static"
    themes = []
    
    # Fallback metadata for known themes
    fallback_metadata = {
        "theme-green.css": {
            "name": "Green Primary",
            "colors": ["#1BEB49", "#0E1F81"]
        },
        "theme-blue.css": {
            "name": "Blue Primary",
            "colors": ["#0E1F81", "#1BEB49"]
        },
        "theme-balanced.css": {
            "name": "Tri-Color",
            "colors": ["#0E1F81", "#1BEB49", "#FFA400"]
        },
        "theme-professional.css": {
            "name": "Professional",
            "colors": ["#2C3E50", "#16A085", "#E67E22"]
        },
        "theme-company.css": {
            "name": "Company",
            "colors": ["#0E1F81", "#1BEB49", "#FFA400"]
        }
    }
    
    try:
        theme_files = sorted(static_dir.glob("theme-*.css"))
        
        for theme_file in theme_files:
            filename = theme_file.name
            theme_id = filename.replace("theme-", "").replace(".css", "")
            
            css_metadata = parse_theme_metadata_from_css(theme_file)
            
            if css_metadata:
                theme_data = {
                    "id": theme_id,
                    "name": css_metadata.get("name", theme_id.title()),
                    "colors": css_metadata.get("colors", ["#667eea", "#764ba2"])
                }
                logger.info(f"✅ Discovered theme from CSS: {theme_data['name']} ({filename})")
            elif filename in fallback_metadata:
                theme_data = {
                    "id": theme_id,
                    **fallback_metadata[filename]
                }
                logger.info(f"📦 Using fallback metadata: {theme_data['name']} ({filename})")
            else:
                theme_data = {
                    "id": theme_id,
                    "name": theme_id.replace("-", " ").title(),
                    "colors": ["#667eea", "#764ba2"]
                }
                logger.info(f"🔧 Auto-generated theme: {theme_data['name']} ({filename})")
            
            themes.append(theme_data)
        
        logger.info(f"🎨 Total themes available: {len(themes)}")
        
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


# Service URLs - use port from config
CHAT_SERVICE_URL = f"http://localhost:{settings.chat_service_port}"
NCT_SERVICE_URL = f"http://localhost:{settings.nct_service_port}"

# Cross-branch job visibility: detect current branch and compute the other branch's chat URL
CURRENT_BRANCH = "main" if settings.chat_service_port < 9000 else "dev"
OTHER_BRANCH = "dev" if CURRENT_BRANCH == "main" else "main"
OTHER_CHAT_PORT = settings.chat_service_port + 1000 if CURRENT_BRANCH == "main" else settings.chat_service_port - 1000
OTHER_CHAT_SERVICE_URL = f"http://localhost:{OTHER_CHAT_PORT}"

logger.info(f"Branch: {CURRENT_BRANCH} (chat port {settings.chat_service_port}), other branch: {OTHER_BRANCH} (chat port {OTHER_CHAT_PORT})")

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
    annotation_mode: bool = False  

class ChatMessageRequest(BaseModel):
    conversation_id: str
    message: str
    temperature: float = 0.7
    nct_ids: Optional[List[str]] = None  


class ExtractRequest(BaseModel):
    nct_id: str


class ExtractResponse(BaseModel):
    nct_id: str
    extraction: Dict[str, Any]


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
        }
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
async def list_models():
    """
    CRITICAL FIX: Proxy request to chat service to list available Ollama models.
    
    BUGFIX: Chat service returns a LIST directly, not a dict with 'models' key!
    We need to wrap it for the frontend.
    """
    try:
        logger.info(f"Proxying /models request to {CHAT_SERVICE_URL}/models")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{CHAT_SERVICE_URL}/models",
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # BUGFIX: Chat service returns list directly, not {"models": [...]}
                if isinstance(data, list):
                    # Wrap list in dict for frontend compatibility
                    logger.info(f"Successfully fetched {len(data)} models from chat service")
                    return {"models": data}
                elif isinstance(data, dict) and "models" in data:
                    # Already in correct format
                    logger.info(f"Successfully fetched {len(data['models'])} models from chat service")
                    return data
                else:
                    logger.error(f"Unexpected response format: {type(data)}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Unexpected response format from chat service"
                    )
            else:
                error_detail = response.text
                logger.error(f"Chat service /models returned {response.status_code}: {error_detail}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Chat service error: {error_detail}"
                )
    
    except httpx.TimeoutException:
        logger.error("Timeout connecting to chat service for /models")
        raise HTTPException(
            status_code=503,
            detail="Chat service timeout - is it running on port 9001?"
        )
    except httpx.ConnectError:
        logger.error("Connection refused to chat service for /models")
        raise HTTPException(
            status_code=503,
            detail="Cannot connect to chat service on port 9001. "
                   "Start it with: cd 'standalone modules/chat_with_llm' && uvicorn chat_api:app --port 9001 --reload"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching models: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching models: {str(e)}")


# ============================================================================
# Chat Endpoints - Proxy to Chat Service
# ============================================================================

@app.post("/chat/init")
async def initialize_chat(request: InitChatRequest):
    """Initialize a chat session - proxied to chat service."""
    try:
        logger.info(f"Initializing chat with model: {request.model}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{CHAT_SERVICE_URL}/chat/init",
                json=request.dict(),
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Chat initialized: {data.get('conversation_id')}")
                return data
            else:
                error_detail = response.text
                logger.error(f"Chat init failed: {error_detail}")
                raise HTTPException(status_code=response.status_code, detail=error_detail)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error initializing chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/message")
async def send_chat_message(request: ChatMessageRequest):
    """Send a message in a chat session - proxied to chat service."""
    try:
        logger.info(f"Sending message to conversation: {request.conversation_id}")
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{CHAT_SERVICE_URL}/chat/message",
                json=request.dict(),
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=response.status_code, detail=response.text)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chat/conversations")
async def list_conversations():
    """List all conversations - proxied to chat service."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{CHAT_SERVICE_URL}/conversations")
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=response.status_code, detail=response.text)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chat/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Get conversation history - proxied to chat service."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{CHAT_SERVICE_URL}/conversations/{conversation_id}")
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=response.status_code, detail=response.text)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/chat/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation - proxied to chat service."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.delete(f"{CHAT_SERVICE_URL}/conversations/{conversation_id}")
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=response.status_code, detail=response.text)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Model Parameters & Email Config Proxy Endpoints
# ============================================================================

@app.get("/api/chat/model-parameters")
async def get_model_parameters_proxy():
    """Proxy model parameters request to chat service."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{CHAT_SERVICE_URL}/chat/model-parameters")
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=response.status_code, detail=response.text)
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Chat service not available")
    except Exception as e:
        logger.error(f"Model parameters proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat/model-parameters")
async def update_model_parameters_proxy(request: dict):
    """Proxy model parameters update to chat service."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{CHAT_SERVICE_URL}/chat/model-parameters",
                json=request
            )
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=response.status_code, detail=response.text)
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Chat service not available")
    except Exception as e:
        logger.error(f"Model parameters proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat/model-parameters/reset")
async def reset_model_parameters_proxy():
    """Proxy model parameters reset to chat service."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{CHAT_SERVICE_URL}/chat/model-parameters/reset")
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=response.status_code, detail=response.text)
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Chat service not available")
    except Exception as e:
        logger.error(f"Model parameters proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat/model-parameters/preset/{preset_name}")
async def apply_model_preset_proxy(preset_name: str):
    """Proxy model preset application to chat service."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{CHAT_SERVICE_URL}/chat/model-parameters/preset/{preset_name}")
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=response.status_code, detail=response.text)
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Chat service not available")
    except Exception as e:
        logger.error(f"Model preset proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/chat/email-config")
async def get_email_config_proxy():
    """Proxy email configuration check to chat service."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{CHAT_SERVICE_URL}/chat/email-config")
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=response.status_code, detail=response.text)
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Chat service not available")
    except Exception as e:
        logger.error(f"Email config proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/chat/jobs")
async def list_jobs_proxy():
    """Fetch jobs from both main and dev chat services, tagged by branch."""
    all_jobs = []
    total = 0
    active = 0

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Fetch from both branches concurrently
        branches = [
            (CURRENT_BRANCH, CHAT_SERVICE_URL),
            (OTHER_BRANCH, OTHER_CHAT_SERVICE_URL),
        ]
        for branch_name, chat_url in branches:
            try:
                response = await client.get(f"{chat_url}/chat/jobs")
                if response.status_code == 200:
                    data = response.json()
                    for job in data.get("jobs", []):
                        job["branch"] = branch_name
                    all_jobs.extend(data.get("jobs", []))
                    total += data.get("total", 0)
                    active += data.get("active", 0)
            except Exception as e:
                logger.debug(f"Could not fetch jobs from {branch_name} ({chat_url}): {e}")

    # Sort by created_at descending (newest first)
    all_jobs.sort(key=lambda j: j.get("created_at", ""), reverse=True)

    return {"jobs": all_jobs, "total": total, "active": active}


@app.get("/api/chat/resources")
async def get_resources_proxy():
    """Proxy resource status to chat service."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{CHAT_SERVICE_URL}/chat/resources")
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=response.status_code, detail=response.text)
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Chat service not available")
    except Exception as e:
        logger.error(f"Resource status proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/chat/jobs/{job_id}")
async def cancel_job_proxy(job_id: str, branch: str = CURRENT_BRANCH):
    """Proxy job cancellation to the correct branch's chat service."""
    chat_url = CHAT_SERVICE_URL if branch == CURRENT_BRANCH else OTHER_CHAT_SERVICE_URL
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.delete(f"{chat_url}/chat/jobs/{job_id}")
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=response.status_code, detail=response.text)
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=f"Chat service ({branch}) not available")
    except Exception as e:
        logger.error(f"Job cancel proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/chat/jobs/completed")
async def clear_completed_jobs_proxy():
    """Clear completed jobs from both branch chat services."""
    total_cleared = 0
    async with httpx.AsyncClient(timeout=10.0) as client:
        for branch_name, chat_url in [(CURRENT_BRANCH, CHAT_SERVICE_URL), (OTHER_BRANCH, OTHER_CHAT_SERVICE_URL)]:
            try:
                response = await client.delete(f"{chat_url}/chat/jobs/completed")
                if response.status_code == 200:
                    data = response.json()
                    total_cleared += data.get("cleared_count", 0)
            except Exception as e:
                logger.debug(f"Could not clear completed jobs on {branch_name}: {e}")
    return {"status": "cleared", "cleared_count": total_cleared, "message": f"Cleared {total_cleared} completed/failed jobs from both branches"}


@app.post("/chat/annotate")
async def annotate_manual_proxy(request: dict):
    """
    Proxy manual NCT annotation requests to chat service.
    This is the async version that returns immediately with a job_id.
    """
    try:
        logger.info(f"📝 Proxying manual annotation request: {len(request.get('nct_ids', []))} NCT IDs")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{CHAT_SERVICE_URL}/chat/annotate",
                json=request,
                headers={"Content-Type": "application/json"}
            )

            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=response.status_code, detail=response.text)

    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Chat service not available")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Manual annotation proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/annotate-csv")
async def annotate_csv_proxy(
    conversation_id: str,
    model: str,
    background_tasks: BackgroundTasks,
    temperature: float = 0.15,
    notification_email: Optional[str] = None,
    file: UploadFile = File(...)
):
    """
    Start async CSV annotation job. Returns immediately with job_id.
    Poll /chat/annotate-csv-status/{job_id} for progress.
    Optional: notification_email to receive email when job completes.
    """
    import uuid

    try:
        logger.info(f"📄 Starting async CSV annotation: {file.filename}")
        if notification_email:
            logger.info(f"📧 Will notify {notification_email} on completion")
        
        # Generate job ID
        job_id = str(uuid.uuid4())
        
        # Read file contents
        contents = await file.read()
        filename = file.filename
        
        # Initialize job status
        csv_annotation_jobs[job_id] = {
            "status": "processing",
            "filename": filename,
            "conversation_id": conversation_id,
            "model": model,
            "started_at": datetime.now().isoformat(),
            "progress": "Starting annotation...",
            "result": None,
            "error": None,
            "notification_email": notification_email
        }

        # Start background task
        background_tasks.add_task(
            process_csv_annotation,
            job_id, contents, filename, conversation_id, model, temperature, notification_email
        )
        
        logger.info(f"✅ Job started: {job_id}")
        
        return {
            "job_id": job_id,
            "status": "processing",
            "message": "CSV annotation started. Poll /chat/annotate-csv-status/{job_id} for progress."
        }
    
    except Exception as e:
        logger.error(f"Error starting CSV annotation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Store for async jobs
csv_annotation_jobs: Dict[str, Dict[str, Any]] = {}


async def process_csv_annotation(
    job_id: str,
    contents: bytes,
    filename: str,
    conversation_id: str,
    model: str,
    temperature: float,
    notification_email: Optional[str] = None
):
    """Background task to process CSV annotation."""
    try:
        csv_annotation_jobs[job_id]["progress"] = "Sending to annotation service..."

        async with httpx.AsyncClient(timeout=1800.0) as client:
            files = {"file": (filename, contents, "text/csv")}
            params = {
                "conversation_id": conversation_id,
                "model": model,
                "temperature": str(temperature)
            }
            # Add notification email if provided
            if notification_email:
                params["notification_email"] = notification_email
            
            response = await client.post(
                f"{CHAT_SERVICE_URL}/chat/annotate-csv",
                params=params,
                files=files
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Fix download URL to use proxy
                if 'download_url' in result:
                    original_url = result['download_url']
                    if '/download-csv/' in original_url:
                        csv_filename = original_url.split('/download-csv/')[-1]
                        result['download_url'] = f"/chat/download-csv/{csv_filename}"
                
                csv_annotation_jobs[job_id].update({
                    "status": "completed",
                    "progress": "Annotation complete!",
                    "result": result,
                    "completed_at": datetime.now().isoformat()
                })
                logger.info(f"✅ Job {job_id} completed: {result.get('total', 0)} trials")
            else:
                error_msg = response.text
                csv_annotation_jobs[job_id].update({
                    "status": "failed",
                    "progress": "Annotation failed",
                    "error": error_msg,
                    "completed_at": datetime.now().isoformat()
                })
                logger.error(f"❌ Job {job_id} failed: {error_msg}")
    
    except Exception as e:
        csv_annotation_jobs[job_id].update({
            "status": "failed",
            "progress": "Annotation failed",
            "error": str(e),
            "completed_at": datetime.now().isoformat()
        })
        logger.error(f"❌ Job {job_id} error: {e}", exc_info=True)


@app.get("/chat/annotate-csv-status/{job_id}")
async def get_csv_annotation_status(job_id: str):
    """Get status of async CSV annotation job."""
    if job_id not in csv_annotation_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = csv_annotation_jobs[job_id]
    
    response = {
        "job_id": job_id,
        "status": job["status"],
        "progress": job["progress"],
        "filename": job["filename"],
        "started_at": job["started_at"]
    }
    
    if job["status"] == "completed":
        response["result"] = job["result"]
        response["completed_at"] = job.get("completed_at")
    elif job["status"] == "failed":
        response["error"] = job["error"]
        response["completed_at"] = job.get("completed_at")
    
    return response


RUNNER_SERVICE_URL = f"http://localhost:{settings.runner_service_port}"


@app.get("/chat/download/{job_id}")
async def download_job_csv_proxy(job_id: str, branch: str = CURRENT_BRANCH):
    """
    Proxy CSV download by job ID to the correct branch's chat service.
    This is used by email notification links and the jobs panel.
    """
    chat_url = CHAT_SERVICE_URL if branch == CURRENT_BRANCH else OTHER_CHAT_SERVICE_URL
    try:
        logger.info(f"📥 Proxying job CSV download: {job_id} (branch: {branch})")

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(f"{chat_url}/chat/download/{job_id}")

            if response.status_code == 200:
                # Get filename from content-disposition header if available
                content_disp = response.headers.get("content-disposition", "")
                filename = f"annotations_{job_id}.csv"
                if "filename=" in content_disp:
                    import re
                    match = re.search(r'filename="?([^";\s]+)"?', content_disp)
                    if match:
                        filename = match.group(1)

                return Response(
                    content=response.content,
                    media_type="text/csv",
                    headers={
                        "Content-Disposition": f"attachment; filename={filename}"
                    }
                )
            else:
                raise HTTPException(status_code=response.status_code, detail=response.text)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading job CSV: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chat/download-csv/{filename}")
async def download_csv_proxy(filename: str):
    """
    Proxy CSV download requests to runner service.
    This allows downloads to work through Cloudflare/external access.
    """
    try:
        # Security: only allow .csv files, no path traversal
        if not filename.endswith('.csv') or '/' in filename or '\\' in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")
        
        logger.info(f"📥 Proxying CSV download: {filename}")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(f"{RUNNER_SERVICE_URL}/download-csv/{filename}")
            
            if response.status_code == 200:
                return Response(
                    content=response.content,
                    media_type="text/csv",
                    headers={
                        "Content-Disposition": f"attachment; filename={filename}"
                    }
                )
            else:
                raise HTTPException(status_code=response.status_code, detail=response.text)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading CSV: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Legacy Chat Endpoint (for backward compatibility)
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
# NCT Lookup Endpoint - Proxy to Standalone API
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
    on port 9002, which provides comprehensive trial data from multiple sources.
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
                    search_request = {
                        "include_extended": request.use_extended_apis
                    }
                    
                    if request.databases:
                        search_request["databases"] = request.databases
                    
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
                
                except Exception as e:
                    logger.error(f"Error initiating search for {nct_id}: {e}")
                    errors.append({"nct_id": nct_id, "error": str(e)})
            
            # Poll for results
            max_wait = 300  # 5 minutes max
            poll_interval = 2  # Check every 2 seconds
            start_time = asyncio.get_event_loop().time()
            
            while search_jobs and (asyncio.get_event_loop().time() - start_time) < max_wait:
                completed_jobs = []
                
                for nct_id, job_id in list(search_jobs.items()):
                    try:
                        status_response = await client.get(
                            f"{NCT_SERVICE_URL}/api/search/{job_id}/status"
                        )
                        
                        if status_response.status_code == 200:
                            status_data = status_response.json()
                            
                            if status_data["status"] == "completed":
                                results_response = await client.get(
                                    f"{NCT_SERVICE_URL}/api/results/{job_id}"
                                )
                                
                                if results_response.status_code == 200:
                                    result_data = results_response.json()
                                    results.append(result_data)
                                    completed_jobs.append(nct_id)
                                    logger.info(f"Retrieved results for {nct_id}")
                            
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
                
                for nct_id in completed_jobs:
                    del search_jobs[nct_id]
                
                if search_jobs:
                    await asyncio.sleep(poll_interval)
            
            # Handle timeouts
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
            "errors": errors if errors else None
        }
    )
@app.post("/api/nct/search/{nct_id}")
async def nct_search_proxy(
    nct_id: str,
    request: dict,
    api_key: str = Depends(verify_api_key)
):
    """Proxy NCT search requests to the NCT service."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{NCT_SERVICE_URL}/api/search/{nct_id}",
                json=request,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=response.text
                )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"NCT service not available on port {settings.nct_service_port}"
        )
    except Exception as e:
        logger.error(f"NCT search proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/nct/search/{job_id}/status")
async def nct_status_proxy(
    job_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Proxy NCT status requests to the NCT service."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{NCT_SERVICE_URL}/api/search/{job_id}/status"
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=response.text
                )
    except Exception as e:
        logger.error(f"NCT status proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/nct/results/{job_id}")
async def nct_results_proxy(
    job_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Proxy NCT results requests to the NCT service."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{NCT_SERVICE_URL}/api/results/{job_id}"
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=response.text
                )
    except Exception as e:
        logger.error(f"NCT results proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/nct/registry")
async def nct_registry_proxy(api_key: str = Depends(verify_api_key)):
    """Proxy NCT registry requests to the NCT service."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{NCT_SERVICE_URL}/api/registry")
            
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=response.text
                )
    except Exception as e:
        logger.error(f"NCT registry proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# File Management Endpoints
# ============================================================================

@app.get("/files/list")
async def list_files():
    """List all output files (JSON from output dir, CSV from annotations dir)."""
    try:
        files = []

        # JSON files from output directory
        for file_path in OUTPUT_DIR.glob("*.json"):
            stat = file_path.stat()
            files.append({
                "name": file_path.name,
                "size": f"{stat.st_size / 1024:.1f} KB",
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "type": "json",
                "source": "output"
            })

        # CSV files from annotations directory
        if ANNOTATIONS_DIR.exists():
            for file_path in ANNOTATIONS_DIR.glob("*.csv"):
                stat = file_path.stat()
                files.append({
                    "name": file_path.name,
                    "size": f"{stat.st_size / 1024:.1f} KB",
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "type": "csv",
                    "source": "annotations"
                })

        files.sort(key=lambda x: x["modified"], reverse=True)
        return FileListResponse(files=files)

    except Exception as e:
        logger.error(f"Error listing files: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/files/content/{filename}")
async def get_file_content(filename: str, source: str = "output"):
    """Get the content of a specific file.

    Args:
        filename: Name of the file
        source: 'output' for JSON files, 'annotations' for CSV files
    """
    try:
        safe_filename = Path(filename).name

        # Check in appropriate directory based on source
        if source == "annotations":
            file_path = ANNOTATIONS_DIR / safe_filename
        else:
            file_path = OUTPUT_DIR / safe_filename

        # Fallback: check both directories if not found
        if not file_path.exists():
            alt_path = ANNOTATIONS_DIR / safe_filename if source == "output" else OUTPUT_DIR / safe_filename
            if alt_path.exists():
                file_path = alt_path

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")

        if not file_path.is_file():
            raise HTTPException(status_code=400, detail="Not a file")

        content = file_path.read_text(encoding='utf-8')

        return FileContentResponse(
            filename=safe_filename,
            content=content
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/files/save")
async def save_file(request: FileSaveRequest):
    """Save content to a file in the output directory."""
    try:
        safe_filename = Path(request.filename).name
        
        if not safe_filename.endswith('.json'):
            safe_filename += '.json'
        
        file_path = OUTPUT_DIR / safe_filename
        file_path.write_text(request.content, encoding='utf-8')
        
        logger.info(f"Saved file: {safe_filename}")
        
        return {
            "status": "success",
            "filename": safe_filename,
            "path": str(file_path.absolute())
        }
    
    except Exception as e:
        logger.error(f"Error saving file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/files/download/{filename}")
async def download_file(filename: str, source: str = "output"):
    """Download a file from output or annotations directory."""
    try:
        safe_filename = Path(filename).name

        if source == "annotations":
            file_path = ANNOTATIONS_DIR / safe_filename
        else:
            file_path = OUTPUT_DIR / safe_filename

        # Fallback: check both directories
        if not file_path.exists():
            alt_path = ANNOTATIONS_DIR / safe_filename if source == "output" else OUTPUT_DIR / safe_filename
            if alt_path.exists():
                file_path = alt_path

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")

        # Determine media type
        media_type = "text/csv" if safe_filename.endswith('.csv') else "application/json"

        return FileResponse(
            path=str(file_path),
            media_type=media_type,
            filename=safe_filename,
            headers={"Content-Disposition": f"attachment; filename=\"{safe_filename}\""}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/files/delete/{filename}")
async def delete_file(filename: str, source: str = "output"):
    """Delete a file from output or annotations directory."""
    try:
        safe_filename = Path(filename).name

        if source == "annotations":
            file_path = ANNOTATIONS_DIR / safe_filename
        else:
            file_path = OUTPUT_DIR / safe_filename

        # Fallback: check both directories
        if not file_path.exists():
            alt_path = ANNOTATIONS_DIR / safe_filename if source == "output" else OUTPUT_DIR / safe_filename
            if alt_path.exists():
                file_path = alt_path

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")

        # Delete the file
        file_path.unlink()
        logger.info(f"🗑️ Deleted file: {safe_filename}")

        return {"status": "deleted", "filename": safe_filename}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/files/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a file to the output directory."""
    try:
        safe_filename = Path(file.filename).name
        file_path = OUTPUT_DIR / safe_filename
        
        content = await file.read()
        file_path.write_bytes(content)
        
        logger.info(f"Uploaded file: {safe_filename}")
        
        return {
            "status": "success",
            "filename": safe_filename,
            "size": len(content)
        }
    
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
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
    uvicorn.run(
        "webapp.server:app", 
        host="0.0.0.0", 
        port=settings.main_server_port,  # <-- NOW READS FROM .ENV
        reload=True
    )