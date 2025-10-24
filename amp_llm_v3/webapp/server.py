"""
Enhanced AMP LLM Web API Server with Automatic Theme Discovery
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
    
    **Auto-Discovery**: Just drop a new `theme-*.css` file into the static directory!
    
    **Optional Metadata in CSS**: Add these comments to the top of your CSS file:
    ```css
    /* THEME_NAME: My Beautiful Theme
       THEME_COLORS: #1BEB49, #0E1F81, #FFA400
    *\/
    ```
    
    If metadata comments are not found, the system will:
    1. Use fallback metadata for known themes
    2. Auto-generate a name from the filename
    3. Use default colors
    
    Returns:
        List of theme objects with id, name, and preview colors
    """
    static_dir = WEBAPP_DIR / "static"
    themes = []
    
    # Fallback metadata for known themes (used if CSS comments not found)
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
        # Scan for all theme-*.css files
        theme_files = sorted(static_dir.glob("theme-*.css"))
        
        for theme_file in theme_files:
            filename = theme_file.name
            theme_id = filename.replace("theme-", "").replace(".css", "")
            
            # Try to parse metadata from CSS comments first
            css_metadata = parse_theme_metadata_from_css(theme_file)
            
            if css_metadata:
                # Use metadata from CSS file
                theme_data = {
                    "id": theme_id,
                    "name": css_metadata.get("name", theme_id.title()),
                    "colors": css_metadata.get("colors", ["#667eea", "#764ba2"])
                }
                logger.info(f"✅ Discovered theme from CSS: {theme_data['name']} ({filename})")
            elif filename in fallback_metadata:
                # Use fallback metadata for known themes
                theme_data = {
                    "id": theme_id,
                    **fallback_metadata[filename]
                }
                logger.info(f"📦 Using fallback metadata: {theme_data['name']} ({filename})")
            else:
                # Auto-generate metadata for unknown themes
                theme_data = {
                    "id": theme_id,
                    "name": theme_id.replace("-", " ").title(),
                    "colors": ["#667eea", "#764ba2"]  # Default gradient
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


# NOTE: Additional endpoints (models, chat, NCT lookup, files) would continue here
# This file shows just the theme discovery portion - the rest remains unchanged


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