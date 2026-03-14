"""
Pipeline status and progress endpoints.
"""

from fastapi import APIRouter, HTTPException

from app.services.orchestrator import orchestrator
from app.services.ollama_client import ollama_client

router = APIRouter(prefix="/api/status", tags=["status"])


@router.get("/pipeline/{job_id}")
async def pipeline_status(job_id: str):
    """Get real-time progress for a running job."""
    job = orchestrator.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress": job.progress.model_dump(),
    }


@router.get("/models")
async def available_models():
    """List models available in Ollama."""
    try:
        models = await ollama_client.list_models()
        return {"models": [m.get("name", "") for m in models]}
    except Exception as e:
        return {"models": [], "error": str(e)}
