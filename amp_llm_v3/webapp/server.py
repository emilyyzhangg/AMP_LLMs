"""
Enhanced AMP LLM Web API Server
Adds file management and complete terminal feature parity
"""
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import logging
from pathlib import Path
import json
import os
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from amp_llm.llm.utils.session import OllamaSessionManager
from amp_llm.data.workflows.core_fetch import fetch_clinical_trial_and_pubmed_pmc
from amp_llm.data.clinical_trials.rag import ClinicalTrialRAG
from webapp.config import settings
from webapp.auth import verify_api_key

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WEBAPP_DIR = Path(__file__).parent

app = FastAPI(title="AMP LLM Enhanced API", version="3.0.0")
app.mount("/static", StaticFiles(directory=str(WEBAPP_DIR / "static")), name="static")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins + ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directory setup
OUTPUT_DIR = Path("output")
DATABASE_DIR = Path("ct_database")
OUTPUT_DIR.mkdir(exist_ok=True)
DATABASE_DIR.mkdir(exist_ok=True)

# Initialize RAG system
try:
    rag_system = ClinicalTrialRAG(DATABASE_DIR)
    logger.info(f"✅ RAG system initialized with {len(rag_system.db.trials)} trials")
except Exception as e:
    logger.warning(f"RAG system not available: {e}")
    rag_system = None


# ============================================================================
# Request/Response Models
# ============================================================================

class ChatRequest(BaseModel):
    query: str
    model: str = "llama3.2"
    temperature: float = 0.7
    context_file: Optional[str] = None  # NEW: Optional file to load as context


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


# ============================================================================
# Health & Models
# ============================================================================
@app.get("/app")
async def app_page():
    """Serve main app page at /app endpoint."""
    index_file = Path(__file__).parent / "static" / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse("<h1>AMP LLM Web Interface</h1>")

# Also keep the root endpoint
@app.get("/")
async def root():
    """Root endpoint - redirect to /app."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/app")

@app.get("/health")
async def health_check():
    """Health check."""
    try:
        async with OllamaSessionManager(settings.ollama_host, settings.ollama_port) as session:
            is_alive = await session.is_alive()
        
        return {
            "status": "healthy" if is_alive else "degraded",
            "ollama_connected": is_alive,
            "rag_available": rag_system is not None,
            "trials_indexed": len(rag_system.db.trials) if rag_system else 0,
            "output_dir": str(OUTPUT_DIR.absolute()),
            "files_count": len(list(OUTPUT_DIR.glob("*.json")))
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "ollama_connected": False,
            "error": str(e)
        }


@app.get("/models")
async def list_models(api_key: str = Depends(verify_api_key)):
    """List available models."""
    try:
        async with OllamaSessionManager(settings.ollama_host, settings.ollama_port) as session:
            models = await session.list_models()
        
        return {"models": [{"name": m} for m in models], "count": len(models)}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ============================================================================
# Chat Endpoint (Enhanced with File Context)
# ============================================================================

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, api_key: str = Depends(verify_api_key)):
    """Chat with LLM, optionally with file context."""
    logger.info(f"Chat: model={request.model}, query_length={len(request.query)}")
    
    try:
        # Build prompt with file context if provided
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
    """
    Fetch clinical trial data for NCT numbers.
    Equivalent to terminal Option 4.
    """
    logger.info(f"NCT Lookup: {len(request.nct_ids)} trials, extended={request.use_extended_apis}")
    
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
    """
    Query the Research Assistant with RAG.
    Equivalent to terminal Option 5.
    """
    if not rag_system:
        raise HTTPException(
            status_code=503,
            detail="Research Assistant not available. No trials indexed."
        )
    
    logger.info(f"Research query: {request.query[:50]}... max_trials={request.max_trials}")
    
    try:
        # Get RAG context
        context = rag_system.get_context_for_llm(request.query, max_trials=request.max_trials)
        
        # Build prompt
        prompt = f"""You are a clinical trial research assistant. Use the trial data below to answer the question.

Question: {request.query}

{context}

Provide a clear, well-structured answer based on the trial data above."""
        
        # Get LLM response
        async with OllamaSessionManager(settings.ollama_host, settings.ollama_port) as session:
            response = await session.send_prompt(
                model=request.model,
                prompt=prompt,
                temperature=0.7,
                max_retries=3
            )
        
        # Count trials used
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
    """
    Extract structured data from a clinical trial.
    Uses RAG + LLM for structured extraction.
    """
    if not rag_system:
        raise HTTPException(status_code=503, detail="RAG system not available")
    
    logger.info(f"Extract: {request.nct_id}")
    
    try:
        # Get extraction from RAG
        extraction = rag_system.db.extract_structured_data(request.nct_id)
        
        if not extraction:
            raise HTTPException(status_code=404, detail=f"Trial {request.nct_id} not found")
        
        # Convert to dict
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
    
    # Count by status
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
# FILE MANAGEMENT ENDPOINTS (NEW)
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
        
        # Sort by modified time (newest first)
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
        # Validate file type
        if not file.filename.endswith(('.json', '.txt')):
            raise HTTPException(status_code=400, detail="Only .json and .txt files are allowed")
        
        file_path = OUTPUT_DIR / file.filename
        
        # Save file
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
    logger.info(f"RAG Available: {rag_system is not None}")
    if rag_system:
        logger.info(f"Trials Indexed: {len(rag_system.db.trials)}")
    logger.info(f"Output Directory: {OUTPUT_DIR.absolute()}")
    logger.info(f"Files in output/: {len(list(OUTPUT_DIR.glob('*.json')))}")
    logger.info("=" * 60)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("webapp.server:app", host="0.0.0.0", port=8000, reload=True)