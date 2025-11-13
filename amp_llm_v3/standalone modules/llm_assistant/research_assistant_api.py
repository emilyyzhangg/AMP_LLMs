"""
Research Assistant API
======================

FastAPI application for Research Assistant service with RAG capabilities.

Usage:
    uvicorn research_assistant_api:app --host 0.0.0.0 --port 9002 --reload
"""
import logging
import os
from datetime import datetime
from typing import List, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

# Import your existing modules
from prompt_generator import PromptGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# Initialize PromptGenerator
# ============================================================================
try:
    prompt_gen = PromptGenerator()
    logger.info("✅ PromptGenerator loaded successfully")
except Exception as e:
    logger.error(f"❌ Failed to load PromptGenerator: {e}")
    prompt_gen = None

# ============================================================================
# Pydantic Models
# ============================================================================

class HealthResponse(BaseModel):
    status: str
    version: str
    prompt_generator_loaded: bool
    timestamp: str

class ResearchQuery(BaseModel):
    query: str
    nct_id: Optional[str] = None
    use_rag: bool = True
    model: str = "llama3.2:3b"
    temperature: float = 0.7

class ResearchResponse(BaseModel):
    query: str
    response: str
    nct_id: Optional[str] = None
    model: str
    timestamp: str

class FileUploadResponse(BaseModel):
    filename: str
    size: int
    status: str
    message: str

class NCTInfo(BaseModel):
    nct_id: str
    title: Optional[str] = None
    status: Optional[str] = None
    brief_summary: Optional[str] = None

# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="Research Assistant API",
    description="AI-powered research assistant with RAG capabilities for clinical trial analysis",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Configuration
# ============================================================================

# Directories
UPLOAD_DIR = Path("uploads")
DOCUMENTS_DIR = Path("documents")
RAG_DB_DIR = Path("rag_database")

# Create directories if they don't exist
UPLOAD_DIR.mkdir(exist_ok=True)
DOCUMENTS_DIR.mkdir(exist_ok=True)
RAG_DB_DIR.mkdir(exist_ok=True)

# ============================================================================
# Lifecycle Events
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize service on startup"""
    logger.info("Research Assistant API v1.0.0 starting...")
    
    if prompt_gen:
        logger.info("✅ PromptGenerator ready")
    else:
        logger.warning("⚠️ PromptGenerator not available")
    
    logger.info(f"📁 Upload directory: {UPLOAD_DIR.absolute()}")
    logger.info(f"📁 Documents directory: {DOCUMENTS_DIR.absolute()}")
    logger.info(f"📁 RAG database directory: {RAG_DB_DIR.absolute()}")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Research Assistant API stopped")

# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Research Assistant API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "health": "GET /health",
            "research": "POST /research",
            "upload": "POST /upload",
            "documents": "GET /documents",
            "nct_lookup": "GET /nct/{nct_id}",
            "websocket": "WS /ws/research"
        }
    }

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy" if prompt_gen else "degraded",
        version="1.0.0",
        prompt_generator_loaded=prompt_gen is not None,
        timestamp=datetime.utcnow().isoformat()
    )

@app.post("/research", response_model=ResearchResponse)
async def research_query(request: ResearchQuery):
    """
    Process a research query with optional RAG enhancement.
    
    Args:
        request: Research query with optional NCT ID and RAG settings
        
    Returns:
        AI-generated research response
    """
    try:
        if not prompt_gen:
            raise HTTPException(
                status_code=503,
                detail="PromptGenerator not available"
            )
        
        logger.info(f"Processing research query: {request.query[:100]}...")
        
        # TODO: Implement your research logic here
        # This is a placeholder - replace with your actual implementation
        
        response_text = f"Research response for: {request.query}"
        
        if request.nct_id:
            response_text += f"\n\nNCT ID: {request.nct_id}"
        
        if request.use_rag:
            response_text += "\n\n[RAG context would be applied here]"
        
        return ResearchResponse(
            query=request.query,
            response=response_text,
            nct_id=request.nct_id,
            model=request.model,
            timestamp=datetime.utcnow().isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Research query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload", response_model=FileUploadResponse)
async def upload_file(file: UploadFile = File(...)):
    """
    Upload a document for RAG processing.
    
    Args:
        file: File to upload
        
    Returns:
        Upload confirmation with file details
    """
    try:
        # Save file
        file_path = UPLOAD_DIR / file.filename
        
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        
        file_size = len(content)
        
        logger.info(f"Uploaded file: {file.filename} ({file_size} bytes)")
        
        # TODO: Process file for RAG (extract text, create embeddings, etc.)
        
        return FileUploadResponse(
            filename=file.filename,
            size=file_size,
            status="success",
            message=f"File uploaded successfully to {file_path}"
        )
        
    except Exception as e:
        logger.error(f"File upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/documents")
async def list_documents():
    """List all uploaded documents"""
    try:
        documents = []
        
        for file_path in UPLOAD_DIR.iterdir():
            if file_path.is_file():
                stat = file_path.stat()
                documents.append({
                    "filename": file_path.name,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
        
        return {
            "documents": documents,
            "count": len(documents)
        }
        
    except Exception as e:
        logger.error(f"Failed to list documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/documents/{filename}")
async def download_document(filename: str):
    """Download a specific document"""
    try:
        file_path = UPLOAD_DIR / filename
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type="application/octet-stream"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File download failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/documents/{filename}")
async def delete_document(filename: str):
    """Delete a document"""
    try:
        file_path = UPLOAD_DIR / filename
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        file_path.unlink()
        logger.info(f"Deleted file: {filename}")
        
        return {
            "status": "deleted",
            "filename": filename
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File deletion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/nct/{nct_id}", response_model=NCTInfo)
async def get_nct_info(nct_id: str):
    """
    Get clinical trial information by NCT ID.
    
    Args:
        nct_id: ClinicalTrials.gov NCT identifier
        
    Returns:
        Clinical trial information
    """
    try:
        # TODO: Implement NCT lookup logic
        # This is a placeholder - replace with your actual NCT lookup
        
        logger.info(f"Looking up NCT ID: {nct_id}")
        
        return NCTInfo(
            nct_id=nct_id,
            title="[NCT lookup not yet implemented]",
            status="Unknown",
            brief_summary="Placeholder summary"
        )
        
    except Exception as e:
        logger.error(f"NCT lookup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws/research")
async def websocket_research(websocket: WebSocket):
    """
    WebSocket endpoint for streaming research responses.
    
    Protocol:
        Client -> {"action": "query", "query": "...", "use_rag": true, "model": "..."}
        Client -> {"action": "exit"}
        
        Server -> {"type": "chunk", "content": "...", "done": false}
        Server -> {"type": "done"}
        Server -> {"type": "error", "message": "..."}
    """
    await websocket.accept()
    
    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            
            if action == "query":
                query = data.get("query")
                use_rag = data.get("use_rag", True)
                model = data.get("model", "llama3.2:3b")
                
                if not query:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Query required"
                    })
                    continue
                
                # TODO: Implement streaming research response
                # This is a placeholder
                response = f"Streaming response for: {query}"
                
                # Send in chunks
                for i, char in enumerate(response):
                    await websocket.send_json({
                        "type": "chunk",
                        "content": char,
                        "done": i == len(response) - 1
                    })
                
                await websocket.send_json({
                    "type": "done"
                })
            
            elif action == "exit":
                await websocket.send_json({
                    "type": "exit",
                    "message": "Connection closed"
                })
                break
            
            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown action: {action}"
                })
    
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except:
            pass

@app.get("/stats")
async def get_statistics():
    """Get service statistics"""
    try:
        doc_count = len(list(UPLOAD_DIR.iterdir()))
        
        return {
            "service": "Research Assistant API",
            "version": "1.0.0",
            "prompt_generator_loaded": prompt_gen is not None,
            "documents_count": doc_count,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Stats retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "research_assistant_api:app",
        host="0.0.0.0",
        port=9002,
        reload=True,
        log_level="info"
    )