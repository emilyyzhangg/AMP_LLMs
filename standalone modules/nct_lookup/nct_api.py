"""
NCT Lookup API - Standalone Clinical Trial Search Service
=========================================================

A FastAPI-based service for comprehensive clinical trial literature search.

Features:
- Core databases: ClinicalTrials.gov, PubMed, PMC
- Extended databases: DuckDuckGo, SERP API, Google Scholar, OpenFDA
- JSON output with database tagging
- Summary statistics
- Async processing for performance

Installation:
    pip install fastapi uvicorn aiohttp requests python-dotenv beautifulsoup4

Usage:
    uvicorn nct_api:app --reload --port 8000

API Endpoints:
    POST /api/search/{nct_id}
    GET /api/search/{nct_id}/status
    GET /api/results/{nct_id}
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path
import asyncio
import json
import logging

from nct_core import NCTSearchEngine, SearchConfig
from nct_models import SearchRequest, SearchResponse, SearchStatus, SearchSummary

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="NCT Lookup API",
    description="Comprehensive clinical trial literature search service",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Global search engine instance
search_engine = NCTSearchEngine()

# In-memory status tracking (use Redis/database in production)
search_status_db: Dict[str, SearchStatus] = {}


@app.on_event("startup")
async def startup_event():
    """Initialize search engine on startup."""
    logger.info("Starting NCT Lookup API")
    await search_engine.initialize()


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
        "version": "1.0.0",
        "status": "operational",
        "endpoints": {
            "search": "POST /api/search/{nct_id}",
            "status": "GET /api/search/{nct_id}/status",
            "results": "GET /api/results/{nct_id}"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "active_searches": len([s for s in search_status_db.values() if s.status == "running"])
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
        request: Search configuration
        
    Returns:
        Search response with job ID and initial status
    """
    # Validate NCT format
    nct_id = nct_id.upper().strip()
    if not nct_id.startswith("NCT") or len(nct_id) != 11:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid NCT format: {nct_id}. Expected: NCT########"
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
    
    logger.info(f"Queued search for {nct_id}")
    
    return SearchResponse(
        job_id=nct_id,
        status="queued",
        message=f"Search initiated for {nct_id}",
        created_at=status.created_at
    )


@app.get("/api/search/{nct_id}/status")
async def get_search_status(nct_id: str):
    """
    Get current search status.
    
    Args:
        nct_id: NCT number
        
    Returns:
        Current search status and progress
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
        "created_at": status.created_at.isoformat(),
        "updated_at": status.updated_at.isoformat() if status.updated_at else None,
        "error": status.error
    }


@app.get("/api/results/{nct_id}")
async def get_search_results(
    nct_id: str, 
    summary_only: bool = False,
    save_to_file: bool = False
):
    """
    Get search results.
    
    Args:
        nct_id: NCT number
        summary_only: If True, return only summary statistics
        save_to_file: If True, save results to file with NCT number as filename
        
    Returns:
        Search results or summary with optional file save confirmation
    """
    nct_id = nct_id.upper().strip()
    
    # Check status
    if nct_id not in search_status_db:
        raise HTTPException(
            status_code=404,
            detail=f"No search found for {nct_id}"
        )
    
    status = search_status_db[nct_id]
    
    if status.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Search not completed. Current status: {status.status}"
        )
    
    # Load results
    results_file = Path(f"results/{nct_id}.json")
    if not results_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Results file not found for {nct_id}"
        )
    
    with open(results_file, 'r') as f:
        results = json.load(f)
    
    # Handle save to file request
    if save_to_file:
        # Create user downloads directory if it doesn't exist
        downloads_dir = Path("downloads")
        downloads_dir.mkdir(exist_ok=True)
        
        # Save with NCT number as filename
        user_file = downloads_dir / f"{nct_id}.json"
        with open(user_file, 'w') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        # Return response with file info
        response_data = _generate_summary(results) if summary_only else results
        
        # Add file save metadata
        if isinstance(response_data, dict):
            response_data["file_saved"] = {
                "saved": True,
                "filename": f"{nct_id}.json",
                "filepath": str(user_file.absolute()),
                "size_bytes": user_file.stat().st_size
            }
        
        return response_data
    
    # Return summary or full results
    if summary_only:
        return _generate_summary(results)
    else:
        return results


@app.post("/api/results/{nct_id}/save")
async def save_results_to_file(nct_id: str):
    """
    Save search results to downloads folder with NCT number as filename.
    
    Args:
        nct_id: NCT number
        
    Returns:
        File save confirmation with path and metadata
    """
    nct_id = nct_id.upper().strip()
    
    # Check status
    if nct_id not in search_status_db:
        raise HTTPException(
            status_code=404,
            detail=f"No search found for {nct_id}"
        )
    
    status = search_status_db[nct_id]
    
    if status.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Search not completed. Current status: {status.status}"
        )
    
    # Load results from internal storage
    results_file = Path(f"results/{nct_id}.json")
    if not results_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Results file not found for {nct_id}"
        )
    
    with open(results_file, 'r') as f:
        results = json.load(f)
    
    # Create downloads directory
    downloads_dir = Path("downloads")
    downloads_dir.mkdir(exist_ok=True)
    
    # Save with NCT number as filename
    output_file = downloads_dir / f"{nct_id}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Saved results to {output_file}")
    
    # Generate summary for response
    summary = _generate_summary(results)
    
    return {
        "success": True,
        "message": f"Results saved successfully",
        "file": {
            "filename": f"{nct_id}.json",
            "path": str(output_file.absolute()),
            "size_bytes": output_file.stat().st_size,
            "size_human": _format_file_size(output_file.stat().st_size)
        },
        "summary": summary
    }


@app.get("/api/results/{nct_id}/download")
async def download_results_file(nct_id: str):
    """
    Download results as a file attachment.
    
    Args:
        nct_id: NCT number
        
    Returns:
        File download response
    """
    from fastapi.responses import FileResponse
    
    nct_id = nct_id.upper().strip()
    
    # Check if results exist
    results_file = Path(f"results/{nct_id}.json")
    if not results_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Results file not found for {nct_id}"
        )
    
    # Return file for download
    return FileResponse(
        path=str(results_file),
        media_type='application/json',
        filename=f"{nct_id}.json"
    )


def _format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


@app.delete("/api/results/{nct_id}}")
async def delete_search(nct_id: str):
    """
    Delete search results and status.
    
    Args:
        nct_id: NCT number
        
    Returns:
        Deletion confirmation
    """
    nct_id = nct_id.upper().strip()
    
    # Remove from status db
    if nct_id in search_status_db:
        del search_status_db[nct_id]
    
    # Remove results file
    results_file = Path(f"results/{nct_id}.json")
    if results_file.exists():
        results_file.unlink()
    
    return {
        "message": f"Deleted search data for {nct_id}",
        "nct_id": nct_id
    }


# Internal helper functions

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
        
        # Save results
        results_dir = Path("results")
        results_dir.mkdir(exist_ok=True)
        
        output_file = results_dir / f"{nct_id}.json"
        with open(output_file, 'w') as f:
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
    """Get list of databases to search."""
    databases = ["clinicaltrials", "pubmed", "pmc"]
    
    if request.include_extended:
        if request.databases:
            databases.extend(request.databases)
        else:
            databases.extend(["duckduckgo", "serpapi", "scholar", "openfda"])
    
    return databases


def _generate_summary(results: Dict[str, Any]) -> SearchSummary:
    """Generate summary statistics from results."""
    summary = SearchSummary(
        nct_id=results["nct_id"],
        title=results.get("title", ""),
        status=results.get("status", ""),
        databases_searched=[],
        total_results=0,
        results_by_database={},
        search_timestamp=results.get("timestamp", "")
    )
    
    # Count results per database
    for db_name, db_data in results.get("databases", {}).items():
        if db_data and not db_data.get("error"):
            count = _count_results(db_data)
            summary.databases_searched.append(db_name)
            summary.results_by_database[db_name] = count
            summary.total_results += count
    
    return summary


def _count_results(db_data: Dict[str, Any]) -> int:
    """Count results in database data."""
    # Handle different result structures
    if "results" in db_data:
        return len(db_data["results"])
    elif "pmids" in db_data:
        return len(db_data["pmids"])
    elif "pmcids" in db_data:
        return len(db_data["pmcids"])
    elif "articles" in db_data:
        return len(db_data["articles"])
    return 0


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)