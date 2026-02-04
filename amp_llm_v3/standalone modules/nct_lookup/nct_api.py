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
    python nct_api.py  # Uses NCT_SERVICE_PORT from .env

API Endpoints:
    GET /api/registry - List all available APIs
    POST /api/search/{nct_id}
    GET /api/search/{nct_id}/status
    GET /api/results/{nct_id}
    POST /api/results/{nct_id}/check-duplicate - Check if file exists
    POST /api/results/{nct_id}/save - Save results with duplicate handling

UPDATED: Now loads all port configuration from .env file.
"""

from pathlib import Path
from dotenv import load_dotenv
import os

# Load environment variables from .env file
# Look in parent directories for webapp/.env
current_dir = Path(__file__).parent
for parent in [current_dir, current_dir.parent, current_dir.parent.parent]:
    env_file = parent / "webapp" / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        break
    env_file = parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        break
else:
    load_dotenv()  # Try default locations

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncio
import json
import logging
import re

# Port configuration from .env
NCT_SERVICE_PORT = int(os.getenv("NCT_SERVICE_PORT", "9002"))
MAIN_SERVER_PORT = int(os.getenv("MAIN_SERVER_PORT", "9000"))

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
        f"http://localhost:{NCT_SERVICE_PORT}",
        f"http://127.0.0.1:{NCT_SERVICE_PORT}",
        f"http://localhost:{MAIN_SERVER_PORT}",
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

        # Clean empty values from results before saving
        cleaned_results = clean_empty_values(results)

        # Save results to temporary location (will be renamed on save)
        results_dir = Path("results")
        results_dir.mkdir(exist_ok=True)

        output_file = results_dir / f"{nct_id}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(cleaned_results, f, indent=2, ensure_ascii=False)
        
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


# ============================================================================
# JSON Cleaning - Remove Empty/Null Values
# ============================================================================

def clean_empty_values(data: Any, preserve_false: bool = True) -> Any:
    """
    Recursively remove empty/null values from a data structure.

    Args:
        data: The data structure to clean (dict, list, or value)
        preserve_false: If True, keep boolean False values (default: True)

    Returns:
        Cleaned data structure with empty values removed

    Empty values removed:
        - None
        - Empty strings ("")
        - Empty lists ([])
        - Empty dicts ({})
        - Strings that are just whitespace
    """
    if isinstance(data, dict):
        cleaned = {}
        for key, value in data.items():
            cleaned_value = clean_empty_values(value, preserve_false)
            # Keep the value if it's not empty
            if not _is_empty(cleaned_value, preserve_false):
                cleaned[key] = cleaned_value
        return cleaned

    elif isinstance(data, list):
        cleaned = []
        for item in data:
            cleaned_item = clean_empty_values(item, preserve_false)
            if not _is_empty(cleaned_item, preserve_false):
                cleaned.append(cleaned_item)
        return cleaned

    else:
        return data


def _is_empty(value: Any, preserve_false: bool = True) -> bool:
    """Check if a value should be considered empty."""
    if value is None:
        return True
    if isinstance(value, bool):
        return False if preserve_false else not value
    if isinstance(value, str):
        return len(value.strip()) == 0
    if isinstance(value, (list, dict)):
        return len(value) == 0
    if isinstance(value, (int, float)):
        return False  # Numbers are never empty (0 is valid)
    return False


# ============================================================================
# LLM-Optimized Output Format
# ============================================================================

@app.get("/api/results/{nct_id}/llm")
async def get_llm_optimized_results(nct_id: str, include_tools: bool = True):
    """
    Get search results in an LLM-optimized format.

    This endpoint returns a structured, information-dense format designed for:
    1. Minimal token usage while preserving key information
    2. Clear structure for LLM parsing
    3. Optional tool hints for agentic workflows

    Args:
        nct_id: NCT number
        include_tools: Whether to include tool hints (default: True)

    Returns:
        LLM-optimized data structure
    """
    nct_id = nct_id.upper().strip()

    results_file = Path(f"results/{nct_id}.json")
    if not results_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Results not found for {nct_id}. Run a search first."
        )

    try:
        with open(results_file, 'r', encoding='utf-8') as f:
            raw_results = json.load(f)

        # Clean empty values first
        cleaned = clean_empty_values(raw_results)

        # Transform to LLM-optimized format
        llm_output = _transform_to_llm_format(cleaned, nct_id, include_tools)

        return llm_output

    except Exception as e:
        logger.error(f"Error generating LLM output for {nct_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error generating LLM output: {str(e)}"
        )


def _transform_to_llm_format(data: Dict[str, Any], nct_id: str, include_tools: bool) -> Dict[str, Any]:
    """
    Transform search results into an LLM-optimized format.

    Design principles:
    1. Front-load critical information (trial identity, status, key findings)
    2. Group related data (all literature together, all regulatory together)
    3. Flatten nested structures where possible
    4. Include actionable tool hints for agentic workflows
    """
    metadata = data.get("metadata", {})
    sources = data.get("sources", {})

    # Build the LLM-optimized structure
    output = {
        "trial_summary": {
            "nct_id": nct_id,
            "title": metadata.get("title"),
            "status": metadata.get("status"),
            "condition": metadata.get("condition"),
            "intervention": metadata.get("intervention"),
            "abstract": _truncate(metadata.get("abstract", ""), 500)
        },
        "literature": _extract_literature(sources),
        "regulatory": _extract_regulatory(sources),
        "web_sources": _extract_web_sources(sources),
        "statistics": _generate_stats(sources)
    }

    # Add tool hints for agentic workflows
    if include_tools:
        output["available_actions"] = _generate_tool_hints(output, nct_id)

    # Clean any remaining empty values
    output = clean_empty_values(output)

    return output


def _extract_literature(sources: Dict) -> Dict[str, Any]:
    """Extract and consolidate literature findings."""
    literature = {
        "pubmed_articles": [],
        "pmc_articles": [],
        "europe_pmc": [],
        "semantic_scholar": [],
        "crossref": [],
        "total_publications": 0
    }

    # PubMed
    pubmed_data = sources.get("pubmed", {}).get("data", {})
    if pubmed_data and pubmed_data.get("articles"):
        for article in pubmed_data["articles"][:10]:
            literature["pubmed_articles"].append({
                "pmid": article.get("pmid"),
                "title": article.get("title"),
                "journal": article.get("journal"),
                "year": article.get("year"),
                "authors": article.get("authors", [])[:3]  # First 3 authors
            })

    # PMC
    pmc_data = sources.get("pmc", {}).get("data", {})
    if pmc_data and pmc_data.get("articles"):
        for article in pmc_data["articles"][:10]:
            literature["pmc_articles"].append({
                "pmcid": article.get("pmcid"),
                "title": article.get("title"),
                "journal": article.get("journal"),
                "doi": article.get("doi", [None])[0] if article.get("doi") else None
            })

    # Extended sources
    extended = sources.get("extended", {})

    # Europe PMC
    epmc_data = extended.get("europe_pmc", {}).get("data", {})
    if epmc_data and epmc_data.get("results"):
        for result in epmc_data["results"][:5]:
            literature["europe_pmc"].append({
                "pmid": result.get("pmid"),
                "title": result.get("title"),
                "year": result.get("year"),
                "citations": result.get("citation_count"),
                "open_access": result.get("is_open_access")
            })

    # Semantic Scholar
    ss_data = extended.get("semantic_scholar", {}).get("data", {})
    if ss_data and ss_data.get("results"):
        for result in ss_data["results"][:5]:
            literature["semantic_scholar"].append({
                "title": result.get("title"),
                "year": result.get("year"),
                "citations": result.get("citation_count"),
                "influential_citations": result.get("influential_citations"),
                "open_access_url": result.get("open_access_pdf")
            })

    # CrossRef
    cr_data = extended.get("crossref", {}).get("data", {})
    if cr_data and cr_data.get("results"):
        for result in cr_data["results"][:5]:
            literature["crossref"].append({
                "doi": result.get("doi"),
                "title": result.get("title"),
                "year": result.get("year"),
                "citations": result.get("citation_count"),
                "type": result.get("type")
            })

    # Calculate total
    literature["total_publications"] = (
        len(literature["pubmed_articles"]) +
        len(literature["pmc_articles"]) +
        len(literature["europe_pmc"]) +
        len(literature["semantic_scholar"]) +
        len(literature["crossref"])
    )

    return literature


def _extract_regulatory(sources: Dict) -> Dict[str, Any]:
    """Extract regulatory and safety information."""
    regulatory = {
        "fda_data": {},
        "clinical_trial_data": {}
    }

    # Clinical trial data
    ct_data = sources.get("clinical_trials", {}).get("data", {})
    if ct_data:
        protocol = ct_data.get("protocolSection", {})

        # Extract key regulatory info
        regulatory["clinical_trial_data"] = {
            "phase": _extract_phase(protocol),
            "enrollment": _extract_enrollment(protocol),
            "sponsor": _extract_sponsor(protocol),
            "start_date": _extract_date(protocol, "startDateStruct"),
            "completion_date": _extract_date(protocol, "completionDateStruct"),
            "primary_outcomes": _extract_outcomes(protocol, "primaryOutcomes"),
            "secondary_outcomes": _extract_outcomes(protocol, "secondaryOutcomes")
        }

    # OpenFDA data
    extended = sources.get("extended", {})
    fda_data = extended.get("openfda", {}).get("data", {})
    if fda_data:
        regulatory["fda_data"] = {
            "drug_labels": len(fda_data.get("drug_labels", [])),
            "adverse_events": len(fda_data.get("adverse_events", [])),
            "enforcement_reports": len(fda_data.get("enforcement_reports", [])),
            "label_details": fda_data.get("drug_labels", [])[:3],
            "event_summary": fda_data.get("adverse_events", [])[:3]
        }

    return regulatory


def _extract_web_sources(sources: Dict) -> List[Dict]:
    """Extract web search results."""
    web_results = []
    extended = sources.get("extended", {})

    # DuckDuckGo results
    ddg_data = extended.get("duckduckgo", {}).get("data", {})
    if ddg_data and ddg_data.get("results"):
        for result in ddg_data["results"][:5]:
            web_results.append({
                "source": "duckduckgo",
                "title": result.get("title"),
                "url": result.get("url"),
                "snippet": _truncate(result.get("snippet", ""), 200),
                "relevance": result.get("relevance_score")
            })

    # SerpAPI results (if available)
    serp_data = extended.get("serpapi", {}).get("data", {})
    if serp_data and serp_data.get("results"):
        for result in serp_data["results"][:5]:
            web_results.append({
                "source": "google",
                "title": result.get("title"),
                "url": result.get("url"),
                "snippet": _truncate(result.get("snippet", ""), 200)
            })

    return web_results


def _generate_stats(sources: Dict) -> Dict[str, Any]:
    """Generate summary statistics."""
    stats = {
        "sources_searched": [],
        "sources_with_results": [],
        "total_items_found": 0
    }

    # Core sources
    for source_name in ["clinical_trials", "pubmed", "pmc", "pmc_bioc"]:
        source_data = sources.get(source_name, {})
        if source_data.get("success"):
            stats["sources_searched"].append(source_name)
            count = _count_source_results(source_name, source_data.get("data", {}))
            if count > 0:
                stats["sources_with_results"].append(source_name)
                stats["total_items_found"] += count

    # Extended sources
    extended = sources.get("extended", {})
    for source_name, source_data in extended.items():
        if source_data.get("success"):
            stats["sources_searched"].append(source_name)
            count = source_data.get("data", {}).get("total_found", 0)
            if count > 0:
                stats["sources_with_results"].append(source_name)
                stats["total_items_found"] += count

    return stats


def _generate_tool_hints(output: Dict, nct_id: str) -> List[Dict]:
    """
    Generate tool hints for agentic LLM workflows.

    These hints tell the LLM what actions it can take with the data.
    """
    hints = []

    # Literature-related tools
    lit = output.get("literature", {})
    if lit.get("pubmed_articles"):
        pmids = [a.get("pmid") for a in lit["pubmed_articles"] if a.get("pmid")]
        if pmids:
            hints.append({
                "action": "fetch_full_text",
                "description": "Retrieve full article text from PubMed Central",
                "parameters": {"pmids": pmids[:5]},
                "when_useful": "Need detailed methodology, results, or discussion from papers"
            })

    if lit.get("semantic_scholar"):
        papers_with_pdf = [p for p in lit["semantic_scholar"] if p.get("open_access_url")]
        if papers_with_pdf:
            hints.append({
                "action": "download_open_access",
                "description": "Download open access PDFs for analysis",
                "parameters": {"urls": [p["open_access_url"] for p in papers_with_pdf[:3]]},
                "when_useful": "Need to analyze full paper content"
            })

    # Regulatory-related tools
    reg = output.get("regulatory", {})
    if reg.get("fda_data", {}).get("adverse_events", 0) > 0:
        hints.append({
            "action": "analyze_adverse_events",
            "description": "Deep dive into FDA adverse event reports",
            "parameters": {"nct_id": nct_id},
            "when_useful": "Assessing safety profile or risk analysis"
        })

    # Trial-related tools
    trial = output.get("trial_summary", {})
    if trial.get("status") in ["RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION"]:
        hints.append({
            "action": "get_enrollment_sites",
            "description": "Retrieve list of clinical trial enrollment locations",
            "parameters": {"nct_id": nct_id},
            "when_useful": "Finding where patients can enroll"
        })

    # Citation analysis
    if lit.get("total_publications", 0) > 5:
        hints.append({
            "action": "citation_network_analysis",
            "description": "Analyze citation relationships between papers",
            "parameters": {"nct_id": nct_id},
            "when_useful": "Understanding research landscape and key papers"
        })

    # Always available actions
    hints.append({
        "action": "search_related_trials",
        "description": "Find similar clinical trials",
        "parameters": {
            "condition": trial.get("condition"),
            "intervention": trial.get("intervention")
        },
        "when_useful": "Comparing with other trials or finding alternatives"
    })

    hints.append({
        "action": "generate_summary_report",
        "description": "Create a structured report of all findings",
        "parameters": {"nct_id": nct_id, "format": "markdown"},
        "when_useful": "Need a comprehensive overview document"
    })

    return hints


# Helper functions for LLM output
def _truncate(text: str, max_length: int) -> str:
    """Truncate text to max length, adding ellipsis if needed."""
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."


def _extract_phase(protocol: Dict) -> str:
    """Extract trial phase."""
    try:
        design = protocol.get("designModule", {})
        phases = design.get("phases", [])
        return ", ".join(phases) if phases else None
    except:
        return None


def _extract_enrollment(protocol: Dict) -> int:
    """Extract enrollment count."""
    try:
        design = protocol.get("designModule", {})
        enrollment = design.get("enrollmentInfo", {})
        return enrollment.get("count")
    except:
        return None


def _extract_sponsor(protocol: Dict) -> str:
    """Extract lead sponsor."""
    try:
        sponsor = protocol.get("sponsorCollaboratorsModule", {})
        lead = sponsor.get("leadSponsor", {})
        return lead.get("name")
    except:
        return None


def _extract_date(protocol: Dict, date_field: str) -> str:
    """Extract a date from protocol."""
    try:
        status = protocol.get("statusModule", {})
        date_struct = status.get(date_field, {})
        return date_struct.get("date")
    except:
        return None


def _extract_outcomes(protocol: Dict, outcome_type: str) -> List[str]:
    """Extract outcome measures."""
    try:
        outcomes_mod = protocol.get("outcomesModule", {})
        outcomes = outcomes_mod.get(outcome_type, [])
        return [o.get("measure") for o in outcomes[:3] if o.get("measure")]
    except:
        return []


# ============================================================================
# Updated save endpoint with cleaning
# ============================================================================

@app.post("/api/results/{nct_id}/save-clean", response_model=SaveResponse)
async def save_clean_results(nct_id: str, request: SaveRequest):
    """
    Save search results with empty values removed.

    This endpoint saves a cleaned version of the results JSON,
    removing all null, empty string, empty list, and empty dict values.
    """
    nct_id = nct_id.upper().strip()
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)

    temp_results_file = results_dir / f"{nct_id}.json"
    if not temp_results_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No results found for {nct_id}. Please run a search first."
        )

    try:
        with open(temp_results_file, 'r', encoding='utf-8') as f:
            results = json.load(f)

        # Clean empty values
        cleaned_results = clean_empty_values(results)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error loading results: {str(e)}"
        )

    # Determine target filename
    if request.custom_filename:
        target_filename = f"{request.custom_filename}.json"
    elif request.overwrite:
        target_filename = f"{nct_id}.json"
    else:
        target_filename = get_next_version_filename(nct_id, results_dir)

    target_path = results_dir / target_filename
    was_duplicate = target_path.exists()

    try:
        with open(target_path, 'w', encoding='utf-8') as f:
            json.dump(cleaned_results, f, indent=2, ensure_ascii=False)

        file_size = target_path.stat().st_size

        logger.info(f"Saved cleaned results for {nct_id} to {target_filename}")

        return SaveResponse(
            success=True,
            filename=target_filename,
            filepath=str(target_path.absolute()),
            message=f"Cleaned results saved to {target_filename}",
            size_bytes=file_size,
            was_duplicate=was_duplicate,
            overwritten=request.overwrite and was_duplicate
        )

    except Exception as e:
        logger.error(f"Error saving cleaned results for {nct_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error saving results: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    
    print("=" * 80)
    print(f"🚀 Starting NCT Lookup API on port {NCT_SERVICE_PORT}...")
    print("=" * 80)
    print(f"📚 API Docs: http://localhost:{NCT_SERVICE_PORT}/docs")
    print(f"🔍 Health Check: http://localhost:{NCT_SERVICE_PORT}/health")
    print("-" * 80)
    print(f"✨ Port configuration loaded from .env")
    print(f"   NCT Service: {NCT_SERVICE_PORT}")
    print("=" * 80)
    
    uvicorn.run(app, host="0.0.0.0", port=NCT_SERVICE_PORT)