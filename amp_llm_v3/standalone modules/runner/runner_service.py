"""
Runner Service (Port 9003) - Enhanced with Annotation Support
==============================================================

File manager and data fetcher for NCT trial data with integrated annotation.

Endpoints:
- GET /get-data - Get NCT data (from file or fetch)
- POST /batch-get-data - Get multiple NCT trials
- POST /annotate - Annotate a single trial (calls LLM Assistant API)
- POST /batch-annotate - Annotate multiple trials
- GET /files - List available JSON files
- GET /health - Health check with service dependencies

Service Dependencies:
- NCT Service (9002) - Fetches trial data from ClinicalTrials.gov
- LLM Assistant API (9004) - Handles annotation with JSON parsing
"""
import logging
import httpx
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import time

# Setup logging with detail
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# Initialize FastAPI app
# ============================================================================

app = FastAPI(
    title="Runner Service",
    description="File manager, NCT data fetcher, and annotation orchestrator",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Configuration
# ============================================================================

NCT_SERVICE_URL = "http://localhost:9002"
LLM_ASSISTANT_URL = "http://localhost:9004"
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

logger.info(f"📁 Results directory: {RESULTS_DIR}")
logger.info(f"🔗 NCT Service URL: {NCT_SERVICE_URL}")
logger.info(f"🤖 LLM Assistant URL: {LLM_ASSISTANT_URL}")


# ============================================================================
# Models
# ============================================================================

class DataRequest(BaseModel):
    nct_id: str


class BatchDataRequest(BaseModel):
    nct_ids: List[str]


class DataResponse(BaseModel):
    nct_id: str
    status: str
    data: dict
    source: str  # "file" or "fetched"
    file_path: Optional[str] = None
    error: Optional[str] = None


class BatchDataResponse(BaseModel):
    results: List[DataResponse]
    total: int
    successful: int
    failed: int


class AnnotationRequest(BaseModel):
    """Request for annotating a single trial"""
    nct_id: str
    model: str = "llama3.2"
    temperature: float = Field(default=0.15, ge=0.0, le=2.0)
    fetch_if_missing: bool = True  # Automatically fetch if not in cache


class BatchAnnotationRequest(BaseModel):
    """Request for annotating multiple trials"""
    nct_ids: List[str]
    model: str = "llama3.2"
    temperature: float = Field(default=0.15, ge=0.0, le=2.0)
    fetch_if_missing: bool = True


class AnnotationResult(BaseModel):
    """Result of a single annotation"""
    nct_id: str
    annotation: str
    model: str
    status: str
    source: str  # "file" or "fetched"
    processing_time_seconds: float
    sources_summary: Dict[str, Any] = {}
    error: Optional[str] = None


class BatchAnnotationResponse(BaseModel):
    """Response for batch annotation"""
    results: List[AnnotationResult]
    total: int
    successful: int
    failed: int
    total_time_seconds: float


# ============================================================================
# Helper Functions - Data Fetching
# ============================================================================

def find_nct_file(nct_id: str) -> tuple[Optional[Path], Optional[dict]]:
    """
    Find existing JSON file for NCT ID.
    Returns (file_path, data) or (None, None) if not found.
    """
    nct_id = nct_id.strip().upper()
    
    logger.info(f"🔍 Looking for file for {nct_id} in {RESULTS_DIR}")
    
    # Look for exact match first
    exact_file = RESULTS_DIR / f"{nct_id}.json"
    if exact_file.exists():
        logger.info(f"📄 Found existing file: {exact_file.name}")
        try:
            with open(exact_file, 'r') as f:
                data = json.load(f)
                logger.info(f"✅ Successfully loaded {exact_file.name}")
                return exact_file, data
        except Exception as e:
            logger.error(f"❌ Error reading {exact_file}: {e}")
            return None, None
    
    # Look for versioned files (e.g., NCT12345678_v1.json)
    import glob
    pattern = str(RESULTS_DIR / f"{nct_id}_v*.json")
    files = sorted(glob.glob(pattern), reverse=True)
    
    if files:
        file_path = Path(files[0])
        logger.info(f"📄 Found versioned file: {file_path.name}")
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                logger.info(f"✅ Successfully loaded {file_path.name}")
                return file_path, data
        except Exception as e:
            logger.error(f"❌ Error reading {file_path}: {e}")
            return None, None
    
    logger.info(f"📂 No file found for {nct_id}")
    return None, None


async def fetch_and_save_nct_data(nct_id: str) -> tuple[Optional[dict], Optional[str]]:
    """
    Fetch NCT data from service (9002) and save to JSON file.
    Returns (data, error_message) tuple.
    """
    nct_id = nct_id.strip().upper()
    logger.info(f"📡 Fetching data for {nct_id} from NCT service at {NCT_SERVICE_URL}")
    
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            # Step 1: Check if NCT service is alive
            try:
                health_response = await client.get(f"{NCT_SERVICE_URL}/health", timeout=5.0)
                if health_response.status_code != 200:
                    error_msg = f"NCT service health check failed: {health_response.status_code}"
                    logger.error(f"❌ {error_msg}")
                    return None, error_msg
                logger.info("✅ NCT service is healthy")
            except Exception as e:
                error_msg = f"Cannot connect to NCT service: {e}"
                logger.error(f"❌ {error_msg}")
                return None, error_msg
            
            # Step 2: Initiate search
            search_url = f"{NCT_SERVICE_URL}/api/search/{nct_id}"
            logger.info(f"📤 POST {search_url}")
            
            try:
                response = await client.post(
                    search_url,
                    json={"include_extended": False},
                    timeout=30.0
                )
                
                logger.info(f"📥 Response status: {response.status_code}")
                
                if response.status_code != 200:
                    error_text = response.text
                    logger.error(f"❌ Search initiation failed: {response.status_code}")
                    return None, f"NCT service returned {response.status_code}: {error_text[:200]}"
                
                data = response.json()
                job_id = data.get("job_id")
                
                if not job_id:
                    logger.error("❌ No job_id in response")
                    return None, "No job_id returned from NCT search"
                
                logger.info(f"✅ Search initiated with job_id: {job_id}")
                
            except httpx.TimeoutException:
                return None, "Timeout initiating search (30s)"
            except Exception as e:
                return None, f"Error initiating search: {e}"
            
            # Step 3: Poll for results
            import asyncio
            max_attempts = 30
            poll_interval = 2
            
            logger.info(f"⏳ Polling for results (max {max_attempts} attempts)")
            
            for attempt in range(max_attempts):
                await asyncio.sleep(poll_interval)
                
                status_url = f"{NCT_SERVICE_URL}/api/search/{job_id}/status"
                
                try:
                    status_response = await client.get(status_url, timeout=10.0)
                    
                    if status_response.status_code != 200:
                        continue
                    
                    status_data = status_response.json()
                    status = status_data.get("status")
                    
                    logger.info(f"📊 Status: {status} (attempt {attempt + 1})")
                    
                    if status == "completed":
                        # Get results
                        results_url = f"{NCT_SERVICE_URL}/api/results/{job_id}"
                        results_response = await client.get(results_url, timeout=30.0)
                        
                        if results_response.status_code == 200:
                            trial_data = results_response.json()
                            
                            # Save to file
                            output_file = RESULTS_DIR / f"{nct_id}.json"
                            with open(output_file, 'w') as f:
                                json.dump(trial_data, f, indent=2)
                            
                            logger.info(f"✅ Saved to {output_file.name}")
                            return trial_data, None
                        else:
                            return None, f"Failed to get results: {results_response.status_code}"
                    
                    elif status == "failed":
                        error = status_data.get("error", "Unknown error")
                        return None, f"NCT search failed: {error}"
                    
                except Exception as e:
                    logger.warning(f"⚠️ Error polling: {e}")
                    continue
            
            return None, f"Search timed out after {max_attempts * poll_interval}s"
            
    except Exception as e:
        return None, f"Unexpected error: {str(e)}"


async def get_or_fetch_nct_data(nct_id: str) -> tuple[Optional[dict], str, Optional[str], Optional[str]]:
    """
    Get NCT data - from file if exists, otherwise fetch and save.
    Returns (data, source, file_path, error) where source is "file" or "fetched"
    """
    nct_id = nct_id.strip().upper()
    
    logger.info(f"{'='*60}")
    logger.info(f"Processing request for {nct_id}")
    logger.info(f"{'='*60}")
    
    # Try to find existing file
    file_path, data = find_nct_file(nct_id)
    
    if data:
        logger.info(f"✅ Using cached data from file")
        return data, "file", str(file_path) if file_path else None, None
    
    # Not found - fetch and save
    logger.info(f"📥 No cached file found, fetching from NCT service...")
    data, error = await fetch_and_save_nct_data(nct_id)
    
    if data:
        file_path = RESULTS_DIR / f"{nct_id}.json"
        return data, "fetched", str(file_path), None
    else:
        return None, "failed", None, error


# ============================================================================
# Helper Functions - Annotation
# ============================================================================

async def annotate_single_trial(
    nct_id: str,
    trial_data: dict,
    source: str,
    model: str,
    temperature: float
) -> AnnotationResult:
    """
    Send trial data to LLM Assistant API for annotation.
    """
    logger.info(f"🔬 Annotating {nct_id} with {model}")
    start_time = time.time()
    
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            # Check LLM Assistant health
            try:
                health = await client.get(f"{LLM_ASSISTANT_URL}/health", timeout=5.0)
                if health.status_code != 200:
                    raise HTTPException(
                        status_code=503,
                        detail="LLM Assistant service not available"
                    )
            except httpx.ConnectError:
                raise HTTPException(
                    status_code=503,
                    detail=f"Cannot connect to LLM Assistant at {LLM_ASSISTANT_URL}"
                )
            
            # Send annotation request
            response = await client.post(
                f"{LLM_ASSISTANT_URL}/annotate",
                json={
                    "trial_data": {
                        "nct_id": nct_id,
                        "data": trial_data,
                        "source": source
                    },
                    "model": model,
                    "temperature": temperature,
                    "use_extraction_prompt": True
                }
            )
            
            if response.status_code != 200:
                error_text = response.text
                logger.error(f"❌ Annotation failed: {error_text}")
                
                return AnnotationResult(
                    nct_id=nct_id,
                    annotation="",
                    model=model,
                    status="error",
                    source=source,
                    processing_time_seconds=time.time() - start_time,
                    error=f"LLM Assistant error: {error_text[:200]}"
                )
            
            result = response.json()
            
            return AnnotationResult(
                nct_id=nct_id,
                annotation=result.get("annotation", ""),
                model=model,
                status=result.get("status", "success"),
                source=source,
                processing_time_seconds=result.get("processing_time_seconds", 0),
                sources_summary=result.get("sources_summary", {}),
                error=result.get("error")
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Annotation error for {nct_id}: {e}", exc_info=True)
        return AnnotationResult(
            nct_id=nct_id,
            annotation="",
            model=model,
            status="error",
            source=source,
            processing_time_seconds=time.time() - start_time,
            error=str(e)
        )


# ============================================================================
# Routes - Data
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Runner Service",
        "version": "2.0.0",
        "status": "running",
        "description": "File manager, NCT fetcher, and annotation orchestrator",
        "endpoints": {
            "get_data": "POST /get-data",
            "batch_get_data": "POST /batch-get-data",
            "annotate": "POST /annotate",
            "batch_annotate": "POST /batch-annotate",
            "list_files": "GET /files",
            "health": "GET /health"
        },
        "dependencies": {
            "nct_service": NCT_SERVICE_URL,
            "llm_assistant": LLM_ASSISTANT_URL
        }
    }


@app.get("/health")
async def health_check():
    """Health check with service dependencies"""
    
    # Check NCT service
    nct_connected = False
    nct_error = None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{NCT_SERVICE_URL}/health")
            nct_connected = response.status_code == 200
    except Exception as e:
        nct_error = str(e)
    
    # Check LLM Assistant
    llm_connected = False
    llm_error = None
    llm_features = {}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{LLM_ASSISTANT_URL}/health")
            if response.status_code == 200:
                llm_connected = True
                data = response.json()
                llm_features = data.get("dependencies", {})
    except Exception as e:
        llm_error = str(e)
    
    # Count available files
    files_count = len(list(RESULTS_DIR.glob("*.json")))
    
    return {
        "status": "healthy",
        "service": "Runner Service",
        "version": "2.0.0",
        "nct_service": {
            "url": NCT_SERVICE_URL,
            "connected": nct_connected,
            "error": nct_error
        },
        "llm_assistant": {
            "url": LLM_ASSISTANT_URL,
            "connected": llm_connected,
            "error": llm_error,
            "features": llm_features
        },
        "storage": {
            "results_dir": str(RESULTS_DIR),
            "files_count": files_count
        }
    }


@app.post("/get-data", response_model=DataResponse)
async def get_data(request: DataRequest):
    """
    Get NCT data for a single NCT ID.
    Returns existing file or fetches new data if not found.
    """
    try:
        nct_id = request.nct_id.strip().upper()
        logger.info(f"📥 API Request for {nct_id}")
        
        data, source, file_path, error = await get_or_fetch_nct_data(nct_id)
        
        if not data:
            raise HTTPException(
                status_code=404,
                detail=error or f"Could not find or fetch data for {nct_id}"
            )
        
        return DataResponse(
            nct_id=nct_id,
            status="success",
            data=data,
            source=source,
            file_path=file_path
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error processing request: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/batch-get-data", response_model=BatchDataResponse)
async def batch_get_data(request: BatchDataRequest):
    """
    Get NCT data for multiple NCT IDs.
    """
    logger.info(f"📥 Batch request for {len(request.nct_ids)} NCT IDs")
    
    results = []
    successful = 0
    failed = 0
    
    for nct_id in request.nct_ids:
        try:
            nct_id = nct_id.strip().upper()
            if not nct_id:
                continue
            
            data, source, file_path, error = await get_or_fetch_nct_data(nct_id)
            
            if data:
                results.append(DataResponse(
                    nct_id=nct_id,
                    status="success",
                    data=data,
                    source=source,
                    file_path=file_path
                ))
                successful += 1
            else:
                results.append(DataResponse(
                    nct_id=nct_id,
                    status="failed",
                    data={},
                    source="failed",
                    error=error
                ))
                failed += 1
                
        except Exception as e:
            logger.error(f"❌ Error processing {nct_id}: {e}")
            results.append(DataResponse(
                nct_id=nct_id,
                status="failed",
                data={},
                source="error",
                error=str(e)
            ))
            failed += 1
    
    return BatchDataResponse(
        results=results,
        total=len(request.nct_ids),
        successful=successful,
        failed=failed
    )


# ============================================================================
# Routes - Annotation
# ============================================================================

@app.post("/annotate", response_model=AnnotationResult)
async def annotate(request: AnnotationRequest):
    """
    Annotate a single clinical trial.
    
    Workflow:
    1. Get trial data (from cache or fetch)
    2. Send to LLM Assistant API for annotation
    3. Return structured annotation
    """
    nct_id = request.nct_id.strip().upper()
    logger.info(f"🔬 Annotation request for {nct_id}")
    
    start_time = time.time()
    
    try:
        # Step 1: Get trial data
        data, source, file_path, error = await get_or_fetch_nct_data(nct_id)
        
        if not data:
            if not request.fetch_if_missing:
                raise HTTPException(
                    status_code=404,
                    detail=f"No data found for {nct_id} and fetch_if_missing=False"
                )
            raise HTTPException(
                status_code=404,
                detail=error or f"Could not find or fetch data for {nct_id}"
            )
        
        logger.info(f"✅ Got data for {nct_id} (source: {source})")
        
        # Step 2: Send to LLM Assistant
        result = await annotate_single_trial(
            nct_id=nct_id,
            trial_data=data,
            source=source,
            model=request.model,
            temperature=request.temperature
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error annotating {nct_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/batch-annotate", response_model=BatchAnnotationResponse)
async def batch_annotate(request: BatchAnnotationRequest):
    """
    Annotate multiple clinical trials.
    """
    logger.info(f"🔬 Batch annotation for {len(request.nct_ids)} trials with {request.model}")
    
    start_time = time.time()
    results = []
    successful = 0
    failed = 0
    
    for nct_id in request.nct_ids:
        nct_id = nct_id.strip().upper()
        if not nct_id:
            continue
        
        try:
            # Get trial data
            data, source, file_path, error = await get_or_fetch_nct_data(nct_id)
            
            if not data:
                results.append(AnnotationResult(
                    nct_id=nct_id,
                    annotation="",
                    model=request.model,
                    status="error",
                    source="failed",
                    processing_time_seconds=0,
                    error=error or f"Could not find or fetch data for {nct_id}"
                ))
                failed += 1
                continue
            
            # Annotate
            result = await annotate_single_trial(
                nct_id=nct_id,
                trial_data=data,
                source=source,
                model=request.model,
                temperature=request.temperature
            )
            
            results.append(result)
            
            if result.status == "success":
                successful += 1
            else:
                failed += 1
                
        except Exception as e:
            logger.error(f"❌ Error with {nct_id}: {e}")
            results.append(AnnotationResult(
                nct_id=nct_id,
                annotation="",
                model=request.model,
                status="error",
                source="error",
                processing_time_seconds=0,
                error=str(e)
            ))
            failed += 1
    
    total_time = time.time() - start_time
    
    logger.info(f"✅ Batch complete: {successful}/{len(request.nct_ids)} in {total_time:.1f}s")
    
    return BatchAnnotationResponse(
        results=results,
        total=len(request.nct_ids),
        successful=successful,
        failed=failed,
        total_time_seconds=round(total_time, 2)
    )


# ============================================================================
# Routes - Files
# ============================================================================

@app.get("/files")
async def list_files():
    """List all available NCT data files"""
    files = []
    for file_path in sorted(RESULTS_DIR.glob("*.json")):
        try:
            nct_id = file_path.stem.split('_')[0]
            size_bytes = file_path.stat().st_size
            
            files.append({
                "nct_id": nct_id,
                "filename": file_path.name,
                "size_kb": round(size_bytes / 1024, 2),
                "path": str(file_path)
            })
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")
    
    return {
        "total_files": len(files),
        "files": files
    }


@app.get("/files/{nct_id}")
async def get_file_info(nct_id: str):
    """Get info about files for a specific NCT ID"""
    nct_id = nct_id.strip().upper()
    
    file_path, data = find_nct_file(nct_id)
    
    if not file_path:
        raise HTTPException(
            status_code=404,
            detail=f"No file found for {nct_id}"
        )
    
    return {
        "nct_id": nct_id,
        "filename": file_path.name,
        "size_kb": round(file_path.stat().st_size / 1024, 2),
        "path": str(file_path),
        "exists": True
    }


# ============================================================================
# Run standalone
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    print("=" * 80)
    print("🚀 Starting Runner Service (Enhanced) on port 9003...")
    print("=" * 80)
    print(f"📡 NCT Service: {NCT_SERVICE_URL}")
    print(f"🤖 LLM Assistant: {LLM_ASSISTANT_URL}")
    print(f"📁 Results Directory: {RESULTS_DIR}")
    print(f"📚 API Docs: http://localhost:9003/docs")
    print(f"🔍 Health Check: http://localhost:9003/health")
    print("=" * 80)
    uvicorn.run(app, host="0.0.0.0", port=9003, reload=True)