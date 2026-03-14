"""
Pipeline status and progress endpoints.
"""

from fastapi import APIRouter, HTTPException

from app.services.orchestrator import orchestrator
from app.services.ollama_client import ollama_client

router = APIRouter(prefix="/api/status", tags=["status"])


def _format_duration(seconds: float) -> str:
    """Format seconds into human-readable string."""
    if seconds <= 0:
        return ""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


@router.get("/pipeline/{job_id}")
async def pipeline_status(job_id: str):
    """Get real-time progress for a running job."""
    job = orchestrator.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    progress = job.progress.model_dump()
    progress["elapsed_display"] = _format_duration(progress["elapsed_seconds"])
    progress["estimated_remaining_display"] = _format_duration(progress["estimated_remaining_seconds"])
    progress["avg_per_trial_display"] = _format_duration(progress["avg_seconds_per_trial"])
    progress["percent"] = (
        round(progress["completed_trials"] / progress["total_trials"] * 100)
        if progress["total_trials"] > 0
        else 0
    )

    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress": progress,
    }


@router.get("/models")
async def available_models():
    """List models available in Ollama."""
    try:
        models = await ollama_client.list_models()
        return {"models": [m.get("name", "") for m in models]}
    except Exception as e:
        return {"models": [], "error": str(e)}
