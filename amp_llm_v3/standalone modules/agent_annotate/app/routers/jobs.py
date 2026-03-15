"""
Job management endpoints - create, list, cancel annotation jobs.

The create_job endpoint acts as a cross-branch gatekeeper: it checks
both the local orchestrator AND the other branch's agent-annotate service
to ensure only one annotation job runs at a time across all branches.
This is necessary because both branches share the same Ollama instance.
"""

import logging
import re
import httpx
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from app.config import AGENT_ANNOTATE_PORT
from app.services.orchestrator import orchestrator
from app.services.ollama_client import ollama_client

logger = logging.getLogger("agent_annotate.jobs")

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

NCT_PATTERN = re.compile(r"^NCT\d{8}$")
MAX_BATCH_SIZE = 500
MAX_CONCURRENT_JOBS = 1

# Cross-branch gatekeeper: detect the other branch's annotate port
_CURRENT_BRANCH = "main" if AGENT_ANNOTATE_PORT < 9000 else "dev"
_OTHER_ANNOTATE_PORT = 9005 if _CURRENT_BRANCH == "main" else 8005
_OTHER_ANNOTATE_URL = f"http://localhost:{_OTHER_ANNOTATE_PORT}"


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

    # Concurrent job limit — cross-branch gatekeeper
    # Check local jobs first
    if orchestrator.active_count() >= MAX_CONCURRENT_JOBS:
        raise HTTPException(
            status_code=429,
            detail=f"An annotation job is already running on {_CURRENT_BRANCH}. Wait for it to complete or cancel it.",
        )

    # Check the other branch's agent-annotate service
    other_branch = "main" if _CURRENT_BRANCH == "dev" else "dev"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{_OTHER_ANNOTATE_URL}/api/jobs/active")
            if resp.status_code == 200:
                other_active = resp.json().get("active", 0)
                if other_active > 0:
                    raise HTTPException(
                        status_code=429,
                        detail=f"An annotation job is already running on {other_branch}. Only one job can run at a time across all branches.",
                    )
    except httpx.ConnectError:
        # Other branch's service is not running — safe to proceed
        logger.debug(f"Other branch ({other_branch}) agent-annotate not reachable — proceeding")
    except HTTPException:
        raise
    except Exception as e:
        logger.debug(f"Could not check other branch ({other_branch}) active jobs: {e}")

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
