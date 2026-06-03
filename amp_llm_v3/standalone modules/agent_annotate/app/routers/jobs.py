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
from app.services.memory.edam_config import TRAINING_NCTS, ALL_GT_NCTS, TEST_BATCH_NCTS, ALL_SUBMITTABLE_NCTS, MASTER_NCTS

logger = logging.getLogger("agent_annotate.jobs")

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

NCT_PATTERN = re.compile(r"^NCT\d{8}$")
# 2026-05-22: raised 500 → 750 so the whole 629-NCT training corpus can run as a
# single job. Jobs are resumable (per-trial persistence) and mini-batched, so
# this only affects how many NCTs one job tracks, not peak memory.
# 2026-06-03: raised 750 → 1100 to accommodate the 994-NCT master extension
# (master_extension_v1.json — annotator-master xlsx minus ALL_GT_NCTS).
MAX_BATCH_SIZE = 1100


class CreateJobRequest(BaseModel):
    nct_ids: list[str]
    allow_test_batch: bool = False
    # 2026-06-03: when true, widens the allowed NCT set to ALL_SUBMITTABLE_NCTS
    # (ALL_GT_NCTS ∪ MASTER_NCTS = the full annotator-master xlsx universe,
    # ~1844 NCTs). EDAM gating is unchanged — the orchestrator still only
    # learns from TRAINING_NCTS, so external NCTs never contaminate memory.
    # Use this for dataset-extension runs on trials with no/partial human GT.
    allow_external: bool = False


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

    # Validate against the allowed NCT set, which widens by flag:
    #   default                         → TRAINING_NCTS (629, the EDAM-learning pool)
    #   allow_test_batch=True           → ALL_GT_NCTS (850, train + val + new test + legacy test_batch)
    #   allow_external=True             → ALL_SUBMITTABLE_NCTS (~1844, the full annotator-master
    #                                     xlsx universe; trials with no or partial human GT).
    # EDAM learning is gated on TRAINING_NCTS in the orchestrator regardless,
    # so wider allow sets never contaminate memory.
    if req.allow_external and ALL_SUBMITTABLE_NCTS:
        allowed = ALL_SUBMITTABLE_NCTS
    elif req.allow_test_batch and ALL_GT_NCTS:
        allowed = ALL_GT_NCTS
    else:
        allowed = TRAINING_NCTS
    if allowed:
        outside = [nct for nct in valid_ids if nct not in allowed]
        if outside:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{len(outside)}/{len(valid_ids)} NCT IDs are outside the allowed set "
                    f"({'ALL_SUBMITTABLE_NCTS' if req.allow_external else 'ALL_GT_NCTS' if req.allow_test_batch else 'TRAINING_NCTS'}). "
                    f"For trials with no human GT, set allow_external=True. "
                    f"First 10: {outside[:10]}"
                ),
            )
    if req.allow_test_batch and TEST_BATCH_NCTS:
        n_tb = sum(1 for nct in valid_ids if nct in TEST_BATCH_NCTS)
        if n_tb:
            logger.warning(
                "Job submission includes %d test-batch NCT(s); allow_test_batch=True. "
                "These annotations will NOT contaminate EDAM (gated on TRAINING_NCTS).",
                n_tb,
            )
    if req.allow_external and MASTER_NCTS:
        n_ext = sum(1 for nct in valid_ids if nct in MASTER_NCTS and nct not in ALL_GT_NCTS)
        if n_ext:
            logger.warning(
                "Job submission includes %d external master-extension NCT(s) with no/partial human GT; "
                "allow_external=True. These annotations will NOT contaminate EDAM (gated on TRAINING_NCTS).",
                n_ext,
            )

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
