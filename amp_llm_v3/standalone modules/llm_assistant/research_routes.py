"""
Research Assistant Routes for Chat Service (Port 9001)
======================================================

Adds research assistant functionality to the main chat service.
Integrates with NCT Lookup service (port 9002) for automatic data fetching.
"""
import logging
import json
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import aiohttp
import asyncio

# Setup logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/research", tags=["research"])

# ============================================================================
# Configuration
# ============================================================================

class ResearchConfig:
    """Research assistant configuration"""
    NCT_SERVICE_URL = "http://localhost:9002"
    OUTPUT_DIR = Path("output")
    PROMPTS_DIR = Path("prompts")
    
    # Timeouts
    NCT_SEARCH_TIMEOUT = 30  # seconds
    NCT_POLL_MAX_WAIT = 120  # 2 minutes
    NCT_POLL_INTERVAL = 3  # seconds
    ANNOTATION_TIMEOUT = 300  # 5 minutes

config = ResearchConfig()

# Ensure directories exist
config.OUTPUT_DIR.mkdir(exist_ok=True)
config.PROMPTS_DIR.mkdir(exist_ok=True)

# ============================================================================
# Models
# ============================================================================

class AnnotationRequest(BaseModel):
    nct_id: str
    model: str
    temperature: float = 0.15
    auto_fetch: bool = True
    conversation_id: Optional[str] = None  # Reuse existing conversation


class AnnotationResponse(BaseModel):
    nct_id: str
    annotation: str
    model: str
    sources_used: Dict[str, Any]
    status: str
    auto_fetched: bool = False
    conversation_id: str


class FileCheckResponse(BaseModel):
    exists: bool
    nct_id: str
    file: Optional[str] = None
    message: Optional[str] = None

# ============================================================================
# Helper Functions
# ============================================================================

def find_nct_file(nct_id: str) -> Tuple[Path, Dict]:
    """
    Find JSON file containing the specified NCT ID.
    
    Returns:
        Tuple of (file_path, trial_data)
    
    Raises:
        HTTPException: If file not found
    """
    output_dir = config.OUTPUT_DIR
    
    logger.info(f"🔍 Searching for {nct_id} in {output_dir}")
    
    for file in output_dir.glob("*.json"):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check if this file contains the NCT ID
            if isinstance(data, list):
                for item in data:
                    if item.get('nct_id') == nct_id:
                        logger.info(f"✅ Found {nct_id} in {file.name}")
                        return file, item
            elif isinstance(data, dict):
                if data.get('nct_id') == nct_id:
                    logger.info(f"✅ Found {nct_id} in {file.name}")
                    return file, data
                    
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️  Invalid JSON in {file.name}: {e}")
            continue
        except Exception as e:
            logger.warning(f"⚠️  Error reading {file.name}: {e}")
            continue
    
    logger.error(f"❌ {nct_id} not found in any JSON files")
    raise HTTPException(
        status_code=404,
        detail=f"No JSON file found for NCT ID: {nct_id}"
    )


async def fetch_nct_data(nct_id: str) -> Dict[str, Any]:
    """
    Automatically fetch NCT data using the NCT Lookup service (port 9002).
    
    Returns:
        Trial data dictionary
    """
    logger.info(f"🌐 Auto-fetching data for {nct_id} from NCT service")
    
    # Check if NCT service is available
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                f"{config.NCT_SERVICE_URL}/health",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status != 200:
                    raise HTTPException(
                        status_code=503,
                        detail="NCT Lookup service not available on port 9002"
                    )
                logger.info("✅ NCT Lookup service is available")
        except aiohttp.ClientConnectorError:
            raise HTTPException(
                status_code=503,
                detail="Cannot connect to NCT Lookup service on port 9002. "
                       "Make sure it's running."
            )
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=503,
                detail="NCT Lookup service timeout on port 9002"
            )
    
    # Initiate search
    async with aiohttp.ClientSession() as session:
        try:
            logger.info(f"📡 Initiating search for {nct_id}")
            search_url = f"{config.NCT_SERVICE_URL}/api/nct/search/{nct_id}"
            
            async with session.post(
                search_url,
                json={"include_extended": False},  # Core sources only for speed
                timeout=aiohttp.ClientTimeout(total=config.NCT_SEARCH_TIMEOUT)
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise HTTPException(
                        status_code=503,
                        detail=f"Failed to initiate NCT search: {error_text}"
                    )
                
                search_data = await resp.json()
                job_id = search_data.get("job_id")
                
                if not job_id:
                    raise HTTPException(
                        status_code=503,
                        detail="No job ID returned from NCT search"
                    )
            
            logger.info(f"✅ Search initiated, job_id: {job_id}")
            
            # Poll for results
            elapsed = 0
            while elapsed < config.NCT_POLL_MAX_WAIT:
                await asyncio.sleep(config.NCT_POLL_INTERVAL)
                elapsed += config.NCT_POLL_INTERVAL
                
                status_url = f"{config.NCT_SERVICE_URL}/api/nct/status/{job_id}"
                async with session.get(status_url) as resp:
                    if resp.status == 200:
                        status_data = await resp.json()
                        
                        if status_data.get("status") == "completed":
                            logger.info(f"✅ Search completed after {elapsed}s")
                            
                            # Get results
                            results_url = f"{config.NCT_SERVICE_URL}/api/nct/results/{job_id}"
                            async with session.get(results_url) as results_resp:
                                if results_resp.status == 200:
                                    trial_data = await results_resp.json()
                                    
                                    # Save to output directory
                                    output_file = config.OUTPUT_DIR / f"{nct_id}_auto_fetched.json"
                                    with open(output_file, 'w', encoding='utf-8') as f:
                                        json.dump(trial_data, f, indent=2)
                                    logger.info(f"💾 Saved auto-fetched data to {output_file}")
                                    
                                    return trial_data
                                else:
                                    raise HTTPException(
                                        status_code=503,
                                        detail="Failed to retrieve NCT results"
                                    )
                        
                        elif status_data.get("status") == "failed":
                            error = status_data.get("error", "Unknown error")
                            raise HTTPException(
                                status_code=503,
                                detail=f"NCT search failed: {error}"
                            )
                        
                        # Still processing, continue polling
                        logger.debug(f"⏳ Still processing... ({elapsed}s elapsed)")
            
            # Timeout
            raise HTTPException(
                status_code=504,
                detail=f"NCT search timed out after {config.NCT_POLL_MAX_WAIT}s"
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Auto-fetch error: {e}", exc_info=True)
            raise HTTPException(
                status_code=503,
                detail=f"Failed to fetch NCT data: {str(e)}"
            )


def generate_annotation_prompt(trial_data: Dict[str, Any], nct_id: str) -> str:
    """
    Generate annotation prompt from trial data.
    This is a simplified version - you can integrate your full PromptGenerator here.
    """
    sources = trial_data.get("sources", {})
    metadata = trial_data.get("metadata", {})
    
    # Build comprehensive prompt
    prompt = f"""# Clinical Trial Annotation Task

**NCT ID:** {nct_id}

You are a Clinical Trial Data Annotation Specialist. Extract structured information from the clinical trial data provided below.

## OUTPUT FORMAT

Format your response EXACTLY like this (use actual data, NOT placeholders):

NCT Number: {nct_id}
Study Title: [Extract from data]
Study Status: [RECRUITING/COMPLETED/etc]
Brief Summary: [Extract from data]
Conditions: [List conditions]
Interventions/Drug: [List interventions]
Phases: [PHASE1/PHASE2/etc]
Enrollment: [Number]
Start Date: [YYYY-MM-DD]
Completion Date: [YYYY-MM]
Classification: [AMP/Other]

  Evidence: [Explain classification]
Delivery Mode: [Injection/Infusion/Topical/Oral/Other]
Sequence: [If peptide, provide sequence]
DRAMP Name: [If found in DRAMP]

  Evidence: [Cite evidence]
Study IDs: [PMC:ID, PMID:ID, etc]
Outcome: [Positive/Withdrawn/Terminated/Failed/Active/Unknown]
Reason for Failure: [If applicable]
Subsequent Trial IDs: [If any]

  Evidence: [Cite evidence]
Peptide: [True/False]
Comments: [Additional notes]

## CRITICAL RULES

1. Use ACTUAL data from the trial, NOT placeholder text
2. Do NOT wrap response in markdown code blocks (no ```)
3. Write values directly without brackets [ ]
4. For missing data, write exactly: N/A
5. Use EXACT values from validation lists

## CLINICAL TRIAL DATA

"""
    
    # Add ClinicalTrials.gov data
    ct_data = sources.get("clinicaltrials") or sources.get("clinical_trials")
    if ct_data:
        prompt += f"\n### ClinicalTrials.gov Data\n\n```json\n{json.dumps(ct_data, indent=2)}\n```\n"
    
    # Add PubMed data
    if sources.get("pubmed"):
        prompt += f"\n### PubMed References\n\n```json\n{json.dumps(sources['pubmed'], indent=2)}\n```\n"
    
    # Add PMC data
    if sources.get("pmc"):
        prompt += f"\n### PMC Full-Text Articles\n\n```json\n{json.dumps(sources['pmc'], indent=2)}\n```\n"
    
    # Add metadata
    if metadata:
        prompt += f"\n### Metadata\n\n```json\n{json.dumps(metadata, indent=2)}\n```\n"
    
    prompt += "\n\n## NOW: Extract the structured annotation following the format exactly.\n"
    
    return prompt


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/health")
async def research_health():
    """Health check for research assistant"""
    return {
        "status": "healthy",
        "service": "Research Assistant (integrated with chat service)",
        "nct_service": config.NCT_SERVICE_URL,
        "auto_fetch": "enabled"
    }


@router.get("/files/{nct_id}", response_model=FileCheckResponse)
async def check_file_exists(nct_id: str):
    """
    Check if a JSON file exists for the given NCT ID.
    """
    nct_id = nct_id.strip().upper()
    logger.info(f"🔍 Checking for file: {nct_id}")
    
    try:
        file_path, trial_data = find_nct_file(nct_id)
        return FileCheckResponse(
            exists=True,
            file=str(file_path.name),
            nct_id=nct_id
        )
    except HTTPException as e:
        logger.warning(f"⚠️  File not found: {e.detail}")
        return FileCheckResponse(
            exists=False,
            nct_id=nct_id,
            message=e.detail
        )


@router.post("/annotate", response_model=AnnotationResponse)
async def annotate_trial(request: AnnotationRequest):
    """
    Annotate a clinical trial based on NCT ID.
    
    This endpoint:
    1. Checks for existing data or auto-fetches from NCT service (port 9002)
    2. Generates an annotation prompt
    3. Uses the chat service's existing LLM integration (via internal function)
    4. Returns the structured annotation
    
    Note: This uses the chat service's session manager to communicate with the LLM.
    """
    from assistant_config import config as chat_config
    from assistant import ChatAssistant  # Import from same module
    
    try:
        nct_id = request.nct_id.strip().upper()
        logger.info(f"🔬 Starting annotation for {nct_id} with model {request.model}")
        
        auto_fetched = False
        
        # Step 1: Get trial data (existing or auto-fetch)
        logger.info(f"📁 Step 1: Looking for trial data for {nct_id}")
        try:
            json_file, trial_data = find_nct_file(nct_id)
            logger.info(f"✅ Found existing file: {json_file.name}")
        except HTTPException:
            # File not found
            if not request.auto_fetch:
                raise HTTPException(
                    status_code=404,
                    detail=f"No JSON file found for {nct_id} and auto_fetch is disabled"
                )
            
            # Auto-fetch the data
            logger.info(f"📥 Step 1b: Auto-fetching trial data for {nct_id}")
            trial_data = await fetch_nct_data(nct_id)
            auto_fetched = True
            logger.info(f"✅ Successfully auto-fetched data for {nct_id}")
        
        # Step 2: Generate prompt
        logger.info(f"📝 Step 2: Generating annotation prompt")
        prompt = generate_annotation_prompt(trial_data, nct_id)
        logger.info(f"✅ Generated prompt ({len(prompt)} characters)")
        
        # Save prompt for debugging
        try:
            prompt_file = config.PROMPTS_DIR / f"{nct_id}_annotation.txt"
            with open(prompt_file, 'w', encoding='utf-8') as f:
                f.write(prompt)
            logger.info(f"💾 Saved prompt to: {prompt_file}")
        except Exception as e:
            logger.warning(f"⚠️  Could not save prompt: {e}")
        
        # Step 3: Send to LLM using chat service's assistant
        logger.info(f"🤖 Step 3: Sending to LLM ({request.model})")
        
        # Initialize chat assistant (uses existing Ollama connection)
        chat_assistant = ChatAssistant()
        
        # Create or use existing conversation
        if request.conversation_id:
            conversation_id = request.conversation_id
            logger.info(f"♻️  Reusing conversation {conversation_id}")
        else:
            # Create new conversation
            conversation_id = chat_assistant.create_conversation(request.model)
            logger.info(f"🆕 Created new conversation {conversation_id}")
        
        # Send message and get response
        response = await chat_assistant.send_message(
            conversation_id=conversation_id,
            message=prompt,
            temperature=request.temperature
        )
        
        annotation = response["message"]["content"]
        logger.info(f"✅ Received annotation ({len(annotation)} characters)")
        
        # Step 4: Return structured response
        return AnnotationResponse(
            nct_id=nct_id,
            annotation=annotation,
            model=request.model,
            sources_used=trial_data.get("sources", {}),
            status="success",
            auto_fetched=auto_fetched,
            conversation_id=conversation_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Annotation error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Annotation error: {str(e)}"
        )


# ============================================================================
# Optional: Batch annotation endpoint
# ============================================================================

@router.post("/batch-annotate")
async def batch_annotate(nct_ids: list[str], model: str, temperature: float = 0.15):
    """
    Annotate multiple trials in batch.
    Returns list of results with successes and failures.
    """
    results = []
    
    for nct_id in nct_ids:
        try:
            request = AnnotationRequest(
                nct_id=nct_id,
                model=model,
                temperature=temperature,
                auto_fetch=True
            )
            result = await annotate_trial(request)
            results.append({
                "nct_id": nct_id,
                "status": "success",
                "data": result.dict()
            })
        except Exception as e:
            results.append({
                "nct_id": nct_id,
                "status": "failed",
                "error": str(e)
            })
            logger.error(f"❌ Failed to annotate {nct_id}: {e}")
    
    return {
        "total": len(nct_ids),
        "successful": sum(1 for r in results if r["status"] == "success"),
        "failed": sum(1 for r in results if r["status"] == "failed"),
        "results": results
    }