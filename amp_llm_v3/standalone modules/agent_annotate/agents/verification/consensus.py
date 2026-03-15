"""
Consensus Checker.

Compares the primary annotator's answer against all verifier opinions
and determines if consensus is reached.
"""

import logging

from app.models.verification import ModelOpinion, ConsensusResult

logger = logging.getLogger("agent_annotate.verification.consensus")


class ConsensusChecker:
    """Checks agreement between primary annotator and blind verifiers."""

    def check(
        self,
        field_name: str,
        primary_value: str,
        primary_model: str,
        verifier_opinions: list[ModelOpinion],
        threshold: float = 1.0,
    ) -> ConsensusResult:
        """
        Compare primary answer against verifier opinions.

        Args:
            field_name: The annotation field being checked
            primary_value: What the primary annotator concluded
            primary_model: Name of the primary model
            verifier_opinions: List of blind verifier opinions
            threshold: Fraction of verifiers that must agree (1.0 = unanimous)

        Returns:
            ConsensusResult with agreement details
        """
        if not verifier_opinions:
            # No verifiers configured — pass through
            return ConsensusResult(
                field_name=field_name,
                original_value=primary_value,
                final_value=primary_value,
                consensus_reached=True,
                agreement_ratio=1.0,
                opinions=[],
            )

        # Count agreements (case-insensitive)
        primary_lower = primary_value.strip().lower()
        agreements = 0
        for opinion in verifier_opinions:
            if opinion.suggested_value and opinion.suggested_value.strip().lower() == primary_lower:
                opinion.agrees = True
                agreements += 1
            else:
                opinion.agrees = False

        total = len(verifier_opinions)
        ratio = agreements / total if total > 0 else 0.0
        consensus = ratio >= threshold

        if consensus:
            logger.info(
                f"  {field_name}: CONSENSUS ({agreements}/{total} agree on '{primary_value}')"
            )
        else:
            dissenting = [
                o.suggested_value for o in verifier_opinions if not o.agrees
            ]
            logger.warning(
                f"  {field_name}: NO CONSENSUS ({agreements}/{total}). "
                f"Primary='{primary_value}', Dissenting={dissenting}"
            )

        return ConsensusResult(
            field_name=field_name,
            original_value=primary_value,
            final_value=primary_value if consensus else "",
            consensus_reached=consensus,
            agreement_ratio=round(ratio, 3),
            opinions=verifier_opinions,
        )
