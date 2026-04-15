"""
EDAM Loop 1: Cross-Run Stability Tracker.

Compares how the same (nct_id, field) is annotated across multiple jobs.
Identifies stable fields (consistent value) and flipping fields (unstable).
Grades evidence anchoring to distinguish reliable stability from consistent
hallucination.

Runs automatically after every job completes.
"""

import logging
from collections import Counter
from pathlib import Path

from app.services.memory.memory_store import MemoryStore, compute_weight
from app.services.memory.edam_config import (
    STABILITY_EXEMPLAR_MIN_RUNS, STABILITY_EXEMPLAR_MIN_SCORE,
    EVIDENCE_GRADE_STRONG_MIN_CONFIDENCE, EVIDENCE_GRADE_STRONG_MIN_CONSENSUS,
    EVIDENCE_GRADE_MEDIUM_MIN_CONFIDENCE,
    ANOMALY_THRESHOLD, ANOMALY_MIN_TRIALS,
    TRAINING_NCTS,
)

logger = logging.getLogger("agent_annotate.edam.stability")


class StabilityTracker:
    """Loop 1: Cross-run stability analysis."""

    def __init__(self, memory: MemoryStore):
        self._memory = memory

    async def analyze_job(self, job_id: str, job_results: list[dict],
                          config_hash: str, git_commit: str) -> dict:
        """
        Post-job hook: store experiences and compute stability for every
        (nct_id, field) in this job.

        Returns a summary dict with stability metrics and anomaly flags.
        """
        epoch = self._memory.get_or_create_epoch(config_hash, git_commit)
        stored = 0
        embedded = 0

        # Step 1: Store all annotation outcomes as experiences
        # v18: Only learn from training set NCTs (held-out test set excluded)
        skipped_ncts = 0
        for trial in job_results:
            nct_id = trial.get("nct_id", "")
            if not nct_id:
                continue
            if TRAINING_NCTS and nct_id.upper() not in TRAINING_NCTS:
                skipped_ncts += 1
                continue

            verification = trial.get("verification") or {}
            fields = verification.get("fields", [])
            annotations = trial.get("annotations", [])
            ann_by_field = {a.get("field_name", ""): a for a in annotations}

            for field_obj in fields:
                field_name = field_obj.get("field_name", "")
                final_value = field_obj.get("final_value", "")
                consensus = field_obj.get("consensus_reached", False)

                ann = ann_by_field.get(field_name, {})
                confidence = ann.get("confidence", 0.0)
                reasoning = ann.get("reasoning", "")

                # Build evidence summary from annotation evidence
                evidence_parts = []
                for e in ann.get("evidence", [])[:5]:
                    src = e.get("source_name", "")
                    snippet = e.get("snippet", "")[:200]
                    if snippet:
                        evidence_parts.append(f"[{src}] {snippet}")
                evidence_summary = " | ".join(evidence_parts)

                exp_id = self._memory.store_experience(
                    nct_id=nct_id, field_name=field_name, job_id=job_id,
                    value=final_value, confidence=confidence,
                    consensus_reached=consensus,
                    evidence_summary=evidence_summary,
                    reasoning=reasoning,
                    config_hash=config_hash, git_commit=git_commit,
                )
                stored += 1

                # v38: Embedding generation DISABLED.
                # Generates an Ollama call per experience for similarity search
                # in build_guidance(). With reconciliation corrections purged and
                # guidance now using direct field-name queries instead of semantic
                # search, embeddings add compute overhead for no value.

        if skipped_ncts:
            logger.info("EDAM: skipped %d non-training NCTs (stored %d)", skipped_ncts, stored)

        # Step 2: Compute stability for all (nct_id, field) pairs in this job
        stable_count = 0
        unstable_count = 0
        newly_unstable = []

        # v18: Only compute stability for training NCTs
        nct_ids = set(t.get("nct_id", "") for t in job_results if t.get("nct_id"))
        if TRAINING_NCTS:
            nct_ids = {n for n in nct_ids if n.upper() in TRAINING_NCTS}
        fields = ["classification", "delivery_mode", "outcome", "reason_for_failure", "peptide"]

        for nct_id in nct_ids:
            for field_name in fields:
                result = self.compute_stability(nct_id, field_name)
                if result["total_runs"] < 2:
                    continue  # not enough data yet
                if result["stability_score"] >= STABILITY_EXEMPLAR_MIN_SCORE:
                    stable_count += 1
                else:
                    unstable_count += 1
                    if result["total_runs"] == 2:  # newly unstable
                        newly_unstable.append((nct_id, field_name))

        # Step 3: Detect anomalies
        anomalies = []
        for field_name in fields:
            field_anomalies = self._memory.detect_anomalies(field_name)
            anomalies.extend(field_anomalies)

        summary = {
            "experiences_stored": stored,
            "embeddings_generated": embedded,
            "stable_count": stable_count,
            "unstable_count": unstable_count,
            "newly_unstable": newly_unstable,
            "anomalies": anomalies,
        }

        logger.info(
            "EDAM stability: %d experiences stored, %d stable, %d unstable, %d anomalies",
            stored, stable_count, unstable_count, len(anomalies),
        )
        for nct, field in newly_unstable:
            logger.warning("EDAM: newly unstable — %s/%s", nct, field)
        for a in anomalies:
            logger.warning("EDAM anomaly: %s", a["warning"])

        return summary

    def compute_stability(self, nct_id: str, field_name: str) -> dict:
        """
        Compare all experiences for this (nct_id, field) across jobs.
        Returns stability score, majority value, evidence grade, etc.
        """
        experiences = self._memory.get_experiences(
            nct_id=nct_id, field_name=field_name, limit=100
        )
        if not experiences:
            return {
                "stability_score": 0.0,
                "majority_value": "",
                "evidence_grade": "none",
                "total_runs": 0,
                "distinct_values": 0,
                "value_distribution": {},
            }

        # Count value occurrences (weighted by epoch relevance)
        current_epoch = self._memory.get_current_epoch()
        weighted_counts: dict[str, float] = {}
        raw_counts: Counter = Counter()
        for exp in experiences:
            value = exp["value"]
            weight = compute_weight(exp["epoch"], current_epoch)
            weighted_counts[value] = weighted_counts.get(value, 0) + weight
            raw_counts[value] += 1

        total_runs = len(experiences)
        distinct_values = len(raw_counts)

        # Majority value (by weighted count)
        majority_value = max(weighted_counts, key=weighted_counts.get)
        majority_count = raw_counts[majority_value]

        # Stability score: fraction of runs that agree with majority
        stability_score = majority_count / total_runs if total_runs > 0 else 0.0

        # Evidence grade
        evidence_grade = self._grade_evidence(experiences, majority_value)

        # Update stability index in DB
        self._memory.upsert_stability(
            nct_id=nct_id, field_name=field_name,
            stability_score=round(stability_score, 3),
            majority_value=majority_value,
            evidence_grade=evidence_grade,
            total_runs=total_runs,
            distinct_values=distinct_values,
        )

        return {
            "stability_score": round(stability_score, 3),
            "majority_value": majority_value,
            "evidence_grade": evidence_grade,
            "total_runs": total_runs,
            "distinct_values": distinct_values,
            "value_distribution": dict(raw_counts),
        }

    @staticmethod
    def _grade_evidence(experiences: list[dict], majority_value: str) -> str:
        """
        Grade evidence anchoring based on confidence and consensus.

        strong: majority of runs have high confidence + consensus reached
        medium: moderate confidence or mixed consensus
        weak:   low confidence or consensus rarely reached
        none:   single run or no consensus data
        """
        matching = [e for e in experiences if e["value"] == majority_value]
        if not matching:
            return "none"

        avg_confidence = sum(e["confidence"] for e in matching) / len(matching)
        consensus_rate = (
            sum(1 for e in matching if e["consensus_reached"]) / len(matching)
        )

        if (avg_confidence >= EVIDENCE_GRADE_STRONG_MIN_CONFIDENCE
                and consensus_rate >= 0.8
                and len(matching) >= STABILITY_EXEMPLAR_MIN_RUNS):
            return "strong"
        elif (avg_confidence >= EVIDENCE_GRADE_MEDIUM_MIN_CONFIDENCE
              and consensus_rate >= 0.5):
            return "medium"
        elif len(matching) >= 2:
            return "weak"
        else:
            return "none"
