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

        # Configure Ollama keep_alive based on hardware profile
        from app.services.ollama_client import ollama_client
        hw_profile = getattr(config.orchestrator, "hardware_profile", "mac_mini")
        ollama_client.set_hardware_profile(hw_profile)
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
        all_trial_results = await self._run_phase2_annotate(
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
        """Phase 2: Annotate and verify each trial sequentially.

        Each trial goes through annotation -> consistency -> verification.
        Ollama calls are serialized by the ollama_client lock.
        """
        import time as _time

        job.progress.current_phase = "annotation"
        all_trial_results = []
        trial_times: list[float] = []

        for i, nct_id in enumerate(job.nct_ids):
            if job.status == "cancelled":
                break

            # Load cached annotation if already on disk (resume)
            if nct_id in skip_nct_ids:
                cached = persistence.load_annotation(job.job_id, nct_id)
                if cached:
                    all_trial_results.append(cached)
                    job.progress.completed_trials += 1
                    logger.info(
                        f"[{job.job_id}] Loaded cached annotation for {nct_id}"
                    )
                    continue

            trial_start = _time.monotonic()
            job.progress.current_nct_id = nct_id
            research = research_data.get(nct_id, [])
            logger.info(
                f"[{job.job_id}] Annotating {nct_id} ({i+1}/{len(job.nct_ids)})"
            )

            try:
                # --- Annotation ---
                job.progress.current_stage = "annotating"
                job.progress.elapsed_seconds = round(
                    _time.monotonic() - pipeline_start, 1
                )
                job.updated_at = now_pacific()

                annotations = await self._run_annotation(
                    nct_id, research, config, job
                )
                self._enforce_consistency(annotations)

                # --- Verification ---
                job.progress.current_stage = "verifying"
                job.progress.elapsed_seconds = round(
                    _time.monotonic() - pipeline_start, 1
                )
                job.updated_at = now_pacific()

                verified = await self._run_verification(
                    nct_id, annotations, research, config
                )

                # --- Peptide cascade re-verification ---
                # If verification flipped peptide, re-run classification
                # with the corrected value
                annotations, verified = await self._peptide_cascade_check(
                    nct_id, annotations, verified, research, config
                )

                # --- Post-verification consistency enforcement ---
                # Cross-field rules on final verified values resolve
                # ~25 of 32 review items automatically (v7)
                self._enforce_post_verification_consistency(verified)

                # Build trial result
                metadata = self._extract_metadata(nct_id, research)

                # Build research coverage metadata (Phase 1.5)
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
                all_trial_results.append(trial_output)

                # Persist annotation to disk
                persistence.save_annotation(job.job_id, nct_id, trial_output)

                # Queue flagged fields for manual review
                if verified.flagged_for_review:
                    self._queue_for_review(
                        job.job_id, nct_id, annotations, verified,
                        commit_hash=job.commit_hash,
                        created_at=job.started_at.isoformat() if job.started_at else "",
                    )

                job.progress.completed_trials += 1
                self._update_timing(job, trial_start, pipeline_start, trial_times)
                self._persist_job(job, trial_times)

            except Exception as e:
                logger.error(f"[{job.job_id}] Error processing {nct_id}: {e}")
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

        return all_trial_results

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
                    metadata = {"interventions": interventions}
                    logger.info(
                        f"  Extracted interventions: "
                        f"{[i['name'] for i in interventions]}"
                    )
            except Exception as e:
                logger.warning(f"clinical_protocol failed: {e}")
                results.append(ResearchResult(
                    agent_name="clinical_protocol",
                    nct_id=nct_id,
                    error=str(e),
                ))

        # Step 2: Run all other agents in parallel with metadata
        tasks = {}
        for agent_name, agent_cls in RESEARCH_AGENTS.items():
            if agent_name == "clinical_protocol":
                continue  # already ran
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

        # --- Step 2: Run classification, delivery_mode, outcome (NOT failure_reason yet) ---
        # failure_reason depends on outcome, so we run it after outcome completes.
        step2_fields = [f for f in ANNOTATION_AGENTS if f not in ("peptide", "reason_for_failure")]

        job.progress.current_field = ", ".join(step2_fields)
        job.progress.current_agent = "annotation (parallel)" if config.orchestrator.parallel_annotation else "annotation"
        _step2_start = _field_time.monotonic()
        if config.orchestrator.parallel_annotation:
            tasks = []
            for field in step2_fields:
                meta = shared_metadata if field == "classification" else None
                tasks.append(annotate_field(field, metadata=meta))
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
                    meta = shared_metadata if field == "classification" else None
                    ann = await annotate_field(field, metadata=meta)
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

        # --- Step 3: Run failure_reason AFTER outcome (it needs the outcome result) ---
        job.progress.current_field = "reason_for_failure"
        job.progress.current_agent = "failure_reason_annotator"
        _rf_start = _field_time.monotonic()
        outcome_ann = next((a for a in annotations if a.field_name == "outcome"), None)
        if outcome_ann:
            shared_metadata["outcome_result"] = outcome_ann.value
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
            self._enforce_consistency(annotations)

            # Re-verify classification only
            verifier = BlindVerifier()
            checker = ConsensusChecker()

            verifier_models = [
                (key, m) for key, m in config.verification.models.items()
                if m.role == "verifier"
            ]
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
    def _enforce_consistency(annotations: list[FieldAnnotation]) -> None:
        """Enforce cross-field consistency rules after annotation, before verification.

        Fixes contradictions that arise from fields being annotated independently:
        - peptide=False -> classification must be "Other"
        - outcome is non-failure -> reason_for_failure must be ""
        """
        ann_by_field = {a.field_name: a for a in annotations}
        peptide = ann_by_field.get("peptide")
        classification = ann_by_field.get("classification")
        outcome = ann_by_field.get("outcome")
        failure = ann_by_field.get("reason_for_failure")

        # Rule 1: peptide=False -> classification must be "Other"
        if peptide and classification and peptide.value == "False":
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
    def _update_timing(
        job: AnnotationJob,
        trial_start: float,
        pipeline_start: float,
        trial_times: list[float],
    ) -> None:
        """Update elapsed/estimated timing on the job progress."""
        import time as _time

        trial_elapsed = _time.monotonic() - trial_start
        trial_times.append(trial_elapsed)

        total_elapsed = _time.monotonic() - pipeline_start
        job.progress.elapsed_seconds = round(total_elapsed, 1)

        avg = sum(trial_times) / len(trial_times)
        job.progress.avg_seconds_per_trial = round(avg, 1)

        remaining_trials = job.progress.total_trials - job.progress.completed_trials
        job.progress.estimated_remaining_seconds = round(avg * remaining_trials, 1)

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
    ) -> VerifiedAnnotation:
        """Run blind verification for each annotation field."""
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
            job.progress.current_agent = model_key
            job.progress.current_model = model_cfg.name
            logger.info(f"  Verifier {model_key} ({model_cfg.name}): verifying {len(verify_annotations)} fields")

            for j, annotation in enumerate(verify_annotations):
                field = annotation.field_name
                job.progress.current_field = field
                job.progress.verification_progress = (
                    f"{model_key}: {j+1}/{len(verify_annotations)} fields"
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
        job.progress.current_agent = "consensus"
        job.progress.current_model = None
        job.progress.verification_progress = "checking consensus"

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
            job.progress.current_agent = "reconciler"
            job.progress.current_model = reconciler_model
            job.progress.verification_progress = f"reconciling {len(fields_needing_reconciliation)} fields"

            for annotation, consensus in fields_needing_reconciliation:
                field = annotation.field_name
                job.progress.current_field = field
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

        job.progress.verification_progress = None
        job.progress.current_field = None
        job.progress.current_agent = None
        job.progress.current_model = None

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
