"""
Consensus Checker.

Compares the primary annotator's answer against all verifier opinions
and determines if consensus is reached. Normalizes common value aliases
before comparison to prevent false disagreements from format differences.
"""

import logging

from app.models.verification import ModelOpinion, ConsensusResult

logger = logging.getLogger("agent_annotate.verification.consensus")

# Normalize common value aliases to canonical forms before comparison.
# This prevents false disagreements from format differences.
_VALUE_ALIASES = {
    "intravenous": "iv",
    "injection/infusion - intravenous": "iv",
    "active": "active, not recruiting",
    "active not recruiting": "active, not recruiting",
    "active_not_recruiting": "active, not recruiting",
    # Bare "AMP" is ambiguous — normalize to "other" (safer default)
    "amp": "other",
    # Verifiers sometimes return statuses instead of failure reasons
    "completed": "",
    "none": "",
    "n/a": "",
    "not applicable": "",
    "unknown": "",
}

# For reason_for_failure: any value starting with these is "no failure" (empty)
_REASON_NO_FAILURE_PREFIXES = (
    "completed", "unknown", "active", "recruiting", "not_yet", "n/a",
)


def _normalize(value: str, field_name: str = "") -> str:
    """Normalize a value for consensus comparison."""
    lower = value.strip().lower().strip('"').strip("'").strip("*")
    # Direct alias match
    if lower in _VALUE_ALIASES:
        return _VALUE_ALIASES[lower]
    # For reason_for_failure: verbose explanations starting with status keywords → empty
    if field_name == "reason_for_failure":
        for prefix in _REASON_NO_FAILURE_PREFIXES:
            if lower.startswith(prefix):
                return ""
    return lower


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

        # Count agreements using normalized values
        primary_norm = _normalize(primary_value, field_name)
        agreements = 0
        for opinion in verifier_opinions:
            if opinion.suggested_value is not None:
                verifier_norm = _normalize(opinion.suggested_value, field_name)
                if verifier_norm == primary_norm:
                    opinion.agrees = True
                    agreements += 1
                else:
                    opinion.agrees = False
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
