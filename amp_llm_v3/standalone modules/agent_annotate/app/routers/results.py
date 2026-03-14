"""
Results and CSV export endpoints.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from app.services.orchestrator import orchestrator
from app.services.output_service import generate_standard_csv, generate_full_csv, save_csv
from app.services.version_service import get_version_info
from app.models.output import CSVExportRequest

router = APIRouter(prefix="/api/results", tags=["results"])


@router.get("/{job_id}")
async def get_results(job_id: str):
    """Get annotation results for a completed job."""
    job = orchestrator.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "completed":
        raise HTTPException(status_code=400, detail=f"Job is {job.status}, not completed")
    return {
        "job_id": job.job_id,
        "version": get_version_info().model_dump(),
        "trials": job.results,
    }


@router.post("/export/csv")
async def export_csv(req: CSVExportRequest):
    """Export results as CSV."""
    job = orchestrator.get_job(req.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "completed":
        raise HTTPException(status_code=400, detail=f"Job is {job.status}, not completed")

    if req.format == "full":
        csv_content = generate_full_csv(job.results)
    else:
        csv_content = generate_standard_csv(job.results)

    # Save to disk
    path = save_csv(req.job_id, csv_content, label=req.format)

    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={path.name}"},
    )


@router.get("/{job_id}/summary")
async def results_summary(job_id: str):
    """Summary statistics for a completed job."""
    job = orchestrator.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job.job_id,
        "status": job.status,
        "total_trials": job.progress.total_trials,
        "completed_trials": job.progress.completed_trials,
        "flagged_for_review": sum(
            1 for r in job.results if r.get("flagged_for_review", False)
        ),
    }
