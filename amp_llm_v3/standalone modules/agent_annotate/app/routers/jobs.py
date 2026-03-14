"""
Job management endpoints - create, list, cancel annotation jobs.
"""

import asyncio
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from app.services.orchestrator import orchestrator

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class CreateJobRequest(BaseModel):
    nct_ids: list[str]


@router.post("")
async def create_job(req: CreateJobRequest, background_tasks: BackgroundTasks):
    """Create and start a new annotation pipeline job."""
    if not req.nct_ids:
        raise HTTPException(status_code=400, detail="nct_ids list cannot be empty")

    job = orchestrator.create_job(req.nct_ids)
    # Run pipeline in background so the POST returns immediately
    background_tasks.add_task(orchestrator.run_pipeline, job.job_id)
    return {"job_id": job.job_id, "status": job.status, "total_trials": len(req.nct_ids)}


@router.get("")
async def list_jobs():
    """List all jobs with summary info."""
    return orchestrator.list_jobs()


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
        raise HTTPException(status_code=400, detail="Job cannot be cancelled")
    return {"job_id": job_id, "status": "cancelled"}
