"""
Runner Service (Port 9003)
==========================

Simple file manager and data fetcher for NCT trial data.
- Finds existing JSON files for NCT IDs
- Fetches new data from NCT service (9002) if not found
- Returns JSON data to chat service (9001)
"""
import logging
import httpx
import json
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Setup logging
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
    version="1.0.0",
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
    
    # Look for exact match first
    exact_file = RESULTS_DIR / f"{nct_id}.json"
    if exact_file.exists():
        logger.info(f"📁 Found existing file: {exact_file.name}")
        try:
            with open(exact_file, 'r') as f:
                return exact_file, json.load(f)
        except Exception as e:
            logger.error(f"❌ Error reading {exact_file}: {e}")
            return None, None
    
    # Look for versioned files
    import glob
    pattern = str(RESULTS_DIR / f"{nct_id}_v*.json")
    files = sorted(glob.glob(pattern), reverse=True)
    
    if files:
        file_path = Path(files[0])
        logger.info(f"📁 Found versioned file: {file_path.name}")
        try:
            with open(file_path, 'r') as f:
                return file_path, json.load(f)
        except Exception as e:
            logger.error(f"❌ Error reading {file_path}: {e}")
            return None, None
    
    logger.info(f"📂 No file found for {nct_id}")
    return None, None

async def fetch_and_save_nct_data(nct_id: str) -> Optional[dict]:
    """
    Fetch NCT data from service (9002) and save to JSON file.
    Returns the data or None if fetch failed.
    """
    nct_id = nct_id.strip().upper()
    logger.info(f"📡 Fetching data for {nct_id} from NCT service...")
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Initiate search
            response = await client.post(
                f"{NCT_SERVICE_URL}/api/nct/search/{nct_id}",
                json={"include_extended": False}
            )
            
            if response.status_code != 200:
                logger.error(f"❌ Failed to initiate search: {response.status_code}")
                return None
            
            data = response.json()
            job_id = data.get("job_id")
            
            if not job_id:
                logger.error("❌ No job_id returned from search")
                return None
            
            # Poll for results
            import asyncio
            max_attempts = 30
            for attempt in range(max_attempts):
                await asyncio.sleep(2)
                
                status_response = await client.get(
                    f"{NCT_SERVICE_URL}/api/nct/search/{job_id}/status"
                )
                
                if status_response.status_code != 200:
                    continue
                
                status_data = status_response.json()
                
                if status_data.get("status") == "completed":
                    # Get results
                    results_response = await client.get(
                        f"{NCT_SERVICE_URL}/api/nct/results/{job_id}"
                    )
                    
                    if results_response.status_code == 200:
                        trial_data = results_response.json()
                        
                        # Save to file
                        output_file = RESULTS_DIR / f"{nct_id}.json"
                        with open(output_file, 'w') as f:
                            json.dump(trial_data, f, indent=2)
                        
                        logger.info(f"💾 Saved data to {output_file.name}")
                        return trial_data
                
                elif status_data.get("status") == "failed":
                    logger.error(f"❌ Search failed: {status_data.get('error')}")
                    return None
            
            logger.error("❌ Search timed out")
            return None
            
    except Exception as e:
        logger.error(f"❌ Error fetching trial data: {e}")
        return None

async def get_or_fetch_nct_data(nct_id: str) -> tuple[Optional[dict], str, Optional[str]]:
    """
    Get NCT data - from file if exists, otherwise fetch and save.
    Returns (data, source, file_path) where source is "file" or "fetched"
    """
    nct_id = nct_id.strip().upper()
    
    # Try to find existing file
    file_path, data = find_nct_file(nct_id)
    
    if data:
        return data, "file", str(file_path) if file_path else None
    
    # Not found - fetch and save
    logger.info(f"🔄 File not found, fetching from NCT service...")
    data = await fetch_and_save_nct_data(nct_id)
    
    if data:
        file_path = RESULTS_DIR / f"{nct_id}.json"
        return data, "fetched", str(file_path)
    
    return None, "failed", None

# ============================================================================
# Routes
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Runner Service",
        "version": "1.0.0",
        "status": "running",
        "description": "File manager and NCT data fetcher",
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
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{NCT_SERVICE_URL}/health")
            nct_connected = response.status_code == 200
    except:
        pass
    
    # Count available files
    files_count = len(list(RESULTS_DIR.glob("*.json")))
    
    return {
        "status": "healthy",
        "service": "Runner Service",
        "version": "1.0.0",
        "nct_service": {
            "url": NCT_SERVICE_URL,
            "connected": nct_connected
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
        logger.info(f"📥 Request for {nct_id}")
        
        data, source, file_path = await get_or_fetch_nct_data(nct_id)
        
        if not data:
            raise HTTPException(
                status_code=404,
                detail=f"Could not find or fetch data for {nct_id}"
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
        logger.info(f"📥 Batch request for {len(request.nct_ids)} NCT IDs")
        
        results = []
        successful = 0
        failed = 0
        
        for nct_id in request.nct_ids:
            try:
                nct_id = nct_id.strip().upper()
                if not nct_id:
                    continue
                
                data, source, file_path = await get_or_fetch_nct_data(nct_id)
                
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
                        file_path=None
                    ))
                    failed += 1
                    
            except Exception as e:
                logger.error(f"❌ Error processing {nct_id}: {e}")
                results.append(DataResponse(
                    nct_id=nct_id,
                    status="failed",
                    data={},
                    source="error",
                    file_path=None
                ))
                failed += 1
        
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
    print("🚀 Starting Runner Service on port 9003...")
    print(f"📡 NCT Service: {NCT_SERVICE_URL}")
    print(f"📁 Results Directory: {RESULTS_DIR}")
    print("📚 Docs: http://localhost:9003/docs")
    uvicorn.run(app, host="0.0.0.0", port=9003, reload=True)