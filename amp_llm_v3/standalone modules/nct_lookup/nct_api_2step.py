"""
NCT Lookup API - 2-Step Workflow
=================================

FastAPI service with support for 2-step NCT lookup workflow.

Step 1: Core API searches (ClinicalTrials, PubMed, PMC, PMC BioC)
Step 2: Extended API searches with user-selected fields

Maintains backward compatibility with original single-step workflow.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path
import asyncio
import json
import logging

from config import config
from nct_models_extended import (
    Step1Request, Step1Response, Step1Status,
    Step2Request, Step2Response, Step2Status,
    SearchStepStatus, CombinedNCTResults,
    SearchRequest, SearchResponse, SearchStatus  # Legacy models
)
from nct_step1 import NCTStep1Searcher
from nct_step2 import NCTStep2Searcher
from nct_api_registry import APIRegistry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="NCT Lookup API - 2-Step Workflow",
    description="Comprehensive clinical trial literature search with 2-step workflow",
    version="3.0.0",
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

# Global state
search_engine = None
step1_cache: Dict[str, Dict[str, Any]] = {}  # Cache Step 1 results
step1_status_db: Dict[str, Step1Status] = {}
step2_status_db: Dict[str, Step2Status] = {}


@app.on_event("startup")
async def startup_event():
    """Initialize search engine on startup."""
    global search_engine
    
    logger.info("=" * 60)
    logger.info("NCT Lookup API Starting")
    logger.info("=" * 60)
    
    # Import here to avoid circular dependencies
    from nct_core import NCTSearchEngine
    
    search_engine = NCTSearchEngine()
    await search_engine.initialize()
    
    logger.info("✓ Search engine initialized")
    logger.info(f"✓ Configuration loaded from .env")
    logger.info(f"✓ Service running on port {config.NCT_SERVICE_PORT}")
    logger.info(f"✓ Environment: {config.ENVIRONMENT}")
    logger.info("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    if search_engine:
        await search_engine.close()
    logger.info("NCT Lookup API shutdown complete")


# ============================================================================
# Health Check
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "environment": config.ENVIRONMENT,
        "port": config.NCT_SERVICE_PORT,
        "step1_cached": len(step1_cache),
        "active_step1": len([s for s in step1_status_db.values() if s.status == SearchStepStatus.RUNNING]),
        "active_step2": len([s for s in step2_status_db.values() if s.status == SearchStepStatus.RUNNING])
    }


# ============================================================================
# API Registry
# ============================================================================

@app.get("/api/registry")
async def get_api_registry():
    """
    Get the complete API registry.
    
    Returns metadata about all available APIs (core and extended).
    """
    registry_data = APIRegistry.to_dict()
    
    # Add availability status
    for category in ['core', 'extended']:
        for api_data in registry_data[category]:
            api_def = APIRegistry.get_api_by_id(api_data['id'])
            if api_def and api_def.requires_key:
                env_var = api_def.config.get('env_var')
                if env_var == 'SERPAPI_KEY':
                    api_data['available'] = bool(config.SERPAPI_KEY)
                elif env_var == 'NCBI_API_KEY':
                    api_data['available'] = bool(config.NCBI_API_KEY)
                else:
                    api_data['available'] = False
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


# ============================================================================
# STEP 1: Core API Search
# ============================================================================

@app.post("/api/nct/step1/{nct_id}", response_model=Step1Response)
async def execute_step1(
    nct_id: str,
    background_tasks: BackgroundTasks
):
    """
    Execute Step 1: Core API searches.
    
    Searches ClinicalTrials.gov, PubMed, PMC, and PMC BioC.
    Results are cached for use in Step 2.
    
    Args:
        nct_id: NCT identifier (e.g., NCT12345678)
    
    Returns:
        Complete Step 1 results with metadata and all core API results
    """
    # Validate NCT format
    nct_id = nct_id.upper().strip()
    if not nct_id.startswith("NCT") or len(nct_id) != 11:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid NCT format: {nct_id}. Expected: NCT######## (11 chars)"
        )
    
    if not nct_id[3:].isdigit():
        raise HTTPException(
            status_code=400,
            detail=f"Invalid NCT format: {nct_id}. Last 8 characters must be digits"
        )
    
    # Check cache first
    if nct_id in step1_cache:
        cache_age = datetime.utcnow() - datetime.fromisoformat(
            step1_cache[nct_id].get("timestamp")
        )
        if cache_age.seconds < 3600:  # Cache for 1 hour
            logger.info(f"Returning cached Step 1 results for {nct_id}")
            return step1_cache[nct_id]
    
    # Initialize status
    status = Step1Status(
        nct_id=nct_id,
        status=SearchStepStatus.RUNNING,
        progress=0,
        message="Starting Step 1 search",
        created_at=datetime.utcnow()
    )
    step1_status_db[nct_id] = status
    
    # Create Step 1 searcher
    step1_searcher = NCTStep1Searcher(search_engine.clients)
    
    def status_callback(message: str, progress: int):
        """Update status during search"""
        status.message = message
        status.progress = progress
        status.updated_at = datetime.utcnow()
        logger.info(f"Step 1 [{nct_id}]: {progress}% - {message}")
    
    try:
        # Execute Step 1
        logger.info(f"Starting Step 1 for {nct_id}")
        
        results = await step1_searcher.execute_step1(
            nct_id,
            status_callback=status_callback
        )
        
        # Update status
        status.status = SearchStepStatus.COMPLETED
        status.progress = 100
        status.message = "Step 1 complete"
        status.updated_at = datetime.utcnow()
        
        # Cache results
        step1_cache[nct_id] = results
        
        logger.info(f"✓ Step 1 completed for {nct_id}")
        
        return results
        
    except Exception as e:
        logger.error(f"✗ Step 1 failed for {nct_id}: {e}", exc_info=True)
        
        # Update status
        status.status = SearchStepStatus.FAILED
        status.error = str(e)
        status.message = f"Step 1 failed: {str(e)}"
        status.updated_at = datetime.utcnow()
        
        raise HTTPException(
            status_code=500,
            detail=f"Step 1 search failed: {str(e)}"
        )


@app.get("/api/nct/step1/{nct_id}/status", response_model=Step1Status)
async def get_step1_status(nct_id: str):
    """Get Step 1 search status."""
    nct_id = nct_id.upper().strip()
    
    if nct_id not in step1_status_db:
        raise HTTPException(
            status_code=404,
            detail=f"No Step 1 search found for {nct_id}"
        )
    
    return step1_status_db[nct_id]


@app.get("/api/nct/step1/{nct_id}/results", response_model=Step1Response)
async def get_step1_results(nct_id: str):
    """Get cached Step 1 results."""
    nct_id = nct_id.upper().strip()
    
    if nct_id not in step1_cache:
        raise HTTPException(
            status_code=404,
            detail=f"No Step 1 results found for {nct_id}. Execute Step 1 first."
        )
    
    return step1_cache[nct_id]


# ============================================================================
# STEP 2: Extended API Search
# ============================================================================

@app.post("/api/nct/step2/{nct_id}", response_model=Step2Response)
async def execute_step2(
    nct_id: str,
    request: Step2Request,
    background_tasks: BackgroundTasks
):
    """
    Execute Step 2: Extended API searches.
    
    Searches selected extended APIs using user-selected fields from Step 1.
    
    Args:
        nct_id: NCT identifier
        request: Step 2 configuration with selected APIs and fields
    
    Returns:
        Complete Step 2 results with all extended API results
    """
    nct_id = nct_id.upper().strip()
    
    # Validate Step 1 was completed
    if nct_id not in step1_cache:
        raise HTTPException(
            status_code=400,
            detail=f"Step 1 must be completed before Step 2. Execute /api/nct/step1/{nct_id} first."
        )
    
    # Get Step 1 results
    step1_results = step1_cache[nct_id]
    
    # Initialize status
    status = Step2Status(
        nct_id=nct_id,
        status=SearchStepStatus.RUNNING,
        progress=0,
        message="Starting Step 2 search",
        total_searches=0,
        completed_searches=0,
        created_at=datetime.utcnow()
    )
    step2_status_db[nct_id] = status
    
    # Create Step 2 searcher
    step2_searcher = NCTStep2Searcher(search_engine.clients, config)
    
    def status_callback(message: str, progress: int):
        """Update status during search"""
        status.message = message
        status.progress = progress
        status.updated_at = datetime.utcnow()
        logger.info(f"Step 2 [{nct_id}]: {progress}% - {message}")
    
    try:
        logger.info(f"Starting Step 2 for {nct_id}")
        logger.info(f"Selected APIs: {request.selected_apis}")
        logger.info(f"Field selections: {request.field_selections}")
        
        results = await step2_searcher.execute_step2(
            nct_id,
            step1_results,
            request.selected_apis,
            request.field_selections,
            status_callback=status_callback
        )
        
        # Update status
        status.status = SearchStepStatus.COMPLETED
        status.progress = 100
        status.message = "Step 2 complete"
        status.updated_at = datetime.utcnow()
        
        logger.info(f"✓ Step 2 completed for {nct_id}")
        
        return results
        
    except Exception as e:
        logger.error(f"✗ Step 2 failed for {nct_id}: {e}", exc_info=True)
        
        # Update status
        status.status = SearchStepStatus.FAILED
        status.error = str(e)
        status.message = f"Step 2 failed: {str(e)}"
        status.updated_at = datetime.utcnow()
        
        raise HTTPException(
            status_code=500,
            detail=f"Step 2 search failed: {str(e)}"
        )


@app.get("/api/nct/step2/{nct_id}/status", response_model=Step2Status)
async def get_step2_status(nct_id: str):
    """Get Step 2 search status."""
    nct_id = nct_id.upper().strip()
    
    if nct_id not in step2_status_db:
        raise HTTPException(
            status_code=404,
            detail=f"No Step 2 search found for {nct_id}"
        )
    
    return step2_status_db[nct_id]


# ============================================================================
# Combined Results
# ============================================================================

@app.get("/api/nct/combined/{nct_id}", response_model=CombinedNCTResults)
async def get_combined_results(nct_id: str):
    """
    Get combined Step 1 and Step 2 results.
    
    Returns Step 1 results and Step 2 results (if available).
    """
    nct_id = nct_id.upper().strip()
    
    if nct_id not in step1_cache:
        raise HTTPException(
            status_code=404,
            detail=f"No results found for {nct_id}"
        )
    
    step1_results = step1_cache[nct_id]
    step2_results = None
    
    # Get Step 2 results if available
    step2_status = step2_status_db.get(nct_id)
    if step2_status and step2_status.status == SearchStepStatus.COMPLETED:
        # Note: We'd need to cache Step 2 results similar to Step 1
        # For now, return None if not found
        pass
    
    # Generate combined summary
    combined_summary = {
        "nct_id": nct_id,
        "step1_complete": True,
        "step2_complete": step2_results is not None,
        "total_core_results": step1_results.get("summary", {}).get("total_results", 0),
        "total_extended_results": 0 if not step2_results else step2_results.get("summary", {}).get("total_results", 0)
    }
    
    return {
        "nct_id": nct_id,
        "timestamp": datetime.utcnow().isoformat(),
        "step1": step1_results,
        "step2": step2_results,
        "combined_summary": combined_summary
    }


# ============================================================================
# Cache Management
# ============================================================================

@app.delete("/api/nct/cache/{nct_id}")
async def clear_cache(nct_id: str):
    """Clear cached results for a specific NCT ID."""
    nct_id = nct_id.upper().strip()
    
    removed = []
    
    if nct_id in step1_cache:
        del step1_cache[nct_id]
        removed.append("step1_cache")
    
    if nct_id in step1_status_db:
        del step1_status_db[nct_id]
        removed.append("step1_status")
    
    if nct_id in step2_status_db:
        del step2_status_db[nct_id]
        removed.append("step2_status")
    
    return {
        "nct_id": nct_id,
        "cleared": removed,
        "message": f"Cleared {len(removed)} cached items for {nct_id}"
    }


@app.delete("/api/nct/cache")
async def clear_all_cache():
    """Clear all cached results."""
    step1_count = len(step1_cache)
    status1_count = len(step1_status_db)
    status2_count = len(step2_status_db)
    
    step1_cache.clear()
    step1_status_db.clear()
    step2_status_db.clear()
    
    return {
        "message": "All caches cleared",
        "cleared": {
            "step1_cache": step1_count,
            "step1_status": status1_count,
            "step2_status": status2_count
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "nct_api_2step:app",
        host="0.0.0.0",
        port=config.NCT_SERVICE_PORT,
        reload=True
    )