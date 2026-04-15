"""
EDAM — Experience-Driven Annotation Memory (v38 redesign).

Self-learning system for agent_annotate. Redesigned for autonomous operation
(no human reviewers). Three active feedback loops:

  Loop 1 (Stability):     Cross-run comparison → stable exemplars + instability flags
  Loop 2 (Ground Truth):  Compare agent output to training CSV R1 annotations →
                           highest-quality non-human learning signal
  Loop 2b (Self-Audit):   Evidence consistency checking → catches agent contradictions

Disabled in v38:
  - Reconciliation corrections (91.6% of prior corrections, unreliable signal)
  - Embedding generation (expensive, zero ROI without reliable corrections)
  - Prompt optimization (7 variants created, 0 experiments ever ran)

EDAM failures are NEVER fatal — the annotation pipeline runs normally if
any EDAM component fails.
"""

import csv
import logging
from pathlib import Path

from app.services.memory.memory_store import MemoryStore, memory_store
from app.services.memory.stability_tracker import StabilityTracker
from app.services.memory.correction_learner import CorrectionLearner
from app.services.memory.self_audit import SelfAuditor
from app.services.memory.edam_config import TRAINING_NCTS

logger = logging.getLogger("agent_annotate.edam")

# Module-level instances (singletons)
stability_tracker = StabilityTracker(memory_store)
correction_learner = CorrectionLearner(memory_store)
self_auditor = SelfAuditor(memory_store)

# Ground truth CSV path
_GT_CSV = Path(__file__).resolve().parents[3] / "docs" / "human_ground_truth_train_df.csv"

# Field mappings: agent field_name → CSV column for R1
_GT_FIELD_MAP = {
    "classification": "Classification_ann1",
    "delivery_mode": "Delivery Mode_ann1",
    "outcome": "Outcome_ann1",
    "reason_for_failure": "Reason for Failure_ann1",
    "peptide": "Peptide_ann1",
    "sequence": "Sequence_ann1",
}

# Value normalization for comparison (same as concordance_service)
_CLASSIFICATION_NORM = {
    "amp": "AMP", "amp(infection)": "AMP", "amp(other)": "AMP",
    "amp (infection)": "AMP", "amp (other)": "AMP", "other": "Other",
}
_DELIVERY_NORM = {
    "iv": "Injection/Infusion", "intravenous": "Injection/Infusion",
    "injection/infusion": "Injection/Infusion", "subcutaneous": "Injection/Infusion",
    "intradermal": "Injection/Infusion", "intramuscular": "Injection/Infusion",
    "oral": "Oral", "topical": "Topical", "inhalation": "Other",
    "intranasal": "Other", "other": "Other",
}
_OUTCOME_NORM = {
    "active": "Active", "active, not recruiting": "Active",
    "active not recruiting": "Active", "recruiting": "Recruiting",
    "positive": "Positive", "terminated": "Terminated",
    "withdrawn": "Withdrawn", "unknown": "Unknown",
    "failed - completed trial": "Failed - completed trial",
}
_PEPTIDE_NORM = {"true": "TRUE", "false": "FALSE", "yes": "TRUE", "no": "FALSE"}

_FIELD_NORMALIZERS = {
    "classification": _CLASSIFICATION_NORM,
    "delivery_mode": _DELIVERY_NORM,
    "outcome": _OUTCOME_NORM,
    "peptide": _PEPTIDE_NORM,
}

# Cached ground truth data: {nct_id_upper: {field_name: normalized_value}}
_gt_cache: dict[str, dict[str, str]] = {}


def _load_ground_truth() -> dict[str, dict[str, str]]:
    """Load and cache ground truth from training CSV."""
    global _gt_cache
    if _gt_cache:
        return _gt_cache

    if not _GT_CSV.exists():
        logger.warning("Ground truth CSV not found at %s", _GT_CSV)
        return {}

    try:
        with open(_GT_CSV) as f:
            reader = csv.DictReader(f)
            for row in reader:
                nct = row.get("nct_id", "").strip().upper()
                if not nct:
                    continue
                fields = {}
                for agent_field, csv_col in _GT_FIELD_MAP.items():
                    raw = row.get(csv_col, "").strip()
                    if not raw:
                        continue
                    # Normalize value
                    norm_map = _FIELD_NORMALIZERS.get(agent_field, {})
                    normalized = norm_map.get(raw.lower(), raw)
                    fields[agent_field] = normalized
                _gt_cache[nct] = fields
        logger.info("EDAM: loaded ground truth for %d NCTs", len(_gt_cache))
    except Exception as e:
        logger.error("EDAM: failed to load ground truth CSV: %s", e)
    return _gt_cache


def _normalize_agent_value(field_name: str, value: str) -> str:
    """Normalize agent output for comparison with ground truth."""
    if not value:
        return ""
    norm_map = _FIELD_NORMALIZERS.get(field_name, {})
    return norm_map.get(value.lower().strip(), value.strip())


async def _ground_truth_comparison(
    job_id: str,
    all_trial_results: list[dict],
    config_hash: str,
    git_commit: str,
) -> dict:
    """Compare agent output against training CSV R1 annotations.

    Stores disagreements as high-quality corrections with source="ground_truth".
    This is the most reliable non-human learning signal: when the agent
    disagrees with R1, R1 is correct ~85-93% of the time (depending on field).

    Skips sequence (too noisy — 52% human agreement) and reason_for_failure
    (frequently blank in GT). Focuses on classification, delivery, outcome, peptide.
    """
    gt = _load_ground_truth()
    if not gt:
        return {"skipped": True, "reason": "no ground truth data"}

    # Fields worth learning from (skip sequence — human agreement only 52%)
    learnable_fields = {"classification", "delivery_mode", "outcome", "peptide"}

    corrections_stored = 0
    agreements = 0
    disagreements = 0
    skipped = 0

    for trial in all_trial_results:
        nct_id = trial.get("nct_id", "").upper()
        if not nct_id or nct_id not in gt:
            skipped += 1
            continue

        gt_values = gt[nct_id]

        # Get agent's final values from verification output
        verification = trial.get("verification", {})
        verified_fields = verification.get("fields", [])
        if not verified_fields:
            # Fallback: get from annotations list
            for ann in trial.get("annotations", []):
                if not isinstance(ann, dict):
                    continue
                field = ann.get("field_name", "")
                if field not in learnable_fields:
                    continue
                gt_val = gt_values.get(field, "")
                if not gt_val:
                    continue

                agent_val = _normalize_agent_value(field, ann.get("value", ""))
                gt_norm = gt_val  # already normalized at load time

                if agent_val.upper() == gt_norm.upper():
                    agreements += 1
                else:
                    disagreements += 1
                    # Store as ground truth correction
                    try:
                        memory_store.store_correction(
                            nct_id=nct_id,
                            field_name=field,
                            job_id=job_id,
                            original_value=agent_val,
                            corrected_value=gt_norm,
                            source="ground_truth",
                            reflection=(
                                f"Agent said '{agent_val}' but training CSV R1 says '{gt_norm}'. "
                                f"R1 is the human expert annotation."
                            ),
                            evidence_citations=[{
                                "source": "human_ground_truth_train_df.csv",
                                "text": f"R1 annotation for {nct_id}/{field}: {gt_norm}",
                            }],
                            config_hash=config_hash,
                            git_commit=git_commit,
                        )
                        corrections_stored += 1
                    except Exception as e:
                        logger.warning(
                            "EDAM GT: failed to store correction %s/%s: %s",
                            nct_id, field, e,
                        )
            continue

        # Process verified fields
        for vf in verified_fields:
            if not isinstance(vf, dict):
                continue
            field = vf.get("field_name", "")
            if field not in learnable_fields:
                continue
            gt_val = gt_values.get(field, "")
            if not gt_val:
                continue

            agent_val = _normalize_agent_value(field, vf.get("final_value", ""))
            gt_norm = gt_val

            if agent_val.upper() == gt_norm.upper():
                agreements += 1
            else:
                disagreements += 1
                try:
                    memory_store.store_correction(
                        nct_id=nct_id,
                        field_name=field,
                        job_id=job_id,
                        original_value=agent_val,
                        corrected_value=gt_norm,
                        source="ground_truth",
                        reflection=(
                            f"Agent said '{agent_val}' but training CSV R1 says '{gt_norm}'. "
                            f"R1 is the human expert annotation."
                        ),
                        evidence_citations=[{
                            "source": "human_ground_truth_train_df.csv",
                            "text": f"R1 annotation for {nct_id}/{field}: {gt_norm}",
                        }],
                        config_hash=config_hash,
                        git_commit=git_commit,
                    )
                    corrections_stored += 1
                except Exception as e:
                    logger.warning(
                        "EDAM GT: failed to store correction %s/%s: %s",
                        nct_id, field, e,
                    )

    logger.info(
        "EDAM GT comparison: %d agreements, %d disagreements, "
        "%d corrections stored, %d skipped (not in GT)",
        agreements, disagreements, corrections_stored, skipped,
    )
    return {
        "agreements": agreements,
        "disagreements": disagreements,
        "corrections_stored": corrections_stored,
        "skipped": skipped,
    }


async def edam_post_job_hook(job_id: str, all_trial_results: list[dict],
                             config_snapshot: dict) -> dict:
    """
    Post-job hook called by the orchestrator after every completed job.

    v38 redesign: 3 active loops, 2 disabled.
      Active:
        1. Stability tracking (cross-run consistency)
        2. Ground truth comparison (training CSV R1 vs agent output)
        2b. Self-audit (evidence consistency)
      Disabled:
        3. Prompt optimization (never worked)
        - Embedding generation (removed from stability tracker)
        - Reconciliation correction storage (removed from orchestrator)
    """
    from app.services.version_service import get_git_commit_short
    import hashlib
    config_str = str(sorted(str(config_snapshot)))
    config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:12]
    git_commit = get_git_commit_short()

    summary = {
        "job_id": job_id,
        "stability": None,
        "ground_truth": None,
        "self_audit": None,
        "errors": [],
    }

    # --- Loop 1: Stability tracking (always runs) ---
    try:
        stability_result = await stability_tracker.analyze_job(
            job_id, all_trial_results, config_hash, git_commit
        )
        summary["stability"] = stability_result
    except Exception as e:
        logger.error("EDAM Loop 1 (stability) failed: %s", e, exc_info=True)
        summary["errors"].append(f"stability: {e}")

    # --- Loop 2: Ground truth comparison (v38 — replaces self-review) ---
    try:
        gt_result = await _ground_truth_comparison(
            job_id, all_trial_results, config_hash, git_commit,
        )
        summary["ground_truth"] = gt_result
    except Exception as e:
        logger.error("EDAM Loop 2 (ground truth) failed: %s", e, exc_info=True)
        summary["errors"].append(f"ground_truth: {e}")

    # --- Loop 2b: Self-audit ALL trials for evidence consistency ---
    try:
        audit_trials = all_trial_results
        if TRAINING_NCTS:
            audit_trials = [t for t in all_trial_results
                           if t.get("nct_id", "").upper() in TRAINING_NCTS]
        audit_result = await self_auditor.audit_job(
            job_id, audit_trials, config_hash, git_commit
        )
        summary["self_audit"] = audit_result
    except Exception as e:
        logger.error("EDAM Loop 2b (self-audit) failed: %s", e, exc_info=True)
        summary["errors"].append(f"self_audit: {e}")

    # --- Loop 3: Prompt optimization — DISABLED v38 ---
    # Never ran a single experiment (7 variants, 0 trials, 0 accuracy).
    # Disabled to reduce complexity.

    logger.info(
        "EDAM post-job complete for %s: stability=%s, ground_truth=%s, "
        "self_audit=%s, errors=%d",
        job_id,
        "OK" if summary["stability"] else "skipped",
        "OK" if summary["ground_truth"] else "skipped",
        "OK" if summary["self_audit"] else "skipped",
        len(summary["errors"]),
    )

    return summary
