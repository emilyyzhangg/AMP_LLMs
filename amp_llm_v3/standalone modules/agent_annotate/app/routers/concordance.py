"""
Concordance analysis API endpoints.

All endpoints are read-only reference data for scientific analysis
and are exempt from authentication.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.concordance import (
    AnnotatorListResponse,
    ComparisonResult,
    ConcordanceHistory,
    FullJobConcordanceResponse,
    JobConcordance,
)
from app.services import concordance_service


class MultiAnnotatorRequest(BaseModel):
    """Request body for multi-annotator concordance endpoints."""
    annotators: list[str]
    replicate: str  # "r1" or "r2"


class HumanMultiAnnotatorRequest(BaseModel):
    """Request body for human inter-rater with multi-annotator filtering."""
    r1_annotators: Optional[list[str]] = None
    r2_annotators: Optional[list[str]] = None

router = APIRouter(prefix="/api/concordance", tags=["concordance"])


@router.get("/jobs")
async def list_concordance_jobs():
    """List all completed jobs available for concordance analysis."""
    import json
    from app.config import RESULTS_DIR

    job_ids = concordance_service._list_completed_jobs()
    jobs = []
    for job_id in job_ids:
        json_path = RESULTS_DIR / "json" / f"{job_id}.json"
        total_trials = 0
        timestamp = concordance_service._get_job_timestamp(job_id) or ""
        try:
            with open(json_path) as f:
                data = json.load(f)
            trials = data.get("trials", [])
            # Count unique NCTs (not raw array length) to handle any residual duplicates
            unique_ncts = {t.get("nct_id") for t in trials if t.get("nct_id")}
            total_trials = len(unique_ncts)
        except Exception:
            pass
        jobs.append({
            "job_id": job_id,
            "timestamp": timestamp,
            "total_trials": total_trials,
        })
    return {"jobs": jobs}


@router.get("/job/{job_id}", response_model=FullJobConcordanceResponse)
async def get_job_concordance(job_id: str):
    """Full concordance of a job against human R1, R2, and inter-rater R1 vs R2."""
    vs_r1 = concordance_service.agent_vs_r1(job_id)
    if not vs_r1.fields:
        raise HTTPException(
            status_code=404,
            detail=f"Job '{job_id}' not found or has no overlapping trials",
        )

    vs_r2 = concordance_service.agent_vs_r2(job_id)
    human = concordance_service.r1_vs_r2()

    return FullJobConcordanceResponse(
        agent_vs_r1=vs_r1,
        agent_vs_r2=vs_r2,
        r1_vs_r2=human,
    )


class MultiJobRequest(BaseModel):
    job_ids: list[str]


@router.post("/jobs/multi", response_model=FullJobConcordanceResponse)
async def get_multi_job_concordance(req: MultiJobRequest):
    """Concordance across multiple jobs merged. Latest job wins for overlapping NCTs."""
    if not req.job_ids:
        raise HTTPException(status_code=400, detail="job_ids list cannot be empty")

    vs_r1 = concordance_service.agent_vs_r1_multi(req.job_ids)
    if not vs_r1.fields:
        raise HTTPException(
            status_code=404,
            detail="No overlapping trials found across selected jobs",
        )

    vs_r2 = concordance_service.agent_vs_r2_multi(req.job_ids)
    human = concordance_service.r1_vs_r2()

    return FullJobConcordanceResponse(
        agent_vs_r1=vs_r1,
        agent_vs_r2=vs_r2,
        r1_vs_r2=human,
    )


@router.get("/compare/{job_id_a}/{job_id_b}", response_model=ComparisonResult)
async def compare_jobs(job_id_a: str, job_id_b: str):
    """Inter-version comparison: field-by-field kappa delta between two agent jobs."""
    result = concordance_service.compare_jobs(job_id_a, job_id_b)
    if not result.fields:
        raise HTTPException(
            status_code=404,
            detail="One or both jobs not found",
        )
    return result


@router.get("/history", response_model=ConcordanceHistory)
async def get_concordance_history():
    """Kappa trends across all completed jobs (agent vs R1)."""
    return concordance_service.concordance_history()


@router.get("/human", response_model=JobConcordance)
async def get_human_concordance():
    """R1 vs R2 human inter-rater agreement (no job dependency)."""
    result = concordance_service.r1_vs_r2()
    if not result.fields:
        raise HTTPException(
            status_code=404,
            detail="Human annotation data not available",
        )
    return result


@router.get("/annotators", response_model=AnnotatorListResponse)
async def list_annotators():
    """List all human annotators with their NCT counts."""
    annotators = concordance_service.annotator_list()
    return AnnotatorListResponse(annotators=annotators)


@router.get("/job/{job_id}/annotator/{annotator}", response_model=JobConcordance)
async def get_job_annotator_concordance(job_id: str, annotator: str):
    """Concordance of an agent job against a specific human annotator's NCTs."""
    result = concordance_service.agent_vs_annotator(job_id, annotator)
    if not result.fields:
        raise HTTPException(
            status_code=404,
            detail=f"No data for job '{job_id}' vs annotator '{annotator}'",
        )
    return result


@router.get("/human/annotator/{annotator}", response_model=JobConcordance)
async def get_human_annotator_concordance(annotator: str):
    """R1 vs R2 filtered to only NCTs by a specific annotator."""
    result = concordance_service.r1_vs_r2_for_annotator(annotator)
    if not result.fields:
        raise HTTPException(
            status_code=404,
            detail=f"No data for annotator '{annotator}'",
        )
    return result


@router.post("/job/{job_id}/annotators", response_model=JobConcordance)
async def get_job_multi_annotator_concordance(job_id: str, body: MultiAnnotatorRequest):
    """Concordance of an agent job against multiple annotators from one replicate.

    Combines NCTs from all selected annotators in the specified replicate
    into a single concordance computation.
    """
    if body.replicate not in ("r1", "r2"):
        raise HTTPException(status_code=400, detail="replicate must be 'r1' or 'r2'")
    if not body.annotators:
        raise HTTPException(status_code=400, detail="annotators list must not be empty")

    result = concordance_service.agent_vs_annotators(job_id, body.annotators, body.replicate)
    if not result.fields:
        raise HTTPException(
            status_code=404,
            detail=f"No data for job '{job_id}' vs annotators {body.annotators} ({body.replicate})",
        )
    return result


@router.post("/human/annotators", response_model=JobConcordance)
async def get_human_multi_annotator_concordance(body: HumanMultiAnnotatorRequest):
    """R1 vs R2 inter-rater agreement filtered by selected annotators.

    When annotators are selected for a replicate, only their NCTs are used
    for that side. Unselected replicates use all data.
    """
    result = concordance_service.r1_vs_r2_for_annotators(
        r1_names=body.r1_annotators,
        r2_names=body.r2_annotators,
    )
    if not result.fields:
        raise HTTPException(
            status_code=404,
            detail="No overlapping data for selected annotators",
        )
    return result
