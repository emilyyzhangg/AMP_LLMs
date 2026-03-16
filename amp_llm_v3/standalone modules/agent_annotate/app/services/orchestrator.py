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
    """Creates, tracks, and runs annotation pipeline jobs."""

    def __init__(self):
        self._jobs: dict[str, AnnotationJob] = {}

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
        return job

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

        if job.status == "cancelled":
            return

        # --- Phase 2: Annotation + Verification ---
        persistence.init_annotations_dir(job_id)
        all_trial_results = await self._run_phase2_annotate(
            job, config, research_data, persistence, skip_annotations, pipeline_start
        )

        if job.status == "cancelled":
            return

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
        job.status = "completed"
        job.finished_at = now_pacific()
        job.progress.current_stage = "done"
        job.progress.current_nct_id = None
        job.progress.current_phase = ""
        job.updated_at = now_pacific()
        logger.info(f"[{job_id}] Pipeline completed: {len(all_trial_results)} trials")

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
                        job.job_id, nct_id, annotations, verified
                    )

                job.progress.completed_trials += 1
                self._update_timing(job, trial_start, pipeline_start, trial_times)

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

        return all_trial_results

    async def _run_research(
        self,
        nct_id: str,
        config,
        job: AnnotationJob,
    ) -> list[ResearchResult]:
        """Dispatch all research agents in parallel."""
        tasks = {}
        for agent_name, agent_cls in RESEARCH_AGENTS.items():
            agent_config = config.research_agents.get(agent_name)
            if not agent_config:
                continue
            agent = agent_cls()
            tasks[agent_name] = agent.research(nct_id)

        results = []
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

            # Check evidence threshold
            threshold = getattr(thresholds, field_name, None)
            if threshold:
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

        # --- Step 1: Run peptide FIRST (classification depends on it) ---
        try:
            peptide_ann = await annotate_field("peptide")
        except Exception as e:
            peptide_ann = FieldAnnotation(
                field_name="peptide",
                value="Unknown",
                reasoning=f"Agent error: {e}",
            )
        annotations.append(peptide_ann)
        shared_metadata["peptide_result"] = peptide_ann.value

        # --- Step 2: Run remaining agents (classification gets peptide result) ---
        remaining_fields = [f for f in ANNOTATION_AGENTS if f != "peptide"]

        if config.orchestrator.parallel_annotation:
            tasks = []
            for field in remaining_fields:
                meta = shared_metadata if field == "classification" else None
                tasks.append(annotate_field(field, metadata=meta))
            results = list(await asyncio.gather(*tasks, return_exceptions=True))
            for i, ann in enumerate(results):
                if isinstance(ann, Exception):
                    field = remaining_fields[i]
                    results[i] = FieldAnnotation(
                        field_name=field,
                        value="Unknown",
                        reasoning=f"Agent error: {ann}",
                    )
            annotations.extend(results)
        else:
            for field in remaining_fields:
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
        reconciler_model = None
        for key, m in config.verification.models.items():
            if m.role == "reconciler":
                reconciler_model = m.name
                break

        threshold = config.verification.consensus_threshold
        consensus_results = []
        any_flagged = False
        flag_reasons = []

        for annotation in annotations:
            field = annotation.field_name
            primary_value = annotation.value
            logger.info(f"  Verifying {field}: primary='{primary_value}'")

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
                continue

            # Run each verifier SEQUENTIALLY (one Ollama model at a time)
            verifier_opinions = []
            for model_key, model_cfg in verifier_models:
                opinion = await verifier.verify(
                    nct_id=nct_id,
                    field_name=field,
                    research_results=research_data,
                    model_name=model_key,
                    ollama_model=model_cfg.name,
                )
                verifier_opinions.append(opinion)

            # Consensus check
            consensus = checker.check(
                field_name=field,
                primary_value=primary_value,
                primary_model="primary",
                verifier_opinions=verifier_opinions,
                threshold=threshold,
            )

            # If no consensus, try reconciliation
            if not consensus.consensus_reached and reconciler_model:
                logger.info(f"  {field}: Attempting reconciliation with {reconciler_model}")
                consensus = await reconciler.reconcile(
                    field_name=field,
                    consensus_result=consensus,
                    research_results=research_data,
                    reconciler_model=reconciler_model,
                )

            if not consensus.consensus_reached:
                any_flagged = True
                flag_reasons.append(f"{field}: model disagreement")

            consensus_results.append(consensus)

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
          {citations_count: int, has_data: bool, quality_avg: float}
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
            coverage[result.agent_name] = {
                "citations_count": citations_count,
                "has_data": has_data,
                "quality_avg": quality_avg,
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
        return True


# Module-level singleton
orchestrator = PipelineOrchestrator()
