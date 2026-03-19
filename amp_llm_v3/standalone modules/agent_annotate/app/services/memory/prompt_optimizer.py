"""
EDAM Loop 3: Prompt Auto-Optimizer.

Analyzes per-field accuracy across recent jobs, identifies systematic
error patterns, generates prompt modifications, and A/B tests them.
Variants that prove improvement are promoted; those that regress are
auto-discarded.

Runs after every Nth job (configurable via OPTIMIZATION_INTERVAL_JOBS).
"""

import logging
from collections import Counter

from app.services.memory.memory_store import MemoryStore
from app.services.memory.edam_config import (
    MIN_TRIALS_FOR_PROMOTION, MIN_IMPROVEMENT_FOR_PROMOTION,
    MIN_TRIALS_FOR_DISCARD, MAX_REGRESSION_FOR_DISCARD,
)

logger = logging.getLogger("agent_annotate.edam.optimizer")

VARIANT_GENERATION_SYSTEM = """You are an LLM prompt optimization specialist. You will be shown:
1. The current prompt instructions for a clinical trial annotation field
2. Error analysis showing common mistakes the current prompt causes
3. Specific examples of incorrect annotations and what they should have been

Your task: propose a MINIMAL modification to the prompt that addresses the most common error pattern. Do not rewrite the entire prompt — add 1-2 sentences or modify an existing rule.

Rules:
- Keep changes small and targeted. One fix per variant.
- The fix must be testable — it should specifically address the identified error pattern.
- Do not add complexity that doesn't directly address a measured error.
- Frame the fix as a RULE or EXAMPLE that the annotator can follow.

Respond EXACTLY in this format:
Variant Name: [short descriptive name, e.g., "completed_not_positive"]
Change Description: [1-2 sentences describing what changes and why]
Addition: [the exact text to ADD to the prompt, or "NONE" if only removing]
Removal: [the exact text to REMOVE from the prompt, or "NONE" if only adding]"""


class PromptOptimizer:
    """Loop 3: Automatic prompt tuning via A/B testing."""

    def __init__(self, memory: MemoryStore):
        self._memory = memory

    async def analyze_field_accuracy(self, field_name: str,
                                     recent_epochs: int = 3) -> dict:
        """
        Compute per-field accuracy metrics across recent epochs.

        Uses corrections as the ground truth signal — if a correction
        exists for an experience, the original was wrong.
        """
        current_epoch = self._memory.get_current_epoch()
        min_epoch = max(0, current_epoch - recent_epochs)

        # Get all experiences and corrections for this field in recent epochs
        experiences = self._memory.get_experiences(
            field_name=field_name, min_epoch=min_epoch, limit=500
        )
        corrections = self._memory.get_corrections(
            field_name=field_name, min_epoch=min_epoch, limit=200
        )

        # Build correction index: (nct_id, job_id) → corrected_value
        correction_index = {}
        for c in corrections:
            key = (c["nct_id"], c["job_id"])
            correction_index[key] = c

        total = len(experiences)
        corrected = 0
        error_patterns = Counter()  # (original_value, corrected_value) → count

        for exp in experiences:
            key = (exp["nct_id"], exp["job_id"])
            if key in correction_index:
                corrected += 1
                corr = correction_index[key]
                pattern = (exp["value"], corr["corrected_value"])
                error_patterns[pattern] += 1

        correction_rate = corrected / total if total > 0 else 0.0

        # Get stability data for this field
        stability_data = self._memory.get_stability(
            field_name=field_name, min_score=0.0, limit=500
        )
        stable_count = sum(1 for s in stability_data if s["stability_score"] >= 0.9)
        stability_rate = stable_count / len(stability_data) if stability_data else 0.0

        # Format common errors
        common_errors = []
        for (from_val, to_val), count in error_patterns.most_common(5):
            common_errors.append({
                "from": from_val,
                "to": to_val,
                "count": count,
                "pct": round(count / total * 100, 1) if total > 0 else 0,
            })

        # Detect systematic pattern
        error_pattern = None
        if common_errors and common_errors[0]["pct"] > 5:
            top = common_errors[0]
            error_pattern = (
                f"Most common error: '{top['from']}' should be '{top['to']}' "
                f"({top['count']} times, {top['pct']}% of trials)"
            )

        return {
            "field_name": field_name,
            "total_trials": total,
            "correction_rate": round(correction_rate, 3),
            "stability_rate": round(stability_rate, 3),
            "common_errors": common_errors,
            "error_pattern": error_pattern,
        }

    async def generate_variant(self, field_name: str,
                               error_analysis: dict) -> dict | None:
        """
        Use the premium model to propose a prompt modification.

        Returns variant dict or None if no modification warranted.
        """
        if not error_analysis.get("error_pattern"):
            return None
        if error_analysis["correction_rate"] < 0.05:
            logger.info("EDAM optimizer: %s error rate %.1f%% below threshold — no variant needed",
                        field_name, error_analysis["correction_rate"] * 100)
            return None

        # Get the current field prompt
        from agents.verification.verifier import FIELD_PROMPTS
        field_config = FIELD_PROMPTS.get(field_name)
        if not field_config:
            return None

        # Build the prompt for the optimizer
        prompt = f"FIELD: {field_name}\n\n"
        prompt += f"CURRENT PROMPT INSTRUCTIONS:\n{field_config['instruction'][:1500]}\n\n"
        prompt += f"ERROR ANALYSIS:\n{error_analysis['error_pattern']}\n\n"
        prompt += "SPECIFIC ERRORS:\n"
        for err in error_analysis["common_errors"][:3]:
            prompt += f"  - '{err['from']}' should be '{err['to']}' ({err['count']} times)\n"

        # Also include relevant corrections with reflections
        corrections = self._memory.get_corrections(field_name=field_name, limit=5)
        if corrections:
            prompt += "\nCORRECTION EXAMPLES:\n"
            for c in corrections[:3]:
                prompt += (
                    f"  - {c['nct_id']}: '{c['original_value']}' → '{c['corrected_value']}'\n"
                    f"    Why: {c['reflection'][:150]}\n"
                )

        from app.services.ollama_client import ollama_client
        from app.services.config_service import config_service
        config = config_service.get()

        # Use reconciler model for prompt generation
        model = "qwen2.5:14b"
        for key, m in config.verification.models.items():
            if m.role == "reconciler":
                model = m.name
                break

        try:
            response = await ollama_client.generate(
                model=model, prompt=prompt,
                system=VARIANT_GENERATION_SYSTEM,
                temperature=0.3,  # slightly creative
            )
            raw_text = response.get("response", "")
        except Exception as e:
            logger.warning("EDAM optimizer: variant generation failed: %s", e)
            return None

        # Parse the response
        import re
        name_match = re.search(r"Variant Name:\s*(.+?)(?:\n|$)", raw_text)
        desc_match = re.search(r"Change Description:\s*(.+?)(?:\n|$)", raw_text, re.DOTALL)
        add_match = re.search(r"Addition:\s*(.+?)(?:\nRemoval:|$)", raw_text, re.DOTALL)
        rem_match = re.search(r"Removal:\s*(.+?)(?:\n\n|$)", raw_text, re.DOTALL)

        if not name_match:
            logger.info("EDAM optimizer: could not parse variant name from response")
            return None

        variant_name = name_match.group(1).strip().lower().replace(" ", "_")[:50]
        description = desc_match.group(1).strip()[:300] if desc_match else "No description"
        addition = add_match.group(1).strip() if add_match else "NONE"
        removal = rem_match.group(1).strip() if rem_match else "NONE"

        if addition == "NONE" and removal == "NONE":
            logger.info("EDAM optimizer: no changes proposed")
            return None

        # Store the variant
        epoch = self._memory.get_current_epoch()
        self._memory.store_variant(
            field_name=field_name,
            variant_name=variant_name,
            prompt_diff=description,
            parent_variant=self._memory.get_active_variant(field_name),
            epoch=epoch,
        )

        logger.info("EDAM optimizer: generated variant '%s' for %s — %s",
                     variant_name, field_name, description)

        return {
            "variant_name": variant_name,
            "field_name": field_name,
            "prompt_diff": description,
            "addition": addition,
            "removal": removal,
        }

    def should_promote(self, field_name: str, variant_name: str) -> bool:
        """Check if a variant should be promoted (replace base prompt)."""
        rows = self._memory._conn.execute(
            "SELECT total_trials, correct_trials, accuracy_score FROM prompt_variants "
            "WHERE field_name = ? AND variant_name = ? AND status = 'testing'",
            (field_name, variant_name),
        ).fetchone()
        if not rows:
            return False
        if rows["total_trials"] < MIN_TRIALS_FOR_PROMOTION:
            return False
        # Compare against base accuracy
        base_rows = self._memory._conn.execute(
            "SELECT accuracy_score FROM prompt_variants "
            "WHERE field_name = ? AND variant_name = 'base'",
            (field_name,),
        ).fetchone()
        base_accuracy = base_rows["accuracy_score"] if base_rows else 0.0
        improvement = rows["accuracy_score"] - base_accuracy
        return improvement >= MIN_IMPROVEMENT_FOR_PROMOTION

    def should_discard(self, field_name: str, variant_name: str) -> bool:
        """Check if a variant should be discarded (accuracy regression)."""
        rows = self._memory._conn.execute(
            "SELECT total_trials, accuracy_score FROM prompt_variants "
            "WHERE field_name = ? AND variant_name = ? AND status = 'testing'",
            (field_name, variant_name),
        ).fetchone()
        if not rows:
            return False
        if rows["total_trials"] < MIN_TRIALS_FOR_DISCARD:
            return False
        base_rows = self._memory._conn.execute(
            "SELECT accuracy_score FROM prompt_variants "
            "WHERE field_name = ? AND variant_name = 'base'",
            (field_name,),
        ).fetchone()
        base_accuracy = base_rows["accuracy_score"] if base_rows else 0.0
        regression = base_accuracy - rows["accuracy_score"]
        return regression > MAX_REGRESSION_FOR_DISCARD

    async def run_optimization_pass(self, recent_job_ids: list[str] = None) -> dict:
        """
        Full optimization cycle for all fields.

        1. Analyze accuracy for each field
        2. For fields with error_rate > 5%, generate a variant
        3. Check existing variants for promotion/discard
        """
        fields = ["classification", "delivery_mode", "outcome", "reason_for_failure", "peptide"]
        summary = {
            "analyzed": [],
            "variants_generated": [],
            "variants_promoted": [],
            "variants_discarded": [],
        }

        for field_name in fields:
            analysis = await self.analyze_field_accuracy(field_name)
            summary["analyzed"].append(analysis)

            # Check existing testing variants
            testing = self._memory._conn.execute(
                "SELECT variant_name FROM prompt_variants "
                "WHERE field_name = ? AND status = 'testing'",
                (field_name,),
            ).fetchall()

            for row in testing:
                vname = row["variant_name"]
                if self.should_promote(field_name, vname):
                    self._memory.promote_variant(field_name, vname)
                    summary["variants_promoted"].append((field_name, vname))
                    logger.info("EDAM optimizer: PROMOTED %s/%s", field_name, vname)
                elif self.should_discard(field_name, vname):
                    self._memory.discard_variant(field_name, vname)
                    summary["variants_discarded"].append((field_name, vname))
                    logger.info("EDAM optimizer: DISCARDED %s/%s", field_name, vname)

            # Generate new variant if error rate is high
            if analysis["correction_rate"] > 0.05:
                variant = await self.generate_variant(field_name, analysis)
                if variant:
                    summary["variants_generated"].append(variant)

        logger.info(
            "EDAM optimizer: analyzed %d fields, generated %d variants, "
            "promoted %d, discarded %d",
            len(summary["analyzed"]), len(summary["variants_generated"]),
            len(summary["variants_promoted"]), len(summary["variants_discarded"]),
        )
        return summary
