"""
EDAM — Experience-Driven Annotation Memory.

Self-learning system for agent_annotate. Three feedback loops:
  Loop 1 (Stability):  Cross-run comparison → stable exemplars + instability flags
  Loop 2 (Corrections): Human review + self-review → error reflections
  Loop 3 (Prompt Opt):  Accuracy analysis → prompt variant A/B testing

All loops persist to SQLite and use Ollama embeddings for similarity search.
EDAM failures are NEVER fatal — the annotation pipeline runs normally if
any EDAM component fails.
"""

import logging

from app.services.memory.memory_store import MemoryStore, memory_store
from app.services.memory.stability_tracker import StabilityTracker
from app.services.memory.correction_learner import CorrectionLearner
from app.services.memory.prompt_optimizer import PromptOptimizer
from app.services.memory.edam_config import OPTIMIZATION_INTERVAL_JOBS

logger = logging.getLogger("agent_annotate.edam")

# Module-level instances (singletons)
stability_tracker = StabilityTracker(memory_store)
correction_learner = CorrectionLearner(memory_store)
prompt_optimizer = PromptOptimizer(memory_store)

# Job counter for optimization interval
_job_count = 0


async def edam_post_job_hook(job_id: str, all_trial_results: list[dict],
                             config_snapshot: dict) -> dict:
    """
    Post-job hook called by the orchestrator after every completed job.

    Runs all three EDAM loops in sequence:
    1. Store experiences + compute stability (always)
    2. Self-review flagged items (if enabled)
    3. Prompt optimization (every Nth job)

    Returns a summary dict. All failures are logged but never raised —
    EDAM must not interfere with the annotation pipeline.
    """
    global _job_count
    _job_count += 1

    from app.services.version_service import get_git_commit_short
    config_hash = config_snapshot.get("verification", {}).get("consensus_threshold", "")
    # Use a more complete hash from the config
    import hashlib
    config_str = str(sorted(str(config_snapshot)))
    config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:12]
    git_commit = get_git_commit_short()

    summary = {
        "job_id": job_id,
        "stability": None,
        "self_review": None,
        "optimization": None,
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

    # --- Loop 2: Self-review flagged items ---
    try:
        flagged = [t for t in all_trial_results
                   if t.get("verification", {}).get("flagged_for_review")]
        if flagged:
            corrections = await correction_learner.self_review_flagged(
                job_id, flagged, config_hash, git_commit
            )
            summary["self_review"] = {
                "flagged_count": len(flagged),
                "corrections_made": len(corrections),
                "corrections": corrections,
            }
    except Exception as e:
        logger.error("EDAM Loop 2 (corrections) failed: %s", e, exc_info=True)
        summary["errors"].append(f"corrections: {e}")

    # --- Loop 3: Prompt optimization (every Nth job) ---
    if _job_count % OPTIMIZATION_INTERVAL_JOBS == 0:
        try:
            opt_result = await prompt_optimizer.run_optimization_pass()
            summary["optimization"] = opt_result
        except Exception as e:
            logger.error("EDAM Loop 3 (optimizer) failed: %s", e, exc_info=True)
            summary["errors"].append(f"optimizer: {e}")

    # Log summary
    logger.info(
        "EDAM post-job complete for %s: stability=%s, self_review=%s, "
        "optimization=%s, errors=%d",
        job_id,
        "OK" if summary["stability"] else "skipped",
        "OK" if summary["self_review"] else "skipped",
        "OK" if summary["optimization"] else "skipped",
        len(summary["errors"]),
    )

    return summary
