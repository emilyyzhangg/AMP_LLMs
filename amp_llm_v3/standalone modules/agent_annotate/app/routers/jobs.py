"""
Job management endpoints - create, list, cancel annotation jobs.
"""

import re
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from app.services.orchestrator import orchestrator
from app.services.ollama_client import ollama_client

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

NCT_PATTERN = re.compile(r"^NCT\d{8}$")
MAX_BATCH_SIZE = 500
MAX_CONCURRENT_JOBS = 1


class CreateJobRequest(BaseModel):
    nct_ids: list[str]


@router.post("")
async def create_job(req: CreateJobRequest, background_tasks: BackgroundTasks):
    """Create and start a new annotation pipeline job."""
    if not req.nct_ids:
        raise HTTPException(status_code=400, detail="nct_ids list cannot be empty")

    # Validate NCT IDs
    valid_ids = []
    invalid_ids = []
    for raw_id in req.nct_ids:
        nct_id = raw_id.strip().upper()
        if NCT_PATTERN.match(nct_id):
            valid_ids.append(nct_id)
        else:
            invalid_ids.append(raw_id)

    if not valid_ids:
        raise HTTPException(
            status_code=400,
            detail=f"No valid NCT IDs. Expected format: NCT followed by 8 digits. Invalid: {invalid_ids[:10]}",
        )

    # Batch size limit (16GB RAM constraint)
    if len(valid_ids) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Batch too large: {len(valid_ids)} trials. Maximum is {MAX_BATCH_SIZE}.",
        )

    # Concurrent job limit (one Ollama model at a time)
    if orchestrator.active_count() >= MAX_CONCURRENT_JOBS:
        raise HTTPException(
            status_code=429,
            detail="An annotation job is already running. Wait for it to complete or cancel it.",
        )

    # Pre-check Ollama
    ollama_ok = await ollama_client.health_check()
    if not ollama_ok:
        raise HTTPException(
            status_code=503,
            detail="Ollama is unreachable. Ensure Ollama is running at localhost:11434.",
        )

    # Deduplicate
    valid_ids = list(dict.fromkeys(valid_ids))

    job = orchestrator.create_job(valid_ids)
    background_tasks.add_task(orchestrator.run_pipeline, job.job_id)

    response = {
        "job_id": job.job_id,
        "status": job.status,
        "total_trials": len(valid_ids),
    }
    if invalid_ids:
        response["warning"] = f"{len(invalid_ids)} invalid IDs skipped: {invalid_ids[:5]}"

    return response


@router.get("")
async def list_jobs():
    """List all jobs with summary info."""
    return orchestrator.list_jobs()


@router.get("/active")
async def active_jobs():
    """Return count of active jobs (for graceful restart checks)."""
    return {"active": orchestrator.active_count()}


@router.get("/{job_id}")
async def get_job(job_id: str):
    """Get full details for a specific job."""
    job = orchestrator.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Cancel a running or queued job."""
    success = orchestrator.cancel_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="Job cannot be cancelled (not running or queued)")
    return {"job_id": job_id, "status": "cancelled"}
