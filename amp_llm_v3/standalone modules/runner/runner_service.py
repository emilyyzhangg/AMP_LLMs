"""
Runner Service (Port 9003) - FIXED VERSION
===========================================

Simple file manager and data fetcher for NCT trial data.
- Finds existing JSON files for NCT IDs
- Fetches new data from NCT service (9002) if not found
- Returns JSON data to chat service (9001)

FIXES:
- Better error logging
- More detailed status messages
- Validates JSON structure before saving
- Better timeout handling
"""
import logging
import httpx
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Setup logging with more detail
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
    description="File manager and NCT data fetcher",
    version="1.1.0",
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
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

logger.info(f"📁 Results directory: {RESULTS_DIR}")
logger.info(f"🔗 NCT Service URL: {NCT_SERVICE_URL}")

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

# ============================================================================
# Helper Functions
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
            search_url = f"{NCT_SERVICE_URL}/api/nct/search/{nct_id}"
            logger.info(f"📤 POST {search_url}")
            
            try:
                response = await client.post(
                    search_url,
                    json={"include_extended": False},
                    timeout=30.0
                )
                
                logger.info(f"📥 Response status: {response.status_code}")
                
                if response.status_code != 200:
                    error_text = await response.text()
                    logger.error(f"❌ Search initiation failed: {response.status_code}")
                    logger.error(f"❌ Response: {error_text[:500]}")
                    return None, f"NCT service returned {response.status_code}: {error_text[:200]}"
                
                data = response.json()
                logger.info(f"📊 Search response: {json.dumps(data, indent=2)[:500]}")
                
                job_id = data.get("job_id")
                
                if not job_id:
                    logger.error("❌ No job_id in response")
                    logger.error(f"❌ Full response: {json.dumps(data, indent=2)}")
                    return None, "No job_id returned from NCT search"
                
                logger.info(f"✅ Search initiated with job_id: {job_id}")
                
            except httpx.TimeoutException:
                error_msg = "Timeout initiating search (30s)"
                logger.error(f"❌ {error_msg}")
                return None, error_msg
            except Exception as e:
                error_msg = f"Error initiating search: {e}"
                logger.error(f"❌ {error_msg}")
                return None, error_msg
            
            # Step 3: Poll for results
            import asyncio
            max_attempts = 30
            poll_interval = 2
            
            logger.info(f"⏳ Polling for results (max {max_attempts} attempts, {poll_interval}s interval)")
            
            for attempt in range(max_attempts):
                await asyncio.sleep(poll_interval)
                
                status_url = f"{NCT_SERVICE_URL}/api/nct/search/{job_id}/status"
                logger.info(f"📤 GET {status_url} (attempt {attempt + 1}/{max_attempts})")
                
                try:
                    status_response = await client.get(status_url, timeout=10.0)
                    
                    if status_response.status_code != 200:
                        logger.warning(f"⚠️ Status check failed: {status_response.status_code}")
                        continue
                    
                    status_data = status_response.json()
                    status = status_data.get("status")
                    
                    logger.info(f"📊 Status: {status}")
                    
                    if status == "completed":
                        # Step 4: Get results
                        results_url = f"{NCT_SERVICE_URL}/api/nct/results/{job_id}"
                        logger.info(f"📤 GET {results_url}")
                        
                        results_response = await client.get(results_url, timeout=30.0)
                        
                        if results_response.status_code == 200:
                            trial_data = results_response.json()
                            
                            # Validate data structure
                            if not isinstance(trial_data, dict):
                                error_msg = f"Invalid data type: expected dict, got {type(trial_data)}"
                                logger.error(f"❌ {error_msg}")
                                return None, error_msg
                            
                            # Check if it has the NCT ID
                            if "nct_id" not in trial_data and "sources" not in trial_data:
                                logger.warning("⚠️ Data structure may be incomplete")
                                logger.info(f"📊 Data keys: {list(trial_data.keys())}")
                            
                            # Save to file
                            output_file = RESULTS_DIR / f"{nct_id}.json"
                            logger.info(f"💾 Saving to {output_file}")
                            
                            with open(output_file, 'w') as f:
                                json.dump(trial_data, f, indent=2)
                            
                            file_size = output_file.stat().st_size
                            logger.info(f"✅ Saved {file_size} bytes to {output_file.name}")
                            
                            return trial_data, None
                        else:
                            error_text = await results_response.text()
                            error_msg = f"Failed to get results: {results_response.status_code}"
                            logger.error(f"❌ {error_msg}")
                            logger.error(f"❌ Response: {error_text[:500]}")
                            return None, error_msg
                    
                    elif status == "failed":
                        error = status_data.get("error", "Unknown error")
                        logger.error(f"❌ Search failed: {error}")
                        return None, f"NCT search failed: {error}"
                    
                    elif status == "pending" or status == "running":
                        logger.info(f"⏳ Still {status}...")
                        continue
                    else:
                        logger.warning(f"⚠️ Unknown status: {status}")
                        continue
                        
                except httpx.TimeoutException:
                    logger.warning(f"⚠️ Timeout checking status (attempt {attempt + 1})")
                    continue
                except Exception as e:
                    logger.error(f"❌ Error polling status: {e}")
                    continue
            
            # Timeout
            error_msg = f"Search timed out after {max_attempts * poll_interval}s"
            logger.error(f"❌ {error_msg}")
            return None, error_msg
            
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"❌ {error_msg}", exc_info=True)
        return None, error_msg

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
        logger.info(f"✅ Successfully fetched and saved data")
        return data, "fetched", str(file_path), None
    else:
        logger.error(f"❌ Failed to fetch data: {error}")
        return None, "failed", None, error

# ============================================================================
# Routes
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Runner Service",
        "version": "1.1.0",
        "status": "running",
        "description": "File manager and NCT data fetcher (FIXED VERSION)",
        "endpoints": {
            "get_data": "POST /get-data",
            "batch_get_data": "POST /batch-get-data",
            "list_files": "GET /files",
            "health": "GET /health"
        }
    }

@app.get("/health")
async def health_check():
    """Health check with NCT service status"""
    
    # Check NCT service
    nct_connected = False
    nct_error = None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{NCT_SERVICE_URL}/health")
            nct_connected = response.status_code == 200
    except Exception as e:
        nct_error = str(e)
    
    # Count available files
    files_count = len(list(RESULTS_DIR.glob("*.json")))
    
    return {
        "status": "healthy",
        "service": "Runner Service",
        "version": "1.1.0",
        "nct_service": {
            "url": NCT_SERVICE_URL,
            "connected": nct_connected,
            "error": nct_error
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
    Returns existing files or fetches new data for each.
    """
    try:
        logger.info(f"📥 Batch request for {len(request.nct_ids)} NCT IDs: {request.nct_ids}")
        
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
                    logger.info(f"✅ {nct_id}: SUCCESS ({source})")
                else:
                    results.append(DataResponse(
                        nct_id=nct_id,
                        status="failed",
                        data={},
                        source="failed",
                        file_path=None,
                        error=error
                    ))
                    failed += 1
                    logger.error(f"❌ {nct_id}: FAILED - {error}")
                    
            except Exception as e:
                logger.error(f"❌ Error processing {nct_id}: {e}")
                results.append(DataResponse(
                    nct_id=nct_id,
                    status="failed",
                    data={},
                    source="error",
                    file_path=None,
                    error=str(e)
                ))
                failed += 1
        
        logger.info(f"📊 Batch complete: {successful} successful, {failed} failed")
        
        return BatchDataResponse(
            results=results,
            total=len(request.nct_ids),
            successful=successful,
            failed=failed
        )
        
    except Exception as e:
        logger.error(f"❌ Batch processing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/files")
async def list_files():
    """List all available NCT data files"""
    try:
        files = []
        for file_path in sorted(RESULTS_DIR.glob("*.json")):
            try:
                # Extract NCT ID from filename
                nct_id = file_path.stem.split('_')[0]  # Handle versioned files
                
                # Get file size
                size_bytes = file_path.stat().st_size
                size_kb = round(size_bytes / 1024, 2)
                
                files.append({
                    "nct_id": nct_id,
                    "filename": file_path.name,
                    "size_kb": size_kb,
                    "path": str(file_path)
                })
            except Exception as e:
                logger.error(f"Error processing file {file_path}: {e}")
                continue
        
        return {
            "total_files": len(files),
            "files": files
        }
        
    except Exception as e:
        logger.error(f"❌ Error listing files: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
    
    size_bytes = file_path.stat().st_size
    
    return {
        "nct_id": nct_id,
        "filename": file_path.name,
        "size_kb": round(size_bytes / 1024, 2),
        "path": str(file_path),
        "exists": True
    }

# ============================================================================
# Run standalone
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    print("="*80)
    print("🚀 Starting Runner Service (FIXED VERSION) on port 9003...")
    print("="*80)
    print(f"📡 NCT Service: {NCT_SERVICE_URL}")
    print(f"📁 Results Directory: {RESULTS_DIR}")
    print(f"📚 API Docs: http://localhost:9003/docs")
    print(f"🔍 Health Check: http://localhost:9003/health")
    print("="*80)
    uvicorn.run(app, host="0.0.0.0", port=9003, reload=True)