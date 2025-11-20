"""
Chat Service with Annotation Mode Integration (Port 9001)
==========================================================

Integrates:
1. LLM chat functionality
2. Runner service (port 9003) for NCT data fetching
3. JSON parser for extracting annotation-relevant data
"""
import logging
import httpx
import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add the json_parser module to path
sys.path.insert(0, str(Path(__file__).parent.parent / "llm_assistant"))

try:
    from json_parser import ClinicalTrialAnnotationParser
    PARSER_AVAILABLE = True
except ImportError:
    PARSER_AVAILABLE = False
    logging.warning("json_parser module not available - annotation mode will be limited")

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
    title="Chat Service with Annotation",
    description="LLM chat with clinical trial annotation support",
    version="2.0.0",
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

RUNNER_SERVICE_URL = "http://localhost:9003"
OLLAMA_BASE_URL = "http://localhost:11434"

# ============================================================================
# Models
# ============================================================================

class ChatInitRequest(BaseModel):
    model: str
    annotation_mode: bool = False

class ChatMessageRequest(BaseModel):
    conversation_id: str
    message: str
    nct_ids: Optional[List[str]] = None  # For annotation mode
    temperature: Optional[float] = 0.7

class Message(BaseModel):
    role: str
    content: str

class ChatResponse(BaseModel):
    conversation_id: str
    model: str
    message: Message
    annotation_mode: bool = False  # Whether annotation mode was used
    nct_data_used: Optional[List[str]] = None  # NCT IDs that were processed

# ============================================================================
# In-memory conversation storage
# ============================================================================

conversations: Dict[str, Dict[str, Any]] = {}

# ============================================================================
# Helper Functions - NCT Data Management
# ============================================================================

async def get_nct_data_from_runner(nct_ids: List[str]) -> Dict[str, Any]:
    """
    Fetch NCT data from runner service for multiple NCT IDs.
    
    Returns:
        Dict with 'successful', 'failed', and 'data' (list of successful results)
    """
    logger.info(f"📡 Requesting data for {len(nct_ids)} NCT IDs from runner service")
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{RUNNER_SERVICE_URL}/batch-get-data",
                json={"nct_ids": nct_ids}
            )
            
            if response.status_code != 200:
                logger.error(f"❌ Runner service error: {response.status_code}")
                return {
                    "successful": 0,
                    "failed": len(nct_ids),
                    "data": [],
                    "error": f"Runner service returned {response.status_code}"
                }
            
            result = response.json()
            
            # Extract successful data
            successful_data = []
            for item in result.get("results", []):
                if item["status"] == "success":
                    successful_data.append({
                        "nct_id": item["nct_id"],
                        "data": item["data"],
                        "source": item["source"],  # "file" or "fetched"
                        "file_path": item.get("file_path")
                    })
            
            logger.info(f"✅ Retrieved {len(successful_data)}/{len(nct_ids)} NCT datasets")
            
            return {
                "successful": result.get("successful", 0),
                "failed": result.get("failed", 0),
                "data": successful_data
            }
            
    except httpx.TimeoutException:
        logger.error("❌ Runner service timeout")
        return {
            "successful": 0,
            "failed": len(nct_ids),
            "data": [],
            "error": "Runner service timeout (120s)"
        }
    except Exception as e:
        logger.error(f"❌ Error connecting to runner service: {e}")
        return {
            "successful": 0,
            "failed": len(nct_ids),
            "data": [],
            "error": str(e)
        }

def parse_nct_data_for_annotation(nct_data: Dict[str, Any]) -> str:
    """
    Parse NCT JSON data using the ClinicalTrialAnnotationParser.
    
    Args:
        nct_data: The full NCT data dictionary from runner service
        
    Returns:
        Formatted text for LLM annotation
    """
    if not PARSER_AVAILABLE:
        logger.warning("⚠️ JSON parser not available, using raw data")
        return json.dumps(nct_data, indent=2)
    
    try:
        # Create a temporary file for the parser
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
            json.dump(nct_data, tmp, indent=2)
            tmp_path = tmp.name
        
        try:
            # Use the parser
            parser = ClinicalTrialAnnotationParser(tmp_path)
            combined_text = parser.get_combined_annotation_text(trial_index=0)
            return combined_text
        finally:
            # Clean up temp file
            Path(tmp_path).unlink(missing_ok=True)
            
    except Exception as e:
        logger.error(f"❌ Error parsing NCT data: {e}")
        # Fallback to raw JSON
        return json.dumps(nct_data, indent=2)

async def process_annotation_request(nct_ids: List[str]) -> tuple[str, List[str]]:
    """
    Process annotation request for multiple NCT IDs.
    
    Returns:
        (formatted_text_for_llm, list_of_successful_nct_ids)
    """
    logger.info(f"🔬 Processing annotation request for: {', '.join(nct_ids)}")
    
    # Get data from runner
    result = await get_nct_data_from_runner(nct_ids)
    
    if result["failed"] > 0 and result["successful"] == 0:
        error_msg = result.get("error", "Unknown error")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve any NCT data: {error_msg}"
        )
    
    # Process each successful dataset
    formatted_texts = []
    successful_nct_ids = []
    
    for item in result["data"]:
        nct_id = item["nct_id"]
        data = item["data"]
        source = item["source"]
        
        logger.info(f"📄 Processing {nct_id} (source: {source})")
        
        # Parse the data for annotation
        formatted_text = parse_nct_data_for_annotation(data)
        formatted_texts.append(f"\n{'='*80}\nNCT ID: {nct_id} (Data source: {source})\n{'='*80}\n\n{formatted_text}")
        successful_nct_ids.append(nct_id)
    
    # Combine all formatted texts
    combined = "\n\n".join(formatted_texts)
    
    # Add annotation instructions at the beginning
    instructions = f"""
ANNOTATION REQUEST FOR {len(successful_nct_ids)} CLINICAL TRIAL(S)
{'='*80}

Please annotate the following clinical trial(s) with these fields:

• **Classification:** AMP or Other
• **Delivery Mode:** Injection/Infusion, Topical, Oral, or Other
• **Outcome:** Positive, Withdrawn, Terminated, Failed - completed trial, Active, or Unknown
• **Reason for Failure:** Business reasons, Ineffective for purpose, Toxic/unsafe, Due to covid, Recruitment issues, or N/A (if not applicable)
• **Peptide:** True or False

For each trial, provide the annotations in a clear format.

{'='*80}

"""
    
    final_text = instructions + combined
    
    if result["failed"] > 0:
        final_text += f"\n\n⚠️ Note: {result['failed']} NCT ID(s) could not be retrieved.\n"
    
    logger.info(f"✅ Prepared annotation text for {len(successful_nct_ids)} trials")
    
    return final_text, successful_nct_ids

# ============================================================================
# Helper Functions - LLM Communication
# ============================================================================

async def call_ollama(model: str, messages: List[Dict[str, str]], temperature: float = 0.7) -> str:
    """
    Call Ollama API for chat completion.
    
    Args:
        model: Model name
        messages: List of message dicts with 'role' and 'content'
        temperature: Sampling temperature
        
    Returns:
        The model's response text
    """
    logger.info(f"🤖 Calling Ollama with model: {model}")
    
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": temperature
                    }
                }
            )
            
            if response.status_code != 200:
                logger.error(f"❌ Ollama error: {response.status_code}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Ollama returned status {response.status_code}"
                )
            
            result = response.json()
            content = result.get("message", {}).get("content", "")
            
            logger.info(f"✅ Received response from {model}")
            return content
            
    except httpx.TimeoutException:
        logger.error("❌ Ollama timeout")
        raise HTTPException(
            status_code=504,
            detail="LLM request timed out (300s)"
        )
    except Exception as e:
        logger.error(f"❌ Error calling Ollama: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error communicating with LLM: {str(e)}"
        )

# ============================================================================
# Routes
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Chat Service with Annotation",
        "version": "2.0.0",
        "status": "running",
        "features": {
            "chat": "Standard LLM chat",
            "annotation": "Clinical trial annotation with NCT data",
            "parser_available": PARSER_AVAILABLE
        },
        "endpoints": {
            "init": "POST /chat/init",
            "message": "POST /chat/message",
            "models": "GET /models",
            "health": "GET /health"
        }
    }

@app.get("/health")
async def health_check():
    """Health check with service dependencies"""
    
    # Check Ollama
    ollama_connected = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            ollama_connected = response.status_code == 200
    except:
        pass
    
    # Check Runner service
    runner_connected = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{RUNNER_SERVICE_URL}/health")
            runner_connected = response.status_code == 200
    except:
        pass
    
    return {
        "status": "healthy",
        "service": "Chat Service with Annotation",
        "version": "2.0.0",
        "dependencies": {
            "ollama": {
                "url": OLLAMA_BASE_URL,
                "connected": ollama_connected
            },
            "runner_service": {
                "url": RUNNER_SERVICE_URL,
                "connected": runner_connected
            },
            "json_parser": {
                "available": PARSER_AVAILABLE
            }
        },
        "active_conversations": len(conversations)
    }

@app.get("/models")
async def list_models():
    """List available Ollama models"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=500,
                    detail="Could not fetch models from Ollama"
                )
            
            data = response.json()
            models = [model["name"] for model in data.get("models", [])]
            
            return {
                "models": models,
                "count": len(models)
            }
            
    except Exception as e:
        logger.error(f"❌ Error fetching models: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching models: {str(e)}"
        )

@app.post("/chat/init")
async def initialize_chat(request: ChatInitRequest):
    """
    Initialize a new chat conversation.
    
    Args:
        model: Model name to use
        annotation_mode: Whether to enable annotation mode
    """
    import uuid
    
    conversation_id = str(uuid.uuid4())
    
    conversations[conversation_id] = {
        "model": request.model,
        "annotation_mode": request.annotation_mode,
        "messages": [],
        "created_at": None,  # You can add timestamp if needed
    }
    
    logger.info(f"✅ Initialized conversation {conversation_id[:8]}... with {request.model} (annotation: {request.annotation_mode})")
    
    return {
        "conversation_id": conversation_id,
        "model": request.model,
        "annotation_mode": request.annotation_mode
    }

@app.post("/chat/message", response_model=ChatResponse)
async def send_message(request: ChatMessageRequest):
    """
    Send a message in a conversation.
    
    For annotation mode:
    - Provide nct_ids list to annotate specific trials
    - Or provide message with NCT IDs (will be parsed)
    """
    conversation_id = request.conversation_id
    
    if conversation_id not in conversations:
        raise HTTPException(
            status_code=404,
            detail=f"Conversation {conversation_id} not found"
        )
    
    conversation = conversations[conversation_id]
    model = conversation["model"]
    annotation_mode = conversation["annotation_mode"]
    
    # Handle annotation mode
    if annotation_mode:
        logger.info(f"🔬 Annotation mode message received")
        
        # Extract NCT IDs - either from explicit list or from message text
        nct_ids = request.nct_ids
        
        if not nct_ids:
            # Try to parse NCT IDs from message
            import re
            nct_pattern = r'NCT\d{8}'
            nct_ids = re.findall(nct_pattern, request.message.upper())
            logger.info(f"📝 Extracted {len(nct_ids)} NCT IDs from message: {nct_ids}")
        
        if not nct_ids:
            raise HTTPException(
                status_code=400,
                detail="No NCT IDs provided. Please provide NCT IDs either in the nct_ids field or in the message text (e.g., NCT12345678)"
            )
        
        # Get and parse NCT data
        try:
            annotation_text, successful_nct_ids = await process_annotation_request(nct_ids)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Annotation processing error: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error processing annotation request: {str(e)}"
            )
        
        # Build messages for LLM
        messages = conversation["messages"].copy()
        messages.append({
            "role": "user",
            "content": annotation_text
        })
        
        # Get LLM response
        response_content = await call_ollama(model, messages, request.temperature or 0.15)
        
        # Save to conversation history
        conversation["messages"].append({
            "role": "user",
            "content": f"Annotate: {', '.join(successful_nct_ids)}"
        })
        conversation["messages"].append({
            "role": "assistant",
            "content": response_content
        })
        
        return ChatResponse(
            conversation_id=conversation_id,
            model=model,
            message=Message(role="assistant", content=response_content),
            annotation_mode=True,
            nct_data_used=successful_nct_ids
        )
    
    # Regular chat mode
    else:
        logger.info(f"💬 Regular chat message received")
        
        # Build messages
        messages = conversation["messages"].copy()
        messages.append({
            "role": "user",
            "content": request.message
        })
        
        # Get LLM response
        response_content = await call_ollama(model, messages, request.temperature or 0.7)
        
        # Save to conversation history
        conversation["messages"].append({
            "role": "user",
            "content": request.message
        })
        conversation["messages"].append({
            "role": "assistant",
            "content": response_content
        })
        
        return ChatResponse(
            conversation_id=conversation_id,
            model=model,
            message=Message(role="assistant", content=response_content),
            annotation_mode=False
        )

@app.delete("/chat/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation"""
    if conversation_id in conversations:
        del conversations[conversation_id]
        logger.info(f"🗑️ Deleted conversation {conversation_id[:8]}...")
        return {"status": "deleted"}
    else:
        raise HTTPException(status_code=404, detail="Conversation not found")

@app.get("/chat/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Get conversation details"""
    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return conversations[conversation_id]

# ============================================================================
# Run standalone
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    print("=" * 80)
    print("🚀 Starting Chat Service with Annotation Mode")
    print("=" * 80)
    print(f"🤖 Ollama: {OLLAMA_BASE_URL}")
    print(f"🏃 Runner Service: {RUNNER_SERVICE_URL}")
    print(f"📊 JSON Parser: {'Available ✅' if PARSER_AVAILABLE else 'Not Available ⚠️'}")
    print(f"📚 Docs: http://localhost:9001/docs")
    print("=" * 80)
    
    uvicorn.run(app, host="0.0.0.0", port=9001, reload=True)