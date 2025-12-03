"""
NCT Lookup API - Standalone Clinical Trial Search Service
=========================================================

A FastAPI-based service for comprehensive clinical trial literature search.

Features:
- Core databases: ClinicalTrials.gov, PubMed, PMC
- Extended databases: DuckDuckGo, SERP API, Google Scholar, OpenFDA, UniProt
- JSON output with database tagging
- Summary statistics
- Async processing for performance
- Dynamic API registry for easy extensibility
- NCT ID-based file naming with duplicate detection

Installation:
    pip install fastapi uvicorn aiohttp requests python-dotenv beautifulsoup4

Usage:
    uvicorn nct_api:app --reload --port 8000

API Endpoints:
    GET /api/registry - List all available APIs
    POST /api/search/{nct_id}
    GET /api/search/{nct_id}/status
    GET /api/results/{nct_id}
    POST /api/results/{nct_id}/check-duplicate - Check if file exists
    POST /api/results/{nct_id}/save - Save results with duplicate handling
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path
import asyncio
import json
import logging
import os
import re

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from nct_core import NCTSearchEngine
from nct_models import SearchRequest, SearchResponse, SearchStatus, SearchSummary, SearchConfig
from nct_api_registry import APIRegistry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="NCT Lookup API",
    description="Comprehensive clinical trial literature search service with dynamic API registry",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:9000",
        "http://127.0.0.1:9000",
        "http://localhost:3000",  # if using separate frontend
        "*"  # For development only - restrict in production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global search engine instance
search_engine = NCTSearchEngine()

# In-memory status tracking (use Redis/database in production)
search_status_db: Dict[str, SearchStatus] = {}


# ============================================================================
# NEW: Models for Duplicate Handling
# ============================================================================

class DuplicateCheckResponse(BaseModel):
    """Response for duplicate file check."""
    exists: bool
    filename: str
    suggested_filename: str
    existing_files: List[str] = Field(default_factory=list)
    message: str


class SaveRequest(BaseModel):
    """Request model for saving results."""
    overwrite: bool = Field(
        default=False,
        description="Whether to overwrite existing file or create new version"
    )
    custom_filename: Optional[str] = Field(
        default=None,
        description="Optional custom filename (without extension)"
    )


class SaveResponse(BaseModel):
    """Response model for save operation."""
    success: bool
    filename: str
    filepath: str
    message: str
    size_bytes: int
    was_duplicate: bool = False
    overwritten: bool = False


# ============================================================================
# Helper Functions for File Management
# ============================================================================

def get_next_version_filename(nct_id: str, results_dir: Path) -> str:
    """
    Get the next available versioned filename for an NCT ID.
    
    Args:
        nct_id: The NCT identifier (e.g., NCT12345678)
        results_dir: Directory where results are stored
        
    Returns:
        Filename like "NCT12345678.json" or "NCT12345678_1.json"
    """
    base_filename = f"{nct_id}.json"
    base_path = results_dir / base_filename
    
    # If base file doesn't exist, use it
    if not base_path.exists():
        return base_filename
    
    # Find next available version number
    version = 1
    while True:
        versioned_filename = f"{nct_id}_{version}.json"
        versioned_path = results_dir / versioned_filename
        if not versioned_path.exists():
            return versioned_filename
        version += 1
        
        # Safety check to prevent infinite loops
        if version > 1000:
            raise ValueError(f"Too many versions for {nct_id}")


def find_existing_files(nct_id: str, results_dir: Path) -> List[str]:
    """
    Find all existing files for a given NCT ID.
    
    Args:
        nct_id: The NCT identifier
        results_dir: Directory where results are stored
        
    Returns:
        List of existing filenames (base + all versions)
    """
    pattern = re.compile(rf"^{re.escape(nct_id)}(_\d+)?\.json$")
    existing = []
    
    if results_dir.exists():
        for file in results_dir.iterdir():
            if file.is_file() and pattern.match(file.name):
                existing.append(file.name)
    
    # Sort to show base file first, then versions in order
    existing.sort(key=lambda x: (
        0 if x == f"{nct_id}.json" else int(x.split('_')[1].split('.')[0])
    ))
    
    return existing


def get_file_info(filepath: Path) -> Dict[str, Any]:
    """Get information about a file."""
    if not filepath.exists():
        return None
    
    stat = filepath.stat()
    return {
        "size_bytes": stat.st_size,
        "size_formatted": _format_file_size(stat.st_size),
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "created": datetime.fromtimestamp(stat.st_ctime).isoformat()
    }


# ============================================================================
# API Endpoints
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize search engine on startup."""
    logger.info("Starting NCT Lookup API")
    logger.info(f"SERPAPI_KEY configured: {bool(os.getenv('SERPAPI_KEY'))}")
    logger.info(f"NCBI_API_KEY configured: {bool(os.getenv('NCBI_API_KEY'))}")
    
    # Log available APIs
    all_apis = APIRegistry.get_all_apis()
    logger.info(f"Registered APIs: {len(all_apis)}")
    for api in all_apis:
        status = "✓" if not api.requires_key or os.getenv(api.config.get('env_var', '')) else "⚠"
        logger.info(f"  {status} {api.name} ({api.id}) - {api.category}")
    
    await search_engine.initialize()
    logger.info("Search engine initialized successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Shutting down NCT Lookup API")
    await search_engine.close()


@app.get("/")
async def root():
    """API root endpoint."""
    return {
        "service": "NCT Lookup API",
        "version": "2.0.0",
        "status": "operational",
        "endpoints": {
            "api_registry": "GET /api/registry",
            "search": "POST /api/search/{nct_id}",
            "status": "GET /api/search/{nct_id}/status",
            "results": "GET /api/results/{nct_id}",
            "check_duplicate": "POST /api/results/{nct_id}/check-duplicate",
            "save": "POST /api/results/{nct_id}/save",
            "download": "GET /api/results/{nct_id}/download",
            "delete": "DELETE /api/results/{nct_id}"
        },
        "features": {
            "core_apis": len(APIRegistry.get_core_apis()),
            "extended_apis": len(APIRegistry.get_extended_apis()),
            "total_apis": len(APIRegistry.get_all_apis()),
            "duplicate_detection": True,
            "versioned_saves": True
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "active_searches": len([s for s in search_status_db.values() if s.status == "running"]),
        "registered_apis": len(APIRegistry.get_all_apis())
    }


@app.get("/api/registry")
async def get_api_registry():
    """
    Get the complete API registry with all available data sources.
    
    This endpoint returns metadata about all APIs (core and extended)
    that can be used to dynamically generate UI controls.
    
    Returns:
        Dictionary with 'core' and 'extended' API lists, each containing:
        - id: API identifier
        - name: Display name
        - description: Brief description
        - requires_key: Whether API key is needed
        - enabled_by_default: Default checkbox state
        - available: Whether API is currently usable (has key if required)
    """
    registry_data = APIRegistry.to_dict()
    
    # Add availability status based on API keys
    for category in ['core', 'extended']:
        for api_data in registry_data[category]:
            api_def = APIRegistry.get_api_by_id(api_data['id'])
            if api_def and api_def.requires_key:
                env_var = api_def.config.get('env_var')
                api_data['available'] = bool(os.getenv(env_var)) if env_var else False
            else:
                api_data['available'] = True
    
    return {
        **registry_data,
        "metadata": {
            "total_core": len(registry_data['core']),
            "total_extended": len(registry_data['extended']),
            "total_apis": len(registry_data['core']) + len(registry_data['extended']),
            "apis_requiring_keys": len(APIRegistry.get_apis_requiring_keys()),
            "default_enabled": APIRegistry.get_default_enabled_apis()
        }
    }


@app.post("/api/search/{nct_id}", response_model=SearchResponse)
async def search_nct(
    nct_id: str,
    request: SearchRequest,
    background_tasks: BackgroundTasks
):
    """
    Initiate NCT search across databases.
    
    Args:
        nct_id: NCT number (e.g., NCT12345678)
        request: Search configuration with selected databases
        
    Returns:
        Search response with job ID and initial status
    """
    # Validate NCT format
    nct_id = nct_id.upper().strip()
    if not nct_id.startswith("NCT") or len(nct_id) != 11:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid NCT format: {nct_id}. Expected: NCT######## (NCT followed by 8 digits)"
        )
    
    # Validate that the last 8 characters are digits
    if not nct_id[3:].isdigit():
        raise HTTPException(
            status_code=400,
            detail=f"Invalid NCT format: {nct_id}. The 8 characters after 'NCT' must be digits"
        )
    
    # Validate selected databases
    if request.databases:
        valid_ids, invalid_ids = APIRegistry.validate_api_ids(request.databases)
        if invalid_ids:
            available = [api.id for api in APIRegistry.get_all_apis()]
            raise HTTPException(
                status_code=400,
                detail=f"Invalid database IDs: {invalid_ids}. Available: {available}"
            )
    
    # Check if search already exists
    if nct_id in search_status_db:
        existing = search_status_db[nct_id]
        if existing.status in ["running", "completed"]:
            return SearchResponse(
                job_id=nct_id,
                status=existing.status,
                message=f"Search {'in progress' if existing.status == 'running' else 'already completed'}",
                created_at=existing.created_at
            )
    
    # Create status entry
    status = SearchStatus(
        job_id=nct_id,
        status="queued",
        created_at=datetime.utcnow(),
        databases_to_search=_get_database_list(request)
    )
    search_status_db[nct_id] = status
    
    # Start background search
    background_tasks.add_task(
        _execute_search,
        nct_id,
        request
    )
    
    logger.info(f"Queued search for {nct_id} with databases: {status.databases_to_search}")
    
    return SearchResponse(
        job_id=nct_id,
        status="queued",
        message=f"Search initiated for {nct_id}",
        created_at=status.created_at
    )


@app.get("/api/search/{nct_id}/status")
async def get_search_status(nct_id: str):
    """
    Get current status of a search.
    
    Args:
        nct_id: NCT number
        
    Returns:
        Current search status
    """
    nct_id = nct_id.upper().strip()
    
    if nct_id not in search_status_db:
        raise HTTPException(
            status_code=404,
            detail=f"No search found for {nct_id}"
        )
    
    status = search_status_db[nct_id]
    return {
        "job_id": status.job_id,
        "status": status.status,
        "progress": status.progress,
        "current_database": status.current_database,
        "completed_databases": status.completed_databases,
        "databases_to_search": status.databases_to_search,
        "created_at": status.created_at.isoformat(),
        "updated_at": status.updated_at.isoformat() if status.updated_at else None,
        "error": status.error
    }


@app.get("/api/results/{nct_id}")
async def get_results(nct_id: str):
    """
    Get search results for an NCT ID.
    
    Args:
        nct_id: NCT number
        
    Returns:
        Complete search results with summary
    """
    nct_id = nct_id.upper().strip()
    
    # Check if results exist
    results_file = Path(f"results/{nct_id}.json")
    if not results_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Results file not found for {nct_id}"
        )
    
    try:
        with open(results_file, 'r', encoding='utf-8') as f:
            results = json.load(f)
        
        # Generate summary
        summary = _generate_summary(results)
        
        return {
            "nct_id": nct_id,
            "summary": summary,
            "results": results,
            "file_info": get_file_info(results_file)
        }
    except Exception as e:
        logger.error(f"Error loading results for {nct_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error loading results: {str(e)}"
        )


# ============================================================================
# NEW: Duplicate Check Endpoint
# ============================================================================

@app.post("/api/results/{nct_id}/check-duplicate", response_model=DuplicateCheckResponse)
async def check_duplicate(nct_id: str):
    """
    Check if a file already exists for the given NCT ID.
    
    Args:
        nct_id: NCT number
        
    Returns:
        Information about existing files and suggested filename
    """
    nct_id = nct_id.upper().strip()
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)
    
    # Find existing files
    existing_files = find_existing_files(nct_id, results_dir)
    base_filename = f"{nct_id}.json"
    base_exists = base_filename in existing_files
    
    if not existing_files:
        return DuplicateCheckResponse(
            exists=False,
            filename=base_filename,
            suggested_filename=base_filename,
            existing_files=[],
            message=f"No existing files found for {nct_id}"
        )
    
    # Get suggested filename (next available version)
    suggested = get_next_version_filename(nct_id, results_dir)
    
    return DuplicateCheckResponse(
        exists=True,
        filename=base_filename,
        suggested_filename=suggested,
        existing_files=existing_files,
        message=f"Found {len(existing_files)} existing file(s) for {nct_id}"
    )


# ============================================================================
# NEW: Enhanced Save Endpoint with Duplicate Handling
# ============================================================================

@app.post("/api/results/{nct_id}/save", response_model=SaveResponse)
async def save_results(nct_id: str, request: SaveRequest):
    """
    Save search results with duplicate handling.
    
    Args:
        nct_id: NCT number
        request: Save configuration (overwrite flag, custom filename)
        
    Returns:
        Save response with file information
    """
    nct_id = nct_id.upper().strip()
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)
    
    # Load results from temporary location
    temp_results_file = results_dir / f"{nct_id}.json"
    if not temp_results_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No results found for {nct_id}. Please run a search first."
        )
    
    try:
        with open(temp_results_file, 'r', encoding='utf-8') as f:
            results = json.load(f)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error loading results: {str(e)}"
        )
    
    # Determine target filename
    if request.custom_filename:
        # Use custom filename if provided
        target_filename = f"{request.custom_filename}.json"
    elif request.overwrite:
        # Overwrite base file
        target_filename = f"{nct_id}.json"
    else:
        # Get next versioned filename
        target_filename = get_next_version_filename(nct_id, results_dir)
    
    target_path = results_dir / target_filename
    was_duplicate = target_path.exists()
    
    # Save the file
    try:
        with open(target_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        file_size = target_path.stat().st_size
        
        logger.info(
            f"Saved results for {nct_id} to {target_filename} "
            f"({'overwrite' if was_duplicate and request.overwrite else 'new file'})"
        )
        
        return SaveResponse(
            success=True,
            filename=target_filename,
            filepath=str(target_path.absolute()),
            message=f"Results saved successfully to {target_filename}",
            size_bytes=file_size,
            was_duplicate=was_duplicate,
            overwritten=request.overwrite and was_duplicate
        )
        
    except Exception as e:
        logger.error(f"Error saving results for {nct_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error saving results: {str(e)}"
        )


@app.get("/api/results/{nct_id}/download")
async def download_results(nct_id: str, version: Optional[int] = None):
    """
    Download search results as JSON file.
    
    Args:
        nct_id: NCT number
        version: Optional version number (for versioned files)
        
    Returns:
        JSON file download
    """
    nct_id = nct_id.upper().strip()
    
    # Determine filename
    if version is not None:
        filename = f"{nct_id}_{version}.json"
    else:
        filename = f"{nct_id}.json"
    
    results_file = Path(f"results/{filename}")
    if not results_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Results file not found: {filename}"
        )
    
    # Return file for download
    return FileResponse(
        path=str(results_file),
        media_type='application/json',
        filename=filename
    )


def _format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


@app.delete("/api/results/{nct_id}")
async def delete_search(nct_id: str, version: Optional[int] = None):
    """
    Delete search results and status.
    
    Args:
        nct_id: NCT number
        version: Optional version number (deletes specific version, or all if not specified)
        
    Returns:
        Deletion confirmation
    """
    nct_id = nct_id.upper().strip()
    results_dir = Path("results")
    deleted_files = []
    
    if version is not None:
        # Delete specific version
        filename = f"{nct_id}_{version}.json"
        results_file = results_dir / filename
        if results_file.exists():
            results_file.unlink()
            deleted_files.append(filename)
    else:
        # Delete all versions
        existing_files = find_existing_files(nct_id, results_dir)
        for filename in existing_files:
            filepath = results_dir / filename
            if filepath.exists():
                filepath.unlink()
                deleted_files.append(filename)
        
        # Remove from status db
        if nct_id in search_status_db:
            del search_status_db[nct_id]
    
    if not deleted_files:
        raise HTTPException(
            status_code=404,
            detail=f"No files found to delete for {nct_id}"
        )
    
    return {
        "message": f"Deleted {len(deleted_files)} file(s) for {nct_id}",
        "nct_id": nct_id,
        "deleted_files": deleted_files
    }


# ============================================================================
# Internal helper functions
# ============================================================================

async def _execute_search(nct_id: str, request: SearchRequest):
    """Execute search in background."""
    status = search_status_db[nct_id]
    
    try:
        # Update status
        status.status = "running"
        status.updated_at = datetime.utcnow()
        
        logger.info(f"Starting search for {nct_id}")
        
        # Configure search
        config = SearchConfig(
            use_extended_apis=request.include_extended,
            enabled_databases=request.databases if request.databases else None
        )
        
        # Execute search
        results = await search_engine.search(nct_id, config, status)
        
        # Save results to temporary location (will be renamed on save)
        results_dir = Path("results")
        results_dir.mkdir(exist_ok=True)
        
        output_file = results_dir / f"{nct_id}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        # Update status
        status.status = "completed"
        status.progress = 100
        status.updated_at = datetime.utcnow()
        
        logger.info(f"Completed search for {nct_id}")
        
    except Exception as e:
        logger.error(f"Error in search for {nct_id}: {e}", exc_info=True)
        status.status = "failed"
        status.error = str(e)
        status.updated_at = datetime.utcnow()


def _get_database_list(request: SearchRequest) -> List[str]:
    """Get list of databases to search based on request."""
    if request.databases:
        # User specified exact databases
        return request.databases
    
    # Build default list
    databases = [api.id for api in APIRegistry.get_core_apis()]
    
    if request.include_extended:
        databases.extend([api.id for api in APIRegistry.get_extended_apis()])
    
    return databases


def _generate_summary(results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate summary statistics from search results.
    Uses API registry to dynamically handle all data sources.
    """
    # Extract basic info
    nct_id = results["nct_id"]
    title = results.get("metadata", {}).get("title", "")
    status = results.get("metadata", {}).get("status", "")
    
    # Initialize
    databases_searched = []
    results_by_database = {}
    
    # Count results per source dynamically
    sources = results.get("sources", {})
    
    # Process each registered API
    for api_def in APIRegistry.get_all_apis():
        api_id = api_def.id
        
        # Check core sources
        if api_id in sources and sources[api_id].get("success"):
            databases_searched.append(api_id)
            count = _count_source_results(api_id, sources[api_id].get("data", {}))
            if count > 0:
                results_by_database[api_id] = count
        
        # Check extended sources
        if "extended" in sources and api_id in sources["extended"]:
            ext_data = sources["extended"][api_id]
            if ext_data.get("success"):
                databases_searched.append(api_id)
                count = _count_source_results(api_id, ext_data.get("data", {}))
                if count > 0:
                    results_by_database[api_id] = count
    
    # Calculate total
    total_results = sum(results_by_database.values())
    
    summary = {
        "nct_id": nct_id,
        "title": title,
        "status": status,
        "databases_searched": databases_searched,
        "results_by_database": results_by_database,
        "total_results": total_results,
        "search_timestamp": results.get("timestamp", "")
    }
    
    return summary


def _count_source_results(api_id: str, data: Dict[str, Any]) -> int:
    """
    Count results from a specific API source.
    Handles different response formats dynamically.
    Enhanced with proper OpenFDA counting.
    """
    if not data or data.get("error"):
        return 0
    
    # Core API result counting
    if api_id == "clinicaltrials":
        return 1  # The trial itself
    
    elif api_id == "pubmed":
        return len(data.get("pmids", []))
    
    elif api_id == "pmc":
        return len(data.get("pmcids", []))
    
    elif api_id == "pmc_bioc":
        return data.get("total_fetched", 0)
    
    # Enhanced OpenFDA counting
    elif api_id == "openfda":
        total = 0
        # Count drug labels
        total += len(data.get("drug_labels", []))
        # Count adverse events
        total += len(data.get("adverse_events", []))
        # Count enforcement reports
        total += len(data.get("enforcement_reports", []))
        return total
    
    elif api_id == "uniprot":
        return len(data.get("results", []))
    
    # Extended API result counting (generic patterns)
    # Most extended APIs use "results" array
    if "results" in data:
        results_list = data["results"]
        if isinstance(results_list, list):
            return len(results_list)
    
    # Some APIs use "total_found"
    if "total_found" in data:
        return data.get("total_found", 0)
    
    # Some APIs use "count"
    if "count" in data:
        return data.get("count", 0)
    
    return 0


def _format_openfda_details(data: Dict[str, Any]) -> str:
    """
    Format OpenFDA results for display.
    Returns a formatted string showing breakdown by category.
    """
    if not data or data.get("error"):
        return ""
    
    details = []
    
    drug_labels = len(data.get("drug_labels", []))
    if drug_labels > 0:
        details.append(f"{drug_labels} drug label(s)")
    
    adverse_events = len(data.get("adverse_events", []))
    if adverse_events > 0:
        details.append(f"{adverse_events} adverse event(s)")
    
    enforcement = len(data.get("enforcement_reports", []))
    if enforcement > 0:
        details.append(f"{enforcement} enforcement report(s)")
    
    if not details:
        return "No FDA data found"
    
    return ", ".join(details)


if __name__ == "__main__":
    import uvicorn
    from dotenv import load_dotenv
    import os
    
    load_dotenv()
    port = int(os.getenv("NCT_SERVICE_PORT", "9002"))
    
    logger.info(f"Starting NCT Lookup API on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)