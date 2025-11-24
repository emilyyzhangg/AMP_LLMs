"""
LLM Chat Service with Annotation Support (Port 9001)
====================================================

Chat service that can operate in two modes:
1. Normal chat mode - regular conversation
2. Annotation mode - clinical trial annotation using NCT data from runner service
"""
import logging
import uuid
import httpx
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import io
import csv

try:
    from assistant_config import config
except ImportError:
    # Fallback config
    class ChatConfig:
        OLLAMA_HOST = "localhost"
        OLLAMA_PORT = 11434
        @property
        def OLLAMA_BASE_URL(self):
            return f"http://{self.OLLAMA_HOST}:{self.OLLAMA_PORT}"
        API_VERSION = "3.0.0"
        SERVICE_NAME = "LLM Chat Service"
        CORS_ORIGINS = ["*"]
    config = ChatConfig()

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
    title="LLM Chat Service with Annotation",
    description="Chat and clinical trial annotation service",
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
# Configuration
# ============================================================================

RUNNER_SERVICE_URL = "http://localhost:9003"

# ============================================================================
# In-memory conversation storage
# ============================================================================

conversations: Dict[str, Dict] = {}

# ============================================================================
# Chat Models
# ============================================================================

class ChatInitRequest(BaseModel):
    model: str
    annotation_mode: bool = False

class ChatMessageRequest(BaseModel):
    conversation_id: str
    message: str
    temperature: float = 0.7
    nct_ids: Optional[List[str]] = None  # For annotation mode

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatResponse(BaseModel):
    conversation_id: str
    message: ChatMessage
    model: str
    annotation_mode: bool = False

# ============================================================================
# Helper Functions
# ============================================================================

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

async def get_nct_data_batch(nct_ids: List[str]) -> List[dict]:
    """Get NCT data for multiple IDs from runner service."""
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{RUNNER_SERVICE_URL}/batch-get-data",
                json={"nct_ids": nct_ids}
            )
            
            if response.status_code != 200:
                logger.error(f"Runner service error: {response.text}")
                return []
            
            data = response.json()
            results = data.get("results", [])
            
            # Extract successful results
            trial_data_list = []
            for result in results:
                if result.get("status") == "success":
                    trial_data_list.append({
                        "nct_id": result.get("nct_id"),
                        "data": result.get("data"),
                        "source": result.get("source")
                    })
            
            return trial_data_list
            
    except Exception as e:
        logger.error(f"Error getting NCT data batch: {e}")
        return []

async def annotate_trials(nct_ids: List[str], model: str, temperature: float) -> str:
    """
    Annotate multiple clinical trials.
    Gets data from runner service and generates annotations.
    """
    logger.info(f"🔬 Annotating {len(nct_ids)} trials with {model}")
    
    # Get trial data from runner service
    trial_data_list = await get_nct_data_batch(nct_ids)
    
    if not trial_data_list:
        return "❌ Could not retrieve trial data. Please check that the NCT IDs are valid and the runner service is available. "
    
    # Generate annotations
    annotations = []
    
    for trial_info in trial_data_list:
        nct_id = trial_info["nct_id"]
        trial_data = trial_info["data"]
        source = trial_info["source"]
        
        logger.info(f"📝 Generating annotation for {nct_id} (source: {source})")
        
        # Generate prompt
        prompt = generate_annotation_prompt(trial_data, nct_id)
        
        # Call Ollama
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
                
                if response.status_code == 200:
                    data = response.json()
                    annotation_text = data.get("response", "")
                    
                    annotations.append(f"""
{'='*80}
NCT ID: {nct_id}
Data Source: {source}
{'='*80}

{annotation_text}

""")
                else:
                    annotations.append(f"\n❌ Failed to generate annotation for {nct_id}\n")
                    
        except Exception as e:
            logger.error(f"Error annotating {nct_id}: {e}")
            annotations.append(f"\n❌ Error annotating {nct_id}: {str(e)}\n")
    
    # Combine all annotations
    result = f"""
Clinical Trial Annotation Report
Generated for {len(trial_data_list)} trial(s)
Model: {model}

{'='*80}
""" + "\n".join(annotations)
    
    return result

# ============================================================================
# Chat Endpoints
# ============================================================================

@app.post("/chat/init")
async def init_conversation(request: ChatInitRequest):
    """Initialize a new conversation"""
    conversation_id = str(uuid.uuid4())
    conversations[conversation_id] = {
        "model": request.model,
        "messages": [],
        "annotation_mode": request.annotation_mode
    }
    logger.info(f"✅ Created conversation {conversation_id} with {request.model} (annotation_mode={request.annotation_mode})")
    return {
        "conversation_id": conversation_id,
        "model": request.model,
        "annotation_mode": request.annotation_mode
    }

@app.post("/chat/message", response_model=ChatResponse)
async def send_message(request: ChatMessageRequest):
    """Send a message in an existing conversation"""
    if request.conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    conv = conversations[request.conversation_id]
    annotation_mode = conv.get("annotation_mode", False)

    logger.info(f"🔍 DEBUG /chat/message: annotation_mode={annotation_mode}, nct_ids={request.nct_ids}, message={request.message[:50] if request.message else None}")
    
    # Handle annotation mode
    if annotation_mode and request.nct_ids:
        logger.info(f"🔬 Annotation mode: Processing {len(request.nct_ids)} NCT IDs")
        
        # Add user message
        user_message = f"Annotate trials: {', '.join(request.nct_ids)}"
        conv["messages"].append({
            "role": "user",
            "content": user_message
        })
        
        # Generate annotations
        annotation_result = await annotate_trials(
            request.nct_ids,
            conv["model"],
            request.temperature
        )
        
        # Add assistant message
        conv["messages"].append({
            "role": "assistant",
            "content": annotation_result
        })
        
        return ChatResponse(
            conversation_id=request.conversation_id,
            message=ChatMessage(role="assistant", content=annotation_result),
            model=conv["model"],
            annotation_mode=True
        )
    
    # Normal chat mode
    conv["messages"].append({
        "role": "user",
        "content": request.message
    })
    
    # Call Ollama
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{config.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": conv["model"],
                    "messages": conv["messages"],
                    "temperature": request.temperature,
                    "stream": False
                }
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=503,
                    detail=f"Ollama error: {response.text}"
                )
            
            data = response.json()
            assistant_message = data["message"]["content"]
            
            # Add assistant message
            conv["messages"].append({
                "role": "assistant",
                "content": assistant_message
            })
            
            return ChatResponse(
                conversation_id=request.conversation_id,
                message=ChatMessage(role="assistant", content=assistant_message),
                model=conv["model"],
                annotation_mode=False
            )
            
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to Ollama at {config.OLLAMA_BASE_URL}"
        )
    except Exception as e:
        logger.error(f"❌ Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat/annotate-csv")
async def annotate_csv(
    conversation_id: str,
    model: str,
    temperature: float = 0.15,
    file: UploadFile = File(...)
):
    """
    Upload a CSV file with NCT IDs and generate annotations.
    CSV should have NCT IDs in first column.
    """
    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    try:
        # Read CSV file
        contents = await file.read()
        csv_text = contents.decode('utf-8')
        
        # Parse NCT IDs
        nct_ids = []
        csv_reader = csv.reader(io.StringIO(csv_text))
        for row in csv_reader:
            if row and row[0].strip():
                nct_id = row[0].strip().upper()
                if nct_id.startswith("NCT"):
                    nct_ids.append(nct_id)
        
        if not nct_ids:
            raise HTTPException(
                status_code=400,
                detail="No valid NCT IDs found in CSV file"
            )
        
        logger.info(f"📄 Processing CSV with {len(nct_ids)} NCT IDs")
        
        # Generate annotations
        conv = conversations[conversation_id]
        
        # Add user message
        user_message = f"Annotate trials from CSV: {len(nct_ids)} trials"
        conv["messages"].append({
            "role": "user",
            "content": user_message
        })
        
        # Generate annotations
        annotation_result = await annotate_trials(nct_ids, model, temperature)
        
        # Add assistant message
        conv["messages"].append({
            "role": "assistant",
            "content": annotation_result
        })
        
        return ChatResponse(
            conversation_id=conversation_id,
            message=ChatMessage(role="assistant", content=annotation_result),
            model=model,
            annotation_mode=True
        )
        
    except Exception as e:
        logger.error(f"❌ CSV processing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/chat/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Get conversation history"""
    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversations[conversation_id]

@app.get("/chat/models")
async def list_models():
    """List available Ollama models"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{config.OLLAMA_BASE_URL}/api/tags")
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=503, detail="Cannot fetch models from Ollama")
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to Ollama at {config.OLLAMA_BASE_URL}"
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

# ============================================================================
# Root Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "LLM Chat Service with Annotation",
        "version": "3.0.0",
        "status": "running",
        "features": {
            "chat": "enabled",
            "annotation": "enabled"
        },
        "endpoints": {
            "chat": "/chat/*",
            "docs": "/docs"
        }
    }

@app.get("/health")
async def health():
    """Health check"""
    
    # Check Ollama connection
    ollama_connected = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{config.OLLAMA_BASE_URL}/api/tags")
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
        "service": config.SERVICE_NAME,
        "version": config.API_VERSION,
        "ollama": {
            "url": config.OLLAMA_BASE_URL,
            "connected": ollama_connected
        },
        "runner_service": {
            "url": RUNNER_SERVICE_URL,
            "connected": runner_connected
        },
        "active_conversations": len(conversations)
    }

@app.get("/models")
async def get_models():
    """Get available Ollama models - root level endpoint"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{config.OLLAMA_BASE_URL}/api/tags")
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=503, detail="Cannot fetch models from Ollama")
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to Ollama at {config.OLLAMA_BASE_URL}"
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

# ============================================================================
# Run standalone
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting LLM Chat Service with Annotation on port 9001...")
    print(f"🤖 Ollama: {config.OLLAMA_BASE_URL}")
    print(f"📁 Runner Service: {RUNNER_SERVICE_URL}")
    print("📚 Docs: http://localhost:9001/docs")
    uvicorn.run(app, host="0.0.0.0", port=9001, reload=True)