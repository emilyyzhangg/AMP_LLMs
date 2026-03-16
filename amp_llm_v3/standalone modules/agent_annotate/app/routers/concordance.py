"""
Concordance analysis API endpoints.

All endpoints are read-only reference data for scientific analysis
and are exempt from authentication.
"""

from fastapi import APIRouter, HTTPException

from app.models.concordance import (
    ComparisonResult,
    ConcordanceHistory,
    FullJobConcordanceResponse,
    JobConcordance,
)
from app.services import concordance_service

router = APIRouter(prefix="/api/concordance", tags=["concordance"])


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


@router.get("/compare/{job_id_a}/{job_id_b}", response_model=ComparisonResult)
async def compare_jobs(job_id_a: str, job_id_b: str):
    """Inter-version comparison: field-by-field kappa delta between two agent jobs."""
    result = concordance_service.compare_jobs(job_id_a, job_id_b)
    if not result.per_field:
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
