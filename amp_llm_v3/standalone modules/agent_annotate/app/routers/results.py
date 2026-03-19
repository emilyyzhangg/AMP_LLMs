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
        for path in json_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
                version = data.get("version", {})
                timing = data.get("timing", {})
                results.append({
                    "job_id": path.stem,
                    "version": version.get("version", ""),
                    "git_commit": version.get("git_commit", ""),
                    "timestamp": version.get("timestamp", ""),
                    "total_trials": data.get("total_trials", 0),
                    "successful": data.get("successful", 0),
                    "failed": data.get("failed", 0),
                    "manual_review": data.get("manual_review", 0),
                    "timing": timing,
                })
            except Exception:
                continue
    # Sort by the timestamp embedded in the result JSON (latest first).
    # This is more accurate than sorting by filename (random hex job IDs).
    results.sort(key=lambda r: r.get("timestamp") or "", reverse=True)
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
        if job.status not in ("completed", "cancelled", "failed"):
            raise HTTPException(status_code=400, detail=f"Job is {job.status}, not completed")
        return {
            "job_id": job.job_id,
            "version": get_version_info().model_dump(),
            "trials": job.results,
            "timing": {
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                "elapsed_seconds": job.progress.elapsed_seconds,
                "avg_seconds_per_trial": job.progress.avg_seconds_per_trial,
                "commit_hash": job.commit_hash,
                "timezone": "America/Los_Angeles",
            },
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
        config_snapshot = data.get("config_snapshot", {}) if data else {}
        csv_content = generate_full_csv(trials, config_snapshot=config_snapshot,
                                        job_id=job_id)
    else:
        csv_content = generate_standard_csv(trials, job_id=job_id)

    path = save_csv(job_id, csv_content, label=format)

    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={path.name}"},
    )


@router.get("/{job_id}/partial")
async def get_partial_results(job_id: str):
    """Return trials completed so far for a running (or any) job.

    Reads directly from the persistence directory (results/annotations/{job_id}/*.json)
    so it works even while the pipeline is still running. Returns the same format as
    full results but with only completed trials and a count object.
    """
    annotations_dir = RESULTS_DIR / "annotations" / job_id
    if not annotations_dir.exists():
        raise HTTPException(status_code=404, detail="No annotation data found for this job")

    # Load all completed trial JSONs from disk
    completed_trials = []
    for trial_path in sorted(annotations_dir.glob("*.json")):
        if trial_path.name.endswith(".tmp"):
            continue
        nct_id = trial_path.stem
        try:
            with open(trial_path, "r") as f:
                trial_data = json.load(f)
            # Compute per-trial status
            verification = trial_data.get("verification") or {}
            if trial_data.get("error"):
                trial_status = "error"
            elif verification.get("flagged_for_review"):
                trial_status = "review"
            else:
                trial_status = "ok"
            completed_trials.append({
                "nct_id": trial_data.get("nct_id", nct_id),
                "status": trial_status,
            })
        except Exception:
            continue

    # Determine total trials from the job (in-memory) or research meta
    total = len(completed_trials)
    job = orchestrator.get_job(job_id)
    if job:
        total = job.progress.total_trials
    else:
        # Try research meta for the total count
        research_meta_path = RESULTS_DIR / "research" / job_id / "_meta.json"
        if research_meta_path.exists():
            try:
                with open(research_meta_path, "r") as f:
                    meta = json.load(f)
                total = meta.get("total_trials", len(completed_trials))
            except Exception:
                pass

    return {
        "job_id": job_id,
        "count": {
            "completed": len(completed_trials),
            "total": total,
        },
        "trials": completed_trials,
        "status": job.status if job else "unknown",
    }


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
            "timing": data.get("timing", {}),
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
        "timing": {
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "elapsed_seconds": job.progress.elapsed_seconds,
            "avg_seconds_per_trial": job.progress.avg_seconds_per_trial,
            "commit_hash": job.commit_hash,
            "timezone": "America/Los_Angeles",
        },
    }
