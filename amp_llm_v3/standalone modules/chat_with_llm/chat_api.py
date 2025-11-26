"""
LLM Chat Service with Annotation Support (Port 9001)
====================================================

Chat service that operates in two modes:
1. Normal chat mode - regular conversation with LLM
2. Annotation mode - clinical trial annotation using modular services

Architecture:
- This service (9001) -> Runner Service (9003) -> LLM Assistant (9004)
- Runner fetches data from NCT Service (9002) if needed
- LLM Assistant handles JSON parsing, prompt generation, and LLM calls
"""
import logging
import uuid
import httpx
import time
import io
import csv
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Configuration
try:
    from assistant_config import config
except ImportError:
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
    description="Chat and clinical trial annotation service using modular architecture",
    version="3.1.0",
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
# Models
# ============================================================================

class ChatInitRequest(BaseModel):
    model: str
    annotation_mode: bool = False


class ChatMessageRequest(BaseModel):
    conversation_id: str
    message: str
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    nct_ids: Optional[List[str]] = None  # For annotation mode


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatResponse(BaseModel):
    conversation_id: str
    message: ChatMessage
    model: str
    annotation_mode: bool = False
    processing_time_seconds: Optional[float] = None


class AnnotationSummary(BaseModel):
    """Summary of annotation results"""
    total: int
    successful: int
    failed: int
    processing_time_seconds: float


class CSVAnnotationResponse(BaseModel):
    """Response for CSV batch annotation"""
    conversation_id: str
    message: ChatMessage
    model: str
    annotation_mode: bool = True
    # CSV-specific fields
    csv_filename: str
    download_url: str
    total: int
    successful: int
    failed: int
    total_time_seconds: float
    errors: List[dict] = []


# ============================================================================
# Helper Functions
# ============================================================================

async def annotate_trials_via_runner(
    nct_ids: List[str], 
    model: str, 
    temperature: float
) -> tuple[str, AnnotationSummary]:
    """
    Annotate trials using the Runner Service's batch-annotate endpoint.
    
    The Runner Service coordinates:
    1. Fetching trial data (from cache or NCT Service)
    2. Sending to LLM Assistant for annotation
    
    Returns:
        Tuple of (formatted_annotation_text, summary)
    """
    logger.info(f"🔬 Annotating {len(nct_ids)} trials with {model} via Runner Service")
    
    try:
        async with httpx.AsyncClient(timeout=600.0) as client:  # 10 min timeout for batch
            # Check runner service
            try:
                health = await client.get(f"{RUNNER_SERVICE_URL}/health", timeout=5.0)
                if health.status_code != 200:
                    return (
                        "❌ Runner Service not available. Please ensure it's running on port 9003.",
                        AnnotationSummary(total=len(nct_ids), successful=0, failed=len(nct_ids), processing_time_seconds=0)
                    )
            except httpx.ConnectError:
                return (
                    f"❌ Cannot connect to Runner Service at {RUNNER_SERVICE_URL}.\n\n"
                    "Please start the service:\n"
                    "  cd standalone_modules/runner\n"
                    "  uvicorn runner_service:app --port 9003 --reload",
                    AnnotationSummary(total=len(nct_ids), successful=0, failed=len(nct_ids), processing_time_seconds=0)
                )
            
            # Send batch annotation request
            logger.info(f"📤 Sending batch annotation request to Runner Service")
            
            response = await client.post(
                f"{RUNNER_SERVICE_URL}/batch-annotate",
                json={
                    "nct_ids": nct_ids,
                    "model": model,
                    "temperature": temperature,
                    "fetch_if_missing": True
                }
            )
            
            if response.status_code != 200:
                error_text = response.text
                logger.error(f"❌ Runner Service error: {error_text}")
                return (
                    f"❌ Annotation failed: {error_text[:500]}",
                    AnnotationSummary(total=len(nct_ids), successful=0, failed=len(nct_ids), processing_time_seconds=0)
                )
            
            data = response.json()
            
            # Format results
            results = data.get("results", [])
            total = data.get("total", len(nct_ids))
            successful = data.get("successful", 0)
            failed = data.get("failed", 0)
            total_time = data.get("total_time_seconds", 0)
            
            # Build formatted output
            output_parts = []
            
            for result in results:
                nct_id = result.get("nct_id")
                status = result.get("status")
                source = result.get("source", "unknown")
                annotation = result.get("annotation", "")
                error = result.get("error")
                proc_time = result.get("processing_time_seconds", 0)
                
                output_parts.append(f"\n{'='*80}")
                output_parts.append(f"NCT ID: {nct_id}")
                output_parts.append(f"Data Source: {source}")
                output_parts.append(f"Processing Time: {proc_time:.1f}s")
                output_parts.append(f"{'='*80}\n")
                
                if status == "success":
                    output_parts.append(annotation)
                else:
                    output_parts.append(f"❌ Error: {error}")
                
                output_parts.append("")
            
            formatted_output = "\n".join(output_parts)
            
            summary = AnnotationSummary(
                total=total,
                successful=successful,
                failed=failed,
                processing_time_seconds=total_time
            )
            
            return formatted_output, summary
            
    except httpx.TimeoutException:
        logger.error("❌ Annotation request timed out")
        return (
            "❌ Annotation timed out. Try fewer trials or a faster model.",
            AnnotationSummary(total=len(nct_ids), successful=0, failed=len(nct_ids), processing_time_seconds=0)
        )
    except Exception as e:
        logger.error(f"❌ Annotation error: {e}", exc_info=True)
        return (
            f"❌ Annotation error: {str(e)}",
            AnnotationSummary(total=len(nct_ids), successful=0, failed=len(nct_ids), processing_time_seconds=0)
        )


# ============================================================================
# Chat Routes
# ============================================================================

@app.post("/chat/init")
async def init_chat(request: ChatInitRequest):
    """Initialize a new chat conversation"""
    conversation_id = str(uuid.uuid4())
    
    conversations[conversation_id] = {
        "id": conversation_id,
        "model": request.model,
        "annotation_mode": request.annotation_mode,
        "messages": [],
        "created_at": time.time()
    }
    
    logger.info(f"✅ Created conversation {conversation_id} with model {request.model}")
    
    return {
        "conversation_id": conversation_id,
        "model": request.model,
        "annotation_mode": request.annotation_mode,
        "status": "initialized"
    }


@app.post("/chat/message", response_model=ChatResponse)
async def send_message(request: ChatMessageRequest):
    """Send a message in a conversation"""
    
    if request.conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    conv = conversations[request.conversation_id]
    start_time = time.time()
    
    # Annotation mode with NCT IDs
    if conv.get("annotation_mode") and request.nct_ids:
        logger.info(f"📝 Annotation request for {len(request.nct_ids)} trials")
        
        # Add user message
        user_message = f"Annotate trials: {', '.join(request.nct_ids)}"
        conv["messages"].append({
            "role": "user",
            "content": user_message
        })
        
        # Call annotation via runner service
        annotation_result, summary = await annotate_trials_via_runner(
            request.nct_ids,
            conv["model"],
            request.temperature
        )
        
        # Format response
        response_content = f"""Clinical Trial Annotation Report
Generated for {summary.total} trial(s)
Model: {conv["model"]}
Successful: {summary.successful} | Failed: {summary.failed}
Total Time: {summary.processing_time_seconds:.1f}s

{annotation_result}

═══════════════════════════════════════════

💡 Next:
  • Enter more NCT IDs to annotate
  • Type "exit" to select a different model
  • Click "Clear Chat" to reset"""
        
        # Add assistant message
        conv["messages"].append({
            "role": "assistant",
            "content": response_content
        })
        
        processing_time = time.time() - start_time
        
        return ChatResponse(
            conversation_id=request.conversation_id,
            message=ChatMessage(role="assistant", content=response_content),
            model=conv["model"],
            annotation_mode=True,
            processing_time_seconds=round(processing_time, 2)
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
            
            processing_time = time.time() - start_time
            
            return ChatResponse(
                conversation_id=request.conversation_id,
                message=ChatMessage(role="assistant", content=assistant_message),
                model=conv["model"],
                annotation_mode=False,
                processing_time_seconds=round(processing_time, 2)
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
    Returns a link to download the annotated CSV file.
    
    The input CSV can have NCT IDs in any column - they will be automatically detected.
    """
    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    try:
        # Read file contents
        contents = await file.read()
        
        logger.info(f"📄 Forwarding CSV to Runner Service: {file.filename}")
        
        conv = conversations[conversation_id]
        
        # Add user message
        user_message = f"Annotate trials from CSV: {file.filename}"
        conv["messages"].append({
            "role": "user",
            "content": user_message
        })
        
        # Forward to runner service's CSV endpoint
        async with httpx.AsyncClient(timeout=1800.0) as client:  # 30 min timeout
            try:
                # Check runner health
                health = await client.get(f"{RUNNER_SERVICE_URL}/health", timeout=5.0)
                if health.status_code != 200:
                    raise HTTPException(
                        status_code=503,
                        detail="Runner service not available"
                    )
            except httpx.ConnectError:
                raise HTTPException(
                    status_code=503,
                    detail=f"Cannot connect to Runner Service at {RUNNER_SERVICE_URL}"
                )
            
            # Send file to runner's CSV endpoint
            files = {"file": (file.filename, contents, "text/csv")}
            data = {"model": model, "temperature": str(temperature)}
            
            response = await client.post(
                f"{RUNNER_SERVICE_URL}/annotate-csv",
                files=files,
                data=data
            )
            
            if response.status_code != 200:
                error_text = response.text
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Runner service error: {error_text}"
                )
            
            result = response.json()
        
        # Format response with download link
        download_url = f"{RUNNER_SERVICE_URL}{result['download_url']}"
        
        # Build error summary if any
        error_summary = ""
        if result.get("errors"):
            error_lines = [f"  - {e['nct_id']}: {e['error']}" for e in result["errors"][:5]]
            if len(result["errors"]) > 5:
                error_lines.append(f"  ... and {len(result['errors']) - 5} more errors")
            error_summary = f"\n\nErrors:\n" + "\n".join(error_lines)
        
        response_content = f"""✅ CSV Annotation Complete
═══════════════════════════════════════════
📄 Input File: {file.filename}
📊 Total NCT IDs: {result['total']}
✓ Successful: {result['successful']}
✗ Failed: {result['failed']}
⏱ Processing Time: {result['total_time_seconds']:.1f}s
═══════════════════════════════════════════

📥 Download annotated CSV:
{download_url}

The output CSV includes columns:
• Study Title, Status, Summary, Conditions, Drug
• Phase, Enrollment, Start/Completion Dates  
• Classification (AMP/Other) with Evidence
• Delivery Mode with Evidence
• Outcome with Evidence
• Reason for Failure with Evidence
• Peptide (True/False) with Evidence
• Sequence, Study ID{error_summary}

═══════════════════════════════════════════
💡 Next Steps:
  • Click the download link above to get your annotated CSV
  • Upload another CSV to annotate more trials
  • Type "exit" to leave annotation mode
═══════════════════════════════════════════"""
        
        # Add assistant message
        conv["messages"].append({
            "role": "assistant",
            "content": response_content
        })
        
        return CSVAnnotationResponse(
            conversation_id=conversation_id,
            message=ChatMessage(role="assistant", content=response_content),
            model=model,
            annotation_mode=True,
            csv_filename=result.get('csv_filename', 'annotations.csv'),
            download_url=download_url,
            total=result['total'],
            successful=result['successful'],
            failed=result['failed'],
            total_time_seconds=result['total_time_seconds'],
            errors=result.get('errors', [])
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ CSV processing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chat/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Get conversation history"""
    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversations[conversation_id]


@app.delete("/chat/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation"""
    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")
    del conversations[conversation_id]
    return {"status": "deleted", "conversation_id": conversation_id}


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


# ============================================================================
# Root Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "LLM Chat Service with Annotation",
        "version": "3.1.0",
        "status": "running",
        "architecture": "modular",
        "features": {
            "chat": "enabled",
            "annotation": "enabled (via Runner Service)"
        },
        "endpoints": {
            "chat": "/chat/*",
            "docs": "/docs"
        },
        "dependencies": {
            "ollama": config.OLLAMA_BASE_URL,
            "runner_service": RUNNER_SERVICE_URL
        }
    }


@app.get("/health")
async def health():
    """Health check with dependency status"""
    
    # Check Ollama connection
    ollama_connected = False
    ollama_models = 0
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{config.OLLAMA_BASE_URL}/api/tags")
            if response.status_code == 200:
                ollama_connected = True
                data = response.json()
                ollama_models = len(data.get("models", []))
    except:
        pass
    
    # Check Runner service
    runner_connected = False
    runner_features = {}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{RUNNER_SERVICE_URL}/health")
            if response.status_code == 200:
                runner_connected = True
                data = response.json()
                runner_features = {
                    "llm_assistant": data.get("llm_assistant", {}).get("connected", False),
                    "nct_service": data.get("nct_service", {}).get("connected", False)
                }
    except:
        pass
    
    return {
        "status": "healthy",
        "service": config.SERVICE_NAME,
        "version": "3.1.0",
        "ollama": {
            "url": config.OLLAMA_BASE_URL,
            "connected": ollama_connected,
            "models_count": ollama_models
        },
        "runner_service": {
            "url": RUNNER_SERVICE_URL,
            "connected": runner_connected,
            "features": runner_features
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


# ============================================================================
# Run standalone
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    print("=" * 80)
    print("🚀 Starting LLM Chat Service with Annotation on port 9001...")
    print("=" * 80)
    print(f"🤖 Ollama: {config.OLLAMA_BASE_URL}")
    print(f"📁 Runner Service: {RUNNER_SERVICE_URL}")
    print(f"📚 Docs: http://localhost:9001/docs")
    print("=" * 80)
    print("\n📋 Service Dependencies:")
    print("  - Runner Service (9003) - Data fetching & annotation orchestration")
    print("  - LLM Assistant (9004) - JSON parsing & prompt generation")
    print("  - NCT Service (9002) - Clinical trials data")
    print("  - Ollama (11434) - LLM inference")
    print("=" * 80)
    uvicorn.run(app, host="0.0.0.0", port=9001, reload=True)