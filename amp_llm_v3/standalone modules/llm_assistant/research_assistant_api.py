"""
Research Assistant API Router
Handles NCT annotation workflow with automatic data fetching
"""
import logging
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import aiohttp
from assistant_config import config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from prompt_generator import PromptGenerator
    HAS_PROMPT_GEN = True
    logger.info("✅ PromptGenerator loaded successfully")
except Exception as e:
    logger.warning(f"⚠️  Could not load PromptGenerator: {e}")
    HAS_PROMPT_GEN = False

# ============================================================================
# Initialize FastAPI app
# ============================================================================

app = FastAPI(
    title="LLM Research Assistant API",
    description="Modular service for annotating clinical trials with automatic data fetching",
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

# ============================================================================
# Models
# ============================================================================

class AnnotationRequest(BaseModel):
    nct_id: str
    model: str
    temperature: float = 0.15
    auto_fetch: bool = True  # NEW: automatically fetch if not found


class AnnotationResponse(BaseModel):
    nct_id: str
    annotation: str
    model: str
    sources_used: Dict[str, Any]
    status: str
    auto_fetched: bool = False  # NEW: indicates if data was auto-fetched


class FileCheckResponse(BaseModel):
    exists: bool
    nct_id: str
    file: Optional[str] = None
    message: Optional[str] = None


class AutoFetchProgress(BaseModel):
    """Progress update for auto-fetch"""
    stage: str
    message: str
    progress: int  # 0-100


# ============================================================================
# Helper Functions
# ============================================================================

def get_output_directory() -> Path:
    """Get the output directory path"""
    base_path = Path(__file__).parent
    possible_dirs = [
        base_path / "output",
        base_path.parent / "output",
        base_path.parent.parent / "output",
        base_path.parent.parent / "webapp" / "output",
        Path("output"),
    ]
    
    for dir_path in possible_dirs:
        if dir_path.exists() and dir_path.is_dir():
            logger.info(f"✅ Found output directory: {dir_path}")
            return dir_path
    
    # Create output directory if none exists
    output_dir = base_path.parent.parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"✅ Created output directory: {output_dir}")
    return output_dir


def find_nct_file(nct_id: str) -> Tuple[Path, Dict]:
    """
    Find JSON file containing the specified NCT ID.
    
    Returns:
        Tuple of (file_path, trial_data)
    
    Raises:
        HTTPException: If file not found
    """
    output_dir = get_output_directory()
    
    # Search for the NCT ID in JSON files
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
    Automatically fetch NCT data if it doesn't exist.
    Uses the NCT Lookup service to fetch trial data.
    
    Returns:
        Trial data dictionary
    """
    logger.info(f"🌐 Auto-fetching data for {nct_id}")
    
    # NCT Lookup service should be on port 8000 (main webapp backend)
    # We'll search for it on common ports
    nct_service_urls = [
        "http://localhost:8000",  # Main webapp
        "http://localhost:8003",  # Dedicated NCT service if exists
    ]
    
    nct_service_url = None
    
    # Find active NCT service
    async with aiohttp.ClientSession() as session:
        for url in nct_service_urls:
            try:
                async with session.get(f"{url}/health", timeout=aiohttp.ClientTimeout(total=2)) as resp:
                    if resp.status == 200:
                        nct_service_url = url
                        logger.info(f"✅ Found NCT service at {url}")
                        break
            except:
                continue
    
    if not nct_service_url:
        raise HTTPException(
            status_code=503,
            detail="NCT Lookup service not available. Cannot auto-fetch trial data."
        )
    
    async with aiohttp.ClientSession() as session:
        try:
            # Step 1: Initiate search
            logger.info(f"📡 Initiating search for {nct_id}")
            search_url = f"{nct_service_url}/api/nct/search/{nct_id}"
            
            async with session.post(
                search_url,
                json={
                    "include_extended": False  # Just core sources for speed
                },
                timeout=aiohttp.ClientTimeout(total=30)
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
            
            # Step 2: Poll for results
            import asyncio
            max_wait = 120  # 2 minutes
            poll_interval = 3  # 3 seconds
            elapsed = 0
            
            status_url = f"{nct_service_url}/api/nct/search/{job_id}/status"
            results_url = f"{nct_service_url}/api/nct/results/{job_id}"
            
            while elapsed < max_wait:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
                
                # Check status
                async with session.get(status_url) as resp:
                    if resp.status != 200:
                        continue
                    
                    status_data = await resp.json()
                    status = status_data.get("status")
                    
                    logger.info(f"⏳ Status: {status} ({elapsed}s elapsed)")
                    
                    if status == "completed":
                        # Fetch results
                        async with session.get(results_url) as result_resp:
                            if result_resp.status != 200:
                                raise HTTPException(
                                    status_code=503,
                                    detail="Failed to fetch NCT results"
                                )
                            
                            trial_data = await result_resp.json()
                            logger.info(f"✅ Retrieved trial data for {nct_id}")
                            
                            # Save to output directory
                            await save_trial_data(nct_id, trial_data)
                            
                            return trial_data
                    
                    elif status == "failed":
                        error = status_data.get("error", "Unknown error")
                        raise HTTPException(
                            status_code=503,
                            detail=f"NCT search failed: {error}"
                        )
            
            # Timeout
            raise HTTPException(
                status_code=504,
                detail=f"NCT search timed out after {max_wait} seconds"
            )
            
        except aiohttp.ClientConnectorError:
            raise HTTPException(
                status_code=503,
                detail="Cannot connect to NCT Lookup service"
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Auto-fetch error: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Auto-fetch failed: {str(e)}"
            )


async def save_trial_data(nct_id: str, trial_data: Dict[str, Any]):
    """Save trial data to output directory"""
    output_dir = get_output_directory()
    
    # Create filename
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"nct_{nct_id}_{timestamp}.json"
    filepath = output_dir / filename
    
    # Save data
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(trial_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"💾 Saved trial data to: {filepath}")
    except Exception as e:
        logger.error(f"❌ Failed to save trial data: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save trial data: {str(e)}"
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
            logger.info(f"🔗 Connecting to chat service: {init_url}")
            
            async with session.post(
                init_url,
                json={"model": model},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"❌ Chat init failed: {error_text}")
                    raise HTTPException(
                        status_code=503,
                        detail=f"Failed to initialize chat with {model}: {error_text}"
                    )
                init_data = await resp.json()
                conversation_id = init_data["conversation_id"]
            
            logger.info(f"✅ Initialized conversation {conversation_id} with {model}")
            
        except aiohttp.ClientConnectorError as e:
            logger.error(f"❌ Cannot connect to chat service: {e}")
            raise HTTPException(
                status_code=503,
                detail="Cannot connect to chat service on port 8001. "
                       "Make sure it's running: cd 'standalone modules/chat_with_llm' && "
                       "uvicorn chat_api:app --port 8001 --reload"
            )
        except Exception as e:
            logger.error(f"❌ Chat service error: {e}")
            raise HTTPException(
                status_code=503,
                detail=f"Chat service error: {str(e)}"
            )
        
        # Send annotation request
        try:
            msg_url = f"{chat_service_url}/chat/message"
            logger.info(f"📤 Sending prompt to LLM ({len(prompt)} chars)")
            
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
                    logger.error(f"❌ LLM annotation failed: {error_text}")
                    raise HTTPException(
                        status_code=503,
                        detail=f"LLM annotation failed: {error_text}"
                    )
                response_data = await resp.json()
                annotation = response_data["message"]["content"]
                
                logger.info(f"✅ Received annotation ({len(annotation)} chars)")
                return annotation
                
        except aiohttp.ServerTimeoutError:
            logger.error(f"❌ LLM annotation timed out")
            raise HTTPException(
                status_code=504,
                detail="LLM annotation timed out. Try a smaller trial or different model."
            )
        except Exception as e:
            logger.error(f"❌ LLM communication error: {e}")
            raise HTTPException(
                status_code=503,
                detail=f"LLM communication error: {str(e)}"
            )


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "service": "Research Assistant API",
        "prompt_generator": "available" if HAS_PROMPT_GEN else "unavailable",
        "auto_fetch": "enabled"
    }


@app.get("/files/{nct_id}", response_model=FileCheckResponse)
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


@app.post("/annotate", response_model=AnnotationResponse)
async def annotate_trial(request: AnnotationRequest):
    """
    Annotate a clinical trial based on NCT ID.
    
    Workflow:
    1. Check if JSON file exists
    2. If not exists and auto_fetch=True: Fetch from NCT Lookup
    3. Extract trial data
    4. Generate prompt with prompt_generator.py
    5. Send to LLM for annotation
    6. Return structured annotation
    """
    try:
        nct_id = request.nct_id.strip().upper()
        logger.info(f"🔬 Starting annotation for {nct_id} with model {request.model}")
        
        # Check if prompt generator is available
        if not HAS_PROMPT_GEN:
            logger.error("❌ PromptGenerator not available")
            raise HTTPException(
                status_code=500,
                detail="PromptGenerator not available. Check server logs."
            )
        
        auto_fetched = False
        
        # Step 1: Try to find existing file
        logger.info(f"📁 Step 1: Looking for existing JSON file for {nct_id}")
        try:
            json_file, trial_data = find_nct_file(nct_id)
            logger.info(f"✅ Found existing file: {json_file.name}")
        except HTTPException as e:
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
        
        # Step 2: Generate prompt using PromptGenerator
        logger.info(f"📝 Step 2: Generating extraction prompt")
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
        try:
            prompt_dir = Path(__file__).parent / "prompts"
            prompt_dir.mkdir(exist_ok=True)
            prompt_file = prompt_dir / f"{nct_id}_annotation.txt"
            with open(prompt_file, 'w', encoding='utf-8') as f:
                f.write(prompt)
            logger.info(f"💾 Saved prompt to: {prompt_file}")
        except Exception as e:
            logger.warning(f"⚠️  Could not save prompt: {e}")
        
        # Step 3: Send to LLM
        logger.info(f"🤖 Step 3: Sending to LLM ({request.model})")
        annotation = await send_to_llm(request.model, prompt, request.temperature)
        logger.info(f"✅ Received annotation ({len(annotation)} characters)")
        
        # Step 4: Return structured response
        return AnnotationResponse(
            nct_id=nct_id,
            annotation=annotation,
            model=request.model,
            sources_used=search_results.get("sources", {}),
            status="success",
            auto_fetched=auto_fetched
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
# Standalone App (for testing)
# ============================================================================
@app.get("/")
async def root():
    return {
        "service": "Research Assistant API",
        "status": "running",
        "features": {
            "auto_fetch": "enabled",
            "annotation": "enabled"
        }
    }

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Research Assistant API on port 9002...")
    print("✨ Auto-fetch enabled: Will automatically fetch missing trial data")
    uvicorn.run(app, host="0.0.0.0", port=9002, reload=True)