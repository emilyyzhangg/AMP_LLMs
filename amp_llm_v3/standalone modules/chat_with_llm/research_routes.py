"""
Research Assistant Routes - Integrated with Chat Service
=========================================================

Clinical trial annotation endpoints that use the chat service's LLM connection.
"""
import logging
import httpx
from typing import Optional
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/research", tags=["research"])

# ============================================================================
# Configuration
# ============================================================================

try:
    from assistant_config import config
except ImportError:
    # Fallback config
    class Config:
        OLLAMA_HOST = "localhost"
        OLLAMA_PORT = 11434
        @property
        def OLLAMA_BASE_URL(self):
            return f"http://{self.OLLAMA_HOST}:{self.OLLAMA_PORT}"
    config = Config()

NCT_SERVICE_URL = "http://localhost:9002"

# ============================================================================
# Models
# ============================================================================

class AnnotationRequest(BaseModel):
    nct_id: str
    model: str = "llama3.2"
    temperature: float = 0.15
    auto_fetch: bool = True

class AnnotationResponse(BaseModel):
    nct_id: str
    status: str
    annotation: str
    model: str
    sources_used: dict
    auto_fetched: bool = False

# ============================================================================
# Helper Functions
# ============================================================================

def find_nct_file(nct_id: str):
    """Find the JSON file for a given NCT ID."""
    results_dir = Path(__file__).parent / "results"
    
    if not results_dir.exists():
        logger.warning(f"Results directory not found: {results_dir}")
        return None, None
    
    # Look for exact match first
    exact_file = results_dir / f"{nct_id}.json"
    if exact_file.exists():
        logger.info(f"Found exact file: {exact_file}")
        import json
        with open(exact_file, 'r') as f:
            return str(exact_file), json.load(f)
    
    # Look for versioned files
    import glob
    pattern = str(results_dir / f"{nct_id}_v*.json")
    files = sorted(glob.glob(pattern), reverse=True)
    
    if files:
        logger.info(f"Found versioned file: {files[0]}")
        import json
        with open(files[0], 'r') as f:
            return files[0], json.load(f)
    
    logger.warning(f"No file found for {nct_id}")
    return None, None

async def fetch_trial_data(nct_id: str) -> Optional[dict]:
    """Fetch trial data from NCT service."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Initiate search
            response = await client.post(
                f"{NCT_SERVICE_URL}/api/nct/search/{nct_id}",
                json={"include_extended": False}
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to initiate search: {response.status_code}")
                return None
            
            data = response.json()
            job_id = data.get("job_id")
            
            if not job_id:
                logger.error("No job_id returned from search")
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
                        return results_response.json()
                
                elif status_data.get("status") == "failed":
                    logger.error(f"Search failed: {status_data.get('error')}")
                    return None
            
            logger.error("Search timed out")
            return None
            
    except Exception as e:
        logger.error(f"Error fetching trial data: {e}")
        return None

def generate_annotation_prompt(trial_data: dict, nct_id: str) -> str:
    """Generate annotation prompt from trial data."""
    
    # Extract metadata
    metadata = trial_data.get("metadata", {})
    sources = trial_data.get("sources", {})
    
    title = metadata.get("title", "Unknown")
    status = metadata.get("status", "Unknown")
    condition = metadata.get("condition", "Unknown")
    intervention = metadata.get("intervention", "Unknown")
    
    prompt = f"""You are an expert clinical trial annotator specializing in antimicrobial peptide research.

Analyze the following clinical trial and provide a structured annotation.

TRIAL INFORMATION:
==================
NCT ID: {nct_id}
Title: {title}
Status: {status}
Condition: {condition}
Intervention: {intervention}

TASK:
=====
Provide a comprehensive annotation of this clinical trial including:

1. **Trial Classification**
   - Is this an antimicrobial peptide trial? (Yes/No)
   - Type of intervention (drug, device, procedure, etc.)
   - Phase of trial

2. **Scientific Assessment**
   - Primary objective
   - Study design
   - Key endpoints
   - Expected outcomes

3. **Peptide Analysis** (if applicable)
   - Peptide sequence (if mentioned)
   - Mechanism of action
   - Target pathogens
   - Delivery method

4. **Clinical Relevance**
   - Potential impact on antimicrobial resistance
   - Novel aspects
   - Limitations

5. **Data Quality**
   - Completeness of available data
   - Number of sources found
   - Reliability assessment

AVAILABLE DATA SOURCES:
=======================
"""
    
    # Add source information
    for source_name, source_data in sources.items():
        if source_name == "extended":
            continue
        if source_data and source_data.get("success"):
            prompt += f"- {source_name}: Available\n"
    
    prompt += "\nProvide your annotation in a clear, structured format."
    
    return prompt

async def call_llm(prompt: str, model: str, temperature: float = 0.15) -> str:
    """Call Ollama LLM with the given prompt."""
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{config.OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "temperature": temperature,
                    "stream": False
                }
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=503,
                    detail=f"Ollama error: {response.text}"
                )
            
            data = response.json()
            return data.get("response", "")
            
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to Ollama at {config.OLLAMA_BASE_URL}"
        )
    except Exception as e:
        logger.error(f"LLM call error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Routes
# ============================================================================

@router.get("/health")
async def health_check():
    """Health check for research assistant."""
    return {
        "status": "healthy",
        "service": "Research Assistant (integrated with chat service)",
        "nct_service": NCT_SERVICE_URL,
        "auto_fetch": "enabled"
    }

@router.post("/annotate", response_model=AnnotationResponse)
async def annotate_trial(request: AnnotationRequest):
    """
    Annotate a clinical trial using AI.
    
    Steps:
    1. Find trial data (local file or auto-fetch from NCT service)
    2. Generate annotation prompt
    3. Call LLM for annotation
    4. Return structured annotation
    """
    try:
        nct_id = request.nct_id.strip().upper()
        logger.info(f"🔬 Starting annotation for {nct_id} with model {request.model}")
        
        auto_fetched = False
        
        # Step 1: Get trial data
        logger.info(f"📁 Step 1: Looking for trial data for {nct_id}")
        json_file, trial_data = find_nct_file(nct_id)
        
        if not trial_data and request.auto_fetch:
            logger.info(f"📡 File not found, auto-fetching from NCT service...")
            trial_data = await fetch_trial_data(nct_id)
            auto_fetched = True
            
            if not trial_data:
                raise HTTPException(
                    status_code=404,
                    detail=f"Could not find or fetch data for {nct_id}. "
                           f"Try running NCT Lookup first or check if NCT service is running."
                )
        elif not trial_data:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for {nct_id}. Run NCT Lookup first or enable auto_fetch."
            )
        
        logger.info(f"✅ Trial data obtained (auto_fetched={auto_fetched})")
        
        # Step 2: Generate prompt
        logger.info("📝 Step 2: Generating annotation prompt")
        prompt = generate_annotation_prompt(trial_data, nct_id)
        logger.info(f"Generated prompt ({len(prompt)} characters)")
        
        # Step 3: Call LLM
        logger.info(f"🤖 Step 3: Calling LLM ({request.model})")
        annotation = await call_llm(prompt, request.model, request.temperature)
        logger.info(f"✅ Annotation complete ({len(annotation)} characters)")
        
        # Determine sources used
        sources_used = {}
        if isinstance(trial_data, dict) and "sources" in trial_data:
            sources = trial_data["sources"]
            for source_name, source_data in sources.items():
                if source_name == "extended":
                    continue
                if source_data and source_data.get("success"):
                    sources_used[source_name] = "available"
        
        return AnnotationResponse(
            nct_id=nct_id,
            status="success",
            annotation=annotation,
            model=request.model,
            sources_used=sources_used,
            auto_fetched=auto_fetched
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Annotation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Annotation failed: {str(e)}"
        )

@router.get("/files/{nct_id}")
async def list_files(nct_id: str):
    """List available files for an NCT ID."""
    nct_id = nct_id.strip().upper()
    results_dir = Path(__file__).parent / "results"
    
    if not results_dir.exists():
        return {"nct_id": nct_id, "files": []}
    
    import glob
    pattern = str(results_dir / f"{nct_id}*.json")
    files = glob.glob(pattern)
    
    return {
        "nct_id": nct_id,
        "files": [Path(f).name for f in files]
    }