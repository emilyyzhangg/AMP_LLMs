"""
Pipeline orchestrator - manages annotation job lifecycle.

Two-phase architecture:
  Phase 1 (Research): All trials run fully parallel -> persisted to disk
  Phase 2 (Annotate): Sequential per trial -> annotate + verify -> persisted to disk

Persistence enables crash resilience, resume from where left off,
and re-annotation without re-researching.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional

from app.models.job import AnnotationJob, JobSummary, JobProgress, now_pacific
from app.models.research import ResearchResult
from app.models.annotation import FieldAnnotation, TrialMetadata, AnnotationResult
from app.models.verification import ConsensusResult, VerifiedAnnotation
from app.services.config_service import config_service
from app.services.output_service import save_json_output
from app.services.version_service import get_version_stamp, get_git_commit_full, get_git_commit_short
from app.services.persistence_service import PersistenceService
from app.config import RESULTS_DIR
from agents.research import RESEARCH_AGENTS
from agents.annotation import ANNOTATION_AGENTS
from agents.verification import BlindVerifier, ConsensusChecker, ReconciliationAgent
from app.services.review_service import review_service
from app.models.job import ReviewItem

logger = logging.getLogger("agent_annotate.orchestrator")


class PipelineOrchestrator:
    """Creates, tracks, and runs annotation pipeline jobs.

    Jobs are queued and processed sequentially by a background worker.
    Only one job runs at a time (Ollama bottleneck), but multiple jobs
    can be queued. The worker starts automatically on first job submission.
    """

    def __init__(self):
        self._jobs: dict[str, AnnotationJob] = {}
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker_running = False
        self._pending_requeue: list[str] = []
        self._pending_resume: list[str] = []
        # Reload persisted job states from disk
        self._reload_persisted_jobs()

    def restore_queued_jobs(self) -> None:
        """Re-enqueue queued jobs and auto-resume interrupted jobs on startup.

        Called from app startup (after event loop is running) because
        asyncio.Queue and ensure_future require a running loop.

        Interrupted jobs (were 'running' when service died) are automatically
        resumed so the autoupdater can restart freely without losing progress.
        """
        # First: resume interrupted jobs (were running, now marked failed)
        for job_id in list(self._pending_resume):
            try:
                job = self.resume_job(job_id, force=True)
                self._queue.put_nowait(job_id)
                logger.info(f"Auto-resuming interrupted job {job_id}")
            except Exception as e:
                logger.warning(f"Failed to auto-resume job {job_id}: {e}")
        self._pending_resume.clear()

        # Then: re-enqueue jobs that were queued
        for job_id in self._pending_requeue:
            job = self._jobs.get(job_id)
            if job and job.status == "queued":
                self._queue.put_nowait(job_id)
                logger.info(f"Re-enqueued persisted job {job_id}")
        self._pending_requeue.clear()

        if not self._queue.empty():
            self._ensure_worker()

    def _reload_persisted_jobs(self) -> None:
        """Reload job states from disk on startup.

        Jobs that were 'running' when the service died are marked 'failed'
        (they can be resumed). Completed/cancelled/failed jobs are loaded as-is.
        """
        persistence = PersistenceService(RESULTS_DIR)
        states = persistence.load_all_job_states()

        for job_id, state in states.items():
            status = state.get("status", "unknown")
            nct_ids = state.get("nct_ids", [])

            # Reconstruct job object
            progress = state.get("progress", {})
            job = AnnotationJob(
                job_id=job_id,
                nct_ids=nct_ids,
                config_snapshot=state.get("config_snapshot", {}),
                progress=JobProgress(
                    total_trials=progress.get("total_trials", len(nct_ids)),
                    completed_trials=progress.get("completed_trials", 0),
                    researched_trials=progress.get("researched_trials", 0),
                    elapsed_seconds=progress.get("elapsed_seconds", 0),
                    avg_seconds_per_trial=progress.get("avg_seconds_per_trial", 0),
                    current_stage=progress.get("current_stage", ""),
                ),
                commit_hash=state.get("commit_hash", ""),
            )

            # Jobs that were running at crash time -> mark failed, auto-resume
            if status == "running":
                job.status = "failed"
                job.error = "Service restarted while job was running"
                job.progress.current_stage = "interrupted"
                self._pending_resume.append(job_id)
            elif status == "queued":
                job.status = "queued"
                self._pending_requeue.append(job_id)
            else:
                job.status = status

            # Restore timestamps
            for ts_field in ["created_at", "started_at", "finished_at"]:
                ts_val = state.get(ts_field)
                if ts_val:
                    try:
                        from datetime import datetime
                        setattr(job, ts_field, datetime.fromisoformat(ts_val))
                    except (ValueError, TypeError):
                        pass

            job.resumed = state.get("resumed", False)

            self._jobs[job_id] = job

        if states:
            logger.info(f"Loaded {len(states)} persisted job states from disk")

    def _persist_job(self, job: AnnotationJob, trial_times: list[float] | None = None) -> None:
        """Write job state to disk for crash recovery."""
        persistence = PersistenceService(RESULTS_DIR)
        job_data = {
            "job_id": job.job_id,
            "nct_ids": job.nct_ids,
            "status": job.status,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "commit_hash": job.commit_hash,
            "resumed": job.resumed,
            "progress": {
                "total_trials": job.progress.total_trials,
                "completed_trials": job.progress.completed_trials,
                "researched_trials": job.progress.researched_trials,
                "elapsed_seconds": job.progress.elapsed_seconds,
                "avg_seconds_per_trial": job.progress.avg_seconds_per_trial,
                "current_stage": job.progress.current_stage,
                "current_nct_id": job.progress.current_nct_id,
                "current_field": job.progress.current_field,
                "current_agent": job.progress.current_agent,
                "current_model": job.progress.current_model,
                "field_timings": job.progress.field_timings,
                "verification_progress": job.progress.verification_progress,
            },
            "trial_times": trial_times or [],
        }
        persistence.save_job_state(job.job_id, job_data)

    def create_job(self, nct_ids: list[str]) -> AnnotationJob:
        job_id = uuid.uuid4().hex[:12]
        job = AnnotationJob(
            job_id=job_id,
            nct_ids=nct_ids,
            config_snapshot=config_service.snapshot(),
            progress=JobProgress(total_trials=len(nct_ids)),
            commit_hash=get_git_commit_short(),
        )
        self._jobs[job_id] = job
        self._persist_job(job)
        return job

    def enqueue_job(self, job_id: str) -> None:
        """Add a job to the processing queue."""
        self._queue.put_nowait(job_id)
        self._ensure_worker()

    def queue_size(self) -> int:
        """Number of jobs waiting in the queue (not including the running one)."""
        return self._queue.qsize()

    def queued_jobs(self) -> list[str]:
        """Return job IDs currently waiting in the queue."""
        return [j.job_id for j in self._jobs.values()
                if j.status == "queued" and j.job_id not in
                {jid for jid in [self._running_job_id()] if jid}]

    def _running_job_id(self) -> Optional[str]:
        """Return the job_id of the currently running job, if any."""
        for j in self._jobs.values():
            if j.status == "running":
                return j.job_id
        return None

    def _ensure_worker(self) -> None:
        """Start the queue worker if not already running."""
        if not self._worker_running:
            self._worker_running = True
            asyncio.ensure_future(self._queue_worker())

    async def _queue_worker(self) -> None:
        """Background worker that processes queued jobs sequentially.

        Waits for the other branch to finish before starting a job,
        since both branches share the same Ollama instance.
        """
        logger.info("Job queue worker started")
        try:
            while True:
                # Wait for next job (blocks until one is available)
                job_id = await asyncio.wait_for(self._queue.get(), timeout=60)
                job = self._jobs.get(job_id)
                if not job:
                    logger.warning(f"Queue worker: job {job_id} not found, skipping")
                    continue
                if job.status == "cancelled":
                    logger.info(f"Queue worker: job {job_id} was cancelled while queued, skipping")
                    continue

                # Wait for other branch to finish (cross-branch gatekeeper)
                await self._wait_for_other_branch(job_id)

                logger.info(f"Queue worker: starting job {job_id} ({job.progress.total_trials} trials)")
                await self.run_pipeline(job_id)
                logger.info(f"Queue worker: job {job_id} finished with status '{job.status}'")
        except asyncio.TimeoutError:
            # No jobs for 60s — shut down worker, will restart on next enqueue
            logger.info("Job queue worker idle, shutting down")
        except Exception as e:
            logger.error(f"Job queue worker crashed: {e}", exc_info=True)
        finally:
            self._worker_running = False

    async def _wait_for_other_branch(self, job_id: str) -> None:
        """Wait until the other branch's agent-annotate has no active jobs.

        Detects which port we're actually running on by checking which port
        is bound, rather than relying on AGENT_ANNOTATE_PORT config (which
        may not be set correctly in the LaunchDaemon environment).
        """
        import httpx

        # Detect our actual port by checking which one we're serving on
        our_port = self._detect_our_port()
        other_port = 9005 if our_port == 8005 else 8005
        other_url = f"http://localhost:{other_port}/api/jobs/active"
        other_branch = "dev" if other_port == 9005 else "main"

        while True:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(other_url)
                    if resp.status_code == 200:
                        other_active = resp.json().get("active", 0)
                        if other_active > 0:
                            logger.info(
                                f"Queue worker: waiting for {other_branch} job to finish "
                                f"before starting {job_id}"
                            )
                            await asyncio.sleep(30)
                            # Check if our job was cancelled while waiting
                            job = self._jobs.get(job_id)
                            if job and job.status == "cancelled":
                                return
                            continue
            except Exception:
                pass  # Other branch not reachable — safe to proceed
            break

    @staticmethod
    def _detect_our_port() -> int:
        """Detect which port this service is actually running on."""
        import socket
        # Try to bind on 8005 — if it fails, we're on 8005
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("127.0.0.1", 8005))
            s.close()
            # Port 8005 is free — we must be on 9005
            return 9005
        except OSError:
            # Port 8005 is in use (by us) — we're on 8005
            return 8005

    def get_job(self, job_id: str) -> Optional[AnnotationJob]:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[JobSummary]:
        summaries = []
        for job in self._jobs.values():
            summaries.append(
                JobSummary(
                    job_id=job.job_id,
                    status=job.status,
                    created_at=job.created_at,
                    total_trials=job.progress.total_trials,
                    completed_trials=job.progress.completed_trials,
                    researched_trials=job.progress.researched_trials,
                    started_at=job.started_at,
                    finished_at=job.finished_at,
                    elapsed_seconds=job.progress.elapsed_seconds,
                    avg_seconds_per_trial=job.progress.avg_seconds_per_trial,
                    commit_hash=job.commit_hash,
                    warnings_count=len(job.progress.warnings),
                    timeouts_count=sum(job.progress.timeouts.values()) if job.progress.timeouts else 0,
                    retries_count=sum(job.progress.retries.values()) if job.progress.retries else 0,
                )
            )
        summaries.sort(key=lambda s: s.created_at or "", reverse=True)
        return summaries

    def active_count(self) -> int:
        return sum(1 for j in self._jobs.values() if j.status in ("queued", "running"))

    def resume_job(self, job_id: str, force: bool = False) -> AnnotationJob:
        """Resume a failed or cancelled job from persisted state."""
        persistence = PersistenceService(RESULTS_DIR)

        if not persistence.research_exists(job_id):
            raise ValueError(f"No research data found for job {job_id}")

        current_commit = get_git_commit_full()
        validation = persistence.validate_resume(job_id, current_commit)

        if not validation.commit_match and not force:
            raise ValueError(
                f"Git commit mismatch. Research: {validation.original_commit[:8]}, "
                f"Current: {validation.current_commit[:8]}. Use force=true to override."
            )

        original_job = self._jobs.get(job_id)
        if original_job and original_job.status not in ("failed", "cancelled"):
            raise ValueError(
                f"Can only resume failed or cancelled jobs. "
                f"Job {job_id} status is '{original_job.status}'."
            )

        meta = persistence.load_research_meta(job_id)
        nct_ids = meta.get("nct_ids", [])

        job = AnnotationJob(
            job_id=job_id,
            nct_ids=nct_ids,
            config_snapshot=config_service.snapshot(),
            progress=JobProgress(total_trials=len(nct_ids)),
            resumed=True,
            resumed_at=now_pacific(),
            commit_hash=get_git_commit_short(),
        )
        self._jobs[job_id] = job
        return job

    async def run_pipeline(self, job_id: str) -> None:
        """Execute the full annotation pipeline for a job."""
        job = self._jobs.get(job_id)
        if not job:
            return

        try:
            await self._run_pipeline_inner(job)
        except Exception as e:
            logger.exception(f"[{job_id}] Pipeline failed with unhandled error: {e}")
            job.status = "failed"
            job.error = str(e)
            job.progress.current_stage = "error"
            job.finished_at = now_pacific()
            job.updated_at = now_pacific()
            self._persist_job(job)

    async def _run_pipeline_inner(self, job: AnnotationJob) -> None:
        """Inner pipeline logic with two-phase architecture.

        Phase 1: Research all trials in parallel (no Ollama dependency)
        Phase 2: Annotate + verify each trial sequentially (Ollama-bottlenecked)
        """
        import time as _time

        job_id = job.job_id
        job.status = "running"
        job.started_at = now_pacific()
        job.updated_at = now_pacific()
        config = config_service.get()

        # Configure Ollama keep_alive and per-model timeouts
        from app.services.ollama_client import ollama_client
        hw_profile = getattr(config.orchestrator, "hardware_profile", "mac_mini")
        ollama_client.set_hardware_profile(hw_profile)
        # v17: Load per-model timeout overrides from config
        model_timeouts = getattr(config.ollama, "model_timeouts", {})
        if model_timeouts:
            ollama_client.set_model_timeouts(model_timeouts)
        pipeline_start = _time.monotonic()
        # If resumed, offset the start time backward to account for previous elapsed time
        if job.resumed and job.progress.elapsed_seconds > 0:
            pipeline_start -= job.progress.elapsed_seconds

        persistence = PersistenceService(RESULTS_DIR)
        version_stamp = get_version_stamp()

        # Determine resume state
        skip_research = set()
        skip_annotations = set()
        if job.resumed:
            skip_research = persistence.get_completed_research(job_id)
            skip_annotations = persistence.get_completed_annotations(job_id)
            logger.info(
                f"[{job_id}] Resuming: {len(skip_research)} research, "
                f"{len(skip_annotations)} annotations already on disk"
            )

        # --- Phase 1: Research (all trials, fully parallel) ---
        if len(skip_research) < len(job.nct_ids):
            persistence.init_research_dir(
                job_id, job.nct_ids, version_stamp, job.config_snapshot
            )
            research_data = await self._run_phase1_research(
                job, config, persistence, skip_research, pipeline_start
            )
        else:
            research_data = {}
            for nct_id in job.nct_ids:
                loaded = persistence.load_research(job_id, nct_id)
                research_data[nct_id] = loaded if loaded is not None else []
            job.progress.researched_trials = len(job.nct_ids)
            job.progress.current_stage = "research_complete"
            logger.info(f"[{job_id}] All research loaded from disk")

        # --- Phase 2: Annotation + Verification ---
        persistence.init_annotations_dir(job_id)
        all_trial_results, trial_times = await self._run_phase2_annotate(
            job, config, research_data, persistence, skip_annotations, pipeline_start
        )

        # --- Save final results ---
        job.progress.current_stage = "saving"
        job.progress.current_phase = ""
        job.progress.elapsed_seconds = round(_time.monotonic() - pipeline_start, 1)
        if job.progress.completed_trials > 0:
            job.progress.avg_seconds_per_trial = round(
                job.progress.elapsed_seconds / job.progress.completed_trials, 1
            )
        version = get_version_stamp()
        flagged = sum(
            1 for r in all_trial_results
            if r.get("verification") and r["verification"].get("flagged_for_review")
        )
        output = {
            "version": version,
            "status": job.status,
            "config_snapshot": job.config_snapshot,
            "trials": all_trial_results,
            "total_trials": len(all_trial_results),
            "successful": sum(1 for r in all_trial_results if r.get("annotations")),
            "failed": sum(1 for r in all_trial_results if not r.get("annotations")),
            "manual_review": flagged,
            "timing": {
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "finished_at": now_pacific().isoformat(),
                "elapsed_seconds": job.progress.elapsed_seconds,
                "avg_seconds_per_trial": job.progress.avg_seconds_per_trial,
                "commit_hash": job.commit_hash,
                "timezone": "America/Los_Angeles",
            },
        }
        if job.resumed:
            output["resumed"] = True
            output["resumed_at"] = job.resumed_at.isoformat() if job.resumed_at else None

        # v17: Populate timeouts from Ollama client at job completion
        from app.services.ollama_client import ollama_client
        job.progress.timeouts = ollama_client.get_timeout_stats()

        # v17: Add diagnostics to output
        output["diagnostics"] = {
            "warnings": job.progress.warnings,
            "timeouts": job.progress.timeouts,
            "retries": job.progress.retries,
            "timing_anomalies": len([w for w in job.progress.warnings if "ANOMALY" in w]),
            "quality_issues": len([w for w in job.progress.warnings if "QUALITY" in w]),
        }

        save_json_output(job_id, output)

        job.results = all_trial_results
        if job.status != "cancelled":
            job.status = "completed"
        job.finished_at = now_pacific()
        if job.status == "cancelled":
            job.progress.current_stage = "cancelled"
        else:
            job.progress.current_stage = "done"
        job.progress.current_nct_id = None
        job.progress.current_phase = ""
        job.progress.current_field = None
        job.progress.current_agent = None
        job.progress.current_model = None
        job.progress.verification_progress = None
        job.progress.field_timings = {}
        job.updated_at = now_pacific()
        self._persist_job(job)
        logger.info(f"[{job_id}] Pipeline {job.status}: {len(all_trial_results)} trials")

        # --- v17: Post-job diagnostics summary ---
        self._log_job_diagnostics(job_id, all_trial_results, trial_times)

        # --- EDAM post-job hook: self-learning feedback loops ---
        try:
            from app.services.memory import edam_post_job_hook
            edam_summary = await edam_post_job_hook(
                job_id, all_trial_results, job.config_snapshot
            )
            if edam_summary.get("errors"):
                logger.warning("[%s] EDAM completed with errors: %s",
                               job_id, edam_summary["errors"])
        except Exception as e:
            logger.warning("[%s] EDAM post-job hook failed (non-fatal): %s", job_id, e)

    async def _run_phase1_research(
        self,
        job: AnnotationJob,
        config,
        persistence: PersistenceService,
        skip_nct_ids: set[str],
        pipeline_start: float,
    ) -> dict[str, list[ResearchResult]]:
        """Phase 1: Run research for all trials in parallel.

        Research agents make external API calls (no Ollama) so all trials
        can be researched concurrently, bounded by a semaphore.
        """
        import time as _time

        job.progress.current_phase = "research"
        job.progress.current_stage = "researching"
        job.updated_at = now_pacific()

        research_data: dict[str, list[ResearchResult]] = {}
        sem = asyncio.Semaphore(20)
        progress_lock = asyncio.Lock()

        # Load already-completed research from disk
        for nct_id in skip_nct_ids:
            loaded = persistence.load_research(job.job_id, nct_id)
            research_data[nct_id] = loaded if loaded is not None else []
            job.progress.researched_trials += 1

        remaining = [nct for nct in job.nct_ids if nct not in skip_nct_ids]

        async def research_one(nct_id: str) -> None:
            if job.status == "cancelled":
                return
            async with sem:
                if job.status == "cancelled":
                    return
                logger.info(f"[{job.job_id}] Researching {nct_id}")
                try:
                    results = await self._run_research(nct_id, config, job)
                    persistence.save_research(job.job_id, nct_id, results)
                    research_data[nct_id] = results
                except Exception as e:
                    logger.error(
                        f"[{job.job_id}] Research failed for {nct_id}: {e}"
                    )
                    research_data[nct_id] = []
                async with progress_lock:
                    job.progress.researched_trials += 1
                    job.progress.elapsed_seconds = round(
                        _time.monotonic() - pipeline_start, 1
                    )
                    job.updated_at = now_pacific()

        if remaining:
            logger.info(
                f"[{job.job_id}] Phase 1: researching {len(remaining)} trials "
                f"({len(skip_nct_ids)} cached)"
            )
            await asyncio.gather(
                *(research_one(nct) for nct in remaining),
                return_exceptions=True,
            )

        job.progress.current_stage = "research_complete"
        job.progress.elapsed_seconds = round(_time.monotonic() - pipeline_start, 1)
        job.updated_at = now_pacific()
        logger.info(
            f"[{job.job_id}] Phase 1 complete: {len(research_data)} trials researched"
        )
        return research_data

    async def _run_phase2_annotate(
        self,
        job: AnnotationJob,
        config,
        research_data: dict[str, list[ResearchResult]],
        persistence: PersistenceService,
        skip_nct_ids: set[str],
        pipeline_start: float,
    ) -> list[dict]:
        """Phase 2: Annotate and verify in mini-batches.

        Mini-batch processing reduces Ollama model switches by grouping:
        1. Annotate N trials (annotation model stays loaded)
        2. Verify all N trials model-grouped (each verifier processes all trials)
        3. Reconcile all disagreements (reconciler loaded once)
        4. Persist each trial after its verification finalizes

        Batch size of 5 reduces model switches from ~4-5/trial to ~0.8/trial.
        On interruption, at most batch_size trials of annotation work are lost
        (research is cached, persisted trials are safe).
        """
        import time as _time

        MINI_BATCH_SIZE = 5

        job.progress.current_phase = "annotation"
        all_trial_results = []
        trial_times: list[float] = []

        # Filter out already-completed trials (resume support)
        pending_ncts = []
        for nct_id in job.nct_ids:
            if nct_id in skip_nct_ids:
                cached = persistence.load_annotation(job.job_id, nct_id)
                if cached:
                    all_trial_results.append(cached)
                    job.progress.completed_trials += 1
                    logger.info(f"[{job.job_id}] Loaded cached annotation for {nct_id}")
                    continue
            pending_ncts.append(nct_id)

        # Process in mini-batches
        for batch_start in range(0, len(pending_ncts), MINI_BATCH_SIZE):
            if job.status == "cancelled":
                break

            batch_ncts = pending_ncts[batch_start:batch_start + MINI_BATCH_SIZE]
            batch_idx_offset = len(job.nct_ids) - len(pending_ncts) + batch_start
            logger.info(
                f"[{job.job_id}] Mini-batch: {len(batch_ncts)} trials "
                f"({batch_idx_offset+1}-{batch_idx_offset+len(batch_ncts)}/{len(job.nct_ids)})"
            )

            # =================================================================
            # Phase A: Annotate all trials in batch (annotation model stays loaded)
            # =================================================================
            job.progress.current_stage = "annotating"
            batch_annotations = {}  # nct_id → (annotations, research, trial_start)
            batch_errors = {}       # nct_id → error string

            for j, nct_id in enumerate(batch_ncts):
                if job.status == "cancelled":
                    break

                trial_start = _time.monotonic()
                job.progress.current_nct_id = nct_id
                job.progress.elapsed_seconds = round(_time.monotonic() - pipeline_start, 1)
                job.updated_at = now_pacific()
                research = research_data.get(nct_id, [])
                logger.info(
                    f"[{job.job_id}] Annotating {nct_id} "
                    f"({batch_idx_offset+j+1}/{len(job.nct_ids)}, "
                    f"batch {j+1}/{len(batch_ncts)})"
                )

                try:
                    annotations = await self._run_annotation(
                        nct_id, research, config, job
                    )
                    # Snapshot pre-consistency values for EDAM learning
                    pre_consistency = {a.field_name: a.value for a in annotations}
                    self._enforce_consistency(annotations, research_data=research)
                    # Store consistency overrides as EDAM corrections
                    self._store_consistency_overrides(
                        nct_id, job.job_id, annotations,
                        pre_consistency, job.config_snapshot,
                    )
                    batch_annotations[nct_id] = (annotations, research, trial_start)
                except Exception as e:
                    logger.error(f"[{job.job_id}] Annotation error for {nct_id}: {e}")
                    batch_errors[nct_id] = str(e)
                    # Persist error result immediately
                    metadata = TrialMetadata(nct_id=nct_id)
                    trial_output = {
                        "nct_id": nct_id,
                        "metadata": metadata.model_dump(),
                        "annotations": [],
                        "verification": None,
                        "research_used": [],
                        "research_results": [r.model_dump() for r in research],
                        "error": str(e),
                    }
                    all_trial_results.append(trial_output)
                    job.progress.completed_trials += 1
                    self._update_timing(job, trial_start, pipeline_start, trial_times)
                    self._persist_job(job, trial_times)

            if not batch_annotations:
                continue  # all errored

            # =================================================================
            # Phase B: Verify all trials model-grouped (3 model switches total)
            # =================================================================
            job.progress.current_stage = "verifying"
            job.progress.elapsed_seconds = round(_time.monotonic() - pipeline_start, 1)
            job.updated_at = now_pacific()

            batch_verified = {}  # nct_id → (annotations, verified)

            # Collect all annotations that need verification across ALL trials
            # Structure: {nct_id: {field_name: annotation}}
            all_trial_annotations = {}
            for nct_id, (annotations, research, _) in batch_annotations.items():
                all_trial_annotations[nct_id] = {a.field_name: a for a in annotations}

            # Separate skip vs verify across all trials
            skip_results = {}     # nct_id → [ConsensusResult]
            verify_items = []     # [(nct_id, annotation)]
            any_flagged_by_trial = {nct_id: False for nct_id in batch_annotations}
            flag_reasons_by_trial = {nct_id: [] for nct_id in batch_annotations}

            for nct_id, (annotations, _, _) in batch_annotations.items():
                skip_results[nct_id] = []
                for annotation in annotations:
                    if annotation.skip_verification:
                        skip_results[nct_id].append(ConsensusResult(
                            field_name=annotation.field_name,
                            original_value=annotation.value,
                            final_value=annotation.value,
                            consensus_reached=True,
                            agreement_ratio=1.0,
                            opinions=[],
                        ))
                    elif annotation.confidence < 0.2 and "[Below threshold" in (annotation.reasoning or ""):
                        skip_results[nct_id].append(ConsensusResult(
                            field_name=annotation.field_name,
                            original_value=annotation.value,
                            final_value="",
                            consensus_reached=False,
                            agreement_ratio=0.0,
                            opinions=[],
                            flag_reason="insufficient_evidence",
                        ))
                        any_flagged_by_trial[nct_id] = True
                        flag_reasons_by_trial[nct_id].append(f"{annotation.field_name}: insufficient evidence")
                    else:
                        verify_items.append((nct_id, annotation))

            # Model-grouped verification across ALL trials in batch
            verifier = BlindVerifier()
            verifier_models = [
                (key, m) for key, m in config.verification.models.items()
                if m.role == "verifier"
            ]
            server_verifiers = getattr(config.orchestrator, "server_verifiers", [])
            if config.orchestrator.hardware_profile == "server" and server_verifiers:
                from app.models.config_models import ModelConfig
                upgraded = []
                for vi, (key, m) in enumerate(verifier_models):
                    if vi < len(server_verifiers):
                        upgraded.append((key, ModelConfig(name=server_verifiers[vi], role="verifier")))
                    else:
                        upgraded.append((key, m))
                verifier_models = upgraded
            # v42.6.7 Eff #7: fast-model verifier override. When set,
            # replaces verifier_1/2/3 names with smaller/faster models to
            # 3x verifier throughput on high-volume jobs. Reconciliation
            # still uses the reconciler model (larger); only the blind
            # verifier pool gets downsized.
            verifier_fast_models = getattr(config.orchestrator, "verifier_fast_models", [])
            if verifier_fast_models:
                from app.models.config_models import ModelConfig
                downsized = []
                for vi, (key, m) in enumerate(verifier_models):
                    if vi < len(verifier_fast_models):
                        downsized.append((key, ModelConfig(name=verifier_fast_models[vi], role="verifier")))
                    else:
                        downsized.append((key, m))
                verifier_models = downsized

            all_opinions = {}  # (nct_id, field_name) → [opinions]
            for nct_id, ann in verify_items:
                all_opinions[(nct_id, ann.field_name)] = []

            total_verify = len(verify_items)
            for model_key, model_cfg in verifier_models:
                job.progress.current_agent = model_key
                job.progress.current_model = model_cfg.name
                logger.info(
                    f"  Verifier {model_key} ({model_cfg.name}): "
                    f"{total_verify} fields across {len(batch_annotations)} trials"
                )

                for vi, (nct_id, annotation) in enumerate(verify_items):
                    if job.status == "cancelled":
                        break
                    job.progress.current_nct_id = nct_id
                    job.progress.current_field = annotation.field_name
                    job.progress.verification_progress = (
                        f"{model_key}: {vi+1}/{total_verify} fields"
                    )

                    research = batch_annotations[nct_id][1]
                    opinion = await verifier.verify(
                        nct_id=nct_id,
                        field_name=annotation.field_name,
                        research_results=research,
                        model_name=model_key,
                        ollama_model=model_cfg.name,
                    )
                    # v17: Retry once on timeout/failure
                    # v28: Also retry parse failures; use reduced evidence (8 citations)
                    should_retry = (
                        (opinion.confidence == 0.0
                         and opinion.suggested_value is None
                         and "failed" in (opinion.reasoning or "").lower())
                        or opinion.parse_failed
                    )
                    if should_retry:
                        logger.warning(
                            f"  Verifier {model_key} failed for {nct_id}/{annotation.field_name} — "
                            f"retrying with reduced evidence..."
                        )
                        import asyncio as _asyncio
                        await _asyncio.sleep(5)
                        retry_opinion = await verifier.verify(
                            nct_id=nct_id,
                            field_name=annotation.field_name,
                            research_results=research,
                            model_name=model_key,
                            ollama_model=model_cfg.name,
                            max_citations_override=8,
                        )
                        if retry_opinion.suggested_value is not None:
                            logger.info(
                                f"  Verifier {model_key} retry SUCCEEDED for "
                                f"{nct_id}/{annotation.field_name}: {retry_opinion.suggested_value}"
                            )
                            opinion = retry_opinion
                        else:
                            logger.warning(
                                f"  Verifier {model_key} retry FAILED for "
                                f"{nct_id}/{annotation.field_name} — accepting failure"
                            )
                            job.progress.warnings.append(
                                f"TIMEOUT [{nct_id}]: {model_key} ({model_cfg.name}) "
                                f"failed for {annotation.field_name} after retry"
                            )
                        job.progress.retries["verification"] = (
                            job.progress.retries.get("verification", 0) + 1
                        )
                    all_opinions[(nct_id, annotation.field_name)].append(opinion)

            # Consensus checks (no LLM calls)
            job.progress.current_agent = "consensus"
            job.progress.current_model = None
            job.progress.verification_progress = "checking consensus"

            checker = ConsensusChecker()
            threshold = config.verification.consensus_threshold
            reconcile_queue = []  # [(nct_id, annotation, consensus)]
            consensus_by_trial = {nct_id: list(skip_results[nct_id]) for nct_id in batch_annotations}

            for nct_id, annotation in verify_items:
                opinions = all_opinions[(nct_id, annotation.field_name)]
                consensus = checker.check(
                    field_name=annotation.field_name,
                    primary_value=annotation.value,
                    primary_model="primary",
                    verifier_opinions=opinions,
                    threshold=threshold,
                )
                consensus.primary_confidence = annotation.confidence

                if not consensus.consensus_reached:
                    # High-confidence primary protection.
                    # v31: Two paths to protect the primary:
                    #   1. At least one verifier agrees (agreement_ratio > 0)
                    #   2. Unanimous dissent, but all dissenters are low-confidence
                    #      (avg < 0.55) — uncertain models shouldn't override
                    #      a confident primary.
                    dissenting = [o for o in consensus.opinions if not o.agrees]
                    verifier_max_conf = max(
                        (o.confidence for o in dissenting),
                        default=0.0,
                    )
                    avg_dissent_conf = (
                        sum(o.confidence for o in dissenting) / len(dissenting)
                        if dissenting else 0.0
                    )
                    # v31: Also check evidence grade — db-confirmed annotations
                    # require stronger dissent to override
                    evidence_grade = getattr(annotation, "evidence_grade", "llm")
                    override_conf_bar = 0.8 if evidence_grade == "db_confirmed" else 0.7

                    if (annotation.confidence > 0.85
                            and verifier_max_conf <= override_conf_bar
                            and (consensus.agreement_ratio > 0.0
                                 or avg_dissent_conf < 0.55)):
                        consensus.final_value = annotation.value
                        consensus.consensus_reached = True
                        consensus.reconciler_used = False
                        consensus.reconciler_reasoning = (
                            f"Primary override: confidence {annotation.confidence:.2f} "
                            f"> 0.85, dissenting verifiers avg {avg_dissent_conf:.2f}"
                        )
                    else:
                        reconcile_queue.append((nct_id, annotation, consensus))
                        continue

                if not consensus.consensus_reached:
                    any_flagged_by_trial[nct_id] = True
                    flag_reasons_by_trial[nct_id].append(f"{annotation.field_name}: model disagreement")

                consensus_by_trial[nct_id].append(consensus)

            # Batch reconciliation (one model load)
            if reconcile_queue:
                reconciler_model = None
                for key, m in config.verification.models.items():
                    if m.role == "reconciler":
                        reconciler_model = m.name
                        break
                if config.orchestrator.hardware_profile == "server":
                    reconciler_model = getattr(
                        config.orchestrator, "server_premium_model", reconciler_model
                    )

                if reconciler_model:
                    reconciler = ReconciliationAgent()
                    job.progress.current_agent = "reconciler"
                    job.progress.current_model = reconciler_model
                    job.progress.verification_progress = f"reconciling {len(reconcile_queue)} fields"

                    for nct_id, annotation, consensus in reconcile_queue:
                        job.progress.current_nct_id = nct_id
                        job.progress.current_field = annotation.field_name
                        research = batch_annotations[nct_id][1]

                        consensus = await reconciler.reconcile(
                            field_name=annotation.field_name,
                            consensus_result=consensus,
                            research_results=research,
                            reconciler_model=reconciler_model,
                            primary_confidence=annotation.confidence,
                        )

                        if not consensus.consensus_reached:
                            any_flagged_by_trial[nct_id] = True
                            flag_reasons_by_trial[nct_id].append(
                                f"{annotation.field_name}: model disagreement"
                            )

                        consensus_by_trial[nct_id].append(consensus)

            # =================================================================
            # Phase C: Finalize + persist each trial
            # =================================================================
            job.progress.current_stage = "saving"
            job.progress.verification_progress = None
            job.progress.current_field = None
            job.progress.current_agent = None
            job.progress.current_model = None

            for nct_id, (annotations, research, trial_start) in batch_annotations.items():
                try:
                    verified = VerifiedAnnotation(
                        nct_id=nct_id,
                        fields=consensus_by_trial.get(nct_id, []),
                        overall_consensus=not any_flagged_by_trial.get(nct_id, False),
                        flagged_for_review=any_flagged_by_trial.get(nct_id, False),
                        flag_reason="; ".join(flag_reasons_by_trial.get(nct_id, [])) or None,
                    )

                    # Peptide cascade re-verification
                    annotations, verified = await self._peptide_cascade_check(
                        nct_id, annotations, verified, research, config
                    )
                    self._enforce_post_verification_consistency(verified)
                    self._normalize_final_values(verified)

                    # v38: Reconciliation corrections DISABLED for EDAM learning.
                    # Reconciler decisions are unreliable (hallucinations, assumptions,
                    # overriding correct answers) and dominated 91.6% of EDAM corrections,
                    # poisoning the learning signal. Logged for diagnostics only.
                    # self._store_reconciliation_corrections(
                    #     nct_id, job.job_id, verified,
                    #     ann_by_field, job.config_snapshot,
                    # )

                    metadata = self._extract_metadata(nct_id, research)
                    research_coverage = self._build_research_coverage(research)

                    trial_output = {
                        "nct_id": nct_id,
                        "metadata": metadata.model_dump(),
                        "annotations": [a.model_dump() for a in annotations],
                        "verification": verified.model_dump(),
                        "research_used": [r.agent_name for r in research],
                        "research_results": [r.model_dump() for r in research],
                        "research_coverage": research_coverage,
                    }
                    persistence.save_annotation(job.job_id, nct_id, trial_output)
                    all_trial_results.append(trial_output)

                    if verified.flagged_for_review:
                        self._queue_for_review(
                            job.job_id, nct_id, annotations, verified,
                            commit_hash=job.commit_hash,
                            created_at=job.started_at.isoformat() if job.started_at else "",
                        )

                    job.progress.completed_trials += 1
                    self._update_timing(job, trial_start, pipeline_start, trial_times)

                except Exception as e:
                    logger.error(f"[{job.job_id}] Finalize error for {nct_id}: {e}")
                    # Only append if this NCT wasn't already added (avoids duplicates
                    # when persistence fails after annotation succeeded)
                    if not any(t["nct_id"] == nct_id for t in all_trial_results):
                        metadata = TrialMetadata(nct_id=nct_id)
                        trial_output = {
                            "nct_id": nct_id,
                            "metadata": metadata.model_dump(),
                            "annotations": [a.model_dump() for a in annotations],
                            "verification": None,
                            "research_used": [r.agent_name for r in research],
                            "research_results": [r.model_dump() for r in research],
                            "error": str(e),
                        }
                        all_trial_results.append(trial_output)
                    job.progress.completed_trials += 1
                    self._update_timing(job, trial_start, pipeline_start, trial_times)

            self._persist_job(job, trial_times)

        return all_trial_results, trial_times

    async def _run_research(
        self,
        nct_id: str,
        config,
        job: AnnotationJob,
    ) -> list[ResearchResult]:
        """Dispatch all research agents in parallel.

        Runs clinical_protocol first to extract intervention names,
        then passes them as metadata to all other agents so they can
        search peptide/drug databases by name.
        """
        results = []

        # Step 1: Run clinical_protocol first to get intervention names
        metadata = None
        proto_config = config.research_agents.get("clinical_protocol")
        if proto_config and "clinical_protocol" in RESEARCH_AGENTS:
            proto_agent = RESEARCH_AGENTS["clinical_protocol"]()
            try:
                proto_result = await proto_agent.research(nct_id)
                results.append(proto_result)
                logger.info(f"  clinical_protocol: {len(proto_result.citations)} citations")

                # Extract intervention names from raw protocol data
                interventions = []
                if proto_result.raw_data:
                    proto_section = proto_result.raw_data.get(
                        "protocol_section",
                        proto_result.raw_data.get("protocolSection", {}),
                    )
                    arms_mod = proto_section.get("armsInterventionsModule", {})
                    for interv in arms_mod.get("interventions", []):
                        name = interv.get("name", "")
                        if name:
                            interventions.append({"name": name})
                if interventions:
                    # v31: Include title for literature API fallback searches
                    id_mod = proto_section.get("identificationModule", {})
                    trial_title = (
                        id_mod.get("briefTitle", "")
                        or id_mod.get("officialTitle", "")
                    )
                    metadata = {"interventions": interventions, "title": trial_title}
                    logger.info(
                        f"  Extracted interventions: "
                        f"{[i['name'] for i in interventions]}"
                    )

                    # Layer 1: Resolve drug names (abbreviations/brand names → generic + synonyms)
                    try:
                        await self._resolve_drug_names(proto_result, interventions, config, nct_id)
                        logger.info(
                            f"  Resolved drug names: "
                            f"{[(i['name'], i.get('resolved', [])) for i in interventions]}"
                        )
                    except Exception as resolve_err:
                        logger.warning(f"  Drug name resolution failed (non-fatal): {resolve_err}")
            except Exception as e:
                logger.warning(f"clinical_protocol failed: {e}")
                results.append(ResearchResult(
                    agent_name="clinical_protocol",
                    nct_id=nct_id,
                    error=str(e),
                ))

        # v42.6.3 Eff #3: skip AMP-specific research agents when the
        # clinical_protocol intervention type clearly indicates a non-peptide
        # trial (Drug small-molecule / Device / Behavioral / Procedure / etc.).
        # These agents (DBAASP, APD, RCSB_PDB, PDBe, EBI_proteins) only
        # produce AMP-specific evidence; burning ~20s per trial on agents
        # that can't contribute is wasted work on throughput runs.
        amp_only_agents = {"dbaasp", "apd", "rcsb_pdb", "pdbe", "ebi_proteins"}
        skip_amp = (
            getattr(config.orchestrator, "skip_amp_research_for_non_peptides", False)
            and self._intervention_is_clearly_non_peptide(results)
        )
        if skip_amp:
            logger.info(
                f"  Eff #3: clinical_protocol indicates non-peptide "
                f"intervention — skipping AMP-specific research agents"
            )

        # Step 2: Run all other agents in parallel with metadata
        tasks = {}
        for agent_name, agent_cls in RESEARCH_AGENTS.items():
            if agent_name == "clinical_protocol":
                continue  # already ran
            if skip_amp and agent_name in amp_only_agents:
                continue
            agent_config = config.research_agents.get(agent_name)
            if not agent_config:
                continue
            agent = agent_cls()
            tasks[agent_name] = agent.research(nct_id, metadata=metadata)

        if config.orchestrator.parallel_research and len(tasks) > 1:
            # Run in parallel
            gathered = await asyncio.gather(
                *tasks.values(), return_exceptions=True
            )
            for agent_name, result in zip(tasks.keys(), gathered):
                if isinstance(result, Exception):
                    logger.warning(f"Research agent {agent_name} failed: {result}")
                    results.append(ResearchResult(
                        agent_name=agent_name,
                        nct_id=nct_id,
                        error=str(result),
                    ))
                else:
                    results.append(result)
                    logger.info(
                        f"  {agent_name}: {len(result.citations)} citations"
                    )
        else:
            # Run sequentially
            for agent_name, coro in tasks.items():
                try:
                    result = await coro
                    results.append(result)
                    logger.info(
                        f"  {agent_name}: {len(result.citations)} citations"
                    )
                except Exception as e:
                    logger.warning(f"Research agent {agent_name} failed: {e}")
                    results.append(ResearchResult(
                        agent_name=agent_name,
                        nct_id=nct_id,
                        error=str(e),
                    ))

        return results

    async def _resolve_drug_names(
        self,
        proto_result: ResearchResult,
        interventions: list[dict],
        config,
        nct_id: str = "",
    ) -> None:
        """Resolve abbreviations/brand names to generic drug names + synonyms.

        Uses the trial's own text (brief summary + detailed description) and the
        annotation_model (qwen3:14b, already loaded during research phase) to
        resolve each intervention name to its generic name and common synonyms.
        Modifies interventions list in-place, adding a 'resolved' key to each dict.

        EDAM integration: checks the drug_names cache first — if a name has been
        resolved before, skip the LLM call. After LLM resolves new names, store
        them in EDAM for future use.

        This is a cheap single LLM call per trial — no model switch needed.
        """
        from app.services.ollama_client import ollama_client

        # --- EDAM cache: check for previously resolved names ---
        try:
            from app.services.memory.memory_store import memory_store as _edam
        except Exception:
            _edam = None

        # Extract trial description text from protocol data
        raw = proto_result.raw_data or {}
        proto_section = raw.get(
            "protocol_section", raw.get("protocolSection", {})
        )
        desc_mod = proto_section.get("descriptionModule", {})
        brief_summary = desc_mod.get("briefSummary", "")
        detailed_desc = desc_mod.get("detailedDescription", "")
        trial_text = f"{brief_summary}\n{detailed_desc}".strip()

        if not trial_text or not interventions:
            return

        # Build the list of intervention names to resolve
        names = [i["name"] for i in interventions if i.get("name")]
        if not names:
            return

        # Check EDAM cache for each name — skip LLM for cached resolutions
        names_needing_llm = []
        cached_resolutions = {}  # name -> [resolved_names]
        for name in names:
            if _edam:
                try:
                    cached = _edam.get_resolved_names(name)
                    if cached:
                        cached_resolutions[name] = cached
                        logger.info(f"  EDAM cache hit for drug '{name}': {cached}")
                        continue
                except Exception:
                    pass  # cache miss is fine
            names_needing_llm.append(name)

        # Apply cached resolutions immediately
        for interv in interventions:
            name = interv.get("name", "")
            if name in cached_resolutions:
                interv["resolved"] = cached_resolutions[name]

        # If all names were cached, skip the LLM call entirely
        if not names_needing_llm:
            logger.info("  All drug names resolved from EDAM cache — skipping LLM call")
            return

        prompt = (
            f"Given this clinical trial description:\n\n{trial_text[:2000]}\n\n"
            f"For each of the following intervention names, provide the generic "
            f"drug name and any common synonyms (abbreviations, brand names, "
            f"chemical names, or alternative names). If the name is already the "
            f"generic name, still list any known synonyms.\n\n"
            f"Interventions: {', '.join(names_needing_llm)}\n\n"
            f"Format your response as one line per intervention:\n"
            f"[original name] -> generic: [generic name]; synonyms: [syn1, syn2, ...]\n"
            f"If you cannot determine the generic name, write: [original name] -> generic: unknown; synonyms: none"
        )

        model = getattr(config.orchestrator, "annotation_model", "qwen3:14b")
        response = await ollama_client.generate(
            model=model,
            prompt=prompt,
            temperature=0.05,
        )
        response_text = response.get("response", "")

        if not response_text:
            return

        # Parse the response and add resolved names to each intervention
        import re
        for interv in interventions:
            name = interv.get("name", "")
            if not name or name in cached_resolutions:
                continue  # already resolved from cache

            resolved = []
            # Find the line matching this intervention (case-insensitive)
            pattern = re.escape(name) + r"\s*->\s*generic:\s*(.+?);\s*synonyms:\s*(.+?)(?:\n|$)"
            match = re.search(pattern, response_text, re.IGNORECASE)
            if match:
                generic = match.group(1).strip()
                synonyms_str = match.group(2).strip()

                if generic.lower() not in ("unknown", "none", name.lower()):
                    resolved.append(generic)

                if synonyms_str.lower() not in ("none", "n/a", ""):
                    # Split on commas, clean up
                    for syn in synonyms_str.split(","):
                        syn = syn.strip().strip(".")
                        if syn and syn.lower() not in ("none", "n/a", name.lower()):
                            resolved.append(syn)

            # Deduplicate while preserving order
            seen = {name.lower()}
            unique_resolved = []
            for r in resolved:
                if r.lower() not in seen:
                    seen.add(r.lower())
                    unique_resolved.append(r)

            interv["resolved"] = unique_resolved

            # Store new resolutions in EDAM cache
            if _edam and unique_resolved:
                context = brief_summary[:200] if brief_summary else None
                for resolved_name in unique_resolved:
                    try:
                        _edam.store_drug_name(
                            original=name,
                            resolved=resolved_name,
                            context=context,
                            nct_id=nct_id,
                        )
                    except Exception:
                        pass  # EDAM storage failures are non-fatal

    async def _run_annotation(
        self,
        nct_id: str,
        research_data: list[ResearchResult],
        config,
        job: AnnotationJob,
    ) -> list[FieldAnnotation]:
        """Run annotation agents, with retry logic for insufficient evidence.

        Peptide runs first so its result can be passed to Classification.
        """
        annotations = []
        agent_config = config.annotation_agents
        thresholds = config.evidence_thresholds
        # Metadata dict that accumulates results for dependent agents
        shared_metadata: dict = {}

        # Extract intervention names from clinical_protocol research data
        # so annotation agents (especially sequence) can look up raw_data keys.
        for res in research_data:
            if res.agent_name == "clinical_protocol" and not res.error and res.raw_data:
                proto_section = res.raw_data.get(
                    "protocol_section",
                    res.raw_data.get("protocolSection", {}),
                )
                arms_mod = proto_section.get("armsInterventionsModule", {})
                intervention_names = [
                    interv.get("name", "")
                    for interv in arms_mod.get("interventions", [])
                    if interv.get("name")
                ]
                if intervention_names:
                    # v18: Enrich intervention names with resolved drug names from EDAM.
                    # This lets the sequence agent search databases with generic names
                    # (e.g., "nesiritide") in addition to brand names.
                    try:
                        from app.services.memory.memory_store import memory_store as _edam
                        enriched: list = []
                        for iname in intervention_names:
                            resolved = _edam.get_resolved_names(iname)
                            # Also try with prefix stripped
                            stripped = iname
                            if ": " in iname:
                                _prefix, _, stripped = iname.partition(": ")
                            if not resolved and stripped != iname:
                                resolved = _edam.get_resolved_names(stripped)
                            if resolved:
                                enriched.append({"name": iname, "resolved": resolved})
                            else:
                                enriched.append(iname)
                        shared_metadata["interventions"] = enriched
                    except Exception:
                        shared_metadata["interventions"] = intervention_names
                break

        async def annotate_field(field_name: str, metadata: Optional[dict] = None) -> FieldAnnotation:
            agent_cls = ANNOTATION_AGENTS.get(field_name)
            if not agent_cls:
                return FieldAnnotation(
                    field_name=field_name,
                    value="Unknown",
                    reasoning=f"No agent registered for {field_name}",
                )

            agent = agent_cls()

            # Get primary research for this field
            field_def = agent_config.get(field_name)
            primary_agent = field_def.primary_research if field_def else None
            secondary_agent = field_def.secondary_research if field_def else None

            # Filter research: start with primary, add secondary on retry
            primary_research = [
                r for r in research_data
                if r.agent_name == primary_agent and not r.error
            ]
            # Always include all research on first pass for better results
            all_research = [r for r in research_data if not r.error]

            # First attempt with all available research
            result = await agent.annotate(nct_id, all_research, metadata=metadata)

            # Check evidence threshold (skip for deterministic results that
            # bypass LLM entirely — they have no evidence array by design)
            threshold = getattr(thresholds, field_name, None)
            if threshold and not result.skip_verification:
                unique_sources = set(c.source_name for c in result.evidence)
                quality_avg = (
                    sum(c.quality_score for c in result.evidence) / max(len(result.evidence), 1)
                )

                if len(unique_sources) < threshold.min_sources or quality_avg < threshold.min_quality:
                    # Threshold not met — this will be flagged for manual review
                    # in Phase 3 verification. For now, mark low confidence.
                    result.confidence = min(result.confidence, 0.3)
                    result.reasoning = (
                        f"[Below threshold: {len(unique_sources)} sources "
                        f"(need {threshold.min_sources}), "
                        f"quality {quality_avg:.2f} (need {threshold.min_quality})] "
                        + result.reasoning
                    )

            return result

        import time as _field_time

        # --- Step 1: Run peptide FIRST (classification depends on it) ---
        job.progress.current_field = "peptide"
        job.progress.current_agent = "peptide_annotator"
        _field_start = _field_time.monotonic()
        # v42.6.2 Eff #2: deterministic peptide pre-gate. Inspect research
        # results for structural signals — if clinical_protocol says
        # intervention is a Drug/Device/Biological with no peptide match in
        # UniProt, DRAMP, APD, DBAASP, or _KNOWN_SEQUENCES, we can declare
        # peptide=False without calling the LLM + 3 verifiers (~2 min).
        pregate_result = None
        if getattr(config.orchestrator, "deterministic_peptide_pregate", False):
            pregate_result = self._deterministic_peptide_pregate(
                research_results=research_data, shared_metadata=shared_metadata,
            )
        if pregate_result is not None:
            peptide_ann = FieldAnnotation(
                field_name="peptide",
                value=pregate_result["value"],
                confidence=pregate_result["confidence"],
                reasoning=pregate_result["reasoning"],
                model_name="deterministic-pregate",
                skip_verification=True,
            )
        else:
            try:
                peptide_ann = await annotate_field("peptide")
            except Exception as e:
                peptide_ann = FieldAnnotation(
                    field_name="peptide",
                    value="Unknown",
                    reasoning=f"Agent error: {e}",
                )
        annotations.append(peptide_ann)
        job.progress.field_timings["peptide"] = round(_field_time.monotonic() - _field_start, 1)
        job.progress.current_model = getattr(peptide_ann, "model_name", None)
        shared_metadata["peptide_result"] = peptide_ann.value

        # v28: Pre-cascade known-sequence check.
        # If peptide=False but the intervention matches a _KNOWN_SEQUENCES entry
        # with 2-100 AA, override to True (same logic as consistency Rule 3,
        # but BEFORE the cascade wipes sequence to N/A).
        # v29: Uses resolve_known_sequence() with alias support + checks
        # EDAM-resolved names from enriched intervention dicts.
        if peptide_ann.value == "False":
            from agents.annotation.sequence import resolve_known_sequence
            intervention_names = shared_metadata.get("interventions", [])
            for name in intervention_names:
                names_to_check = []
                if isinstance(name, dict):
                    names_to_check.append(name["name"].lower().strip())
                    for resolved in name.get("resolved", []):
                        names_to_check.append(resolved.lower().strip())
                else:
                    names_to_check.append(str(name).lower().strip())

                for name_lower in names_to_check:
                    match = resolve_known_sequence(name_lower)
                    if match:
                        drug, seq = match
                        if 2 <= len(seq) <= 100:
                            peptide_ann.value = "True"
                            peptide_ann.reasoning = (
                                f"[Pre-cascade override: '{drug}' has known "
                                f"{len(seq)}aa sequence → peptide=True] "
                                + peptide_ann.reasoning
                            )
                            shared_metadata["peptide_result"] = "True"
                            logger.info(
                                f"  pre-cascade: '{name_lower}'→'{drug}' "
                                f"({len(seq)}aa) forces peptide=True for {nct_id}"
                            )
                            break
                if peptide_ann.value == "True":
                    break

        # v15: If peptide=False, this trial is not a peptide therapeutic — N/A all other fields
        # v18: ALL peptide=False results cascade to N/A (deterministic gate removed).
        if peptide_ann.value == "False":
            for field_name in ANNOTATION_AGENTS:
                if field_name == "peptide":
                    continue
                annotations.append(FieldAnnotation(
                    field_name=field_name,
                    value="N/A",
                    confidence=1.0,
                    reasoning="[Peptide=False: non-peptide trial, all fields N/A]",
                    model_name="cascade",
                    skip_verification=True,
                ))
            # v42 Phase 6 (cosmetic): apply prefer_atomic swaps to cascaded
            # annotations so the field-name schema is uniform across the job
            # (peptide=True normal-flow NCTs apply the swap in step 2/3). All
            # values are N/A here so it's analysis-equivalent — this is for
            # consistent JSON shape across the 94-NCT set.
            if getattr(config.orchestrator, "prefer_atomic_classification", False):
                self._prefer_atomic_swap(annotations, "classification")
            if getattr(config.orchestrator, "prefer_atomic_failure_reason", False):
                self._prefer_atomic_swap(annotations, "reason_for_failure")
            logger.info(f"  peptide=False for {nct_id}, N/A-ing all other fields")
            return annotations

        # --- Step 2: Run classification, delivery_mode, outcome, sequence (NOT failure_reason yet) ---
        # failure_reason depends on outcome, so we run it after outcome completes.
        # sequence is deterministic (no LLM) and has no dependencies.
        # reason_for_failure_atomic is run with the legacy failure_reason in step 3
        # because it also depends on the outcome_atomic result.
        step2_fields = [
            f for f in ANNOTATION_AGENTS
            if f not in ("peptide", "reason_for_failure", "reason_for_failure_atomic")
        ]

        # v42 Phase 4: skip the atomic shadow-mode agent unless explicitly
        # enabled. The agent is registered globally so tests/scripts can invoke
        # it directly, but a default annotation run must not burn LLM cycles
        # on the shadow pipeline.
        if not getattr(config.orchestrator, "outcome_atomic_shadow", False):
            step2_fields = [f for f in step2_fields if f != "outcome_atomic"]
        # v42 B2: classification_atomic shadow. Default OFF.
        if not getattr(config.orchestrator, "classification_atomic_shadow", False):
            step2_fields = [f for f in step2_fields if f != "classification_atomic"]
        # v42.6.1 Eff #1: skip the LEGACY classification LLM when atomic is
        # authoritative AND skip_legacy_when_atomic is set. Saves a two-pass
        # LLM + 3 verifier calls on every peptide=True trial. The atomic
        # sibling remains and the swap helper renames its field_name to
        # "classification" so downstream sees no change.
        if (getattr(config.orchestrator, "prefer_atomic_classification", False)
                and getattr(config.orchestrator, "skip_legacy_when_atomic", False)):
            step2_fields = [f for f in step2_fields if f != "classification"]

        job.progress.current_field = ", ".join(step2_fields)
        job.progress.current_agent = "annotation (parallel)" if config.orchestrator.parallel_annotation else "annotation"
        _step2_start = _field_time.monotonic()
        if config.orchestrator.parallel_annotation:
            tasks = []
            for field in step2_fields:
                tasks.append(annotate_field(field, metadata=shared_metadata))
            results = list(await asyncio.gather(*tasks, return_exceptions=True))
            for i, ann in enumerate(results):
                if isinstance(ann, Exception):
                    field = step2_fields[i]
                    results[i] = FieldAnnotation(
                        field_name=field,
                        value="Unknown",
                        reasoning=f"Agent error: {ann}",
                    )
            annotations.extend(results)
        else:
            for field in step2_fields:
                job.progress.current_field = field
                job.progress.current_agent = f"{field}_annotator"
                _sf = _field_time.monotonic()
                try:
                    ann = await annotate_field(field, metadata=shared_metadata)
                    annotations.append(ann)
                except Exception as e:
                    annotations.append(FieldAnnotation(
                        field_name=field,
                        value="Unknown",
                        reasoning=f"Agent error: {e}",
                    ))
                job.progress.field_timings[field] = round(_field_time.monotonic() - _sf, 1)
        # Record step 2 timing for parallel fields
        if config.orchestrator.parallel_annotation:
            step2_elapsed = round(_field_time.monotonic() - _step2_start, 1)
            for field in step2_fields:
                job.progress.field_timings[field] = step2_elapsed
            for ann in annotations:
                if ann.field_name in step2_fields and hasattr(ann, "model_name"):
                    job.progress.current_model = ann.model_name
                    break

        # v42 Phase 6 cut-over: if prefer_atomic_classification is on, swap the
        # authoritative field names so downstream (CSV export, UI, concordance)
        # sees the atomic value under `classification` and the legacy value
        # under `classification_legacy`. No-op if either agent didn't run.
        if getattr(config.orchestrator, "prefer_atomic_classification", False):
            self._prefer_atomic_swap(
                annotations, "classification",
                skip_verification_on_legacy=getattr(
                    config.orchestrator, "skip_verification_on_legacy", True,
                ),
            )

        # --- Step 3: Run failure_reason AFTER outcome (it needs the outcome result) ---
        job.progress.current_field = "reason_for_failure"
        job.progress.current_agent = "failure_reason_annotator"
        _rf_start = _field_time.monotonic()
        outcome_ann = next((a for a in annotations if a.field_name == "outcome"), None)
        if outcome_ann:
            shared_metadata["outcome_result"] = outcome_ann.value
        # v42 B3: pass atomic outcome through for reason_for_failure_atomic gating.
        outcome_atomic_ann = next(
            (a for a in annotations if a.field_name == "outcome_atomic"), None
        )
        if outcome_atomic_ann:
            shared_metadata["outcome_atomic_result"] = outcome_atomic_ann.value
        # v42.6.1 Eff #1: skip legacy failure_reason LLM when atomic is
        # authoritative AND efficiency flag set.
        skip_legacy_fr = (
            getattr(config.orchestrator, "prefer_atomic_failure_reason", False)
            and getattr(config.orchestrator, "skip_legacy_when_atomic", False)
        )
        if skip_legacy_fr:
            job.progress.field_timings["reason_for_failure"] = 0.0
        else:
            try:
                failure_ann = await annotate_field("reason_for_failure", metadata=shared_metadata)
            except Exception as e:
                failure_ann = FieldAnnotation(
                    field_name="reason_for_failure",
                    value="",
                    reasoning=f"Agent error: {e}",
                )
            annotations.append(failure_ann)
            job.progress.field_timings["reason_for_failure"] = round(_field_time.monotonic() - _rf_start, 1)

        # v42 B3: shadow-mode reason_for_failure_atomic. Gated on its own shadow
        # flag AND on outcome_atomic having produced a failed label — the agent
        # itself short-circuits on non-failure outcomes, but skipping the
        # dispatch avoids the overhead entirely.
        if getattr(config.orchestrator, "failure_reason_atomic_shadow", False):
            _fra_start = _field_time.monotonic()
            try:
                fra_ann = await annotate_field(
                    "reason_for_failure_atomic", metadata=shared_metadata
                )
            except Exception as e:
                fra_ann = FieldAnnotation(
                    field_name="reason_for_failure_atomic",
                    value="",
                    reasoning=f"Agent error: {e}",
                )
            annotations.append(fra_ann)
            job.progress.field_timings["reason_for_failure_atomic"] = round(
                _field_time.monotonic() - _fra_start, 1
            )

        # v42 Phase 6 cut-over: failure_reason prefer-atomic swap. Must run
        # after step 3 so both legacy and atomic annotations are present.
        if getattr(config.orchestrator, "prefer_atomic_failure_reason", False):
            self._prefer_atomic_swap(
                annotations, "reason_for_failure",
                skip_verification_on_legacy=getattr(
                    config.orchestrator, "skip_verification_on_legacy", True,
                ),
            )

        # v17: Post-annotation quality check — detect timeout artifacts,
        # empty/garbage responses, and error messages leaked into values
        quality_issues = self._check_annotation_quality(nct_id, annotations)
        if quality_issues:
            for issue in quality_issues:
                logger.warning(f"  QUALITY CHECK [{nct_id}]: {issue}")
                job.progress.warnings.append(f"QUALITY [{nct_id}]: {issue}")

            # v17: Retry fields with actual corruption (error text in value
            # or zero confidence with a value). One retry per field.
            retried_fields: set[str] = set()
            for issue in quality_issues:
                # Only retry corruption, not cosmetic issues
                if "error text" not in issue and "zero confidence with value" not in issue:
                    continue
                # Extract field name from issue string (format: "field_name: ...")
                field_name = issue.split(":")[0].strip()
                if field_name in retried_fields:
                    continue
                retried_fields.add(field_name)

                logger.info(f"  RETRY [{nct_id}]: re-running {field_name} annotation")
                try:
                    # Remove the bad annotation
                    annotations[:] = [a for a in annotations if a.field_name != field_name]
                    retry_ann = await annotate_field(field_name, metadata=shared_metadata)
                    annotations.append(retry_ann)
                    job.progress.retries["annotation"] = (
                        job.progress.retries.get("annotation", 0) + 1
                    )
                    # Check retry result quality
                    retry_issues = self._check_annotation_quality(nct_id, [retry_ann])
                    if retry_issues:
                        logger.warning(
                            f"  RETRY [{nct_id}]: {field_name} still has issues "
                            f"after retry: {retry_issues[0]}"
                        )
                    else:
                        logger.info(
                            f"  RETRY [{nct_id}]: {field_name} retry succeeded "
                            f"(value={retry_ann.value})"
                        )
                except Exception as e:
                    logger.error(f"  RETRY [{nct_id}]: {field_name} retry failed: {e}")

        # v31: Set evidence_grade for annotations backed by database citations.
        # DB-confirmed annotations get stronger protection against verifier override.
        _DB_KEYWORDS = ("uniprot", "dramp", "dbaasp", "chembl", "apd", "rcsb")
        for ann in annotations:
            if ann.skip_verification:
                ann.evidence_grade = "deterministic"
            elif ann.value and ann.reasoning:
                reasoning_lower = ann.reasoning.lower()
                if any(kw in reasoning_lower for kw in _DB_KEYWORDS):
                    ann.evidence_grade = "db_confirmed"

        return annotations

    async def _peptide_cascade_check(
        self,
        nct_id: str,
        annotations: list[FieldAnnotation],
        verified: VerifiedAnnotation,
        research_data: list[ResearchResult],
        config,
    ) -> tuple[list[FieldAnnotation], VerifiedAnnotation]:
        """If verification changed the peptide value, re-run classification.

        The peptide→classification dependency means a flipped peptide value
        can invalidate the classification. This re-runs classification with
        the corrected peptide value and re-verifies only that field.
        """
        ann_by_field = {a.field_name: a for a in annotations}
        peptide_ann = ann_by_field.get("peptide")
        classification_ann = ann_by_field.get("classification")

        if not peptide_ann or not classification_ann:
            return annotations, verified

        # v9.1: If classification was deterministic, the cascade doesn't apply.
        # Deterministic classification is based on drug name lookup, not peptide value,
        # so a flipped peptide won't change the result.
        if classification_ann.skip_verification:
            logger.info(
                f"  Peptide cascade: skipping — classification was deterministic "
                f"('{classification_ann.value}')"
            )
            return annotations, verified

        # Find the peptide verification result
        peptide_verified_value = None
        for field_result in verified.fields:
            if field_result.field_name == "peptide" and field_result.final_value:
                peptide_verified_value = field_result.final_value
                break

        if not peptide_verified_value:
            return annotations, verified

        # Check if peptide was flipped by verification
        original_peptide = peptide_ann.value
        if peptide_verified_value == original_peptide:
            return annotations, verified

        logger.info(
            f"  Peptide cascade: verification flipped peptide "
            f"from '{original_peptide}' to '{peptide_verified_value}' — "
            f"re-running classification for {nct_id}"
        )

        # Re-run classification with corrected peptide value
        from agents.annotation import ANNOTATION_AGENTS
        cls_agent_cls = ANNOTATION_AGENTS.get("classification")
        if not cls_agent_cls:
            return annotations, verified

        cls_agent = cls_agent_cls()
        new_metadata = {"peptide_result": peptide_verified_value}
        all_research = [r for r in research_data if not r.error]

        try:
            new_classification = await cls_agent.annotate(
                nct_id, all_research, metadata=new_metadata
            )
            # Replace classification in annotations list
            for i, ann in enumerate(annotations):
                if ann.field_name == "classification":
                    new_classification.reasoning = (
                        f"[Peptide cascade: re-classified after peptide "
                        f"flipped {original_peptide}→{peptide_verified_value}] "
                        + new_classification.reasoning
                    )
                    annotations[i] = new_classification
                    break

            # Re-enforce consistency with new classification
            self._enforce_consistency(annotations, research_data=research_data)

            # Re-verify classification only
            verifier = BlindVerifier()
            checker = ConsensusChecker()

            verifier_models = [
                (key, m) for key, m in config.verification.models.items()
                if m.role == "verifier"
            ]
            # v42.6.7 Eff #7: fast-model override (also applied in the
            # classification re-verify path).
            verifier_fast_models = getattr(config.orchestrator, "verifier_fast_models", [])
            if verifier_fast_models:
                from app.models.config_models import ModelConfig
                downsized = []
                for vi, (key, m) in enumerate(verifier_models):
                    if vi < len(verifier_fast_models):
                        downsized.append((key, ModelConfig(name=verifier_fast_models[vi], role="verifier")))
                    else:
                        downsized.append((key, m))
                verifier_models = downsized
            threshold = config.verification.consensus_threshold

            verifier_opinions = []
            for model_key, model_cfg in verifier_models:
                opinion = await verifier.verify(
                    nct_id=nct_id,
                    field_name="classification",
                    research_results=research_data,
                    model_name=model_key,
                    ollama_model=model_cfg.name,
                )
                verifier_opinions.append(opinion)

            new_consensus = checker.check(
                field_name="classification",
                primary_value=new_classification.value,
                primary_model="primary",
                verifier_opinions=verifier_opinions,
                threshold=threshold,
            )

            # Replace classification in verified results
            new_fields = []
            for f in verified.fields:
                if f.field_name == "classification":
                    new_fields.append(new_consensus)
                else:
                    new_fields.append(f)

            any_flagged = any(not f.consensus_reached for f in new_fields)
            flag_reasons = [
                f"{f.field_name}: {f.flag_reason or 'model disagreement'}"
                for f in new_fields if not f.consensus_reached
            ]

            verified = VerifiedAnnotation(
                nct_id=nct_id,
                fields=new_fields,
                overall_consensus=not any_flagged,
                flagged_for_review=any_flagged,
                flag_reason="; ".join(flag_reasons) if flag_reasons else None,
            )

            logger.info(
                f"  Peptide cascade: re-classified as "
                f"'{new_classification.value}' (was '{classification_ann.value}')"
            )

        except Exception as e:
            logger.warning(f"  Peptide cascade re-classification failed: {e}")

        return annotations, verified

    @staticmethod
    def _store_consistency_overrides(
        nct_id: str,
        job_id: str,
        annotations: list[FieldAnnotation],
        pre_consistency: dict[str, str],
        config_snapshot: dict,
    ) -> None:
        """Store EDAM corrections for any values changed by _enforce_consistency.

        Non-fatal: all errors are logged but never raised.
        """
        try:
            from app.services.memory.edam_config import TRAINING_NCTS
            if TRAINING_NCTS and nct_id.upper() not in TRAINING_NCTS:
                return
            from app.services.memory.memory_store import memory_store as _edam
            from app.services.version_service import get_git_commit_short
            import hashlib

            config_str = str(sorted(str(config_snapshot)))
            config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:12]
            git_commit = get_git_commit_short()

            for ann in annotations:
                original = pre_consistency.get(ann.field_name)
                if original is not None and ann.value != original:
                    # Extract the override reason from the reasoning prefix
                    reasoning = ann.reasoning or ""
                    # The override reason is in brackets at the start
                    reflection = reasoning
                    if reasoning.startswith("[Consistency override"):
                        bracket_end = reasoning.find("]")
                        if bracket_end > 0:
                            reflection = reasoning[1:bracket_end]

                    try:
                        _edam.store_correction(
                            nct_id=nct_id,
                            field_name=ann.field_name,
                            job_id=job_id,
                            original_value=original,
                            corrected_value=ann.value,
                            source="consistency_override",
                            reflection=reflection,
                            evidence_citations=[{
                                "source": "consistency_engine",
                                "text": reflection[:200],
                            }],
                            config_hash=config_hash,
                            git_commit=git_commit,
                        )
                        logger.info(
                            "EDAM: stored consistency override %s/%s: '%s' -> '%s'",
                            nct_id, ann.field_name, original, ann.value,
                        )
                    except Exception as e:
                        logger.warning(
                            "EDAM: failed to store consistency override for %s/%s: %s",
                            nct_id, ann.field_name, e,
                        )
        except Exception as e:
            logger.warning("EDAM: consistency override storage failed (non-fatal): %s", e)

    @staticmethod
    def _store_reconciliation_corrections(
        nct_id: str,
        job_id: str,
        verified: 'VerifiedAnnotation',
        ann_by_field: dict[str, FieldAnnotation],
        config_snapshot: dict,
    ) -> None:
        """Store EDAM corrections for fields changed by verification/reconciliation.

        Compares each verified field's final_value against the original annotation
        value. Where they differ (and final_value is not empty), stores a
        correction with source='reconciliation'.

        Non-fatal: all errors are logged but never raised.
        """
        try:
            from app.services.memory.edam_config import TRAINING_NCTS
            if TRAINING_NCTS and nct_id.upper() not in TRAINING_NCTS:
                return
            from app.services.memory.memory_store import memory_store as _edam
            from app.services.version_service import get_git_commit_short
            import hashlib

            config_str = str(sorted(str(config_snapshot)))
            config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:12]
            git_commit = get_git_commit_short()

            for field in verified.fields:
                original_ann = ann_by_field.get(field.field_name)
                if not original_ann:
                    continue

                original_value = original_ann.value
                final_value = field.final_value

                # Skip if no change or final_value is empty
                if not final_value or final_value == original_value:
                    continue

                # Use reconciler reasoning if available, otherwise generic
                reflection = (
                    field.reconciler_reasoning
                    if field.reconciler_used and field.reconciler_reasoning
                    else f"Verification changed {field.field_name} from "
                         f"'{original_value}' to '{final_value}' "
                         f"(agreement_ratio={field.agreement_ratio:.2f})"
                )

                try:
                    _edam.store_correction(
                        nct_id=nct_id,
                        field_name=field.field_name,
                        job_id=job_id,
                        original_value=original_value,
                        corrected_value=final_value,
                        source="reconciliation",
                        reflection=reflection[:500],
                        evidence_citations=[{
                            "source": "verification_consensus",
                            "text": reflection[:200],
                        }],
                        config_hash=config_hash,
                        git_commit=git_commit,
                    )
                    logger.info(
                        "EDAM: stored reconciliation correction %s/%s: '%s' -> '%s'",
                        nct_id, field.field_name, original_value, final_value,
                    )
                except Exception as e:
                    logger.warning(
                        "EDAM: failed to store reconciliation correction for %s/%s: %s",
                        nct_id, field.field_name, e,
                    )
        except Exception as e:
            logger.warning("EDAM: reconciliation correction storage failed (non-fatal): %s", e)

    @staticmethod
    def _enforce_consistency(
        annotations: list[FieldAnnotation],
        research_data: list[ResearchResult] | None = None,
    ) -> None:
        """Enforce cross-field consistency rules after annotation, before verification.

        Fixes contradictions that arise from fields being annotated independently:
        - AMP classification -> peptide must be True
        - peptide=False -> classification must be "Other"
        - outcome is non-failure -> reason_for_failure must be ""

        Note: sequence→peptide cross-validation and UniProt AA length checks
        were removed in v13 because the sequence agent was returning precursor
        protein lengths (500-5000+ AA) instead of mature peptide fragments,
        causing false peptide=False overrides.
        """
        ann_by_field = {a.field_name: a for a in annotations}
        peptide = ann_by_field.get("peptide")
        classification = ann_by_field.get("classification")
        outcome = ann_by_field.get("outcome")
        failure = ann_by_field.get("reason_for_failure")

        # Rule 0b: AMP classification → peptide must be True
        # All AMPs are peptides (not all peptides are AMPs)
        if classification and peptide and classification.value.startswith("AMP") and peptide.value == "False":
            logger.info(
                f"  consistency: classification='{classification.value}' (AMP), "
                f"forcing peptide from 'False' to 'True'"
            )
            peptide.value = "True"
            peptide.reasoning = (
                f"[Consistency override: AMP classification -> peptide=True] "
                + peptide.reasoning
            )

        # Rule 1: peptide=False -> classification must be "Other"
        # v15: Skip if fields are already N/A (peptide=False early exit)
        if peptide and classification and peptide.value == "False":
            if classification.value == "N/A":
                return  # All fields already N/A from peptide=False early exit
            if classification.value != "Other":
                logger.info(
                    f"  consistency: peptide=False, forcing classification "
                    f"from '{classification.value}' to 'Other'"
                )
                classification.value = "Other"
                classification.reasoning = (
                    f"[Consistency override: peptide=False -> Other] "
                    + classification.reasoning
                )

        # Rule 2: non-failure outcome -> clear reason_for_failure
        # Note: Withdrawn excluded — withdrawn trials can have known reasons
        non_failure_outcomes = {
            "Positive", "Recruiting", "Active, not recruiting", "Unknown"
        }
        if outcome and failure and outcome.value in non_failure_outcomes:
            if failure.value:
                logger.info(
                    f"  consistency: outcome='{outcome.value}', "
                    f"clearing reason_for_failure from '{failure.value}'"
                )
                failure.value = ""
                failure.reasoning = (
                    f"[Consistency override: outcome='{outcome.value}' -> "
                    f"no failure reason] " + failure.reasoning
                )

        # Rule 3 (v14, v27: raised to 100 AA): valid sequence (2-100 AA) → peptide must be True
        # A drug with a known peptide sequence is by definition a peptide.
        # Does NOT apply to >100 AA (large proteins like interferons, EPO).
        # Does NOT enforce the reverse (peptide=True without sequence is fine —
        # many peptides are synthetic/modified with no database entry).
        sequence = ann_by_field.get("sequence")
        if sequence and peptide and sequence.value:
            # Use length of first sequence if pipe-separated
            first_seq = sequence.value.split(" | ")[0].strip()
            seq_len = len(first_seq)
            if 2 <= seq_len <= 100 and peptide.value == "False":
                logger.info(
                    f"  consistency: sequence={seq_len} aa, "
                    f"forcing peptide from 'False' to 'True'"
                )
                peptide.value = "True"
                peptide.reasoning = (
                    f"[Consistency override: {seq_len} AA sequence -> peptide=True] "
                    + peptide.reasoning
                )

    @staticmethod
    def _enforce_post_verification_consistency(verified: VerifiedAnnotation) -> None:
        """Enforce cross-field consistency on FINAL verified values.

        Runs AFTER verification to resolve review items that are
        artifacts of cross-field coupling rather than genuine disagreements.

        v7: Resolves ~25 of 32 review items automatically by enforcing:
        - outcome ∈ {Positive, Recruiting, Active, Unknown} → failure_reason = ""
        - peptide = False → classification = "Other"
        """
        field_map = {f.field_name: f for f in verified.fields}
        outcome_f = field_map.get("outcome")
        failure_f = field_map.get("reason_for_failure")
        peptide_f = field_map.get("peptide")
        classification_f = field_map.get("classification")

        # Get effective values (final_value if set, else original_value)
        def effective(f):
            if f is None:
                return None
            return f.final_value if f.final_value else f.original_value

        outcome_val = effective(outcome_f)
        peptide_val = effective(peptide_f)

        # Rule 1: non-failure outcome → force failure_reason empty
        # Note: Withdrawn excluded — withdrawn trials can have known reasons
        non_failure = {"Positive", "Recruiting", "Active, not recruiting", "Unknown"}
        if outcome_val in non_failure and failure_f:
            eff_failure = effective(failure_f)
            if eff_failure and eff_failure.lower() not in ("", "empty"):
                logger.info(
                    f"  post-verification consistency: outcome='{outcome_val}', "
                    f"forcing failure_reason from '{eff_failure}' to ''"
                )
                failure_f.final_value = ""
                failure_f.consensus_reached = True
                # Don't flag for review — the cross-field rule resolves it

        # Rule 2: peptide=False → classification must be Other
        if peptide_val == "False" and classification_f:
            eff_class = effective(classification_f)
            if eff_class and eff_class != "Other":
                logger.info(
                    f"  post-verification consistency: peptide=False, "
                    f"forcing classification from '{eff_class}' to 'Other'"
                )
                classification_f.final_value = "Other"
                classification_f.consensus_reached = True

        # Rule 3 (v30): valid sequence (2-100 AA) → peptide must be True
        # Mirror of pre-verification Rule 3. Catches cases where verifiers
        # incorrectly flip peptide to False despite a validated short sequence
        # (e.g., vosoritide 39 AA classified as "Protein" by ChEMBL).
        sequence_f = field_map.get("sequence")
        if sequence_f and peptide_f:
            seq_val = effective(sequence_f)
            if seq_val and seq_val not in ("N/A", ""):
                first_seq = seq_val.split(" | ")[0].strip()
                seq_len = len(first_seq)
                if 2 <= seq_len <= 100 and effective(peptide_f) == "False":
                    logger.info(
                        f"  post-verification consistency: sequence={seq_len} aa, "
                        f"forcing peptide from 'False' to 'True'"
                    )
                    peptide_f.final_value = "True"
                    peptide_f.consensus_reached = True

        # Update overall flags
        all_consensus = all(f.consensus_reached for f in verified.fields)
        if all_consensus:
            verified.flagged_for_review = False
            verified.flag_reason = ""
        else:
            # Recompute: only flag if there are still genuine disagreements
            remaining = [
                f.field_name for f in verified.fields if not f.consensus_reached
            ]
            if remaining:
                verified.flagged_for_review = True
                verified.flag_reason = f"Unresolved disagreements: {', '.join(remaining)}"
            else:
                verified.flagged_for_review = False
                verified.flag_reason = ""

    @staticmethod
    def _normalize_final_values(verified: VerifiedAnnotation) -> None:
        """Normalize all final_values to canonical forms after verification.

        Catches raw-text outputs from the reconciler that bypass the annotation
        agent's normalization. Applied as the LAST step before persistence.
        """
        for f in verified.fields:
            val = f.final_value if f.final_value else f.original_value
            if not val:
                continue

            field_name = f.field_name
            lower = val.strip().lower()

            if field_name == "reason_for_failure" and len(val) > 30:
                # Long text — reconciler output raw sentence. Apply fuzzy matching.
                if "business" in lower or "funding" in lower or "sponsor" in lower or "administrative" in lower:
                    f.final_value = "Business Reason"
                elif "ineffect" in lower or "efficacy" in lower or "futility" in lower or "endpoint" in lower:
                    f.final_value = "Ineffective for purpose"
                elif "toxic" in lower or "safety" in lower or "unsafe" in lower or "adverse" in lower:
                    f.final_value = "Toxic/Unsafe"
                elif "covid" in lower or "pandemic" in lower or "coronavirus" in lower:
                    f.final_value = "Due to covid"
                elif "recruit" in lower or "enrollment" in lower or "accrual" in lower:
                    f.final_value = "Recruitment issues"
                else:
                    f.final_value = ""  # unrecognizable → empty
                if f.final_value != val:
                    logger.info(
                        f"  normalize: {field_name} '{val[:50]}...' → '{f.final_value}'"
                    )

            elif field_name == "delivery_mode" and len(val) > 50 and "," not in val:
                # Reconciler sometimes outputs verbose descriptions.
                # v17: Skip normalization for comma-separated multi-route values
                # (they are already in canonical form from the deterministic path).
                # v33: Updated to v24 canonical values (was outputting dead v23 categories)
                v_lower = val.lower()
                if "intravenous" in v_lower or "iv " in v_lower or "subcutaneous" in v_lower or "intradermal" in v_lower or "intramuscular" in v_lower or "inject" in v_lower or "infus" in v_lower:
                    f.final_value = "Injection/Infusion"
                elif "oral" in v_lower:
                    f.final_value = "Oral"
                elif "topical" in v_lower:
                    f.final_value = "Topical"
                elif "inhalation" in v_lower or "inhaled" in v_lower or "intranasal" in v_lower:
                    f.final_value = "Other"

            elif field_name == "peptide":
                # Ensure canonical True/False
                if lower in ("true", "[true]", "yes", "1"):
                    f.final_value = "True"
                elif lower in ("false", "[false]", "no", "0"):
                    f.final_value = "False"

    # ------------------------------------------------------------------ #
    #  v17: Annotation quality checks
    # ------------------------------------------------------------------ #

    # Patterns that indicate the LLM response contains an error/timeout
    # message instead of actual annotation content.
    _GARBAGE_PATTERNS = [
        "timed out", "timeout", "ollama", "connection refused",
        "model may be too large", "hung or under memory pressure",
        "failed to generate", "internal server error", "502 bad gateway",
        "connection reset", "broken pipe", "eof", "empty response",
    ]

    @staticmethod
    def _intervention_is_clearly_non_peptide(results: list) -> bool:
        """v42.6.3 helper. Inspect a partial research_results list (usually
        just clinical_protocol at time of call) and return True iff every
        intervention type is one that cannot be a peptide drug. Conservative:
        returns False on any ambiguous type (``BIOLOGICAL``, ``DRUG``) or
        missing data. Used to decide whether to skip AMP-specific research.

        v42.6.4 bugfix: CT.gov returns intervention types UPPERCASE
        ("BIOLOGICAL", "DEVICE", "OTHER"). Original check compared against
        Title Case and never matched, silently no-opping Eff #3 on every
        trial. Normalize to upper on both sides.
        """
        clearly_non_peptide_types_upper = {
            "DEVICE", "PROCEDURE", "BEHAVIORAL", "RADIATION",
            "DIETARY_SUPPLEMENT", "DIETARY SUPPLEMENT",
            "GENETIC", "OTHER",
        }
        found_types: list[str] = []
        for r in results or []:
            if getattr(r, "error", None):
                continue
            if getattr(r, "agent_name", "") != "clinical_protocol":
                continue
            raw = getattr(r, "raw_data", {}) or {}
            proto = raw.get("protocol_section") or raw.get("protocolSection") or {}
            arms = proto.get("armsInterventionsModule", {}) if isinstance(proto, dict) else {}
            for interv in (arms.get("interventions") or []):
                t = (interv.get("type") or "").strip() if isinstance(interv, dict) else ""
                if t:
                    found_types.append(t.upper())
        if not found_types:
            return False
        return all(t in clearly_non_peptide_types_upper for t in found_types)

    @staticmethod
    def _deterministic_peptide_pregate(
        research_results: list,
        shared_metadata: dict,
    ) -> Optional[dict]:
        """v42.6.2 Eff #2: deterministic peptide False pre-gate.

        Returns a dict with ``value``, ``confidence``, ``reasoning`` if we
        can safely declare peptide=False without calling the LLM. Returns
        None if we should run the LLM (default, safe).

        Rules — ALL must be true to declare False:
        - clinical_protocol intervention types are all one of: Drug,
          Device, Procedure, Behavioral, Radiation, Dietary Supplement,
          Genetic. (Excludes ``Biological`` which is frequently peptide.)
        - No UniProt hit in peptide_identity research (any citation whose
          source_name is uniprot with a non-empty snippet).
        - No DRAMP / APD / DBAASP hit in peptide_identity / apd / dbaasp.
        - No _KNOWN_SEQUENCES match (resolve_known_sequence) for any
          intervention name.

        No drug-name cheat sheets; decision is structural (intervention
        type + database hit presence + known-sequence match). Covers the
        "small-molecule Drug with no peptide databases hit" case which is
        the vast majority of non-peptide trials.
        """
        # Gather intervention types from clinical_protocol.
        int_types: list[str] = []
        has_uniprot_hit = False
        has_peptide_db_hit = False
        for r in research_results or []:
            if getattr(r, "error", None):
                continue
            agent = getattr(r, "agent_name", "")
            raw = getattr(r, "raw_data", {}) or {}
            cits = getattr(r, "citations", []) or []
            if agent == "clinical_protocol":
                proto = raw.get("protocol_section") or raw.get("protocolSection") or {}
                arms = proto.get("armsInterventionsModule", {}) if isinstance(proto, dict) else {}
                for interv in (arms.get("interventions") or []):
                    t = (interv.get("type") or "").strip() if isinstance(interv, dict) else ""
                    if t:
                        int_types.append(t)
            if agent in ("peptide_identity", "apd", "dbaasp"):
                for c in cits:
                    src = (getattr(c, "source_name", "") or "").lower()
                    snippet = (getattr(c, "snippet", "") or "").lower()
                    if src == "uniprot" and snippet:
                        has_uniprot_hit = True
                    if src in ("dramp", "apd", "dbaasp"):
                        has_peptide_db_hit = True

        if not int_types:
            return None  # No type data → can't be sure; let LLM decide.

        # v42.6.4 bugfix: CT.gov returns intervention types UPPERCASE.
        # Types known to NEVER be peptide drugs on their own.
        # "BIOLOGICAL" is intentionally absent (many peptide vaccines are
        # registered as Biological); "DRUG" alone is ambiguous but combined
        # with the no-database-hit checks below it's strong evidence.
        non_peptide_types_upper = {
            "DEVICE", "PROCEDURE", "BEHAVIORAL", "RADIATION",
            "DIETARY_SUPPLEMENT", "DIETARY SUPPLEMENT",
            "GENETIC", "OTHER",
        }
        int_types_upper = [t.upper() for t in int_types]
        drug_or_nonpep_only = all(
            t in non_peptide_types_upper or t == "DRUG" for t in int_types_upper
        )
        if not drug_or_nonpep_only:
            return None  # "BIOLOGICAL" or anything novel → defer to LLM.

        if has_uniprot_hit or has_peptide_db_hit:
            return None  # Database suggests a peptide; LLM should confirm.

        # Known-sequence match for any intervention name.
        try:
            from agents.annotation.sequence import resolve_known_sequence
        except Exception:
            return None
        for name in shared_metadata.get("interventions", []) or []:
            candidates = []
            if isinstance(name, dict):
                candidates.append((name.get("name") or "").lower().strip())
                candidates.extend(
                    (r or "").lower().strip() for r in (name.get("resolved") or [])
                )
            else:
                candidates.append(str(name).lower().strip())
            for c in candidates:
                if c and resolve_known_sequence(c):
                    return None  # Known peptide sequence match → let LLM/override handle.

        reason = (
            f"[Deterministic pre-gate] intervention types: "
            f"{sorted(set(int_types_upper))}; no UniProt/DRAMP/APD/DBAASP hit; "
            f"no known-sequence match → peptide=False"
        )
        return {"value": "False", "confidence": 0.85, "reasoning": reason}

    @staticmethod
    def _prefer_atomic_swap(
        annotations: list,
        legacy_field: str,
        skip_verification_on_legacy: bool = True,
    ) -> None:
        """v42 Phase 6 cut-over helper. When the user has flipped
        `prefer_atomic_<field>`, rewrite the field_names so the atomic
        verdict becomes authoritative:
          - atomic annotation's field_name ``<legacy>_atomic`` → ``<legacy>``
          - legacy annotation's field_name ``<legacy>`` → ``<legacy>_legacy``

        No-op if either side is missing (e.g. shadow flag was off). Keeps
        both values in the output for audit. Downstream consumers (CSV
        export, concordance, UI) see the atomic value under the primary
        field name with no code changes.

        v42.6.4 Eff #4: when ``skip_verification_on_legacy`` is True, the
        swapped-out legacy annotation gets ``skip_verification=True`` so it
        doesn't burn 3 verifier LLM calls per trial on an audit-only column.
        """
        atomic_field = f"{legacy_field}_atomic"
        atomic_ann = next(
            (a for a in annotations if a.field_name == atomic_field), None
        )
        if atomic_ann is None:
            return
        legacy_ann = next(
            (a for a in annotations if a.field_name == legacy_field), None
        )
        if legacy_ann is not None:
            legacy_ann.field_name = f"{legacy_field}_legacy"
            if skip_verification_on_legacy:
                legacy_ann.skip_verification = True
        atomic_ann.field_name = legacy_field

    @staticmethod
    def _check_annotation_quality(
        nct_id: str,
        annotations: list,
    ) -> list[str]:
        """v17: Post-annotation quality check.

        Detects:
        - Empty/missing values where one is expected
        - Timeout/error messages leaked into annotation values or reasoning
        - Suspiciously short reasoning (LLM may have been cut off)
        - Identical values across all fields (possible copy-paste from LLM)

        Returns a list of issue descriptions (empty = all clean).
        """
        issues: list[str] = []

        for ann in annotations:
            field = ann.field_name
            value = ann.value or ""
            reasoning = ann.reasoning or ""
            confidence = getattr(ann, "confidence", None)
            model = getattr(ann, "model_name", "")

            # Check 1: Error/timeout messages in the value itself
            value_lower = value.lower()
            for pattern in PipelineOrchestrator._GARBAGE_PATTERNS:
                if pattern in value_lower:
                    issues.append(
                        f"{field}: value contains error text '{pattern}' "
                        f"(value='{value[:80]}', model={model})"
                    )
                    break

            # Check 2: Error/timeout messages in reasoning
            reasoning_lower = reasoning.lower()
            for pattern in PipelineOrchestrator._GARBAGE_PATTERNS:
                if pattern in reasoning_lower and "heuristic" not in reasoning_lower:
                    issues.append(
                        f"{field}: reasoning contains error text '{pattern}' "
                        f"(model={model}, conf={confidence})"
                    )
                    break

            # Check 3: Empty value for fields that should have one
            # (sequence can legitimately be empty; N/A from cascade is fine)
            # reason_for_failure is also excluded — "" means "no failure", which is valid.
            # v42 Phase 6: also exempt *_legacy copies (created by prefer_atomic swap)
            # since they mirror the semantics of the primary field they replaced.
            empty_ok_fields = (
                "sequence",
                "reason_for_failure", "reason_for_failure_legacy",
                "classification_legacy",  # Same-semantics shadow of classification
            )
            if not value and field not in empty_ok_fields and "N/A" not in (reasoning or ""):
                issues.append(
                    f"{field}: empty value (model={model}, conf={confidence})"
                )

            # Check 4: Zero confidence with a non-empty value (LLM call likely failed)
            # v25: N/A is intentional when from cascade (model="cascade") or
            # deterministic sequence lookup (model="deterministic"). Only flag
            # if an LLM-based annotation returns N/A — that's suspicious.
            if confidence is not None and confidence == 0.0 and value:
                is_intentional_na = (
                    value == "N/A"
                    and model in ("cascade", "deterministic")
                )
                if not is_intentional_na:
                    issues.append(
                        f"{field}: zero confidence with value '{value}' "
                        f"(model={model}) — possible failed LLM call"
                    )

            # Check 5: Reasoning too short (possible truncation or empty LLM response)
            if reasoning and len(reasoning) < 10 and "deterministic" not in (model or ""):
                issues.append(
                    f"{field}: suspiciously short reasoning ({len(reasoning)} chars) "
                    f"(model={model})"
                )

        return issues

    @staticmethod
    def _update_timing(
        job: AnnotationJob,
        trial_start: float,
        pipeline_start: float,
        trial_times: list[float],
    ) -> None:
        """Update elapsed/estimated timing on the job progress.

        Uses total_elapsed / completed_trials for avg, which gives true
        effective throughput in mini-batch mode (where individual trial_start
        times overlap with other trials in the batch).
        """
        import time as _time

        trial_elapsed = _time.monotonic() - trial_start
        trial_times.append(trial_elapsed)

        total_elapsed = _time.monotonic() - pipeline_start
        job.progress.elapsed_seconds = round(total_elapsed, 1)

        # Use effective throughput: total pipeline time / completed trials.
        # In mini-batch mode, individual trial times overlap, so summing them
        # is misleading. Effective throughput is the metric that matters for ETA.
        completed = job.progress.completed_trials
        if completed > 0:
            avg = total_elapsed / completed
        else:
            avg = trial_elapsed
        job.progress.avg_seconds_per_trial = round(avg, 1)

        remaining_trials = job.progress.total_trials - completed
        job.progress.estimated_remaining_seconds = round(avg * remaining_trials, 1)

        # v17: Per-trial anomaly detection
        if len(trial_times) >= 3 and trial_elapsed > 0:
            recent_avg = sum(trial_times[-10:]) / len(trial_times[-10:])
            if trial_elapsed > recent_avg * 2.0:
                nct_id = job.progress.current_nct_id or "unknown"
                anomaly_msg = (
                    f"ANOMALY [{nct_id}]: trial took {trial_elapsed:.0f}s "
                    f"(avg={recent_avg:.0f}s, {trial_elapsed/recent_avg:.1f}x). "
                    f"Check field_timings for slow field/model."
                )
                logger.warning(f"  {anomaly_msg}")
                job.progress.warnings.append(anomaly_msg)
                # Log the field timings to identify which agent caused the slowdown
                if job.progress.field_timings:
                    slowest = max(
                        job.progress.field_timings.items(),
                        key=lambda x: x[1],
                    )
                    slowest_msg = (
                        f"ANOMALY [{nct_id}]: slowest field = {slowest[0]} "
                        f"({slowest[1]:.0f}s)"
                    )
                    logger.warning(f"  {slowest_msg}")
                    job.progress.warnings.append(slowest_msg)

    @staticmethod
    def _log_job_diagnostics(
        job_id: str,
        all_trial_results: list[dict],
        trial_times: list[float],
    ) -> None:
        """v17: Post-job diagnostics summary.

        Logs anomalies, timeout patterns, quality issues, and performance
        stats so problems can be caught without human inspection.
        """
        from app.services.ollama_client import ollama_client

        logger.info(f"[{job_id}] === POST-JOB DIAGNOSTICS ===")

        # 1. Timing anomalies
        if trial_times:
            avg_time = sum(trial_times) / len(trial_times)
            max_time = max(trial_times)
            min_time = min(trial_times)
            slow_trials = [t for t in trial_times if t > avg_time * 2]
            logger.info(
                f"[{job_id}] Timing: avg={avg_time:.0f}s, "
                f"min={min_time:.0f}s, max={max_time:.0f}s, "
                f"anomalous={len(slow_trials)}/{len(trial_times)} trials (>2x avg)"
            )
            if slow_trials:
                total_excess = sum(t - avg_time for t in slow_trials)
                logger.warning(
                    f"[{job_id}] Slow trials wasted ~{total_excess:.0f}s "
                    f"({total_excess/60:.1f} min) above average"
                )

        # 2. Timeout stats from Ollama client
        timeout_stats = ollama_client.get_timeout_stats()
        if timeout_stats:
            total_timeouts = sum(timeout_stats.values())
            logger.warning(
                f"[{job_id}] Timeouts: {total_timeouts} total — {timeout_stats}"
            )
        else:
            logger.info(f"[{job_id}] Timeouts: none")

        # 3. Quality issues in results
        quality_issue_count = 0
        empty_value_count = 0
        zero_conf_count = 0
        for trial in all_trial_results:
            for ann in trial.get("annotations", []):
                if not ann.get("value") and ann.get("field_name") != "sequence":
                    empty_value_count += 1
                if ann.get("confidence") == 0.0 and ann.get("value"):
                    zero_conf_count += 1
                # Check for error text in values
                val = (ann.get("value") or "").lower()
                if any(p in val for p in ["timeout", "error", "failed"]):
                    quality_issue_count += 1

        if quality_issue_count or empty_value_count or zero_conf_count:
            logger.warning(
                f"[{job_id}] Quality: {quality_issue_count} error-in-value, "
                f"{empty_value_count} empty values, "
                f"{zero_conf_count} zero-confidence-with-value"
            )
        else:
            logger.info(f"[{job_id}] Quality: all clean")

        # 4. LLM call stats
        call_counts = ollama_client.get_call_counts_by_model()
        if call_counts:
            logger.info(f"[{job_id}] LLM calls by model: {call_counts}")

        logger.info(f"[{job_id}] === END DIAGNOSTICS ===")

    def _queue_for_review(
        self,
        job_id: str,
        nct_id: str,
        annotations: list[FieldAnnotation],
        verified: VerifiedAnnotation,
        commit_hash: str = "",
        created_at: str = "",
    ) -> None:
        """Add flagged fields to the manual review queue."""
        ann_by_field = {a.field_name: a for a in annotations}

        for consensus in verified.fields:
            if consensus.consensus_reached:
                continue

            annotation = ann_by_field.get(consensus.field_name)
            suggested = []
            if annotation:
                suggested.append(annotation.value)
            for opinion in consensus.opinions:
                if opinion.suggested_value and opinion.suggested_value not in suggested:
                    suggested.append(opinion.suggested_value)

            reason = "model_disagreement"
            if consensus.flag_reason and "insufficient" in consensus.flag_reason:
                reason = "insufficient_evidence"

            # Extract primary annotator reasoning and confidence
            primary_reasoning = ""
            primary_confidence = 0.0
            if annotation:
                primary_reasoning = annotation.reasoning or ""
                primary_confidence = annotation.confidence

            item = ReviewItem(
                job_id=job_id,
                nct_id=nct_id,
                field_name=consensus.field_name,
                original_value=consensus.original_value,
                suggested_values=suggested,
                opinions=[o.model_dump() for o in consensus.opinions],
                primary_reasoning=primary_reasoning,
                primary_confidence=primary_confidence,
                created_at=created_at,
                commit_hash=commit_hash,
            )
            review_service.add(item)
            logger.info(
                f"  Queued for review: {nct_id}/{consensus.field_name} ({reason})"
            )

    async def _run_verification(
        self,
        nct_id: str,
        annotations: list[FieldAnnotation],
        research_data: list[ResearchResult],
        config,
        job=None,
    ) -> VerifiedAnnotation:
        """Run blind verification for each annotation field."""
        # Helper: update progress if job is available (not passed during cascade re-verify)
        def _progress(**kwargs):
            if job is not None:
                for k, v in kwargs.items():
                    setattr(job.progress, k, v)

        verifier = BlindVerifier()
        checker = ConsensusChecker()
        reconciler = ReconciliationAgent()

        # Get model configs
        verifier_models = [
            (key, m) for key, m in config.verification.models.items()
            if m.role == "verifier"
        ]

        # Server profile: override verifier models with stronger alternatives
        server_verifiers = getattr(config.orchestrator, "server_verifiers", [])
        if config.orchestrator.hardware_profile == "server" and server_verifiers:
            from app.models.config_models import ModelConfig
            upgraded = []
            for i, (key, m) in enumerate(verifier_models):
                if i < len(server_verifiers):
                    upgraded.append((key, ModelConfig(name=server_verifiers[i], role="verifier")))
                    logger.info(f"  Server verifier override: {key} → {server_verifiers[i]} (was {m.name})")
                else:
                    upgraded.append((key, m))
            verifier_models = upgraded
        # v42.6.7 Eff #7: fast-model override in the single-NCT legacy path.
        verifier_fast_models = getattr(config.orchestrator, "verifier_fast_models", [])
        if verifier_fast_models:
            from app.models.config_models import ModelConfig
            downsized = []
            for i, (key, m) in enumerate(verifier_models):
                if i < len(verifier_fast_models):
                    downsized.append((key, ModelConfig(name=verifier_fast_models[i], role="verifier")))
                else:
                    downsized.append((key, m))
            verifier_models = downsized

        reconciler_model = None
        for key, m in config.verification.models.items():
            if m.role == "reconciler":
                reconciler_model = m.name
                break
        # Server profile: use the premium model for reconciliation
        if config.orchestrator.hardware_profile == "server":
            reconciler_model = getattr(
                config.orchestrator, "server_premium_model", reconciler_model
            )

        threshold = config.verification.consensus_threshold
        consensus_results = []
        any_flagged = False
        flag_reasons = []

        # v11: Separate fields into skip/verify buckets first
        skip_annotations = []
        verify_annotations = []
        for annotation in annotations:
            field = annotation.field_name
            primary_value = annotation.value

            # v9: Skip verification for deterministic pre-classifier results
            if annotation.skip_verification:
                logger.info(
                    f"  {field}: SKIP verification (deterministic, "
                    f"confidence={annotation.confidence})"
                )
                consensus_results.append(ConsensusResult(
                    field_name=field,
                    original_value=primary_value,
                    final_value=primary_value,
                    consensus_reached=True,
                    agreement_ratio=1.0,
                    opinions=[],
                ))
                skip_annotations.append(annotation)
                continue

            # Skip verification for low-confidence annotations already flagged
            if annotation.confidence < 0.2 and "[Below threshold" in (annotation.reasoning or ""):
                consensus_results.append(ConsensusResult(
                    field_name=field,
                    original_value=primary_value,
                    final_value="",
                    consensus_reached=False,
                    agreement_ratio=0.0,
                    opinions=[],
                    flag_reason="insufficient_evidence",
                ))
                any_flagged = True
                flag_reasons.append(f"{field}: insufficient evidence")
                skip_annotations.append(annotation)
                continue

            verify_annotations.append(annotation)

        # v11: MODEL-GROUPED VERIFICATION — run each verifier on ALL fields
        # before switching to the next verifier. Reduces model switches from
        # ~15 (field×verifier) to ~3 (one per verifier model).
        all_opinions: dict[str, list] = {a.field_name: [] for a in verify_annotations}

        for model_key, model_cfg in verifier_models:
            _progress(current_agent=model_key, current_model=model_cfg.name)
            logger.info(f"  Verifier {model_key} ({model_cfg.name}): verifying {len(verify_annotations)} fields")

            for j, annotation in enumerate(verify_annotations):
                field = annotation.field_name
                _progress(
                    current_field=field,
                    verification_progress=f"{model_key}: {j+1}/{len(verify_annotations)} fields",
                )

                opinion = await verifier.verify(
                    nct_id=nct_id,
                    field_name=field,
                    research_results=research_data,
                    model_name=model_key,
                    ollama_model=model_cfg.name,
                )
                all_opinions[field].append(opinion)

        # Phase 2: Run consensus checks (no LLM calls)
        _progress(current_agent="consensus", current_model=None, verification_progress="checking consensus")

        fields_needing_reconciliation = []
        ann_by_field = {a.field_name: a for a in verify_annotations}

        for annotation in verify_annotations:
            field = annotation.field_name
            consensus = checker.check(
                field_name=field,
                primary_value=annotation.value,
                primary_model="primary",
                verifier_opinions=all_opinions[field],
                threshold=threshold,
            )

            if not consensus.consensus_reached and reconciler_model:
                # v18: Protect primary's deliberate empty RfF from verification override.
                # The RfF agent analyzed the evidence and concluded "no failure" — overriding
                # requires ALL verifiers to unanimously agree on the same non-empty value
                # with reasonable confidence. Prevents metadata-biased verifiers (who see
                # whyStopped) from overriding a correct empty assessment.
                if (field == "reason_for_failure"
                        and annotation.value == ""
                        and annotation.confidence >= 0.8):
                    from agents.verification.consensus import _normalize
                    non_empty = [
                        o for o in consensus.opinions
                        if o.suggested_value and o.suggested_value.strip()
                    ]
                    if non_empty:
                        values = set(
                            _normalize(o.suggested_value, "reason_for_failure")
                            for o in non_empty
                        )
                        all_confident = all(o.confidence >= 0.7 for o in non_empty)
                        unanimous = (
                            len(values) == 1
                            and all_confident
                            and len(non_empty) == len(consensus.opinions)
                        )
                        if not unanimous:
                            logger.info(
                                f"  {field}: EMPTY RfF PROTECTION — primary empty "
                                f"(conf={annotation.confidence:.2f}), verifiers not "
                                f"unanimous ({len(values)} values, "
                                f"confident={all_confident}) — keeping empty"
                            )
                            consensus.final_value = ""
                            consensus.consensus_reached = True
                            consensus.reconciler_used = False
                            consensus.reconciler_reasoning = (
                                f"Primary empty RfF protected: verifiers not unanimous "
                                f"({len(values)} distinct values)"
                            )
                            consensus_results.append(consensus)
                            continue

                # High-confidence primary protection
                verifier_max_conf = max(
                    (o.confidence for o in consensus.opinions if not o.agrees),
                    default=0.0,
                )
                if annotation.confidence > 0.85 and verifier_max_conf <= 0.7:
                    logger.info(
                        f"  {field}: HIGH-CONFIDENCE PRIMARY OVERRIDE "
                        f"(primary={annotation.confidence:.2f}, "
                        f"max_dissenting_verifier={verifier_max_conf:.2f}) "
                        f"— accepting primary value '{annotation.value}'"
                    )
                    consensus.final_value = annotation.value
                    consensus.consensus_reached = True
                    consensus.reconciler_used = False
                    consensus.reconciler_reasoning = (
                        f"Primary override: confidence {annotation.confidence:.2f} "
                        f"> threshold 0.85, dissenting verifiers at baseline "
                        f"{verifier_max_conf:.2f}"
                    )
                else:
                    fields_needing_reconciliation.append((annotation, consensus))
                    continue  # defer to batch reconciliation

            if not consensus.consensus_reached:
                any_flagged = True
                flag_reasons.append(f"{field}: model disagreement")

            consensus_results.append(consensus)

        # Phase 3: Batch reconciliation (one model load for all disagreements)
        if fields_needing_reconciliation:
            _progress(
                current_agent="reconciler",
                current_model=reconciler_model,
                verification_progress=f"reconciling {len(fields_needing_reconciliation)} fields",
            )

            for annotation, consensus in fields_needing_reconciliation:
                field = annotation.field_name
                _progress(current_field=field)
                logger.info(f"  {field}: Attempting reconciliation with {reconciler_model}")

                consensus = await reconciler.reconcile(
                    field_name=field,
                    consensus_result=consensus,
                    research_results=research_data,
                    reconciler_model=reconciler_model,
                    primary_confidence=annotation.confidence,
                )

                if not consensus.consensus_reached:
                    any_flagged = True
                    flag_reasons.append(f"{field}: model disagreement")

                consensus_results.append(consensus)

        _progress(verification_progress=None, current_field=None, current_agent=None, current_model=None)

        return VerifiedAnnotation(
            nct_id=nct_id,
            fields=consensus_results,
            overall_consensus=not any_flagged,
            flagged_for_review=any_flagged,
            flag_reason="; ".join(flag_reasons) if flag_reasons else None,
        )

    @staticmethod
    def _build_research_coverage(
        research_data: list[ResearchResult],
    ) -> dict[str, dict]:
        """Build per-agent research coverage metadata for a trial.

        Returns a dict mapping agent_name to:
          {citations_count, has_data, quality_avg, error, source_names}
        """
        coverage: dict[str, dict] = {}
        for result in research_data:
            citations = result.citations
            citations_count = len(citations)
            has_data = citations_count > 0 and not result.error
            quality_avg = 0.0
            if citations_count > 0:
                quality_avg = round(
                    sum(c.quality_score for c in citations) / citations_count, 3
                )
            # Collect unique source names for this agent
            source_names = sorted(set(c.source_name for c in citations)) if citations else []
            coverage[result.agent_name] = {
                "citations_count": citations_count,
                "has_data": has_data,
                "quality_avg": quality_avg,
                "error": result.error if result.error else None,
                "source_names": source_names,
            }
        return coverage

    def _extract_metadata(
        self, nct_id: str, research_data: list[ResearchResult]
    ) -> TrialMetadata:
        """Extract basic trial metadata from research results."""
        metadata = TrialMetadata(nct_id=nct_id)

        for result in research_data:
            if result.agent_name == "clinical_protocol" and result.raw_data:
                raw = result.raw_data
                # Try to pull metadata from raw ClinicalTrials.gov data
                protocol = raw.get("protocol_section", raw.get("ct_data", {}))
                if isinstance(protocol, dict):
                    ident = protocol.get("identificationModule", {})
                    status_mod = protocol.get("statusModule", {})
                    cond_mod = protocol.get("conditionsModule", {})
                    arms_mod = protocol.get("armsInterventionsModule", {})

                    metadata.title = (
                        ident.get("officialTitle")
                        or ident.get("briefTitle")
                        or metadata.title
                    )
                    metadata.status = status_mod.get("overallStatus") or metadata.status
                    metadata.phase = (
                        ", ".join(protocol.get("designModule", {}).get("phases", []))
                        or metadata.phase
                    )
                    metadata.conditions = cond_mod.get("conditions", metadata.conditions)
                    interventions = arms_mod.get("interventions", [])
                    metadata.interventions = [
                        f"{i.get('type', '')}: {i.get('name', '')}"
                        for i in interventions
                    ] or metadata.interventions
                break  # Only need clinical_protocol for metadata

        return metadata

    def cancel_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job or job.status not in ("queued", "running"):
            return False
        job.status = "cancelled"
        job.updated_at = now_pacific()
        self._persist_job(job)
        return True


# Module-level singleton
orchestrator = PipelineOrchestrator()
