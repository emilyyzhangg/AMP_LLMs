"""
Results and CSV export endpoints.
"""

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from app.config import RESULTS_DIR
from app.services.orchestrator import orchestrator
from app.services.output_service import (
    generate_standard_csv,
    generate_full_csv,
    save_csv,
    load_json_output,
)
from app.services.version_service import get_version_info

router = APIRouter(prefix="/api/results", tags=["results"])


@router.get("")
async def list_results():
    """List all completed result files."""
    json_dir = RESULTS_DIR / "json"
    results = []
    if json_dir.exists():
        for path in sorted(json_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(path.read_text())
                version = data.get("version", {})
                results.append({
                    "job_id": path.stem,
                    "version": version.get("version", ""),
                    "git_commit": version.get("git_commit", ""),
                    "timestamp": version.get("timestamp", ""),
                    "total_trials": data.get("total_trials", 0),
                    "successful": data.get("successful", 0),
                    "failed": data.get("failed", 0),
                    "manual_review": data.get("manual_review", 0),
                })
            except Exception:
                continue
    return {"results": results, "total": len(results)}


@router.get("/{job_id}")
async def get_results(job_id: str):
    """Get full annotation results for a completed job."""
    data = load_json_output(job_id)
    if not data:
        # Try in-memory
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
    return data


@router.get("/{job_id}/csv")
async def export_csv(
    job_id: str,
    format: str = Query(default="standard", pattern="^(standard|full)$"),
):
    """Export results as CSV download."""
    data = load_json_output(job_id)
    if not data:
        job = orchestrator.get_job(job_id)
        if not job or job.status != "completed":
            raise HTTPException(status_code=404, detail="Results not found")
        trials = job.results
    else:
        trials = data.get("trials", [])

    if format == "full":
        csv_content = generate_full_csv(trials)
    else:
        csv_content = generate_standard_csv(trials)

    path = save_csv(job_id, csv_content, label=format)

    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={path.name}"},
    )


@router.get("/{job_id}/summary")
async def results_summary(job_id: str):
    """Summary statistics for a completed job."""
    data = load_json_output(job_id)
    if data:
        return {
            "job_id": job_id,
            "total_trials": data.get("total_trials", 0),
            "successful": data.get("successful", 0),
            "failed": data.get("failed", 0),
            "manual_review": data.get("manual_review", 0),
            "version": data.get("version", {}),
        }

    job = orchestrator.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    flagged = sum(
        1 for r in job.results
        if isinstance(r, dict) and r.get("verification", {}).get("flagged_for_review", False)
    )
    return {
        "job_id": job.job_id,
        "status": job.status,
        "total_trials": job.progress.total_trials,
        "completed_trials": job.progress.completed_trials,
        "manual_review": flagged,
    }
