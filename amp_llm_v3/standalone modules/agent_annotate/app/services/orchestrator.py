"""
Pipeline orchestrator - manages annotation job lifecycle.
"""

import uuid
from datetime import datetime
from typing import Optional

from app.models.job import AnnotationJob, JobSummary, JobProgress
from app.services.config_service import config_service


class PipelineOrchestrator:
    """Creates, tracks, and runs annotation pipeline jobs."""

    def __init__(self):
        self._jobs: dict[str, AnnotationJob] = {}

    def create_job(self, nct_ids: list[str]) -> AnnotationJob:
        """Create a new annotation job for the given NCT IDs."""
        job_id = uuid.uuid4().hex[:12]
        job = AnnotationJob(
            job_id=job_id,
            nct_ids=nct_ids,
            config_snapshot=config_service.snapshot(),
            progress=JobProgress(total_trials=len(nct_ids)),
        )
        self._jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[AnnotationJob]:
        """Look up a job by ID."""
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[JobSummary]:
        """Return lightweight summaries of all jobs."""
        summaries = []
        for job in self._jobs.values():
            summaries.append(
                JobSummary(
                    job_id=job.job_id,
                    status=job.status,
                    created_at=job.created_at,
                    total_trials=job.progress.total_trials,
                    completed_trials=job.progress.completed_trials,
                )
            )
        return summaries

    async def run_pipeline(self, job_id: str) -> None:
        """Execute the full annotation pipeline for a job.

        Stub - will be implemented in Phase 2 when all agents are wired up.
        Stages: research -> annotate -> verify -> review-queue -> output
        """
        job = self._jobs.get(job_id)
        if not job:
            return

        job.status = "running"
        job.updated_at = datetime.utcnow()
        job.progress.current_stage = "researching"

        # TODO: Phase 2 - wire up research agents, annotation, verification
        # For now, mark as completed immediately
        job.status = "completed"
        job.progress.current_stage = "done"
        job.progress.completed_trials = job.progress.total_trials
        job.updated_at = datetime.utcnow()

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running or queued job."""
        job = self._jobs.get(job_id)
        if not job or job.status not in ("queued", "running"):
            return False
        job.status = "cancelled"
        job.updated_at = datetime.utcnow()
        return True


# Module-level singleton
orchestrator = PipelineOrchestrator()
