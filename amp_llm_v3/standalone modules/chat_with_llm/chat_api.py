"""
LLM Chat Service with Annotation Support (Port 9001)
====================================================

Chat service that operates in two modes:
1. Normal chat mode - regular conversation with LLM
2. Annotation mode - clinical trial annotation using modular services

Architecture:
- This service (9001) -> Runner Service (9003) -> LLM Assistant (9004)
- Runner fetches data from NCT Service (9002) if needed
- LLM Assistant handles JSON parsing, prompt generation, and LLM calls

UPDATED: Now uses async job processing for CSV annotations to avoid
Cloudflare 524 timeout errors. CSV uploads return immediately with a
job_id, and the frontend polls for status.
"""
import logging
import uuid
import httpx
import time
import io
import csv
import asyncio
import re
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

# Configuration
try:
    from assistant_config import config
except ImportError:
    class ChatConfig:
        OLLAMA_HOST = "localhost"
        OLLAMA_PORT = 11434
        @property
        def OLLAMA_BASE_URL(self):
            return f"http://{self.OLLAMA_HOST}:{self.OLLAMA_PORT}"
        API_VERSION = "3.0.0"
        SERVICE_NAME = "LLM Chat Service"
        CORS_ORIGINS = ["*"]
    config = ChatConfig()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# Job Manager for Async CSV Processing
# ============================================================================

class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AnnotationJob:
    job_id: str
    status: JobStatus = JobStatus.PENDING
    progress: str = "Queued"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    total_trials: int = 0
    processed_trials: int = 0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    csv_filename: Optional[str] = None
    original_filename: Optional[str] = None
    model: str = ""


class CSVJobManager:
    """Manages background CSV annotation jobs to avoid Cloudflare timeouts."""
    
    def __init__(self):
        self.jobs: Dict[str, AnnotationJob] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
    
    def start_cleanup_task(self):
        """Start background task to clean up old jobs"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_old_jobs())
    
    async def _cleanup_old_jobs(self):
        """Remove jobs older than 2 hours"""
        while True:
            await asyncio.sleep(300)  # Check every 5 minutes
            now = datetime.now()
            expired = [
                job_id for job_id, job in self.jobs.items()
                if (now - job.created_at).total_seconds() > 7200  # 2 hours
            ]
            for job_id in expired:
                # Also clean up the output file
                job = self.jobs[job_id]
                if job.csv_filename:
                    try:
                        output_file = Path(f"output/annotations/{job.csv_filename}")
                        if output_file.exists():
                            output_file.unlink()
                    except:
                        pass
                del self.jobs[job_id]
                logger.info(f"🧹 Cleaned up expired job: {job_id}")
    
    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get current status of a job"""
        job = self.jobs.get(job_id)
        
        if not job:
            return {
                "status": "not_found",
                "error": f"Job {job_id} not found"
            }
        
        response = {
            "job_id": job.job_id,
            "status": job.status.value,
            "progress": job.progress,
            "total_trials": job.total_trials,
            "processed_trials": job.processed_trials,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
            "model": job.model
        }
        
        if job.status == JobStatus.COMPLETED and job.result:
            response["result"] = job.result
        elif job.status == JobStatus.FAILED:
            response["error"] = job.error
        
        return response


# Global job manager instance
job_manager = CSVJobManager()


# ============================================================================
# Initialize FastAPI app
# ============================================================================

app = FastAPI(
    title="LLM Chat Service with Annotation",
    description="Chat and clinical trial annotation service using modular architecture",
    version="3.2.0",  # Bumped version for async CSV support
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Startup event to initialize job manager
@app.on_event("startup")
async def startup_event():
    """Initialize background tasks on startup"""
    job_manager.start_cleanup_task()
    
    # Ensure output directory exists
    Path("output/annotations").mkdir(parents=True, exist_ok=True)
    
    logger.info("✅ CSV Job Manager initialized")
    logger.info("✅ Output directory ready: output/annotations/")


# ============================================================================
# Configuration
# ============================================================================

RUNNER_SERVICE_URL = "http://localhost:9003"


# ============================================================================
# In-memory conversation storage
# ============================================================================

conversations: Dict[str, Dict] = {}


# ============================================================================
# Models
# ============================================================================

class ChatInitRequest(BaseModel):
    model: str
    annotation_mode: bool = False


class ChatMessageRequest(BaseModel):
    conversation_id: str
    message: str
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    nct_ids: Optional[List[str]] = None  # For annotation mode


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatResponse(BaseModel):
    conversation_id: str
    message: ChatMessage
    model: str
    annotation_mode: bool = False
    processing_time_seconds: Optional[float] = None


class AnnotationSummary(BaseModel):
    """Summary of annotation results"""
    total: int
    successful: int
    failed: int
    processing_time_seconds: float


class CSVAnnotationResponse(BaseModel):
    """Response for CSV batch annotation"""
    conversation_id: str
    message: ChatMessage
    model: str
    annotation_mode: bool = True
    # CSV-specific fields
    csv_filename: str
    download_url: str
    total: int
    successful: int
    failed: int
    total_time_seconds: float
    errors: List[dict] = []


class CSVJobStartResponse(BaseModel):
    """Response when CSV job is started (async mode)"""
    job_id: str
    message: str
    total: int
    status: str


# ============================================================================
# Helper Functions
# ============================================================================

def extract_nct_ids_from_csv(csv_content: str) -> List[str]:
    """
    Extract NCT IDs from CSV content.
    Looks for NCT IDs in any column using regex pattern.
    """
    nct_pattern = re.compile(r'NCT\d{8}', re.IGNORECASE)
    nct_ids = set()
    
    try:
        reader = csv.reader(io.StringIO(csv_content))
        for row in reader:
            for cell in row:
                matches = nct_pattern.findall(str(cell))
                for match in matches:
                    nct_ids.add(match.upper())
    except Exception as e:
        logger.error(f"Error parsing CSV: {e}")
    
    return list(nct_ids)


async def process_csv_job(
    job_id: str,
    csv_content: bytes,
    original_filename: str,
    model: str,
    temperature: float,
    conversation_id: str
):
    """
    Background task to process CSV annotation.
    Updates job status as it progresses.
    """
    job = job_manager.jobs.get(job_id)
    if not job:
        return
    
    job.status = JobStatus.PROCESSING
    job.progress = "Parsing CSV..."
    job.updated_at = datetime.now()
    
    start_time = time.time()
    
    try:
        # Forward to runner service
        logger.info(f"📤 Job {job_id}: Forwarding CSV to Runner Service")
        job.progress = "Sending to annotation service..."
        job.updated_at = datetime.now()
        
        async with httpx.AsyncClient(timeout=3600.0) as client:  # 1 hour timeout
            # Check runner health first
            try:
                health = await client.get(f"{RUNNER_SERVICE_URL}/health", timeout=5.0)
                if health.status_code != 200:
                    raise Exception("Runner service not available")
            except httpx.ConnectError:
                raise Exception(f"Cannot connect to Runner Service at {RUNNER_SERVICE_URL}")
            
            job.progress = "Runner service connected, processing..."
            job.updated_at = datetime.now()
            
            # Send file to runner's CSV endpoint
            files = {"file": (original_filename, csv_content, "text/csv")}
            data = {"model": model, "temperature": str(temperature)}
            
            response = await client.post(
                f"{RUNNER_SERVICE_URL}/annotate-csv",
                files=files,
                data=data
            )
            
            if response.status_code != 200:
                error_text = response.text
                raise Exception(f"Runner service error: {error_text}")
            
            result = response.json()
        
        # Job completed successfully
        end_time = time.time()
        duration = end_time - start_time
        
        # Build download URL
        download_url = result.get('download_url', '')
        if download_url:
            # Make it a full URL for the frontend
            download_url = f"{RUNNER_SERVICE_URL}{download_url}"
        
        job.status = JobStatus.COMPLETED
        job.progress = "Completed"
        job.processed_trials = result.get('total', 0)
        job.csv_filename = result.get('csv_filename', f'annotations_{job_id}.csv')
        job.result = {
            "total": result.get('total', 0),
            "successful": result.get('successful', 0),
            "failed": result.get('failed', 0),
            "total_time_seconds": round(duration, 1),
            "errors": result.get('errors', []),
            "download_url": download_url,
            "csv_filename": job.csv_filename,
            "model": model
        }
        job.updated_at = datetime.now()
        
        # Update conversation with result
        if conversation_id in conversations:
            conv = conversations[conversation_id]
            
            error_summary = ""
            if result.get("errors"):
                error_lines = [f"  - {e['nct_id']}: {e['error']}" for e in result["errors"][:5]]
                if len(result["errors"]) > 5:
                    error_lines.append(f"  ... and {len(result['errors']) - 5} more errors")
                error_summary = f"\n\nErrors:\n" + "\n".join(error_lines)
            
            response_content = f"""✅ CSV Annotation Complete
═══════════════════════════════════════════
📄 Input File: {original_filename}
📊 Total NCT IDs: {result['total']}
✓ Successful: {result['successful']}
✗ Failed: {result['failed']}
⏱ Processing Time: {duration:.1f}s
═══════════════════════════════════════════
{error_summary}
📥 Your annotated CSV is ready for download."""
            
            conv["messages"].append({
                "role": "assistant",
                "content": response_content
            })
        
        logger.info(f"✅ Job {job_id} completed: {result.get('successful', 0)} success, {result.get('failed', 0)} errors")
        
    except Exception as e:
        logger.error(f"❌ Job {job_id} failed: {e}", exc_info=True)
        job.status = JobStatus.FAILED
        job.error = str(e)
        job.progress = "Failed"
        job.updated_at = datetime.now()


async def annotate_trials_via_runner(
    nct_ids: List[str], 
    model: str, 
    temperature: float
) -> tuple[str, AnnotationSummary]:
    """
    Annotate trials using the Runner Service's batch-annotate endpoint.
    
    The Runner Service coordinates:
    1. Fetching trial data (from cache or NCT Service)
    2. Sending to LLM Assistant for annotation
    
    Returns:
        Tuple of (formatted_annotation_text, summary)
    """
    logger.info(f"🔬 Annotating {len(nct_ids)} trials with {model} via Runner Service")
    
    try:
        async with httpx.AsyncClient(timeout=600.0) as client:  # 10 min timeout for batch
            # Check runner service
            try:
                health = await client.get(f"{RUNNER_SERVICE_URL}/health", timeout=5.0)
                if health.status_code != 200:
                    return (
                        "❌ Runner Service not available. Please ensure it's running on port 9003.",
                        AnnotationSummary(total=len(nct_ids), successful=0, failed=len(nct_ids), processing_time_seconds=0)
                    )
            except httpx.ConnectError:
                return (
                    f"❌ Cannot connect to Runner Service at {RUNNER_SERVICE_URL}.\n\n"
                    "Please start the service:\n"
                    "  cd standalone_modules/runner\n"
                    "  uvicorn runner_service:app --port 9003 --reload",
                    AnnotationSummary(total=len(nct_ids), successful=0, failed=len(nct_ids), processing_time_seconds=0)
                )
            
            # Send batch annotation request
            logger.info(f"📤 Sending batch annotation request to Runner Service")
            
            response = await client.post(
                f"{RUNNER_SERVICE_URL}/batch-annotate",
                json={
                    "nct_ids": nct_ids,
                    "model": model,
                    "temperature": temperature,
                    "fetch_if_missing": True
                }
            )
            
            if response.status_code != 200:
                error_text = response.text
                logger.error(f"❌ Runner Service error: {error_text}")
                return (
                    f"❌ Annotation failed: {error_text[:500]}",
                    AnnotationSummary(total=len(nct_ids), successful=0, failed=len(nct_ids), processing_time_seconds=0)
                )
            
            data = response.json()
            
            # Format results
            results = data.get("results", [])
            total = data.get("total", len(nct_ids))
            successful = data.get("successful", 0)
            failed = data.get("failed", 0)
            total_time = data.get("total_time_seconds", 0)
            
            # Build formatted output
            output_parts = []
            
            for result in results:
                nct_id = result.get("nct_id")
                status = result.get("status")
                source = result.get("source", "unknown")
                annotation = result.get("annotation", "")
                error = result.get("error")
                proc_time = result.get("processing_time_seconds", 0)
                
                output_parts.append(f"\n{'='*80}")
                output_parts.append(f"NCT ID: {nct_id}")
                output_parts.append(f"Data Source: {source}")
                output_parts.append(f"Processing Time: {proc_time:.1f}s")
                output_parts.append(f"{'='*80}\n")
                
                if status == "success":
                    output_parts.append(annotation)
                else:
                    output_parts.append(f"❌ Error: {error}")
                
                output_parts.append("")
            
            formatted_output = "\n".join(output_parts)
            
            summary = AnnotationSummary(
                total=total,
                successful=successful,
                failed=failed,
                processing_time_seconds=total_time
            )
            
            return formatted_output, summary
            
    except httpx.TimeoutException:
        logger.error("❌ Annotation request timed out")
        return (
            "❌ Annotation timed out. Try fewer trials or a faster model.",
            AnnotationSummary(total=len(nct_ids), successful=0, failed=len(nct_ids), processing_time_seconds=0)
        )
    except Exception as e:
        logger.error(f"❌ Annotation error: {e}", exc_info=True)
        return (
            f"❌ Annotation error: {str(e)}",
            AnnotationSummary(total=len(nct_ids), successful=0, failed=len(nct_ids), processing_time_seconds=0)
        )


# ============================================================================
# Chat Routes
# ============================================================================

@app.post("/chat/init")
async def init_chat(request: ChatInitRequest):
    """Initialize a new chat conversation"""
    conversation_id = str(uuid.uuid4())
    
    conversations[conversation_id] = {
        "id": conversation_id,
        "model": request.model,
        "annotation_mode": request.annotation_mode,
        "messages": [],
        "created_at": time.time()
    }
    
    logger.info(f"✅ Created conversation {conversation_id} with model {request.model}")
    
    return {
        "conversation_id": conversation_id,
        "model": request.model,
        "annotation_mode": request.annotation_mode,
        "status": "initialized"
    }


@app.post("/chat/message", response_model=ChatResponse)
async def send_message(request: ChatMessageRequest):
    """Send a message in a conversation"""
    
    if request.conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    conv = conversations[request.conversation_id]
    start_time = time.time()
    
    # Annotation mode with NCT IDs
    if conv.get("annotation_mode") and request.nct_ids:
        logger.info(f"📝 Annotation request for {len(request.nct_ids)} trials")
        
        # Add user message
        user_message = f"Annotate trials: {', '.join(request.nct_ids)}"
        conv["messages"].append({
            "role": "user",
            "content": user_message
        })
        
        # Call annotation via runner service
        annotation_result, summary = await annotate_trials_via_runner(
            request.nct_ids,
            conv["model"],
            request.temperature
        )
        
        # Format response
        response_content = f"""Clinical Trial Annotation Report
Generated for {summary.total} trial(s)
Model: {conv["model"]}
Successful: {summary.successful} | Failed: {summary.failed}
Total Time: {summary.processing_time_seconds:.1f}s

{annotation_result}

═══════════════════════════════════════════

💡 Next:
  • Enter more NCT IDs to annotate
  • Type "exit" to select a different model
  • Click "Clear Chat" to reset"""
        
        # Add assistant message
        conv["messages"].append({
            "role": "assistant",
            "content": response_content
        })
        
        processing_time = time.time() - start_time
        
        return ChatResponse(
            conversation_id=request.conversation_id,
            message=ChatMessage(role="assistant", content=response_content),
            model=conv["model"],
            annotation_mode=True,
            processing_time_seconds=round(processing_time, 2)
        )
    
    # Normal chat mode
    conv["messages"].append({
        "role": "user",
        "content": request.message
    })
    
    # Call Ollama
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{config.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": conv["model"],
                    "messages": conv["messages"],
                    "temperature": request.temperature,
                    "stream": False
                }
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=503,
                    detail=f"Ollama error: {response.text}"
                )
            
            data = response.json()
            assistant_message = data["message"]["content"]
            
            # Add assistant message
            conv["messages"].append({
                "role": "assistant",
                "content": assistant_message
            })
            
            processing_time = time.time() - start_time
            
            return ChatResponse(
                conversation_id=request.conversation_id,
                message=ChatMessage(role="assistant", content=assistant_message),
                model=conv["model"],
                annotation_mode=False,
                processing_time_seconds=round(processing_time, 2)
            )
            
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to Ollama at {config.OLLAMA_BASE_URL}"
        )
    except Exception as e:
        logger.error(f"❌ Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CSV Annotation Routes (ASYNC - fixes Cloudflare 524 timeout)
# ============================================================================

@app.post("/chat/annotate-csv")
async def annotate_csv(
    conversation_id: str = Query(...),
    model: str = Query(...),
    temperature: float = Query(0.15),
    file: UploadFile = File(...)
):
    """
    Upload a CSV file with NCT IDs and generate annotations.
    
    NOW ASYNC: Returns immediately with a job_id.
    Frontend should poll /chat/annotate-csv-status/{job_id} for progress.
    
    The input CSV can have NCT IDs in any column - they will be automatically detected.
    """
    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    try:
        # Read file contents
        contents = await file.read()
        
        # Parse to count NCT IDs
        try:
            text_content = contents.decode('utf-8')
            nct_ids = extract_nct_ids_from_csv(text_content)
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=400,
                detail="Could not decode CSV file. Ensure it's UTF-8 encoded."
            )
        
        if not nct_ids:
            raise HTTPException(
                status_code=400,
                detail="No NCT IDs found in CSV file. NCT IDs should be in format NCT########"
            )
        
        logger.info(f"📄 Received CSV for annotation: {file.filename} ({len(nct_ids)} NCT IDs)")
        
        conv = conversations[conversation_id]
        
        # Add user message
        user_message = f"Annotate trials from CSV: {file.filename} ({len(nct_ids)} trials)"
        conv["messages"].append({
            "role": "user",
            "content": user_message
        })
        
        # Create job
        job_id = str(uuid.uuid4())
        job = AnnotationJob(
            job_id=job_id,
            status=JobStatus.PENDING,
            total_trials=len(nct_ids),
            progress=f"Starting annotation of {len(nct_ids)} trials...",
            original_filename=file.filename,
            model=model
        )
        job_manager.jobs[job_id] = job
        
        # Start background processing
        asyncio.create_task(
            process_csv_job(
                job_id=job_id,
                csv_content=contents,
                original_filename=file.filename,
                model=model,
                temperature=temperature,
                conversation_id=conversation_id
            )
        )
        
        logger.info(f"📋 Created job {job_id} for {len(nct_ids)} NCT IDs")
        
        # Return immediately with job_id
        return {
            "job_id": job_id,
            "message": f"Job started for {len(nct_ids)} NCT IDs from {file.filename}",
            "total": len(nct_ids),
            "status": "processing"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ CSV processing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chat/annotate-csv-status/{job_id}")
async def get_csv_annotation_status(job_id: str):
    """
    Get status of a CSV annotation job.
    
    Poll this endpoint to check job progress.
    
    Returns:
        - status: pending/processing/completed/failed
        - progress: Human-readable progress message
        - result: Full results when completed (includes download_url)
    """
    status = job_manager.get_job_status(job_id)
    
    if status["status"] == "not_found":
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    return status


@app.get("/chat/download/{job_id}")
async def download_annotation_results(job_id: str):
    """
    Download the annotated CSV for a completed job.
    
    Note: This proxies to the Runner Service's download endpoint.
    """
    status = job_manager.get_job_status(job_id)
    
    if status["status"] == "not_found":
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    if status["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Job not completed. Current status: {status['status']}"
        )
    
    # Get download URL from result
    result = status.get("result", {})
    download_url = result.get("download_url", "")
    
    if not download_url:
        raise HTTPException(status_code=404, detail="Download URL not available")
    
    # Proxy the download from runner service
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(download_url)
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Failed to fetch file from runner service"
                )
            
            # Return the file content
            from fastapi.responses import Response
            return Response(
                content=response.content,
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename={result.get('csv_filename', 'annotations.csv')}"
                }
            )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Cannot connect to Runner Service for download"
        )


# ============================================================================
# Other Chat Routes
# ============================================================================

@app.get("/chat/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Get conversation history"""
    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversations[conversation_id]


@app.delete("/chat/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation"""
    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")
    del conversations[conversation_id]
    return {"status": "deleted", "conversation_id": conversation_id}


@app.get("/chat/models")
async def list_models():
    """List available Ollama models"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{config.OLLAMA_BASE_URL}/api/tags")
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=503, detail="Cannot fetch models from Ollama")
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to Ollama at {config.OLLAMA_BASE_URL}"
        )


# ============================================================================
# Root Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "LLM Chat Service with Annotation",
        "version": "3.2.0",
        "status": "running",
        "architecture": "modular",
        "features": {
            "chat": "enabled",
            "annotation": "enabled (via Runner Service)",
            "async_csv": "enabled (no more Cloudflare 524 timeouts!)"
        },
        "endpoints": {
            "chat": "/chat/*",
            "csv_annotation": "/chat/annotate-csv (async)",
            "csv_status": "/chat/annotate-csv-status/{job_id}",
            "docs": "/docs"
        },
        "dependencies": {
            "ollama": config.OLLAMA_BASE_URL,
            "runner_service": RUNNER_SERVICE_URL
        }
    }


@app.get("/health")
async def health():
    """Health check with dependency status"""
    
    # Check Ollama connection
    ollama_connected = False
    ollama_models = 0
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{config.OLLAMA_BASE_URL}/api/tags")
            if response.status_code == 200:
                ollama_connected = True
                data = response.json()
                ollama_models = len(data.get("models", []))
    except:
        pass
    
    # Check Runner service
    runner_connected = False
    runner_features = {}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{RUNNER_SERVICE_URL}/health")
            if response.status_code == 200:
                runner_connected = True
                data = response.json()
                runner_features = {
                    "llm_assistant": data.get("llm_assistant", {}).get("connected", False),
                    "nct_service": data.get("nct_service", {}).get("connected", False)
                }
    except:
        pass
    
    # Count active jobs
    active_jobs = len([j for j in job_manager.jobs.values() 
                       if j.status in [JobStatus.PENDING, JobStatus.PROCESSING]])
    
    return {
        "status": "healthy",
        "service": config.SERVICE_NAME,
        "version": "3.2.0",
        "ollama": {
            "url": config.OLLAMA_BASE_URL,
            "connected": ollama_connected,
            "models_count": ollama_models
        },
        "runner_service": {
            "url": RUNNER_SERVICE_URL,
            "connected": runner_connected,
            "features": runner_features
        },
        "active_conversations": len(conversations),
        "active_csv_jobs": active_jobs,
        "total_csv_jobs": len(job_manager.jobs)
    }


@app.get("/models")
async def get_models():
    """Get available Ollama models - root level endpoint"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{config.OLLAMA_BASE_URL}/api/tags")
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=503, detail="Cannot fetch models from Ollama")
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to Ollama at {config.OLLAMA_BASE_URL}"
        )


# ============================================================================
# Run standalone
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    print("=" * 80)
    print("🚀 Starting LLM Chat Service with Annotation on port 9001...")
    print("=" * 80)
    print(f"🤖 Ollama: {config.OLLAMA_BASE_URL}")
    print(f"📁 Runner Service: {RUNNER_SERVICE_URL}")
    print(f"📚 Docs: http://localhost:9001/docs")
    print("=" * 80)
    print("\n📋 Service Dependencies:")
    print("  - Runner Service (9003) - Data fetching & annotation orchestration")
    print("  - LLM Assistant (9004) - JSON parsing & prompt generation")
    print("  - NCT Service (9002) - Clinical trials data")
    print("  - Ollama (11434) - LLM inference")
    print("=" * 80)
    print("\n✨ NEW: Async CSV processing enabled!")
    print("   CSV uploads now return immediately with a job_id.")
    print("   No more Cloudflare 524 timeout errors!")
    print("=" * 80)
    uvicorn.run(app, host="0.0.0.0", port=9001, reload=True)