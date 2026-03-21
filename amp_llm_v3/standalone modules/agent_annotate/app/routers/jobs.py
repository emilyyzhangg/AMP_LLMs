"""
Job management endpoints - create, list, cancel, queue annotation jobs.

Jobs are queued and processed sequentially by a background worker.
Multiple jobs can be submitted — they will run one at a time. The
queue worker also checks the other branch's service (cross-branch
gatekeeper) since both branches share the same Ollama instance.
"""

import logging
import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.orchestrator import orchestrator
from app.services.ollama_client import ollama_client

logger = logging.getLogger("agent_annotate.jobs")

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

NCT_PATTERN = re.compile(r"^NCT\d{8}$")
MAX_BATCH_SIZE = 500


class CreateJobRequest(BaseModel):
    nct_ids: list[str]


@router.post("")
async def create_job(req: CreateJobRequest):
    """Create and queue a new annotation pipeline job.

    Jobs are queued and processed sequentially. If a job is already running,
    the new job will wait in the queue until the current one finishes.
    """
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
    orchestrator.enqueue_job(job.job_id)

    position = orchestrator.queue_size()
    response = {
        "job_id": job.job_id,
        "status": job.status,
        "total_trials": len(valid_ids),
        "queue_position": position,
    }
    if position > 0:
        response["message"] = f"Job queued. {position} job(s) ahead in queue."
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


@router.get("/queue")
async def queue_status():
    """Return queue status: running job, queued jobs, and queue size."""
    running = None
    for j in orchestrator.list_jobs():
        if j.status == "running":
            running = j.job_id
            break
    return {
        "running": running,
        "queued": orchestrator.queued_jobs(),
        "queue_size": orchestrator.queue_size(),
    }


@router.get("/{job_id}")
async def get_job(job_id: str):
    """Get full details for a specific job."""
    job = orchestrator.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


class ResumeJobRequest(BaseModel):
    force: bool = False


@router.post("/{job_id}/resume")
async def resume_job(job_id: str, req: ResumeJobRequest):
    """Resume a failed or cancelled annotation job from persisted state.

    The resumed job is queued and will run after any currently running job finishes.
    """
    # Pre-check Ollama
    ollama_ok = await ollama_client.health_check()
    if not ollama_ok:
        raise HTTPException(
            status_code=503,
            detail="Ollama is unreachable. Ensure Ollama is running at localhost:11434.",
        )

    try:
        job = orchestrator.resume_job(job_id, force=req.force)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    orchestrator.enqueue_job(job.job_id)

    # Get resume validation info for response
    from app.services.persistence_service import PersistenceService
    from app.services.version_service import get_git_commit_full
    from app.config import RESULTS_DIR

    persistence = PersistenceService(RESULTS_DIR)
    validation = persistence.validate_resume(job_id, get_git_commit_full())

    position = orchestrator.queue_size()
    return {
        "job_id": job.job_id,
        "status": job.status,
        "resumed": True,
        "queue_position": position,
        "research_completed": validation.research_completed,
        "research_total": validation.research_total,
        "annotations_completed": validation.annotations_completed,
        "commit_match": validation.commit_match,
        "warnings": validation.warnings,
    }


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Cancel a running or queued job."""
    success = orchestrator.cancel_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="Job cannot be cancelled (not running or queued)")
    return {"job_id": job_id, "status": "cancelled"}
