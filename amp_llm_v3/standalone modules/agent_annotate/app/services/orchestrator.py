"""
Pipeline orchestrator - manages annotation job lifecycle.

Coordinates research agents (parallel), annotation agents (parallel with retry),
and feeds results to the verification pipeline (Phase 3).
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional

import aiohttp

from app.models.job import AnnotationJob, JobSummary, JobProgress
from app.models.research import ResearchResult
from app.models.annotation import FieldAnnotation, TrialMetadata, AnnotationResult
from app.models.verification import ConsensusResult, VerifiedAnnotation
from app.services.config_service import config_service
from app.services.output_service import save_json_output
from app.services.version_service import get_version_stamp
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
                )
            )
        return summaries

    def active_count(self) -> int:
        return sum(1 for j in self._jobs.values() if j.status in ("queued", "running"))

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
            job.updated_at = datetime.utcnow()

    async def _run_pipeline_inner(self, job: AnnotationJob) -> None:
        """Inner pipeline logic, wrapped by run_pipeline error handler."""
        job_id = job.job_id
        job.status = "running"
        job.updated_at = datetime.utcnow()
        config = config_service.get()

        all_trial_results = []

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=120, connect=30)
        ) as session:

            for i, nct_id in enumerate(job.nct_ids):
                job.progress.current_nct_id = nct_id
                logger.info(f"[{job_id}] Processing {nct_id} ({i+1}/{len(job.nct_ids)})")

                try:
                    # --- Phase 1: Research (parallel) ---
                    job.progress.current_stage = "researching"
                    job.updated_at = datetime.utcnow()

                    research_data = await self._run_research(nct_id, session, config, job)

                    # --- Phase 2: Annotation (parallel with retry) ---
                    job.progress.current_stage = "annotating"
                    job.updated_at = datetime.utcnow()

                    annotations = await self._run_annotation(
                        nct_id, research_data, config, job
                    )

                    # --- Phase 3: Verification (sequential per field) ---
                    job.progress.current_stage = "verifying"
                    job.updated_at = datetime.utcnow()

                    verified = await self._run_verification(
                        nct_id, annotations, research_data, config
                    )

                    # Build trial result
                    metadata = self._extract_metadata(nct_id, research_data)
                    trial_output = {
                        "nct_id": nct_id,
                        "metadata": metadata.model_dump(),
                        "annotations": [a.model_dump() for a in annotations],
                        "verification": verified.model_dump(),
                        "research_used": [r.agent_name for r in research_data],
                    }
                    all_trial_results.append(trial_output)

                    # Queue flagged fields for manual review
                    if verified.flagged_for_review:
                        self._queue_for_review(
                            job_id, nct_id, annotations, verified
                        )

                    job.progress.completed_trials += 1

                except Exception as e:
                    logger.error(f"[{job_id}] Error processing {nct_id}: {e}")
                    metadata = TrialMetadata(nct_id=nct_id)
                    all_trial_results.append({
                        "nct_id": nct_id,
                        "metadata": metadata.model_dump(),
                        "annotations": [],
                        "verification": None,
                        "research_used": [],
                        "error": str(e),
                    })
                    job.progress.completed_trials += 1

        # --- Save results ---
        job.progress.current_stage = "saving"
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
        }
        save_json_output(job_id, output)

        job.results = all_trial_results
        job.status = "completed"
        job.progress.current_stage = "done"
        job.progress.current_nct_id = None
        job.updated_at = datetime.utcnow()
        logger.info(f"[{job_id}] Pipeline completed: {len(all_trial_results)} trials")

    async def _run_research(
        self,
        nct_id: str,
        session: aiohttp.ClientSession,
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
        """Run annotation agents, with retry logic for insufficient evidence."""
        annotations = []
        agent_config = config.annotation_agents
        thresholds = config.evidence_thresholds

        async def annotate_field(field_name: str) -> FieldAnnotation:
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
            result = await agent.annotate(nct_id, all_research)

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

        if config.orchestrator.parallel_annotation:
            # Run all annotation agents in parallel
            # Note: They share the Ollama lock, so actual LLM calls are sequential
            tasks = [annotate_field(field) for field in ANNOTATION_AGENTS]
            annotations = list(await asyncio.gather(*tasks, return_exceptions=True))
            # Replace exceptions with error annotations
            for i, ann in enumerate(annotations):
                if isinstance(ann, Exception):
                    field = list(ANNOTATION_AGENTS.keys())[i]
                    annotations[i] = FieldAnnotation(
                        field_name=field,
                        value="Unknown",
                        reasoning=f"Agent error: {ann}",
                    )
        else:
            for field in ANNOTATION_AGENTS:
                try:
                    ann = await annotate_field(field)
                    annotations.append(ann)
                except Exception as e:
                    annotations.append(FieldAnnotation(
                        field_name=field,
                        value="Unknown",
                        reasoning=f"Agent error: {e}",
                    ))

        return annotations

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

            item = ReviewItem(
                job_id=job_id,
                nct_id=nct_id,
                field_name=consensus.field_name,
                original_value=consensus.original_value,
                suggested_values=suggested,
                opinions=[o.model_dump() for o in consensus.opinions],
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
        job.updated_at = datetime.utcnow()
        return True


# Module-level singleton
orchestrator = PipelineOrchestrator()
