"""
Research Assistant API
Standalone FastAPI service for clinical trial annotation
"""
import logging
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import aiohttp

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from standalone_modules.llm_assistant.prompt_generator import PromptGenerator
    HAS_PROMPT_GEN = True
    logger.info("✅ PromptGenerator loaded successfully")
except Exception as e:
    logger.warning(f"⚠️  Could not load PromptGenerator: {e}")
    HAS_PROMPT_GEN = False

# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="Research Assistant API",
    description="Clinical trial annotation service",
    version="1.0.0"
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
# Models
# ============================================================================

class AnnotationRequest(BaseModel):
    nct_id: str
    model: str
    temperature: float = 0.15


class AnnotationResponse(BaseModel):
    nct_id: str
    annotation: str
    model: str
    sources_used: Dict[str, Any]
    status: str


class FileCheckResponse(BaseModel):
    exists: bool
    nct_id: str
    file: Optional[str] = None
    message: Optional[str] = None


# ============================================================================
# Helper Functions
# ============================================================================

def find_nct_file(nct_id: str) -> tuple:
    """
    Find JSON file containing the specified NCT ID.
    
    Returns:
        Tuple of (file_path, trial_data)
    """
    # Check multiple possible output directories
    possible_dirs = [
        Path("output"),
        Path("../output"),
        Path("../../output"),
        Path(__file__).parent / "output",
        Path(__file__).parent.parent / "output"
    ]
    
    output_dir = None
    for dir_path in possible_dirs:
        if dir_path.exists():
            output_dir = dir_path
            logger.info(f"Found output directory: {output_dir}")
            break
    
    if not output_dir:
        raise HTTPException(
            status_code=404,
            detail=f"Output directory not found. Run NCT Lookup first."
        )
    
    # Search for the NCT ID in JSON files
    for file in output_dir.glob("*.json"):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check if this file contains the NCT ID
            if isinstance(data, list):
                for item in data:
                    if item.get('nct_id') == nct_id:
                        logger.info(f"Found {nct_id} in {file}")
                        return file, item
            elif isinstance(data, dict):
                if data.get('nct_id') == nct_id:
                    logger.info(f"Found {nct_id} in {file}")
                    return file, data
                    
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in {file}: {e}")
            continue
        except Exception as e:
            logger.warning(f"Error reading {file}: {e}")
            continue
    
    raise HTTPException(
        status_code=404,
        detail=f"No JSON file found for NCT ID: {nct_id}. "
               f"Please run NCT Lookup first to fetch the data."
    )


async def send_to_llm(model: str, prompt: str, temperature: float) -> str:
    """
    Send prompt to LLM via chat service.
    """
    chat_service_url = "http://localhost:8001"
    
    async with aiohttp.ClientSession() as session:
        # Initialize conversation
        try:
            init_url = f"{chat_service_url}/chat/init"
            async with session.post(
                init_url,
                json={"model": model},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise HTTPException(
                        status_code=503,
                        detail=f"Failed to initialize chat with {model}: {error_text}"
                    )
                init_data = await resp.json()
                conversation_id = init_data["conversation_id"]
            
            logger.info(f"Initialized conversation {conversation_id} with {model}")
            
        except aiohttp.ClientConnectorError:
            raise HTTPException(
                status_code=503,
                detail="Cannot connect to chat service. Make sure it's running on port 8001."
            )
        except Exception as e:
            raise HTTPException(
                status_code=503,
                detail=f"Chat service error: {str(e)}"
            )
        
        # Send annotation request
        try:
            msg_url = f"{chat_service_url}/chat/message"
            async with session.post(
                msg_url,
                json={
                    "conversation_id": conversation_id,
                    "message": prompt,
                    "temperature": temperature
                },
                timeout=aiohttp.ClientTimeout(total=300)  # 5 minutes for annotation
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise HTTPException(
                        status_code=503,
                        detail=f"LLM annotation failed: {error_text}"
                    )
                response_data = await resp.json()
                annotation = response_data["message"]["content"]
                
                return annotation
                
        except aiohttp.ServerTimeoutError:
            raise HTTPException(
                status_code=504,
                detail="LLM annotation timed out. Try a smaller trial or different model."
            )
        except Exception as e:
            raise HTTPException(
                status_code=503,
                detail=f"LLM communication error: {str(e)}"
            )


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Research Assistant API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "annotate": "POST /api/research/annotate",
            "check_file": "GET /api/research/files/{nct_id}",
            "health": "GET /health"
        }
    }


@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "prompt_generator": "available" if HAS_PROMPT_GEN else "unavailable"
    }


@app.get("/api/research/files/{nct_id}", response_model=FileCheckResponse)
async def check_file_exists(nct_id: str):
    """
    Check if a JSON file exists for the given NCT ID.
    """
    nct_id = nct_id.strip().upper()
    logger.info(f"Checking for file: {nct_id}")
    
    try:
        file_path, trial_data = find_nct_file(nct_id)
        return FileCheckResponse(
            exists=True,
            file=str(file_path.name),
            nct_id=nct_id
        )
    except HTTPException as e:
        return FileCheckResponse(
            exists=False,
            nct_id=nct_id,
            message=e.detail
        )


@app.post("/api/research/annotate", response_model=AnnotationResponse)
async def annotate_trial(request: AnnotationRequest):
    """
    Annotate a clinical trial based on NCT ID.
    
    Workflow:
    1. Load JSON file from output directory
    2. Extract trial data
    3. Generate prompt with prompt_generator.py
    4. Send to LLM for annotation
    5. Return structured annotation
    """
    try:
        nct_id = request.nct_id.strip().upper()
        logger.info(f"🔬 Starting annotation for {nct_id} with model {request.model}")
        
        # Check if prompt generator is available
        if not HAS_PROMPT_GEN:
            raise HTTPException(
                status_code=500,
                detail="PromptGenerator not available. Check server logs."
            )
        
        # Step 1: Find the JSON file
        logger.info(f"Step 1: Finding JSON file for {nct_id}")
        json_file, trial_data = find_nct_file(nct_id)
        logger.info(f"✅ Found JSON file: {json_file}")
        
        # Step 2: Generate prompt using PromptGenerator
        logger.info(f"Step 2: Generating extraction prompt")
        prompt_gen = PromptGenerator()
        
        # The prompt generator expects search_results format
        search_results = {
            "nct_id": nct_id,
            "sources": trial_data.get("sources", {}),
            "metadata": trial_data.get("metadata", {})
        }
        
        prompt = prompt_gen.generate_extraction_prompt(search_results, nct_id)
        logger.info(f"✅ Generated prompt ({len(prompt)} characters)")
        
        # Optional: Save prompt for debugging
        prompt_dir = Path("prompts")
        prompt_dir.mkdir(exist_ok=True)
        prompt_file = prompt_dir / f"{nct_id}_annotation.txt"
        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(prompt)
        logger.info(f"💾 Saved prompt to: {prompt_file}")
        
        # Step 3: Send to LLM
        logger.info(f"Step 3: Sending to LLM ({request.model})")
        annotation = await send_to_llm(request.model, prompt, request.temperature)
        logger.info(f"✅ Received annotation ({len(annotation)} characters)")
        
        # Step 4: Return structured response
        return AnnotationResponse(
            nct_id=nct_id,
            annotation=annotation,
            model=request.model,
            sources_used=search_results.get("sources", {}),
            status="success"
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
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "research_api:app",
        host="0.0.0.0",
        port=9002,
        reload=True,
        log_level="info"
    )