"""
LLM Chat Service with Annotation Support
========================================

Chat service that operates in two modes:
1. Normal chat mode - regular conversation with LLM
2. Annotation mode - clinical trial annotation using modular services

Architecture:
- This service (CHAT_SERVICE_PORT) -> Runner Service (RUNNER_SERVICE_PORT) -> LLM Assistant (LLM_ASSISTANT_PORT)
- Runner fetches data from NCT Service (NCT_SERVICE_PORT) if needed
- LLM Assistant handles JSON parsing, prompt generation, and LLM calls

UPDATED: Now uses async job processing for CSV annotations to avoid
Cloudflare 524 timeout errors. CSV uploads return immediately with a
job_id, and the frontend polls for status.

UPDATED: Now includes git commit and full model version in CSV headers.

UPDATED: Now loads all port configuration from .env file.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
# First try current dir, then parent directories (amp_llm_v3/.env)
load_dotenv()
_script_dir = Path(__file__).parent.resolve()
_root_env = _script_dir.parent.parent / ".env"  # amp_llm_v3/.env
if _root_env.exists():
    load_dotenv(_root_env)

import logging
import uuid
import httpx
import time
import io
import csv
import asyncio
import re
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

# Email notifications
from email_utils import (
    send_annotation_complete_email,
    send_annotation_failed_email,
    is_email_configured
)

# Configuration
try:
    from assistant_config import config
except ImportError:
    class ChatConfig:
        OLLAMA_HOST = os.getenv("ollama_host", "localhost")
        OLLAMA_PORT = int(os.getenv("ollama_port", "11434"))
        @property
        def OLLAMA_BASE_URL(self):
            return f"http://{self.OLLAMA_HOST}:{self.OLLAMA_PORT}"
        API_VERSION = "3.3.0"
        SERVICE_NAME = "LLM Chat Service"
        CORS_ORIGINS = ["*"]
    config = ChatConfig()

# ============================================================================
# Port Configuration from .env
# ============================================================================

# Service ports
CHAT_SERVICE_PORT = int(os.getenv("CHAT_SERVICE_PORT", "9001"))
NCT_SERVICE_PORT = int(os.getenv("NCT_SERVICE_PORT", "9002"))
RUNNER_SERVICE_PORT = int(os.getenv("RUNNER_SERVICE_PORT", "9003"))
LLM_ASSISTANT_PORT = int(os.getenv("LLM_ASSISTANT_PORT", "9004"))

# Ollama configuration (also available via config object)
OLLAMA_HOST = os.getenv("ollama_host", "localhost")
OLLAMA_PORT = int(os.getenv("ollama_port", "11434"))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Output directory for generated CSVs (absolute path based on script location)
SCRIPT_DIR = Path(__file__).parent.resolve()
OUTPUT_DIR = SCRIPT_DIR / "output" / "annotations"

# LLM Assistant URL for metadata fetching
LLM_ASSISTANT_URL = os.getenv("LLM_ASSISTANT_URL", f"http://localhost:{LLM_ASSISTANT_PORT}")


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
    current_step: str = ""  # Current processing step (e.g., "fetching", "parsing", "llm", "csv")
    current_nct: str = ""   # Current NCT ID being processed
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    total_trials: int = 0
    processed_trials: int = 0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    csv_filename: Optional[str] = None
    original_filename: Optional[str] = None
    model: str = ""
    notification_email: Optional[str] = None  # Email to notify when job completes
    _task: Optional[asyncio.Task] = field(default=None, repr=False)  # Store task to prevent GC


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
                        output_file = OUTPUT_DIR / job.csv_filename
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
        
        # Calculate elapsed time
        elapsed_seconds = (datetime.now() - job.created_at).total_seconds()
        
        # Calculate progress percentage
        percent = 0
        if job.total_trials > 0:
            percent = round((job.processed_trials / job.total_trials) * 100)
        
        response = {
            "job_id": job.job_id,
            "status": job.status.value,
            "progress": job.progress,
            "current_step": job.current_step,
            "current_nct": job.current_nct,
            "total_trials": job.total_trials,
            "processed_trials": job.processed_trials,
            "percent_complete": percent,
            "elapsed_seconds": round(elapsed_seconds),
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
            "model": job.model,
            "original_filename": job.original_filename
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
    version="3.3.0",  # Bumped version for CSV metadata support
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
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    logger.info("✅ CSV Job Manager initialized")
    logger.info(f"✅ Output directory ready: {OUTPUT_DIR}")


# ============================================================================
# Configuration
# ============================================================================

RUNNER_SERVICE_URL = os.getenv("RUNNER_SERVICE_URL", f"http://localhost:{RUNNER_SERVICE_PORT}")


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
    output_format: str = Field(default="llm_optimized", description="Output format: 'json' or 'llm_optimized'")


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatResponse(BaseModel):
    conversation_id: str
    message: ChatMessage
    model: str
    annotation_mode: bool = False
    processing_time_seconds: Optional[float] = None
    download_url: Optional[str] = None
    csv_filename: Optional[str] = None


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


async def fetch_csv_metadata(model: str) -> Dict[str, Any]:
    """
    Fetch CSV metadata from LLM Assistant and NCT Service.

    Args:
        model: Model name to get version info for

    Returns:
        Dictionary with git_commit, model_version, service_version, enabled_apis, and model_parameters
    """
    metadata = {
        "git_commit": "unknown",
        "model_version": model,
        "service_version": "unknown",
        "enabled_apis": [],
        "available_apis": [],
        "model_parameters": {},
        "active_preset": None
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Fetch LLM Assistant metadata
        try:
            response = await client.get(
                f"{LLM_ASSISTANT_URL}/csv-header-info",
                params={"model_name": model}
            )
            if response.status_code == 200:
                data = response.json()
                metadata["git_commit"] = data.get("git_commit", "unknown")
                metadata["model_version"] = data.get("model_version", model)
                metadata["service_version"] = data.get("service_version", "unknown")
                logger.info(f"📋 Fetched LLM metadata: git={metadata['git_commit']}, model={metadata['model_version']}")
        except Exception as e:
            logger.warning(f"Could not fetch CSV metadata from LLM Assistant: {e}")

        # Fetch current model parameters from LLM Assistant
        try:
            response = await client.get(f"{LLM_ASSISTANT_URL}/model-parameters")
            if response.status_code == 200:
                params_data = response.json()
                metadata["model_parameters"] = params_data.get("current", {})
                metadata["active_preset"] = params_data.get("active_preset")
                logger.info(f"📋 Fetched model params: preset={metadata['active_preset']}")
        except Exception as e:
            logger.warning(f"Could not fetch model parameters from LLM Assistant: {e}")

        # Fetch NCT Service API registry
        try:
            nct_service_url = f"http://localhost:{NCT_SERVICE_PORT}"
            response = await client.get(f"{nct_service_url}/api/registry")
            if response.status_code == 200:
                registry = response.json()
                # Get default enabled APIs
                metadata["enabled_apis"] = registry.get("metadata", {}).get("default_enabled", [])
                # Get all available APIs (ones that have keys if needed)
                all_apis = []
                for category in ['core', 'extended']:
                    for api in registry.get(category, []):
                        if api.get('available', False):
                            all_apis.append(api.get('id', api.get('name', 'unknown')))
                metadata["available_apis"] = all_apis
                logger.info(f"📋 Fetched NCT APIs: {len(metadata['enabled_apis'])} enabled, {len(metadata['available_apis'])} available")
        except Exception as e:
            logger.warning(f"Could not fetch API registry from NCT Service: {e}")

    return metadata


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
    Processes each trial individually and updates progress in real-time.
    """
    logger.info(f"🚀 Job {job_id}: Background task STARTED")
    
    job = job_manager.jobs.get(job_id)
    if not job:
        logger.error(f"❌ Job {job_id}: Job not found in manager!")
        return
    
    job.status = JobStatus.PROCESSING
    job.progress = "Parsing CSV..."
    job.updated_at = datetime.now()
    
    start_time = time.time()
    results = []
    errors = []
    last_heartbeat = time.time()
    
    try:
        # Parse NCT IDs from CSV
        text_content = csv_content.decode('utf-8')
        nct_ids = extract_nct_ids_from_csv(text_content)
        
        if not nct_ids:
            raise Exception("No NCT IDs found in CSV file")
        
        job.total_trials = len(nct_ids)
        logger.info(f"📋 Job {job_id}: Found {len(nct_ids)} NCT IDs to process")
        
        # Check runner service health first
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                health = await client.get(f"{RUNNER_SERVICE_URL}/health", timeout=5.0)
                if health.status_code != 200:
                    raise Exception("Runner service not available")
            except httpx.ConnectError:
                raise Exception(f"Cannot connect to Runner Service at {RUNNER_SERVICE_URL}")
        
        job.progress = "Runner service connected, starting annotation..."
        job.updated_at = datetime.now()
        
        # Track consecutive failures for model reset
        consecutive_failures = 0
        
        # Create a persistent client for all requests (reduced timeout to 120s)
        async with httpx.AsyncClient(timeout=120.0) as client:
            # Process each NCT ID individually
            for i, nct_id in enumerate(nct_ids):
                job.processed_trials = i
                job.progress = f"Processing {i + 1}/{len(nct_ids)}: {nct_id}"
                job.updated_at = datetime.now()
                
                logger.info(f"📝 Job {job_id}: Processing {nct_id} ({i + 1}/{len(nct_ids)})")
                
                trial_start = time.time()
                max_retries = 3
                result_saved = False
                
                for attempt in range(max_retries):
                    try:
                        # Call batch-annotate with single NCT ID
                        response = await client.post(
                            f"{RUNNER_SERVICE_URL}/batch-annotate",
                            json={
                                "nct_ids": [nct_id],
                                "model": model,
                                "temperature": temperature,
                                "fetch_if_missing": True,
                                "output_format": "llm_optimized"  # Use optimized format for CSV batch
                            }
                        )
                        
                        if response.status_code == 200:
                            data = response.json()
                            trial_results = data.get("results", [])
                            
                            if trial_results:
                                result = trial_results[0]
                                result["processing_time"] = round(time.time() - trial_start, 1)
                                
                                # ALWAYS use the original nct_id, never trust LLM output
                                result["nct_id"] = nct_id
                                
                                # Log what we received from runner
                                logger.info(f"📦 Job {job_id}: Runner returned keys for {nct_id}: {list(result.keys())}")
                                
                                # Detect success: has annotation AND parsed_data with actual content
                                has_annotation = bool(result.get("annotation"))
                                has_error = bool(result.get("error"))
                                
                                # Check if parsed_data has actual useful content
                                parsed_data = result.get("parsed_data", {})
                                has_parsed_data = bool(parsed_data and len(parsed_data) > 3)  # Need at least a few fields
                                
                                # Also check for garbage responses (hallucinations)
                                annotation_text = str(result.get("annotation", ""))
                                is_garbage = (
                                    "# Instruction" in annotation_text or
                                    "# User:" in annotation_text or
                                    "### Solution" in annotation_text
                                )
                                
                                # Mark as success only if: has parsed_data, no error, and not garbage
                                is_success = has_parsed_data and not has_error and not is_garbage
                                
                                if is_success:
                                    result["_success"] = True
                                    results.append(result)
                                    result_saved = True
                                    consecutive_failures = 0  # Reset failure counter
                                    logger.info(f"✅ Job {job_id}: {nct_id} completed successfully (annotation length: {len(annotation_text)}, parsed fields: {len(parsed_data)})")
                                    break  # Success - exit retry loop
                                else:
                                    # Garbage or empty - retry if we have attempts left
                                    reason = "No annotation" if not has_annotation else \
                                             "Empty parsed_data" if not has_parsed_data else \
                                             "Garbage/hallucinated response" if is_garbage else \
                                             result.get("error", "Unknown error")
                                    
                                    if attempt < max_retries - 1:
                                        logger.warning(f"⚠️ Job {job_id}: {nct_id} got bad response ({reason}), retrying ({attempt + 1}/{max_retries})...")
                                        
                                        # If garbage, try to reset the model
                                        if is_garbage:
                                            logger.info(f"🔄 Job {job_id}: Attempting model reset after garbage response...")
                                            try:
                                                # Send a tiny request with keep_alive=0 to unload, then reload
                                                async with httpx.AsyncClient(timeout=30.0) as reset_client:
                                                    await reset_client.post(
                                                        f"{config.OLLAMA_BASE_URL}/api/generate",
                                                        json={
                                                            "model": model,
                                                            "prompt": "test",
                                                            "keep_alive": 0  # Unload after this
                                                        }
                                                    )
                                                    await asyncio.sleep(2)
                                                    # Reload by doing a fresh request
                                                    await reset_client.post(
                                                        f"{config.OLLAMA_BASE_URL}/api/generate",
                                                        json={
                                                            "model": model,
                                                            "prompt": "Hello",
                                                            "keep_alive": "5m"
                                                        }
                                                    )
                                                logger.info(f"✅ Job {job_id}: Model reset complete")
                                            except Exception as reset_err:
                                                logger.warning(f"⚠️ Job {job_id}: Model reset failed: {reset_err}")
                                        
                                        await asyncio.sleep(3)  # Longer wait after garbage
                                        continue
                                    else:
                                        # Last attempt failed - track consecutive failures
                                        consecutive_failures += 1
                                        
                                        result["_success"] = False
                                        results.append(result)
                                        result_saved = True
                                        errors.append({
                                            "nct_id": nct_id,
                                            "error": reason
                                        })
                                        logger.warning(f"⚠️ Job {job_id}: {nct_id} failed after {max_retries} attempts: {reason}")
                                        
                                        # If 3+ consecutive failures, do a hard model reset
                                        if consecutive_failures >= 3:
                                            logger.warning(f"🔄 Job {job_id}: {consecutive_failures} consecutive failures, doing hard model reset...")
                                            try:
                                                async with httpx.AsyncClient(timeout=60.0) as reset_client:
                                                    # Unload model completely
                                                    await reset_client.post(
                                                        f"{config.OLLAMA_BASE_URL}/api/generate",
                                                        json={"model": model, "prompt": "", "keep_alive": 0}
                                                    )
                                                    await asyncio.sleep(5)
                                                    # Reload fresh
                                                    await reset_client.post(
                                                        f"{config.OLLAMA_BASE_URL}/api/generate",
                                                        json={"model": model, "prompt": "Initialize", "keep_alive": "10m"}
                                                    )
                                                logger.info(f"✅ Job {job_id}: Hard model reset complete")
                                                consecutive_failures = 0
                                            except Exception as e:
                                                logger.error(f"❌ Job {job_id}: Hard reset failed: {e}")
                            else:
                                if attempt < max_retries - 1:
                                    logger.warning(f"⚠️ Job {job_id}: {nct_id} no results, retrying ({attempt + 1}/{max_retries})...")
                                    await asyncio.sleep(2)
                                    continue
                                errors.append({
                                    "nct_id": nct_id,
                                    "error": "No result returned from runner"
                                })
                                result_saved = True
                            break  # Exit retry loop
                            
                        else:
                            error_text = response.text[:200]
                            if attempt < max_retries - 1:
                                logger.warning(f"⚠️ Job {job_id}: {nct_id} HTTP {response.status_code}, retrying ({attempt + 1}/{max_retries})...")
                                await asyncio.sleep(2)  # Wait before retry
                                continue
                            errors.append({
                                "nct_id": nct_id,
                                "error": f"HTTP {response.status_code}: {error_text}"
                            })
                            logger.error(f"❌ Job {job_id}: {nct_id} HTTP error: {response.status_code}")
                            
                    except httpx.TimeoutException:
                        if attempt < max_retries - 1:
                            logger.warning(f"⚠️ Job {job_id}: {nct_id} timed out, retrying ({attempt + 1}/{max_retries})...")
                            await asyncio.sleep(2)
                            continue
                        errors.append({
                            "nct_id": nct_id,
                            "error": "Request timed out after retries"
                        })
                        logger.error(f"❌ Job {job_id}: {nct_id} timed out after {max_retries} attempts")
                        
                    except httpx.ConnectError as e:
                        if attempt < max_retries - 1:
                            logger.warning(f"⚠️ Job {job_id}: {nct_id} connection error, retrying ({attempt + 1}/{max_retries})...")
                            await asyncio.sleep(5)  # Longer wait for connection issues
                            continue
                        errors.append({
                            "nct_id": nct_id,
                            "error": f"Connection error: {str(e)}"
                        })
                        logger.error(f"❌ Job {job_id}: {nct_id} connection error after {max_retries} attempts: {e}")
                        
                    except Exception as e:
                        logger.error(f"❌ Job {job_id}: {nct_id} unexpected error: {e}", exc_info=True)
                        errors.append({
                            "nct_id": nct_id,
                            "error": str(e)
                        })
                        break  # Don't retry unexpected errors
                
                # Log progress every 10 trials
                if (i + 1) % 10 == 0:
                    elapsed = time.time() - start_time
                    avg_time = elapsed / (i + 1)
                    remaining = avg_time * (len(nct_ids) - i - 1)
                    logger.info(f"📊 Job {job_id}: Progress {i + 1}/{len(nct_ids)} ({(i+1)/len(nct_ids)*100:.1f}%) - ETA: {remaining/60:.1f} min")
                
                # Heartbeat every 30 seconds
                if time.time() - last_heartbeat > 30:
                    logger.info(f"💓 Job {job_id}: Still alive - processed {i}/{len(nct_ids)} trials")
                    last_heartbeat = time.time()
        
        logger.info(f"🏁 Job {job_id}: All trials processed, generating CSV...")
        
        # All trials processed
        job.processed_trials = len(nct_ids)
        job.progress = "Generating output CSV..."
        job.updated_at = datetime.now()
        
        # Calculate stats before CSV generation
        end_time = time.time()
        duration = end_time - start_time
        successful = len([r for r in results if r.get("_success", False)])
        failed = len(errors)

        # Generate output CSV
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        csv_filename = f"annotations_{job_id}.csv"
        output_path = OUTPUT_DIR / csv_filename

        # Fetch metadata from LLM Assistant and NCT Service
        metadata = await fetch_csv_metadata(model)

        await generate_output_csv(
            output_path,
            results,
            errors,
            model=model,
            git_commit=metadata.get("git_commit", "unknown"),
            model_version=metadata.get("model_version", model),
            total_processing_time=duration,
            temperature=temperature,
            enabled_apis=metadata.get("enabled_apis", []),
            available_apis=metadata.get("available_apis", []),
            output_format=output_format if 'output_format' in dir() else None,
            model_parameters=metadata.get("model_parameters", {}),
            active_preset=metadata.get("active_preset")
        )

        # Store result FIRST (before changing status to avoid race condition)
        public_download_url = f"/chat/download/{job_id}"
        
        job.result = {
            "total": len(nct_ids),
            "successful": successful,
            "failed": failed,
            "total_time_seconds": round(duration, 1),
            "errors": errors[:10],  # Limit errors in response
            "download_url": public_download_url,
            "_output_path": str(output_path),  # Internal use for download
            "csv_filename": csv_filename,
            "model": model
        }
        
        # NOW set status to completed (after result is ready)
        job.csv_filename = csv_filename
        job.status = JobStatus.COMPLETED
        job.progress = "Completed"
        job.updated_at = datetime.now()
        
        logger.info(f"✅ Job {job_id} completed: {successful} success, {failed} errors in {duration:.1f}s")
        logger.info(f"📊 Job {job_id} result object: total={job.result['total']}, successful={job.result['successful']}, failed={job.result['failed']}, time={job.result['total_time_seconds']}")

        # Send email notification if requested
        if job.notification_email:
            logger.info(f"📧 Sending completion email to {job.notification_email}")
            email_sent = send_annotation_complete_email(
                to_email=job.notification_email,
                job_id=job_id,
                original_filename=original_filename or "Unknown",
                total_trials=len(nct_ids),
                successful=successful,
                failed=failed,
                processing_time_seconds=duration,
                model=model
            )
            if email_sent:
                logger.info(f"📧 Email sent successfully to {job.notification_email}")
            else:
                logger.warning(f"📧 Failed to send email to {job.notification_email}")

        # Update conversation
        if conversation_id in conversations:
            conv = conversations[conversation_id]
            
            error_summary = ""
            if errors:
                error_lines = [f"  - {e.get('nct_id', 'unknown')}: {e.get('error', 'unknown error')}" for e in errors[:5]]
                if len(errors) > 5:
                    error_lines.append(f"  ... and {len(errors) - 5} more errors")
                error_summary = f"\n\nErrors:\n" + "\n".join(error_lines)
            
            response_content = f"""✅ CSV Annotation Complete
═══════════════════════════════════════════
📄 Input File: {original_filename}
📊 Total NCT IDs: {len(nct_ids)}
✓ Successful: {successful}
✗ Failed: {failed}
⏱ Processing Time: {round(duration, 1)}s
═══════════════════════════════════════════
{error_summary}
📥 Your annotated CSV is ready for download."""
            
            conv["messages"].append({
                "role": "assistant",
                "content": response_content
            })
        
    except Exception as e:
        logger.error(f"❌ Job {job_id} failed: {e}", exc_info=True)
        job.status = JobStatus.FAILED
        job.error = str(e)
        job.progress = "Failed"
        job.updated_at = datetime.now()

        # Send failure email notification if requested
        if job.notification_email:
            logger.info(f"📧 Sending failure email to {job.notification_email}")
            send_annotation_failed_email(
                to_email=job.notification_email,
                job_id=job_id,
                original_filename=job.original_filename or "Unknown",
                error_message=str(e)
            )


def clean_value(value):
    """Strip markdown formatting from LLM output values."""
    if not isinstance(value, str):
        return value
    # Remove leading ** or * 
    value = value.lstrip('*').strip()
    # Remove trailing **
    value = value.rstrip('*').strip()
    return value
    
async def generate_output_csv(
    output_path: Path,
    results: List[dict],
    errors: List[dict],
    model: str = "unknown",
    git_commit: str = "unknown",
    model_version: str = None,
    total_processing_time: float = None,
    temperature: float = None,
    enabled_apis: List[str] = None,
    available_apis: List[str] = None,
    output_format: str = None,
    model_parameters: Dict[str, Any] = None,
    active_preset: str = None
):
    """Generate the annotated CSV output file with comprehensive metadata header."""

    # Use model_version if provided, otherwise fall back to model name
    model_display = model_version if model_version else model

    # Log what we're working with
    if results:
        logger.info(f"📝 CSV Generation: First result keys: {list(results[0].keys())}")
        if "parsed_data" in results[0]:
            logger.info(f"📝 Parsed data keys: {list(results[0]['parsed_data'].keys())}")

    # Count successes and failures
    successful_count = len([r for r in results if r.get("_success", False)])
    failed_count = len(errors)
    total_count = len(results)  # Total processed (success + failure are in results)

    # Calculate per-trial processing times
    trial_times = [r.get("processing_time_seconds", 0) for r in results if r.get("processing_time_seconds")]
    avg_time_per_trial = sum(trial_times) / len(trial_times) if trial_times else 0

    # Define columns matching the parsed_data structure
    columns = [
        "nct_id", "status",
        "Study Title", "Study Status", "Brief Summary", "Conditions",
        "Interventions/Drug", "Phases", "Enrollment", "Start Date", "Completion Date",
        "Classification", "Classification Evidence",
        "Delivery Mode", "Delivery Mode Evidence",
        "Outcome", "Outcome Evidence",
        "Reason for Failure", "Reason for Failure Evidence",
        "Peptide", "Peptide Evidence",
        "Sequence", "DRAMP Name", "Study IDs", "Comments",
        "annotation", "source", "processing_time", "error"
    ]

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        # Write comprehensive metadata header
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"# ═══════════════════════════════════════════════════════════════════\n")
        f.write(f"# AMP LLM ANNOTATION RESULTS\n")
        f.write(f"# ═══════════════════════════════════════════════════════════════════\n")
        f.write(f"#\n")
        f.write(f"# GENERATION INFO\n")
        f.write(f"# Timestamp: {timestamp}\n")
        f.write(f"# Git Commit: {git_commit}\n")
        f.write(f"#\n")
        f.write(f"# MODEL CONFIGURATION\n")
        f.write(f"# Model: {model_display}\n")
        if active_preset:
            f.write(f"# Preset: {active_preset}\n")
        if temperature is not None:
            f.write(f"# Temperature: {temperature}\n")
        # Write additional model parameters if provided
        if model_parameters:
            for param, value in model_parameters.items():
                # Skip temperature since we already wrote it above
                if param != "temperature" and value is not None:
                    f.write(f"# {param}: {value}\n")
        if output_format:
            f.write(f"# Data Format: {output_format}\n")
        f.write(f"#\n")
        f.write(f"# PROCESSING STATISTICS\n")
        f.write(f"# Total Trials: {total_count}\n")
        f.write(f"# Successful: {successful_count}\n")
        f.write(f"# Failed: {failed_count}\n")
        if total_processing_time is not None:
            f.write(f"# Total Processing Time: {total_processing_time:.1f}s\n")
            if total_count > 0:
                f.write(f"# Avg Time Per Trial: {total_processing_time / total_count:.1f}s\n")
        f.write(f"#\n")
        f.write(f"# DATA SOURCES (NCT Lookup APIs)\n")
        if enabled_apis:
            f.write(f"# Enabled APIs: {', '.join(enabled_apis)}\n")
        if available_apis:
            f.write(f"# Available APIs: {', '.join(available_apis)}\n")
        f.write(f"#\n")
        f.write(f"# ═══════════════════════════════════════════════════════════════════\n")
        f.write(f"#\n")
        
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        
        # Write only SUCCESSFUL results (ones with actual data)
        for result in results:
            # Skip failed results - they'll be written in the errors section
            if not result.get("_success", False):
                continue
                
            row = {
                "nct_id": result.get("nct_id", ""),
                "status": "success",
                "processing_time": result.get("processing_time", ""),
                "source": result.get("source", ""),
                "error": ""
            }
            
            # Get the full annotation text
            annotation = result.get("annotation", "")
            if isinstance(annotation, str):
                row["annotation"] = annotation
            
            # Extract from parsed_data (this is where the structured fields are!)
            parsed_data = result.get("parsed_data", {})
            if parsed_data:
                for key, value in parsed_data.items():
                    value = clean_value(value)
                    # NEVER overwrite nct_id from LLM - it may hallucinate
                    if key == "NCT ID" or key == "nct_id":
                        continue  # Skip - use the original nct_id from result
                    # Map parsed_data keys to our columns
                    elif key in columns:
                        row[key] = value
                    elif key == "Interventions/Drug" or key == "Drug":
                        row["Interventions/Drug"] = value
                    elif key == "Phases" or key == "Phase":
                        row["Phases"] = value
                    elif key == "Study ID" or key == "Study IDs":
                        row["Study IDs"] = value
                    elif key == "Sequence Evidence":
                        row["Sequence"] = value
                    # Store Evidence fields
                    elif "Evidence" in key:
                        row[key] = value
            
            writer.writerow(row)
        
        # Write errors
        for error in errors:
            writer.writerow({
                "nct_id": error.get("nct_id", ""),
                "status": "error",
                "error": error.get("error", "Unknown error")
            })
    
    logger.info(f"💾 CSV saved: {output_path} ({len(results)} results, {len(errors)} errors)")


async def annotate_trials_via_runner(
    nct_ids: List[str],
    model: str,
    temperature: float,
    output_format: str = "llm_optimized"
) -> tuple[str, AnnotationSummary, List[dict]]:
    """
    Annotate trials using the Runner Service's batch-annotate endpoint.

    The Runner Service coordinates:
    1. Fetching trial data (from cache or NCT Service)
    2. Sending to LLM Assistant for annotation

    Args:
        nct_ids: List of NCT IDs to annotate
        model: LLM model to use
        temperature: Temperature for LLM generation
        output_format: 'json' or 'llm_optimized' - format of data sent to LLM

    Returns:
        Tuple of (formatted_annotation_text, summary, raw_results)
    """
    logger.info(f"🔬 Annotating {len(nct_ids)} trials with {model} via Runner Service (format: {output_format})")
    
    try:
        async with httpx.AsyncClient(timeout=600.0) as client:  # 10 min timeout for batch
            # Check runner service
            try:
                health = await client.get(f"{RUNNER_SERVICE_URL}/health", timeout=5.0)
                if health.status_code != 200:
                    return (
                        "❌ Runner Service not available. Please ensure it's running on port 8003.",
                        AnnotationSummary(total=len(nct_ids), successful=0, failed=len(nct_ids), processing_time_seconds=0),
                        []
                    )
            except httpx.ConnectError:
                return (
                    f"❌ Cannot connect to Runner Service at {RUNNER_SERVICE_URL}.\n\n"
                    "Please start the service:\n"
                    "  cd standalone_modules/runner\n"
                    "  uvicorn runner_service:app --port 8003 --reload",
                    AnnotationSummary(total=len(nct_ids), successful=0, failed=len(nct_ids), processing_time_seconds=0),
                    []
                )
            
            # Send batch annotation request
            logger.info(f"📤 Sending batch annotation request to Runner Service")
            
            response = await client.post(
                f"{RUNNER_SERVICE_URL}/batch-annotate",
                json={
                    "nct_ids": nct_ids,
                    "model": model,
                    "temperature": temperature,
                    "fetch_if_missing": True,
                    "output_format": output_format  # 'json' or 'llm_optimized'
                }
            )
            
            if response.status_code != 200:
                error_text = response.text
                logger.error(f"❌ Runner Service error: {error_text}")
                return (
                    f"❌ Annotation failed: {error_text[:500]}",
                    AnnotationSummary(total=len(nct_ids), successful=0, failed=len(nct_ids), processing_time_seconds=0),
                    []
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
            
            return formatted_output, summary, results
            
    except httpx.TimeoutException:
        logger.error("❌ Annotation request timed out")
        return (
            "❌ Annotation timed out. Try fewer trials or a faster model.",
            AnnotationSummary(total=len(nct_ids), successful=0, failed=len(nct_ids), processing_time_seconds=0),
            []
        )
    except Exception as e:
        logger.error(f"❌ Annotation error: {e}", exc_info=True)
        return (
            f"❌ Annotation error: {str(e)}",
            AnnotationSummary(total=len(nct_ids), successful=0, failed=len(nct_ids), processing_time_seconds=0),
            []
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
        annotation_result, summary, raw_results = await annotate_trials_via_runner(
            request.nct_ids,
            conv["model"],
            request.temperature,
            output_format=request.output_format
        )
        
        # Generate CSV for download if we have results
        download_url = None
        csv_filename = None
        if raw_results and summary.successful > 0:
            job_id = str(uuid.uuid4())
            csv_filename = f"annotations_{job_id}.csv"
            output_path = OUTPUT_DIR / csv_filename
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            
            # Mark successful results so CSV generation includes them
            for result in raw_results:
                if result.get("status") == "success" and result.get("parsed_data"):
                    result["_success"] = True
            
            # Fetch metadata from LLM Assistant and NCT Service
            metadata = await fetch_csv_metadata(conv["model"])

            await generate_output_csv(
                output_path,
                raw_results,
                [],
                model=conv["model"],
                git_commit=metadata.get("git_commit", "unknown"),
                model_version=metadata.get("model_version", conv["model"]),
                total_processing_time=summary.processing_time_seconds,
                temperature=request.temperature,
                enabled_apis=metadata.get("enabled_apis", []),
                available_apis=metadata.get("available_apis", []),
                output_format=request.output_format,
                model_parameters=metadata.get("model_parameters", {}),
                active_preset=metadata.get("active_preset")
            )
            download_url = f"/chat/download/{job_id}"
            
            # Store in job manager so download works
            job = AnnotationJob(
                job_id=job_id,
                status=JobStatus.COMPLETED,
                total_trials=len(request.nct_ids),
                processed_trials=len(request.nct_ids),
                csv_filename=csv_filename,
                model=conv["model"]
            )
            job.result = {
                "csv_filename": csv_filename,
                "_output_path": str(output_path)
            }
            job_manager.jobs[job_id] = job
            logger.info(f"📄 Generated CSV for single annotation: {csv_filename}")
        
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
            processing_time_seconds=round(processing_time, 2),
            download_url=download_url,
            csv_filename=csv_filename
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
# Async Annotation Routes (fixes Cloudflare 524 timeout)
# ============================================================================

class ManualAnnotationRequest(BaseModel):
    """Request for manual NCT ID annotation"""
    conversation_id: str
    nct_ids: List[str]
    temperature: float = 0.15
    output_format: str = "llm_optimized"
    notification_email: Optional[str] = None


async def process_manual_annotation_job(
    job_id: str,
    nct_ids: List[str],
    model: str,
    temperature: float,
    output_format: str,
    conversation_id: str
):
    """Background task to process manual NCT annotation."""
    job = job_manager.jobs.get(job_id)
    if not job:
        logger.error(f"❌ Job {job_id} not found")
        return

    try:
        job.status = JobStatus.PROCESSING
        job.progress = f"Starting annotation of {len(nct_ids)} trial(s)..."
        job.current_step = "initializing"
        job.updated_at = datetime.now()

        start_time = time.time()
        results = []
        errors = []

        # Process each NCT ID
        async with httpx.AsyncClient(timeout=300.0) as client:
            for i, nct_id in enumerate(nct_ids):
                job.processed_trials = i
                job.current_nct = nct_id
                job.updated_at = datetime.now()

                # Step 1: Fetching data
                job.current_step = "fetching"
                job.progress = f"[{i + 1}/{len(nct_ids)}] Fetching data for {nct_id}..."
                job.updated_at = datetime.now()
                logger.info(f"📥 Job {job_id}: Fetching {nct_id}")

                try:
                    # Step 2: Processing (this call does fetch + parse + LLM internally)
                    job.current_step = "processing"
                    job.progress = f"[{i + 1}/{len(nct_ids)}] Processing {nct_id} (fetch → parse → LLM)..."
                    job.updated_at = datetime.now()

                    response = await client.post(
                        f"{RUNNER_SERVICE_URL}/annotate",
                        json={
                            "nct_id": nct_id,
                            "model": model,
                            "temperature": temperature,
                            "fetch_if_missing": True,
                            "output_format": output_format
                        },
                        timeout=180.0
                    )

                    if response.status_code == 200:
                        result = response.json()
                        result["_success"] = result.get("status") == "success"
                        results.append(result)

                        # Update progress to show completion
                        job.current_step = "completed"
                        job.progress = f"[{i + 1}/{len(nct_ids)}] ✓ {nct_id} annotated successfully"
                        job.updated_at = datetime.now()
                        logger.info(f"✅ Job {job_id}: {nct_id} annotated successfully")
                    else:
                        errors.append({
                            "nct_id": nct_id,
                            "error": f"HTTP {response.status_code}: {response.text[:200]}"
                        })
                        job.progress = f"[{i + 1}/{len(nct_ids)}] ✗ {nct_id} failed"
                        logger.error(f"❌ Job {job_id}: {nct_id} failed with HTTP {response.status_code}")

                except Exception as e:
                    errors.append({"nct_id": nct_id, "error": str(e)})
                    job.progress = f"[{i + 1}/{len(nct_ids)}] ✗ {nct_id} error: {str(e)[:50]}"
                    logger.error(f"❌ Job {job_id}: {nct_id} error: {e}")

        # Calculate stats before CSV generation
        end_time = time.time()
        duration = end_time - start_time
        successful = len([r for r in results if r.get("_success", False)])
        failed = len(errors)

        # Generate CSV output
        job.current_step = "generating_csv"
        job.current_nct = ""
        job.progress = "Generating output CSV..."
        job.updated_at = datetime.now()

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        csv_filename = f"annotations_{job_id}.csv"
        output_path = OUTPUT_DIR / csv_filename

        metadata = await fetch_csv_metadata(model)
        await generate_output_csv(
            output_path,
            results,
            errors,
            model=model,
            git_commit=metadata.get("git_commit", "unknown"),
            model_version=metadata.get("model_version", model),
            total_processing_time=duration,
            temperature=temperature,
            enabled_apis=metadata.get("enabled_apis", []),
            available_apis=metadata.get("available_apis", []),
            output_format=output_format,
            model_parameters=metadata.get("model_parameters", {}),
            active_preset=metadata.get("active_preset")
        )

        # Build formatted annotation text
        output_parts = []
        for result in results:
            nct_id = result.get("nct_id")
            annotation = result.get("annotation", "")
            if result.get("_success"):
                output_parts.append(f"\n{'='*60}")
                output_parts.append(f"NCT ID: {nct_id}")
                output_parts.append(f"{'='*60}\n")
                output_parts.append(annotation)

        # Store result
        job.csv_filename = csv_filename
        job.result = {
            "total": len(nct_ids),
            "successful": successful,
            "failed": failed,
            "total_time_seconds": round(duration, 1),
            "errors": errors[:10],
            "download_url": f"/chat/download/{job_id}",
            "_output_path": str(output_path),
            "csv_filename": csv_filename,
            "model": model,
            "annotation_text": "\n".join(output_parts)
        }

        job.status = JobStatus.COMPLETED
        job.progress = "Completed"
        job.processed_trials = len(nct_ids)
        job.updated_at = datetime.now()

        logger.info(f"✅ Job {job_id} completed: {successful} success, {failed} errors in {duration:.1f}s")

        # Send email notification if requested
        if job.notification_email:
            logger.info(f"📧 Sending completion email to {job.notification_email}")
            send_annotation_complete_email(
                to_email=job.notification_email,
                job_id=job_id,
                original_filename=job.original_filename or f"{len(nct_ids)} NCT IDs",
                total_trials=len(nct_ids),
                successful=successful,
                failed=failed,
                processing_time_seconds=duration,
                model=model
            )

        # Update conversation
        if conversation_id in conversations:
            conv = conversations[conversation_id]
            response_content = f"""✅ Annotation Complete
═══════════════════════════════════════════
📊 Total NCT IDs: {len(nct_ids)}
✓ Successful: {successful}
✗ Failed: {failed}
⏱ Processing Time: {round(duration, 1)}s
═══════════════════════════════════════════

📥 Your annotated CSV is ready for download."""

            conv["messages"].append({
                "role": "assistant",
                "content": response_content
            })

    except Exception as e:
        logger.error(f"❌ Job {job_id} failed: {e}", exc_info=True)
        job.status = JobStatus.FAILED
        job.error = str(e)
        job.progress = "Failed"
        job.updated_at = datetime.now()

        if job.notification_email:
            send_annotation_failed_email(
                to_email=job.notification_email,
                job_id=job_id,
                original_filename=job.original_filename or "Manual annotation",
                error_message=str(e)
            )


@app.post("/chat/annotate")
async def annotate_manual(request: ManualAnnotationRequest):
    """
    Start async annotation for manually entered NCT IDs.

    Returns immediately with a job_id.
    Frontend should poll /chat/annotate-csv-status/{job_id} for progress.
    """
    if request.conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if not request.nct_ids:
        raise HTTPException(status_code=400, detail="No NCT IDs provided")

    conv = conversations[request.conversation_id]
    model = conv.get("model", "unknown")

    logger.info(f"📝 Starting async annotation for {len(request.nct_ids)} NCT IDs")

    # Add user message
    user_message = f"Annotate trials: {', '.join(request.nct_ids)}"
    conv["messages"].append({
        "role": "user",
        "content": user_message
    })

    # Create job
    job_id = str(uuid.uuid4())
    job = AnnotationJob(
        job_id=job_id,
        status=JobStatus.PENDING,
        total_trials=len(request.nct_ids),
        progress=f"Starting annotation of {len(request.nct_ids)} trial(s)...",
        original_filename=f"Manual: {', '.join(request.nct_ids[:3])}{'...' if len(request.nct_ids) > 3 else ''}",
        model=model,
        notification_email=request.notification_email
    )
    job_manager.jobs[job_id] = job

    if request.notification_email:
        logger.info(f"📧 Job {job_id} will notify {request.notification_email} on completion")

    # Start background processing
    task = asyncio.create_task(
        process_manual_annotation_job(
            job_id=job_id,
            nct_ids=request.nct_ids,
            model=model,
            temperature=request.temperature,
            output_format=request.output_format,
            conversation_id=request.conversation_id
        )
    )
    job._task = task

    def handle_task_error(t):
        if t.cancelled():
            logger.warning(f"⚠️ Job {job_id} was cancelled")
        elif t.exception():
            logger.error(f"❌ Job {job_id} raised exception: {t.exception()}")

    task.add_done_callback(handle_task_error)

    logger.info(f"📋 Created manual annotation job {job_id} for {len(request.nct_ids)} NCT IDs")

    return {
        "job_id": job_id,
        "message": f"Job started for {len(request.nct_ids)} NCT IDs",
        "total": len(request.nct_ids),
        "status": "processing",
        "poll_url": f"/chat/annotate-csv-status/{job_id}"
    }


@app.post("/chat/annotate-csv")
async def annotate_csv(
    conversation_id: str = Query(...),
    model: str = Query(...),
    temperature: float = Query(0.15),
    notification_email: Optional[str] = Query(None, description="Email to notify when job completes"),
    file: UploadFile = File(...)
):
    """
    Upload a CSV file with NCT IDs and generate annotations.

    NOW ASYNC: Returns immediately with a job_id.
    Frontend should poll /chat/annotate-csv-status/{job_id} for progress.

    The input CSV can have NCT IDs in any column - they will be automatically detected.

    Optional: Provide notification_email to receive an email when the job completes.
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
            model=model,
            notification_email=notification_email
        )
        job_manager.jobs[job_id] = job

        if notification_email:
            logger.info(f"📧 Job {job_id} will notify {notification_email} on completion")
        
        # Start background processing - store task to prevent garbage collection
        task = asyncio.create_task(
            process_csv_job(
                job_id=job_id,
                csv_content=contents,
                original_filename=file.filename,
                model=model,
                temperature=temperature,
                conversation_id=conversation_id
            )
        )
        job._task = task  # Keep reference to prevent GC
        
        # Add error handler to log any uncaught exceptions
        def handle_task_error(t):
            if t.cancelled():
                logger.warning(f"⚠️ Job {job_id} was cancelled")
            elif t.exception():
                logger.error(f"❌ Job {job_id} raised exception: {t.exception()}")
        
        task.add_done_callback(handle_task_error)
        
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
    
    # Return with no-cache headers to prevent Cloudflare caching
    return JSONResponse(
        content=status,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


@app.get("/chat/download/{job_id}")
async def download_annotation_results(job_id: str):
    """
    Download the annotated CSV for a completed job.
    
    Serves the locally generated CSV file.
    """
    status = job_manager.get_job_status(job_id)
    
    if status["status"] == "not_found":
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    if status["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Job not completed. Current status: {status['status']}"
        )
    
    # Get the local file path
    result = status.get("result", {})
    csv_filename = result.get("csv_filename", f"annotations_{job_id}.csv")
    
    # Try stored path first
    stored_path = result.get("_output_path", "")
    if stored_path:
        output_path = Path(stored_path)
        if output_path.exists():
            logger.info(f"📥 Serving download for job {job_id}: {output_path}")
            return FileResponse(
                path=str(output_path),
                media_type="text/csv",
                filename=csv_filename,
                headers={
                    "Content-Disposition": f"attachment; filename=\"{csv_filename}\""
                }
            )
    
    # Fallback: try relative to script directory
    output_path = OUTPUT_DIR / csv_filename
    
    if not output_path.exists():
        # Last resort: try current working directory
        output_path = Path("output/annotations") / csv_filename
    
    if not output_path.exists():
        logger.error(f"❌ File not found for job {job_id}. Tried: {stored_path}, {OUTPUT_DIR / csv_filename}")
        raise HTTPException(status_code=404, detail=f"Output file not found: {csv_filename}")
    
    logger.info(f"📥 Serving download for job {job_id}: {output_path}")
    
    return FileResponse(
        path=str(output_path),
        media_type="text/csv",
        filename=csv_filename,
        headers={
            "Content-Disposition": f"attachment; filename=\"{csv_filename}\""
        }
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


@app.get("/chat/email-config")
async def get_email_config():
    """Check if email notifications are configured."""
    return {
        "configured": is_email_configured(),
        "from_address": os.getenv("SMTP_FROM", "luke@amphoraxe.ca") if is_email_configured() else None
    }


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
        "version": "3.3.0",
        "status": "running",
        "architecture": "modular",
        "features": {
            "chat": "enabled",
            "annotation": "enabled (via Runner Service)",
            "async_csv": "enabled (no more Cloudflare 524 timeouts!)",
            "csv_metadata": "enabled (git commit + model version in headers)"
        },
        "endpoints": {
            "chat": "/chat/*",
            "csv_annotation": "/chat/annotate-csv (async)",
            "csv_status": "/chat/annotate-csv-status/{job_id}",
            "docs": "/docs"
        },
        "dependencies": {
            "ollama": config.OLLAMA_BASE_URL,
            "runner_service": RUNNER_SERVICE_URL,
            "llm_assistant": LLM_ASSISTANT_URL
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
    
    # Check LLM Assistant service
    llm_assistant_connected = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{LLM_ASSISTANT_URL}/health")
            if response.status_code == 200:
                llm_assistant_connected = True
    except:
        pass
    
    # Count active jobs
    active_jobs = len([j for j in job_manager.jobs.values() 
                       if j.status in [JobStatus.PENDING, JobStatus.PROCESSING]])
    
    return {
        "status": "healthy",
        "service": config.SERVICE_NAME,
        "version": "3.3.0",
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
        "llm_assistant": {
            "url": LLM_ASSISTANT_URL,
            "connected": llm_assistant_connected
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
# Model Parameters Proxy Endpoints (proxied to LLM Assistant)
# ============================================================================

@app.get("/api/chat/model-parameters")
async def get_model_parameters():
    """
    Get current model parameters with documentation.
    Proxied to LLM Assistant service.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{LLM_ASSISTANT_URL}/model-parameters")
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"LLM Assistant error: {response.text}"
                )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to LLM Assistant at {LLM_ASSISTANT_URL}"
        )


@app.post("/api/chat/model-parameters")
async def set_model_parameters(request: dict):
    """
    Update model parameters.
    Proxied to LLM Assistant service.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{LLM_ASSISTANT_URL}/model-parameters",
                json=request
            )
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"LLM Assistant error: {response.text}"
                )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to LLM Assistant at {LLM_ASSISTANT_URL}"
        )


@app.post("/api/chat/model-parameters/reset")
async def reset_model_parameters():
    """
    Reset model parameters to defaults.
    Proxied to LLM Assistant service.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{LLM_ASSISTANT_URL}/model-parameters/reset")
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"LLM Assistant error: {response.text}"
                )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to LLM Assistant at {LLM_ASSISTANT_URL}"
        )


@app.post("/api/chat/model-parameters/preset/{preset_name}")
async def apply_model_preset(preset_name: str):
    """
    Apply a parameter preset.
    Proxied to LLM Assistant service.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{LLM_ASSISTANT_URL}/model-parameters/preset/{preset_name}"
            )
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"LLM Assistant error: {response.text}"
                )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to LLM Assistant at {LLM_ASSISTANT_URL}"
        )


@app.get("/api/chat/model-parameters/presets")
async def get_model_presets():
    """
    Get available parameter presets.
    Proxied to LLM Assistant service.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{LLM_ASSISTANT_URL}/model-parameters/presets")
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"LLM Assistant error: {response.text}"
                )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to LLM Assistant at {LLM_ASSISTANT_URL}"
        )


# ============================================================================
# Run standalone
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    print("=" * 80)
    print(f"🚀 Starting LLM Chat Service with Annotation on port {CHAT_SERVICE_PORT}...")
    print("=" * 80)
    print(f"🤖 Ollama: {config.OLLAMA_BASE_URL}")
    print(f"📁 Runner Service: {RUNNER_SERVICE_URL}")
    print(f"🔬 LLM Assistant: {LLM_ASSISTANT_URL}")
    print(f"📚 Docs: http://localhost:{CHAT_SERVICE_PORT}/docs")
    print("=" * 80)
    print("\n📋 Service Dependencies (from .env):")
    print(f"  - Runner Service ({RUNNER_SERVICE_PORT}) - Data fetching & annotation orchestration")
    print(f"  - LLM Assistant ({LLM_ASSISTANT_PORT}) - JSON parsing & prompt generation")
    print(f"  - NCT Service ({NCT_SERVICE_PORT}) - Clinical trials data")
    print(f"  - Ollama ({OLLAMA_PORT}) - LLM inference")
    print("=" * 80)
    print("\n✨ NEW: Async CSV processing enabled!")
    print("   CSV uploads now return immediately with a job_id.")
    print("   No more Cloudflare 524 timeout errors!")
    print("\n✨ NEW: CSV headers now include git commit and full model version!")
    print("\n✨ NEW: All ports now loaded from .env file!")
    print("=" * 80)
    uvicorn.run(app, host="0.0.0.0", port=CHAT_SERVICE_PORT, reload=True)
